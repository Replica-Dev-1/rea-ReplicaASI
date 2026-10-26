"""render_film - REPLICA film: serve this folder, call window.__render(t) per frame in headless Chromium, save JPEG frames
(resumable), build the sound bed with ffmpeg (fluorescent hum + drone + a glitch blip at each scene change), mux to MP4.
usage: python render_film.py <outdir> [--fps 30] [--still t1 t2 ...]"""
import functools, http.server, os, re, subprocess, sys, threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
A = sys.argv[1:]
OUT = A[0]
FPS = int(A[A.index("--fps") + 1]) if "--fps" in A else 30
STILLS = [float(x) for x in A[A.index("--still") + 1:]] if "--still" in A else None
PORT = 8793


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=HERE))
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.on("pageerror", lambda e: print("PAGE ERROR", e, flush=True))
    pg.goto("http://127.0.0.1:%d/film.html" % PORT)
    pg.wait_for_function("window.__ready === true", timeout=60000)
    dur = pg.evaluate("window.__dur")
    cuts = pg.evaluate("SC")
    if STILLS:
        for t in STILLS:
            pg.evaluate("t => window.__render(t)", t)
            pg.screenshot(path=os.path.join(OUT, "still_%06.2f.jpg" % t), type="jpeg", quality=88)
        print("stills done", flush=True)
        sys.exit(0)
    n = int(dur * FPS)
    for f in range(n):
        fn = os.path.join(OUT, "frames", "%05d.jpg" % f)
        if os.path.exists(fn):
            continue
        pg.evaluate("t => window.__render(t)", f / FPS)
        pg.screenshot(path=fn, type="jpeg", quality=90)
        if f % 300 == 0:
            print("frame %d/%d" % (f, n), flush=True)
    b.close()

# sound: 60 Hz fluorescent hum with harmonics + slow drone; short filtered-noise blips at each cut
hum = ("0.030*sin(2*PI*60*t)+0.018*sin(2*PI*120*t)+0.010*sin(2*PI*180*t)+0.006*sin(2*PI*240*t)*(0.6+0.4*sin(2*PI*0.13*t))"
       "+0.040*sin(2*PI*41.2*t)*(0.55+0.45*sin(2*PI*0.04*t))+0.020*sin(2*PI*61.7*t+sin(0.21*t))")
blip = "+".join("0.35*(between(t,%.2f,%.2f))*sin(2*PI*(900+400*sin(2*PI*31*t))*t)" % (c, c + 0.07) for c in cuts[1:])
news = ("(lt(t,36))*(0.10*sin(2*PI*110*t)*exp(-8*mod(t,0.5))+0.06*sin(2*PI*220*t)*exp(-10*mod(t+0.25,0.5))"
        "+0.05*sin(2*PI*55*t)*(0.5+0.5*sin(2*PI*0.25*t)))")
static = "(between(t,35.6,39.4))*0.25*sin(2*PI*(3000+2000*sin(2*PI*47*t))*t)"
expr = "(gte(t,39))*(" + hum + ")+" + news + "+" + static + "+" + blip
audio = os.path.join(OUT, "bed.m4a")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "aevalsrc='%s':s=48000:d=%d" % (expr, dur),
                "-af", "highpass=f=30,lowpass=f=4000,afade=t=in:d=2,afade=t=out:st=%d:d=4,loudnorm=I=-20:TP=-2" % (dur - 4),
                "-c:a", "aac", "-b:a", "160k", audio], check=True)
mp4 = os.path.join(OUT, "replica.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(OUT, "frames", "%05d.jpg"),
                "-i", audio, "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast", "-threads", "1", "-x264-params", "rc-lookahead=10",
                "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", mp4], check=True)
print("DONE", mp4, flush=True)
