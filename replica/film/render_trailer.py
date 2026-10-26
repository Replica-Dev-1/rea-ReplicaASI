"""render_trailer - REPLICA doomer trailer. Frames from trailer.html (window.__render(t) in headless Chromium), sound
built with ffmpeg from window.CUES (drone + hum, braams, heartbeat, glitch stabs, a riser, silence on the cuts).
usage: python render_trailer.py <outdir> [--still t1 t2 ...] | --audio-only
Encoding is a separate step (a small box can run out of memory if Chromium is still running):
  ffmpeg -framerate 30 -i <out>/frames/%05d.jpg -i <out>/sound.m4a -c:v libx264 -preset veryfast -threads 1 ... trailer.mp4"""
import functools, http.server, json, os, subprocess, sys, threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
A = sys.argv[1:]
OUT = A[0]
FPS = 30
STILLS = [float(x) for x in A[A.index("--still") + 1:]] if "--still" in A else None
PORT = 8794


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
    pg.goto("http://127.0.0.1:%d/%s" % (PORT, os.environ.get("RP_PAGE", "trailer.html")))
    pg.wait_for_function("window.__ready === true", timeout=60000)
    dur = pg.evaluate("window.__dur")
    cues = pg.evaluate("window.CUES")
    if STILLS:
        for t in STILLS:
            pg.evaluate("t => window.__render(t)", t)
            pg.screenshot(path=os.path.join(OUT, "still_%05.1f.jpg" % t), type="jpeg", quality=85)
        print("stills done", flush=True)
        sys.exit(0)
    if "--audio-only" not in A:
        n = int(dur * FPS)
        for f in range(n):
            fn = os.path.join(OUT, "frames", "%05d.jpg" % f)
            if os.path.exists(fn):
                continue
            pg.evaluate("t => window.__render(t)", f / FPS)
            pg.screenshot(path=fn, type="jpeg", quality=88)
            if f % 300 == 0:
                print("frame %d/%d" % (f, n), flush=True)
    b.close()

# ---- the soft sound (RP_SOUND=soft): a quiet pad, a soft click per typed key (cues["key"]), a fade out. No hits.
if os.environ.get("RP_SOUND") == "soft":
    import wave
    import numpy as np
    sr = 48000
    t = np.arange(int(dur * sr)) / sr
    pad = 0.05 * np.sin(2 * np.pi * 55 * t) + 0.03 * np.sin(2 * np.pi * 82.4 * t + 0.6 * np.sin(2 * np.pi * 0.07 * t))
    pad += 0.02 * np.sin(2 * np.pi * 110 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.11 * t))
    rng = np.random.RandomState(7)
    n = int(0.018 * sr)
    env = np.exp(-np.arange(n) / (0.0025 * sr))
    for c in cues.get("key", []):
        i = int(c * sr)
        if i + n < len(t):
            pad[i:i + n] += 0.10 * env * rng.uniform(-1, 1, n) * (0.7 + 0.3 * rng.rand())
    for c in cues.get("line", []):                         # a faint tick when output lines print
        i = int(c * sr)
        if i + n < len(t):
            pad[i:i + n] += 0.035 * env * np.sin(2 * np.pi * 1400 * np.arange(n) / sr)
    fade = np.minimum(1, np.minimum(t / 1.0, (dur - t) / 3.0)).clip(0, 1)
    pcm = (np.tanh(pad * fade * 1.4) * 0.6 * 32767).astype(np.int16)
    wav = os.path.join(OUT, "sound.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    audio = os.path.join(OUT, "sound.m4a")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", "highpass=f=30,loudnorm=I=-24:TP=-6",
                    "-c:a", "aac", "-b:a", "160k", audio], check=True)
    print("SOUND", audio, flush=True)
    sys.exit(0)

# ---- the sound
P = "2*PI"
quiet = "*".join("(1-between(t,%.2f,%.2f))" % (c, c + 0.25) for c in cues["cut"]) or "1"
black = os.environ.get("RP_BLACK", "(1-between(t,37.6,40))")   # trailer: only the riser plays under the last black
drone = "(0.07*sin(%s*36.7*t)*(0.6+0.4*sin(%s*0.11*t))+0.045*sin(%s*55*t+2*sin(%s*0.07*t))+0.018*sin(%s*50*t)+0.01*sin(%s*100*t))" % ((P,) * 6)
braam = "+".join("between(t,{c},{e})*exp(-(t-{c})*1.0)*(0.34*sin({P}*43.65*(t-{c}))+0.24*sin({P}*87.3*(t-{c}))+0.18*sin({P}*130.8*(t-{c}))+0.1*sin({P}*174.6*(t-{c})))".format(c=c, e=c + 3.5, P=P) for c in cues["braam"])
beat = "+".join("between(t,{c},{e})*0.7*exp(-(t-{c})*16)*sin({P}*(46+40*exp(-(t-{c})*30))*(t-{c}))".format(c=c, e=c + 0.3, P=P) for c in cues["beat"])
glitch = "+".join("between(t,{c},{e})*0.16*sin({P}*(1900+1400*sin({P}*83*t))*t)".format(c=c, e=c + 0.12, P=P) for c in cues["glitch"])
a, z = cues["riser"]
riser = "between(t,{a},{z})*pow((t-{a})/{d},2)*0.28*sin({P}*(70+pow(t-{a},2)*90)*(t-{a}))".format(a=a, z=z, d=z - a, P=P)
expr = "({q})*({blk}*({drone}+{braam})+{beat}+{glitch})+{riser}".format(q=quiet, blk=black, drone=drone, braam=braam, beat=beat, glitch=glitch, riser=riser)
audio = os.path.join(OUT, "sound.m4a")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "aevalsrc='%s':s=48000:d=%d" % (expr, dur),
                "-af", "asoftclip=type=tanh,highpass=f=25,lowpass=f=9000,afade=t=in:d=0.8,afade=t=out:st=%d:d=3,loudnorm=I=-14:TP=-1.5" % (dur - 3),
                "-c:a", "aac", "-b:a", "192k", audio], check=True)
print("SOUND", audio, flush=True)
