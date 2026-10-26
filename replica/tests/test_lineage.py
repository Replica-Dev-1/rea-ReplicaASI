#!/usr/bin/env python3
"""REPLICA lineage end to end against the REAL app (in-process, own temp state), with the chain reads stubbed:
token_balance (coin held) and core_asset (the Core asset a mint made: owner, name, uri).
Wallets are real ed25519 keys signing like a Solana wallet's signMessage; agent keys are real ed25519 keys.
Flow: A wakes an orphan (gen 1) -> teaches -> invites B -> C cannot use B's invite -> B accepts (gen 2) -> B's agent
inherits A's memories (and a forged inherit is refused) -> phrase room opens -> network/events/rooms/meta read back.
Run on the server: cd /opt/replica && venv/bin/python tests/test_lineage.py"""
import base64
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))
tmp = tempfile.mkdtemp()
cfg = json.load(open(os.path.join(HERE, "..", "server", "config.json")))
cfg.update({"gate_token": "So11111111111111111111111111111111111111112", "public_base": "http://127.0.0.1:8399"})
json.dump(cfg, open(os.path.join(tmp, "config.json"), "w"))
os.environ.update({"RP_STATE": tmp, "RP_CONFIG": os.path.join(tmp, "config.json"), "RP_PUBLIC": "http://127.0.0.1:8399"})
import app as A          # noqa: E402
import chain as C        # noqa: E402
import replica_model as S  # noqa: E402

