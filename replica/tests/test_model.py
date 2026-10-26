#!/usr/bin/env python3
"""offline checks for replicas (run on the server: /opt/replica/venv/bin/python tests/test_model.py).
No network: the chain layer is exercised on hand-built account bytes; the model on generated logs."""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
import chain as C        # noqa: E402
import replica_model as S   # noqa: E402

A1 = C.b58encode(bytes(range(1, 33)))
A2 = C.b58encode(bytes(range(2, 34)))
ok = fail = 0


def check(name, cond):
    global ok, fail
    ok, fail = ok + bool(cond), fail + (not cond)
    print(("PASS " if cond else "FAIL ") + name)


# 1. teach -> recall from own memory; untaught -> declines (falls to the core)
m = S.ReplicaModel(A1)
facts = [("What is my dog's name?", "Juniper"), ("Where did I grow up?", "Akwesasne"),
         ("What is the wifi password for the shop?", "ask at the counter"), ("Who built the first lantern?", "Mira")]
facts += [("What is note number %d about?" % i, "note %d body" % i) for i in range(60)]
for c, a in facts:
    m.append("teach", {"cue": c, "answer": a})
check("recall exact cue", m.recall("What is my dog's name?")[0]["answer"] == "Juniper")
check("recall paraphrase (same content words)", m.recall("my dog name?")[0]["answer"] == "Juniper")
check("recall among 64 items", all(m.recall("What is note number %d about?" % i)[0]["answer"] == "note %d body" % i
                                   for i in range(60)))
check("untaught question declines", m.recall("How far is the Moon from Earth?")[0] is None)

# 2. rebuild from the log is identical
log = []
m2 = S.ReplicaModel(A1)
for c, a in facts[:10]:
    log.append(m2.append("teach", {"cue": c, "answer": a}))
log.append(m2.append("forget", {"id": log[1]["h"][:16]}))
r = S.ReplicaModel.rebuild(A1, json.loads(json.dumps(log)))
check("rebuild: same head + fingerprint", r.card() == m2.card())
check("rebuild: forget replays", r.recall("Where did I grow up?")[0] is None and r.recall("my dog's name")[0] is not None)
check("rebuild: same trace", float(abs(r.M - m2.M).max()) < 1e-4)

# 3. a log only fits its own replica; tampering breaks the chain
try:
    S.ReplicaModel.rebuild(A2, log)
    check("log refused on another replica", False)
except S.ChainError:
    check("log refused on another replica", True)
bad = json.loads(json.dumps(log))
bad[3]["body"]["answer"] = "tampered"
try:
    S.ReplicaModel.rebuild(A1, bad)
    check("tampered entry refused", False)
except S.ChainError:
    check("tampered entry refused", True)
try:
    S.ReplicaModel.rebuild(A1, log[:2] + log[3:])
    check("dropped entry refused", False)
except S.ChainError:
    check("dropped entry refused", True)
check("prefix of a log rebuilds (earlier state)", S.ReplicaModel.rebuild(A1, log[:5]).n == 5)

# 4. two replicas taught the same thing live in different spaces
x, y = S.ReplicaModel(A1), S.ReplicaModel(A2)
check("fingerprints differ by replica", x.fingerprint() != y.fingerprint())
check("cue spaces differ", abs(complex(x.cue_vec("dog name") @ y.cue_vec("dog name").conj())) / S.D < 0.1)


# 5. the Solana layer: signMessage check, address norm, Core asset parsing (rpc stubbed, no network)
import base64 as _b64                                                       # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

k = Ed25519PrivateKey.generate()
W = C.b58encode(k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
sig = _b64.b64encode(k.sign(b"REPLICA sign-in")).decode()
check("signMessage verifies for its wallet", C.signed_by("REPLICA sign-in", sig, W))
check("a different message doesn't", not C.signed_by("REPLICA sign-out", sig, W))
check("another wallet doesn't", not C.signed_by("REPLICA sign-in", sig, A1))
check("garbage signature -> False", not C.signed_by("x", "not base64!", W))
check("norm keeps good addresses, rejects bad", C.norm(W) == W and C.norm("0x123") == "" and C.norm("O0Il") == "")
s32 = lambda t: len(t).to_bytes(4, "little") + t                            # noqa: E731
acct = bytes([1]) + C.b58decode(W) + bytes([0]) + s32(b"REPLICA") + s32(b"https://replicaasi.com/meta/x.json") + bytes([0])
st = C.parse_core_asset(acct)
check("Core asset parses: owner, name, uri", st["owner"] == W and st["name"] == "REPLICA" and st["uri"].endswith("/meta/x.json"))
C.rpc = lambda url, m, p: {"value": {"owner": C.CORE_PROGRAM, "data": [_b64.b64encode(acct).decode(), "base64"]}} if p[0] == A1 else {"value": None}
check("owner_of -> owner", C.owner_of("u", A1, ttl=0) == W)
check("owner_of a missing asset -> None", C.owner_of("u", A2, ttl=0) is None)
check("b58 round trip (agent keys)", C.b58decode(C.b58encode(b"\0\0abc")) == b"\0\0abc")

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
