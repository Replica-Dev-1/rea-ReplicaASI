#!/usr/bin/env python3
"""replica_model - one replica's memory, rebuilt from public data: model = f(token address, hash-chained log).

A replica is an ERC-721 token on Robinhood Chain (contract/Replica.sol). Nothing is stored in the token; the memory is DERIVED:
  - token address -> osub_seed keys every vector, so each replica lives in its own HRR space (sha256-seeded phasors).
  - log -> append-only, hash-chained entries starting at genesis(asset), so a log only replays onto its own replica.
Anyone with the address + the log rebuilds the identical memory (same head, same fingerprint, same answers).
Kinds: teach, forget, inherit (a copy's first entry: up to 40 of its parent's memories), agent/learn/fill (reserved).
Recall scores the question against every remembered cue and answers only above CUE_BAR; below it, it says it was never told.

CLI:  python replica_model.py rebuild <asset> <log.json>     -> verifies the chain, prints head / count / fingerprint
      python replica_model.py ask <asset> <log.json> "<question>"
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time

import numpy as np

VERSION = "replica-1"
D = 2048
CUE_BAR = 0.55          # min cue resonance for a taught answer (else fall through to the core)
MAX_ITEMS = 500         # live taught items per replica (trace noise grows ~sqrt(n/D))
MAX_TEXT = 600
KINDS = ("teach", "forget", "agent", "learn", "fill", "inherit")
MAX_INHERIT = 40
STOP = set("a an the is are was were be of to in on at for and or what who whom which when where why how do does did "
           "i you me my your it its this that these those please tell".split())
ADJ = ["Amber", "Quiet", "Iron", "Salt", "Cedar", "Lantern", "North", "Slate", "Ember", "Hollow", "Tidal", "Copper",
       "Willow", "Signal", "Granite", "Morrow"]
NOUN = ["Heron", "Kestrel", "Loom", "Harbor", "Orchard", "Compass", "Fern", "Anvil", "Beacon", "Delta", "Lark",
        "Meridian", "Thicket", "Quarry", "Spindle", "Owl"]


def osub_seed(text: str, dim: int = D) -> np.ndarray:
    h = int(hashlib.sha256(text.lower().strip().encode()).hexdigest(), 16)
    rng = np.random.RandomState(h % (2 ** 31))
    return np.exp(1j * rng.uniform(0, 2 * np.pi, dim)).astype(np.complex64)


def bind(a, b):
    return np.fft.ifft(np.fft.fft(a) * np.fft.fft(b)).astype(np.complex64)


def unbind(c, b):
    return np.fft.ifft(np.fft.fft(c) * np.conj(np.fft.fft(b))).astype(np.complex64)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def genesis(asset: str) -> str:
    return hashlib.sha256(("%s:genesis:%s" % (VERSION, asset)).encode()).hexdigest()


def entry_hash(e: dict) -> str:
    return hashlib.sha256(canon({k: e[k] for k in ("n", "t", "kind", "body", "prev")})).hexdigest()


def make_entry(prev_hash: str, n: int, kind: str, body: dict, t: int | None = None) -> dict:
    e = {"n": n, "t": int(t if t is not None else time.time()), "kind": kind, "body": body, "prev": prev_hash}
    e["h"] = entry_hash(e)
    return e


class ChainError(ValueError):
    pass


class ReplicaModel:
    def __init__(self, asset: str):
        self.asset = asset
        self.head = genesis(asset)
        self.n = 0
        self.items: dict[str, dict] = {}    # item id -> {cue, answer, K, V, t}
        self.M = np.zeros(D, dtype=np.complex64)
        self.state: dict = {}
        h = hashlib.sha256(asset.encode()).digest()
        self.name = "%s %s" % (ADJ[h[0] % 16], NOUN[h[1] % 16])
        self.identity = osub_seed("%s:identity:%s" % (VERSION, asset))

    # ---- keys live in this replica's own space
    def _k(self, s: str) -> np.ndarray:
        return osub_seed("%s:%s:%s" % (VERSION, self.asset, s))

    def cue_vec(self, text: str):
        ts = tokens(text)
        if not ts:
            return None
        v = np.mean(np.stack([self._k("tok:" + t) for t in ts]), axis=0)
        return (v / np.maximum(np.abs(v), 1e-8)).astype(np.complex64)

    # ---- the log is the model
    def apply(self, e: dict) -> None:
        if e.get("prev") != self.head or e.get("n") != self.n or entry_hash(e) != e.get("h"):
            raise ChainError("entry %s does not continue this replica's chain" % e.get("n"))
        b = e["body"]
        if e["kind"] in ("teach", "inherit"):
            if e["kind"] == "inherit":      # a child's FIRST entry: a snapshot of its parent's memories
                if e["n"] != 0 or not isinstance(b.get("items"), list) or len(b["items"]) > MAX_INHERIT:
                    raise ChainError("inherit must be the first entry, with at most %d memories" % MAX_INHERIT)
                pairs = [(str(x.get("cue", "")), str(x.get("answer", ""))) for x in b["items"]]
                ids = [e["h"][:12] + "%04d" % i for i in range(len(pairs))]
            else:
                pairs, ids = [(str(b.get("cue", "")), str(b.get("answer", "")))], [e["h"][:16]]
            for (cue, ans), iid in zip(pairs, ids):
                cue, ans = cue[:MAX_TEXT], ans[:MAX_TEXT]
                K = self.cue_vec(cue)
                if K is None or not ans.strip():
                    raise ChainError("entry %d teaches nothing" % e["n"])
                if len(self.items) >= MAX_ITEMS:
                    raise ChainError("this replica is full (%d taught items); forget some first" % MAX_ITEMS)
                V = self._k("val:" + iid)
                self.items[iid] = {"id": iid, "cue": cue, "answer": ans, "K": K, "V": V, "t": e["t"]}
                self.M += bind(K, V)
            if e["kind"] == "inherit":
                self.state["inherit"] = {"parent": str(b.get("parent", "")), "parent_head": str(b.get("parent_head", "")),
                                         "count": len(pairs)}
        elif e["kind"] == "forget":
            it = self.items.pop(str(b.get("id", "")), None)
            if it is None:
                raise ChainError("entry %d forgets an unknown item" % e["n"])
            self.M -= bind(it["K"], it["V"])
        elif e["kind"] in ("agent", "learn", "fill"):
            # agent settings / strategy learning snapshots / trade fills (written by the owner's own agent)
            if e["kind"] == "fill":
                self.state.setdefault("fills", []).append(b)
            else:
                self.state[e["kind"]] = b
        else:
            raise ChainError("unknown entry kind %r" % e["kind"])
        self.head, self.n = e["h"], self.n + 1

    def append(self, kind: str, body: dict) -> dict:
        e = make_entry(self.head, self.n, kind, body)
        self.apply(e)
        return e

    @classmethod
    def rebuild(cls, asset: str, log: list[dict]) -> "ReplicaModel":
        m = cls(asset)
        for e in log:
            m.apply(e)
        return m

    # ---- recall
    def recall(self, question: str):
        """-> (item, resonance) or (None, best resonance). Only the replica's own taught memory; never guesses."""
        q = self.cue_vec(question)
        if q is None or not self.items:
            return None, 0.0
        # exact scan over the item cues (a top-k cleanup of the trace missed items whose cues differ by one word:
        # 60 near-identical cues flood unbind(M, q)). <=500 x D dot products, ~1 ms.
        ids = list(self.items)
        Ks = np.stack([self.items[i]["K"] for i in ids])
        res = np.real(Ks.conj() @ q) / D
        j = int(np.argmax(res))
        best = float(res[j])
        if best < CUE_BAR:
            return None, best
        return self.items[ids[j]], best

    def fingerprint(self) -> str:
        return hashlib.sha256(canon({"v": VERSION, "asset": self.asset, "head": self.head, "n": self.n})).hexdigest()

    def card(self) -> dict:
        return {"asset": self.asset, "name": self.name, "version": VERSION, "entries": self.n,
                "taught": len(self.items), "head": self.head, "fingerprint": self.fingerprint()}

    def taught(self) -> list[dict]:
        return [{"id": i["id"], "cue": i["cue"], "answer": i["answer"], "t": i["t"]}
                for i in sorted(self.items.values(), key=lambda x: x["t"])]


def read_log(path: str) -> list[dict]:
    """a .jsonl log (one entry per line) or the page's download ({"asset": ..., "log": [...]})"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if text.lstrip().startswith("{\"asset\""):
        return json.loads(text)["log"]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] not in ("rebuild", "ask"):
        sys.exit(__doc__)
    model = ReplicaModel.rebuild(sys.argv[2], read_log(sys.argv[3]))
    if sys.argv[1] == "rebuild":
        print(json.dumps(model.card(), indent=1))
    else:
        it, r = model.recall(sys.argv[4])
        print(json.dumps({"answer": it["answer"], "resonance": round(r, 3)} if it else
                         {"answer": None, "note": "never told this", "best": round(r, 3)}))