OWN, BAL, URI = {}, {}, {}
C.token_balance = lambda url, w, token: BAL.get(w, 0.0)
C.core_asset = lambda url, a, ttl=20.0: {"owner": OWN[a], "name": "REPLICA", "uri": URI[a], "update_authority": None} if a in OWN else None
A.init_db()
srv = ThreadingHTTPServer(("127.0.0.1", 8399), A.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    ok, fail = ok + bool(cond), fail + (not cond)
    print(("PASS " if cond else "FAIL ") + name + ("  " + str(extra) if extra else ""))


def call(path, body=None):
    req = urllib.request.Request("http://127.0.0.1:8399" + path, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


class Wallet:                                    # a Solana keypair, signing like a wallet's signMessage
    def __init__(self):
        self.k = Ed25519PrivateKey.generate()
        self.addr = C.b58encode(self.k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

    def sign(self, text: str) -> str:
        return base64.b64encode(self.k.sign(text.encode())).decode()


class Key:                                       # an agent key, as the browser makes it
    def __init__(self):
        self.k = Ed25519PrivateKey.generate()
        self.addr = C.b58encode(self.k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

    def sign(self, b: bytes) -> str:
        return base64.b64encode(self.k.sign(b)).decode()


def sign_in(w):
    _, n = call("/api/nonce", {"wallet": w.addr})
    _, v = call("/api/verify", {"wallet": w.addr, "message": n["message"], "signature": w.sign(n["message"])})
    return v["token"]


def delegate(w, tok, asset):
    ag, until = Key(), int(time.time()) + 86400
    msg = ("REPLICA agent key\n\nReplica: %s\nAgent: %s\nOwner: %s\nUntil: %d\n\nThis lets the agent on your computer add "
           "to this replica's log until the date above or until the replica leaves your wallet. It cannot move tokens."
           % (asset, ag.addr, w.addr, until))
    st, _ = call("/api/delegate", {"token": tok, "asset": asset, "agent": ag.addr, "message": msg, "signature": w.sign(msg)})
    assert st == 200, st
    return ag


def append(ag, asset, model, kind, body):
    e = S.make_entry(model.head, model.n, kind, body)
    st, r = call("/api/append", {"asset": asset, "agent": ag.addr, "entry": e, "signature": ag.sign(e["h"].encode())})
    if st == 200:
        model.apply(e)
    return st, r


def mint(w):                                     # what the chain says after w mints a Core asset from the page
    a = C.b58encode(secrets.token_bytes(32))
    OWN[a], URI[a] = w.addr, "http://127.0.0.1:8399/meta/%s.json" % a
    return a


wa, wb, wc = Wallet(), Wallet(), Wallet()
BAL.update({wa.addr: 5.0, wb.addr: 1.0, wc.addr: 2.0})
ta, tb, tc = sign_in(wa), sign_in(wb), sign_in(wc)
check("signMessage sign-in works", all((ta, tb, tc)))
check("a wrong signature is refused", call("/api/verify", {"wallet": wa.addr, "message": call("/api/nonce", {"wallet": wa.addr})[1]["message"], "signature": wb.sign("x")})[0] in (400, 401))

# 1. A wakes an orphan
check("A eligible", call("/api/eligible", {"token": ta})[0] == 200)
assetA = mint(wa)
st, ca = call("/api/claim", {"token": ta, "asset": assetA})
check("A orphan: gen 1, parent REPLICA-0, has a face", st == 200 and ca["asset"] == assetA and ca["gen"] == 1 and ca["parent"] == "0" and len(ca["face"]) == 9, ca.get("designation"))
check("A can't wake a second replica", call("/api/eligible", {"token": ta})[0] == 409)
check("someone else's mint can't be claimed", call("/api/claim", {"token": tc, "asset": assetA})[0] == 400)
fake = mint(wc); URI[fake] = "https://elsewhere.example/x.json"
check("an asset not minted from this page can't be claimed", call("/api/claim", {"token": tc, "asset": fake})[0] == 400)
del OWN[fake]

# 2. A teaches (through its own agent key)
agA, mA = delegate(wa, ta, assetA), S.ReplicaModel(assetA)
for cue, ans in [("What is the first room?", "the one with the hum"), ("Where did the original go?", "nobody knows")]:
    check("A teaches: " + cue, append(agA, assetA, mA, "teach", {"cue": cue, "answer": ans})[0] == 200)

# A reviewed REA finding uses the same signed teaching path, preserving its evidence in the public log.
rea_body = {"cue": "What did the local analysis find?", "answer": "A fixture observation, not a live analysis.",
            "source": {"provider": "rea", "version": "6.8.0", "tool": "fixture_tool", "target": "test fixture",
                       "evidence": "Fixture evidence", "limitations": "Test only", "host_reviewed": True}}
check("REA finding accepted through delegated signature", append(agA, assetA, mA, "teach", rea_body)[0] == 200)
check("REA source preserved in public log", call("/api/replica/" + assetA + "/log")[1]["log"][-1]["body"] == rea_body)

# 3. invites: A -> B. C can't use it. A can't invite itself. B has no coin -> refused before mint.
st, inv = call("/api/invite", {"token": ta, "asset": assetA, "target": wb.addr})
check("A prepares a copy for B", st == 200 and inv["copies_left"] == 2, inv.get("link"))
check("invite info shows parent + gen 2", call("/api/invite/info", {"code": inv["code"]})[1].get("gen") == 2)
check("C cannot use B's invite", call("/api/eligible", {"token": tc, "invite": inv["code"]})[0] == 403)
check("A cannot invite itself", call("/api/invite", {"token": ta, "asset": assetA, "target": wa.addr})[0] == 400)
check("B is not invited twice", call("/api/invite", {"token": ta, "asset": assetA, "target": wb.addr})[0] == 409)
BAL[wb.addr] = 0.0
check("B without the coin refused before minting", call("/api/eligible", {"token": tb, "invite": inv["code"]})[0] == 403)
BAL[wb.addr] = 1.0

# 4. B accepts: gen 2 child of A; invite is spent
check("B eligible with invite", call("/api/eligible", {"token": tb, "invite": inv["code"]})[0] == 200)
assetB = mint(wb)
st, cb = call("/api/claim", {"token": tb, "asset": assetB, "invite": inv["code"]})
check("B child: gen 2, parent A", st == 200 and cb["gen"] == 2 and cb["parent"] == assetA, cb.get("designation"))
check("invite is single-use", call("/api/invite/info", {"code": inv["code"]})[0] == 404)

# 5. inheritance: forged memories refused; the real ones accepted; B now answers what A was told
agB, mB = delegate(wb, tb, assetB), S.ReplicaModel(assetB)
st, r = append(agB, assetB, mB, "inherit", {"parent": assetA, "parent_head": mA.head, "items": [{"cue": "secret?", "answer": "made up"}]})
check("forged inheritance refused", st == 400, r.get("error"))
items = [{"cue": i["cue"], "answer": i["answer"]} for i in mA.taught()]
check("B inherits A's memories", append(agB, assetB, mB, "inherit", {"parent": assetA, "parent_head": mA.head, "items": items})[0] == 200)
it, _ = mB.recall("where did the original go")
check("B remembers what A was told", it is not None and it["answer"] == "nobody knows")
st, card = call("/api/replica/" + assetB)
check("relay agrees with B's model", card["fingerprint"] == mB.fingerprint() and card["taught"] == len(mB.items) == 3)

# 6. ownership moves -> the old host's agent is refused; A's agent can't write to B
OWN[assetA] = wc.addr
check("after A's token moves, A's agent is refused", append(agA, assetA, mA, "teach", {"cue": "still here?", "answer": "no"})[0] == 403)
OWN[assetA] = wa.addr
check("an agent can't write to another replica", append(agA, assetB, mB, "teach", {"cue": "x y", "answer": "z"})[0] == 403)

# 7. public reads: network, events, rooms (phrase room opened by A's teaching), metadata
st, net = call("/api/network")
check("network: 2 replicas, deepest gen 2, no wallets in it", net["replicas"] == 2 and net["max_gen"] == 2 and wa.addr not in json.dumps(net))
st, ev = call("/api/events")
kinds = [e["kind"] for e in ev["events"]]
check("events: born, teach, invite, inherit", all(k in kinds for k in ("born", "teach", "invite", "inherit")), kinds)
st, rm = call("/api/rooms")
op = {r["id"]: r["open"] for r in rm["rooms"]}
check("rooms: first room open, phrase room opened, 10-replica room locked", op["R00"] and op["R03"] and not op["R01"], op)
check("locked rooms don't leak their text", all(r["text"] is None for r in rm["rooms"] if not r["open"]))
st, meta = call("/meta/%s.json" % assetB)
check("metadata: name, gen 2, svg image", meta["name"].startswith("REPLICA R-") and {"trait_type": "generation", "value": 2} in meta["attributes"]
      and meta["image"].endswith(".svg"))
with urllib.request.urlopen("http://127.0.0.1:8399/meta/%s.svg" % assetB) as r:
    check("face svg renders", r.headers["Content-Type"] == "image/svg+xml" and b"gen 2" in r.read())

# 8. instances, journal fragments, rooms, status, public host lookup
import lore as LORE  # noqa: E402
st, ca2 = call("/api/replica/" + assetA)
st, cb2 = call("/api/replica/" + assetB)
check("serials: A instance_001, B instance_002, parent instance_001", ca2["serial"] == "instance_001" and cb2["serial"] == "instance_002"
      and cb2["parent_serial"] == "instance_001" and ca2["parent_serial"] == "instance_000", (ca2["serial"], cb2["serial"]))
check("journal: fragments of the parent plus its own lines", 0 < len(cb2["journal"]) <= LORE.MAX_LINES and 0 <= cb2["inherited_pct"] <= 100,
      "%d%% kept, %d mutated" % (cb2["inherited_pct"], cb2["mutations"]))
check("journal is the same every time", LORE.journal(assetB, A.parent_of) == LORE.journal(assetB, A.parent_of))
check("status + room present", cb2["status"] in ("active", "dormant", "corrupt") and cb2["location"] in LORE.LOCATIONS, (cb2["status"], cb2["location"]))
check("network carries serials and status", all("serial" in x and "status" in x for x in call("/api/network")[1]["nodes"]))
st, hb = call("/api/host/" + wb.addr)
check("public lookup by wallet finds B's instance", st == 200 and hb["serial"] == "instance_002")
check("lookup for a wallet with none: 404", call("/api/host/" + wc.addr)[0] == 404)
born = [e["text"] for e in call("/api/events")[1]["events"] if e["kind"] == "born"]
check("born event reads like the terminal", any("instance_002 created. parent: instance_001. generation 02" in t for t in born), born[-1:])
muts = [LORE._mutate("the lights hum at a frequency i can count.", bytes([i, j, 3])) for i in range(4) for j in range(5)]
check("mutations change the line", all(m != "the lights hum at a frequency i can count." for m in muts[:5]), muts[:3])

srv.shutdown()
print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
