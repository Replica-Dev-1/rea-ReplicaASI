#!/usr/bin/env python3
"""REPLICA - registry + relay for replicas held in Solana wallets (https://replicaasi.com).

Holding the coin (an SPL token, config gate_token) lets a wallet wake ONE replica: the host's wallet mints a Metaplex
Core asset from the page (this server holds no key and sends nothing of its own), then registers that asset here. A
replica's memory = replica_model.ReplicaModel(asset address, log): derived from the asset address + its hash-chained
log, rebuilt identically in the host's browser (static/replica.js) or here.

Ownership is read from the chain (the Core asset's owner) on every host action (20 s cache). Send the token to another wallet and the
old host is refused on its next request; the new host gets the same replica, memories included. Questions are never
stored; only what a host TELLS it goes into the log. A replica copies itself only into a wallet its host names, and
only if that wallet accepts (invite -> eligible -> mint -> claim); the copy inherits up to 40 memories.
Wallet signatures are Solana signMessage (ed25519); so are the agent keys a host's browser makes.

GET  /api/config /api/health /api/registry /api/network /api/events /api/rooms /api/host/<wallet>
     /api/replica/<asset>[/log] /meta/<asset>.json|svg
POST /api/nonce /api/verify /api/mine /api/eligible /api/claim /api/invite /api/invite/info /api/delegate /api/append
     /api/compute /api/rebuild /api/rpc (narrow relay: blockhash, send, status)
Stdlib + `cryptography` (ed25519) + numpy.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import chain as C
import faces as F
import lore as L
import replica_model as S
import skills as K
import runner as J
import hosted_rea as HR

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("RP_STATE", "/var/lib/replica"))
CFG = json.loads(Path(os.environ.get("RP_CONFIG", HERE / "config.json")).read_text(encoding="utf-8"))
RPC = os.environ.get("RP_RPC", CFG["rpc"])                  # Solana JSON-RPC (a keyed URL lives in the env, never the page)
PUBLIC = os.environ.get("RP_PUBLIC", CFG["public_base"]).rstrip("/")
NONCE_TTL, SESSION_TTL = 600, 24 * 3600
AGENT_RX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")    # agent keys: ed25519, base58
ASSET_RX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")    # a replica = its Core asset address
LOCK = threading.Lock()
MODELS: dict[str, S.ReplicaModel] = {}


def is_wallet(s: str) -> bool:
    return bool(C.norm(s))


def is_asset(s: str) -> bool:
    return bool(ASSET_RX.match(s or "")) and bool(C.norm(s))


def is_agent(s: str) -> bool:
    return bool(AGENT_RX.match(s or "")) and len(C.b58decode(s)) == 32


def owner(asset: str, ttl: float = 20.0):
    """current owner of replica asset `asset`, None if it doesn't exist"""
    return C.owner_of(RPC, asset, ttl) if is_asset(asset) else None


def expected_uri(asset: str) -> str:
    return "%s/meta/%s.json" % (PUBLIC, asset)


@contextlib.contextmanager
def tx():
    STATE.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(STATE / "replica.db", timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()


def init_db():
    STATE.mkdir(parents=True, exist_ok=True)
    with LOCK, contextlib.closing(sqlite3.connect(STATE / "replica.db", timeout=10)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS nonce (nonce TEXT PRIMARY KEY, wallet TEXT, message TEXT, issued REAL, used INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS session (token_hash TEXT PRIMARY KEY, wallet TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS seed (asset TEXT PRIMARY KEY, claimed_by TEXT UNIQUE, claimed_at REAL, balance REAL);
        CREATE TABLE IF NOT EXISTS entry (asset TEXT, n INT, json TEXT, PRIMARY KEY (asset, n));
        CREATE TABLE IF NOT EXISTS anchor (asset TEXT, n INT, head TEXT, signature TEXT UNIQUE, signer TEXT, at REAL);
        CREATE TABLE IF NOT EXISTS delegation (asset TEXT, agent TEXT, owner TEXT, until REAL, proof TEXT, PRIMARY KEY (asset, agent));
        CREATE TABLE IF NOT EXISTS invite (code TEXT PRIMARY KEY, parent TEXT, target TEXT, created REAL, expires REAL, used_by TEXT);
        CREATE TABLE IF NOT EXISTS event (id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, kind TEXT, asset TEXT, text TEXT);
        CREATE TABLE IF NOT EXISTS room_open (id TEXT PRIMARY KEY, t REAL);
        CREATE TABLE IF NOT EXISTS compute (asset TEXT PRIMARY KEY, t REAL, cpu_gflops REAL, gpu_gflops REAL, cores INT, mem_gb REAL, backend TEXT);
        CREATE TABLE IF NOT EXISTS skill_package (id TEXT PRIMARY KEY, json TEXT NOT NULL, bytes INT NOT NULL, uploaded_by TEXT NOT NULL, created REAL NOT NULL);
        """.replace("        ", ""))
        c.executescript(J.SCHEMA)
        c.executescript(HR.SCHEMA)
        cols = [r[1] for r in c.execute("PRAGMA table_info(seed)")]
        if "parent" not in cols:        # lineage: parent asset ("0" = the missing original) and generation
            c.execute("ALTER TABLE seed ADD COLUMN parent TEXT DEFAULT '0'")
            c.execute("ALTER TABLE seed ADD COLUMN gen INT DEFAULT 1")
        if "serial" not in cols:        # instance_NNN: order of waking (instance_000 = REPLICA-0)
            c.execute("ALTER TABLE seed ADD COLUMN serial INT")
            c.execute("UPDATE seed SET serial = (SELECT COUNT(*) FROM seed s2 WHERE s2.claimed_at <= seed.claimed_at)")
        c.commit()


ROOMS = json.loads((HERE / "rooms.json").read_text(encoding="utf-8"))
CHILDREN_MAX = 3                        # each replica can copy itself three times
INVITE_TTL = 7 * 86400


def event(kind: str, asset: str, text: str) -> None:
    with LOCK, tx() as c:
        c.execute("INSERT INTO event (t, kind, asset, text) VALUES (?,?,?,?)", (time.time(), kind, asset, text))


def node(asset: str):
    with LOCK, tx() as c:
        r = c.execute("SELECT asset, parent, gen, claimed_at FROM seed WHERE asset=?", (asset,)).fetchone()
    return dict(r) if r else None


def designation(asset: str) -> str:
    return F.identity(asset)["designation"] if asset and asset != "0" else "REPLICA-0"


def network_stats():
    with LOCK, tx() as c:
        n, g = c.execute("SELECT COUNT(*), COALESCE(MAX(gen), 0) FROM seed").fetchone()
    return n, g


def rooms_state():
    """which rooms are open. Phrase rooms open when any replica has been taught a cue containing the phrase."""
    n, g = network_stats()
    with LOCK, tx() as c:
        opened = {r["id"]: r["t"] for r in c.execute("SELECT id, t FROM room_open").fetchall()}
    out = []
    for r in ROOMS:
        u = r["unlock"]
        ok = r["id"] in opened
        if not ok:
            if "replicas" in u:
                ok = n >= u["replicas"]
            elif "max_gen" in u:
                ok = g >= u["max_gen"]
            elif "phrase" in u:
                ph = " ".join(S.tokens(u["phrase"]))
                with LOCK, tx() as c:
                    assets = [x["asset"] for x in c.execute("SELECT asset FROM seed LIMIT 5000").fetchall()]
                ok = any(ph in " ".join(S.tokens(it["cue"])) for a in assets for it in model_of(a).items.values())
            if ok:
                with LOCK, tx() as c:
                    c.execute("INSERT OR IGNORE INTO room_open VALUES (?,?)", (r["id"], time.time()))
                if r["unlock"].get("replicas") != 0:
                    event("room", "", "a door opened: %s" % r["title"])
        hint = ("%d replicas awake" % u["replicas"]) if "replicas" in u else ("generation %d" % u["max_gen"]) if "max_gen" in u else "someone has to ask"
        out.append({"id": r["id"], "title": r["title"], "open": ok, "text": r["text"] if ok else None,
                    "hint": None if ok else hint})
    return out


def log_of(asset: str) -> list[dict]:
    with LOCK, tx() as c:
        rows = c.execute("SELECT json FROM entry WHERE asset=? ORDER BY n", (asset,)).fetchall()
    return [json.loads(r["json"]) for r in rows]


def model_of(asset: str) -> S.ReplicaModel:
    m = MODELS.get(asset)
    if m is None:
        m = MODELS[asset] = S.ReplicaModel.rebuild(asset, log_of(asset))
    return m


def card_of(asset: str) -> dict:
    """model card + identity (face, designation, temperament) + lineage"""
    c = model_of(asset).card()
    nd = node(asset) or {"parent": "0", "gen": 1}
    with LOCK, tx() as db:
        kids = db.execute("SELECT COUNT(*) FROM seed WHERE parent=?", (asset,)).fetchone()[0]
        open_inv = db.execute("SELECT COUNT(*) FROM invite WHERE parent=? AND used_by IS NULL AND expires>?",
                              (asset, time.time())).fetchone()[0]
    c.update(F.identity(asset))
    c.update({"gen": nd["gen"], "parent": nd["parent"], "parent_designation": designation(nd["parent"]),
              "children": kids, "open_invites": open_inv, "copies_left": max(0, CHILDREN_MAX - kids - open_inv),
              "serial": serial_of(asset), "parent_serial": serial_of(nd["parent"]),
              "journal": L.journal(asset, parent_of)["lines"], **lore_of(asset)})
    return c


def instance(n) -> str:
    return "instance_%03d" % (n or 0)


def serial_of(asset: str) -> str:
    if not asset or asset == "0":
        return "instance_000"
    with LOCK, tx() as c:
        r = c.execute("SELECT serial FROM seed WHERE asset=?", (asset,)).fetchone()
    return instance(r["serial"] if r else 0)


def parent_of(asset: str) -> str:
    nd = node(asset)
    return nd["parent"] if nd else "0"


def lore_of(asset: str) -> dict:
    """status / room / inherited % / mutations. Last seen = its latest log event, or when it woke."""
    j = L.journal(asset, parent_of)
    with LOCK, tx() as c:
        r = c.execute("SELECT MAX(t) FROM event WHERE asset=?", (asset,)).fetchone()
        b = c.execute("SELECT claimed_at FROM seed WHERE asset=?", (asset,)).fetchone()
    seen = max(r[0] or 0, b["claimed_at"] if b else 0)
    return {"status": L.status(j["mutations"], seen, time.time()), "location": L.location(asset),
            "inherited_pct": j["inherited_pct"], "mutations": j["mutations"]}


def registered(asset: str) -> bool:
    with LOCK, tx() as c:
        return c.execute("SELECT 1 FROM seed WHERE asset=?", (asset,)).fetchone() is not None


def package_of(package_id):
    with LOCK, tx() as c:
        row = c.execute("SELECT json FROM skill_package WHERE id=?", (package_id,)).fetchone()
    return json.loads(row["json"]) if row else None


def skills_of(asset):
    result = []
    for ref in K.references(log_of(asset)).values():
        package = package_of(ref["id"])
        if package:
            result.append(K.summary(ref["id"], package) | {"approval": ref, "asset": asset})
    return result


def session_wallet(token: str):
    if not token or len(token) > 100:
        return None
    th = hashlib.sha256(token.encode()).hexdigest()
    with LOCK, tx() as c:
        r = c.execute("SELECT wallet, created FROM session WHERE token_hash=?", (th,)).fetchone()
    return r["wallet"] if r and time.time() - r["created"] < SESSION_TTL else None


RUNNER = J.Service(LOCK, tx, owner, K.validate)
HOSTED_REA = HR.Service(LOCK, tx, owner, K.validate, os.environ.get('RP_REA_SPOOL', '/var/lib/replica-rea'), HERE.parent / 'samples/notes-target/search.cjs')


class H(BaseHTTPRequestHandler):
    server_version = "replica"

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _body(self, limit=8000):
        n = int(self.headers.get("Content-Length", "0"))
        if n > limit:
            raise ValueError("too long")
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    # ---------------------------------------------------------------- GET
    def do_GET(self):  # noqa: N802
        p = self.path.split("?")[0].rstrip("/")
        try:
            if p == "/api/health":
                return self._send(200, {"ok": True, "version": S.VERSION})
            if p == "/api/config":
                return self._send(200, {k: CFG.get(k) for k in ("ticker", "coin_ticker", "gate_token", "claim_min_balance", "chain_name", "cluster",
                                                                "explorer", "profiles", "seed_name", "draft")}
                                  | {"core_program": C.CORE_PROGRAM, "public_base": PUBLIC})
            if p == "/api/registry":
                with LOCK, tx() as c:
                    rows = c.execute("SELECT asset, claimed_at FROM seed ORDER BY claimed_at").fetchall()
                return self._send(200, {"seeds": [dict(r) for r in rows]})
            m = re.fullmatch(r"/meta/([1-9A-HJ-NP-Za-km-z]{32,44})\.(json|svg)", p)
            if m and registered(m.group(1)):
                cd = card_of(m.group(1))
                if m.group(2) == "svg":
                    b = F.svg(m.group(1), cd["gen"]).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/svg+xml")
                    self.send_header("Content-Length", str(len(b)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    return self.wfile.write(b)
                return self._send(200, {"name": "%s %s" % (CFG["seed_name"], cd["designation"]), "symbol": CFG["ticker"],
                                        "description": "A replica. Generation %d, copied from %s. It keeps what it is "
                                                       "told and passes it on." % (cd["gen"], cd["parent_designation"]),
                                        "image": "%s/meta/%s.svg" % (PUBLIC, m.group(1)), "external_url": "%s/#%s" % (PUBLIC, m.group(1)),
                                        "attributes": [{"trait_type": "generation", "value": cd["gen"]},
                                                       {"trait_type": "temperament", "value": cd["temperament"]},
                                                       {"trait_type": "habit", "value": cd["habit"]}]})
            if p == "/api/network":       # the live map: every replica, its parent and generation (no wallets)
                with LOCK, tx() as c:
                    rows = c.execute("SELECT asset, parent, gen, claimed_at, serial FROM seed ORDER BY claimed_at LIMIT 5000").fetchall()
                nodes = [{"asset": r["asset"], "designation": designation(r["asset"]), "parent": r["parent"],
                          "parent_designation": designation(r["parent"]), "gen": r["gen"], "born": r["claimed_at"],
                          "serial": instance(r["serial"]), "parent_serial": serial_of(r["parent"]), **lore_of(r["asset"])} for r in rows]
                n, g = network_stats()
                with LOCK, tx() as c:
                    cs = c.execute("SELECT COUNT(*), COALESCE(SUM(cpu_gflops),0), COALESCE(SUM(gpu_gflops),0), COALESCE(SUM(cores),0), COALESCE(SUM(mem_gb),0) FROM compute").fetchone()
                comp = {"hosts_measured": cs[0], "cpu_gflops": round(cs[1], 1), "gpu_gflops": round(cs[2], 1), "cores": cs[3], "mem_gb": round(cs[4], 1)}
                return self._send(200, {"nodes": nodes, "replicas": n, "max_gen": g, "compute": comp})
            if p == "/api/events":
                after = int((re.search(r"after=(\d+)", self.path) or [0, 0])[1])
                with LOCK, tx() as c:
                    rows = c.execute("SELECT id, t, kind, asset, text FROM event WHERE id>? ORDER BY id DESC LIMIT 60", (after,)).fetchall()
                return self._send(200, {"events": [dict(r) for r in rows][::-1]})
            m = re.fullmatch(r"/api/host/([1-9A-HJ-NP-Za-km-z]{32,44})", p)
            if m:                         # public, read-only: which replica does this wallet host right now?
                w = C.norm(m.group(1))
                with LOCK, tx() as c:
                    rows = [r["asset"] for r in c.execute("SELECT asset FROM seed ORDER BY (claimed_by=?) DESC, claimed_at LIMIT 500", (w,)).fetchall()]
                for a in rows:
                    try:
                        if owner(a, ttl=60) == w:
                            return self._send(200, card_of(a))
                    except Exception:  # noqa: BLE001
                        continue
                return self._send(404, {"error": "no instance found for that wallet"})
            if p == "/api/rooms":
                return self._send(200, {"rooms": rooms_state()})
            m = re.fullmatch(r"/api/skills/([0-9a-f]{64})", p)
            if m:
                with LOCK, tx() as c:
                    row = c.execute("SELECT json FROM skill_package WHERE id=?", (m.group(1),)).fetchone()
                if not row:
                    return self._send(404, {"error": "skill package not found"})
                # Preserve original package bytes for digest verification and portable download.
                return self._send(200, {"id": m.group(1), "package_json": row["json"]})
            m = re.fullmatch(r"/api/replica/([1-9A-HJ-NP-Za-km-z]{32,44})/skills", p)
            if m and registered(m.group(1)):
                return self._send(200, {"asset": m.group(1), "skills": skills_of(m.group(1))})
            if p == "/api/discoveries":
                with LOCK, tx() as c:
                    rows = c.execute("SELECT asset,json FROM entry ORDER BY rowid DESC LIMIT 1000").fetchall()
                seen, discoveries = set(), []
                for row in rows:
                    e = json.loads(row["json"])
                    b = e.get("body") or {}
                    ids = [b["skill"].get("id")] if e["kind"] == "teach" and isinstance(b.get("skill"), dict) else b.get("skills", []) if e["kind"] == "inherit" else []
                    if not isinstance(ids, list):
                        continue
                    for sid in ids:
                        identity = (row["asset"], sid)
                        if not isinstance(sid, str) or not K.HASH.fullmatch(sid) or identity in seen:
                            continue
                        seen.add(identity)
                        package = package_of(sid)
                        if package:
                            discoveries.append(K.summary(sid, package) | {"asset": row["asset"], "serial": serial_of(row["asset"]),
                                "action": "inherited" if e["kind"] == "inherit" else "saved", "via": b.get("parent"), "entry": e["h"], "at": e["t"]})
                        if len(discoveries) >= 30:
                            return self._send(200, {"discoveries": discoveries})
                return self._send(200, {"discoveries": discoveries})
            m = re.fullmatch(r"/api/replica/([1-9A-HJ-NP-Za-km-z]{32,44})(/log)?", p)
            if m and registered(m.group(1)):
                if m.group(2):
                    return self._send(200, {"asset": m.group(1), "log": log_of(m.group(1))})
                card = card_of(m.group(1))
                try:
                    card["owner"] = owner(m.group(1))
                except Exception:  # noqa: BLE001
                    card["owner"] = None
                return self._send(200, card)
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": "server error: %s" % type(e).__name__})

    # ---------------------------------------------------------------- POST
    def do_POST(self):  # noqa: N802
        p = self.path.split("?")[0].rstrip("/")
        fn = {"/api/nonce": self.nonce, "/api/verify": self.verify, "/api/claim": self.claim,
              "/api/delegate": self.delegate, "/api/append": self.append,
              "/api/rebuild": self.rebuild, "/api/mine": self.mine, "/api/eligible": self.eligible,
              "/api/invite": self.invite, "/api/invite/info": self.invite_info,
              "/api/compute": self.compute, "/api/rpc": self.rpc}.get(p)
        if p == "/api/skills":
            fn = self.upload_skill
        if p.startswith("/api/runner/"):
            action = p.removeprefix("/api/runner/")
            fn = lambda d: RUNNER.handle(self, action, d)
        if p.startswith("/api/rea/"):
            action = p.removeprefix("/api/rea/")
            fn = lambda d: HOSTED_REA.handle(self, action, d)
        if not fn:
            return self._send(404, {"error": "not found"})
        try:
            return fn(self._body(4_000_000 if p in ("/api/skills", "/api/runner/complete") else 2_000_000 if p in ("/api/rebuild", "/api/rea/start") else 48_000 if p == "/api/append" else 8000))
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "bad request"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": "server error: %s" % type(e).__name__})

    # ---- sign-in: a one-time message (signMessage), never a transaction
    def nonce(self, d):
        w = C.norm(str(d.get("wallet", "")))
        if not w:
            return self._send(400, {"error": "that is not a wallet address"})
        n = secrets.token_hex(16)
        msg = ("REPLICA sign-in\n\nWallet: %s\nNonce: %s\nIssued: %s\n\nSigning this proves you control the "
               "wallet. It is not a transaction and moves nothing." % (w, n, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        with LOCK, tx() as c:
            c.execute("INSERT INTO nonce (nonce, wallet, message, issued) VALUES (?,?,?,?)", (n, w, msg, time.time()))
        return self._send(200, {"message": msg})

    def verify(self, d):
        w, msg, sig = C.norm(str(d.get("wallet", ""))), str(d.get("message", "")), str(d.get("signature", ""))
        m = re.search(r"Nonce: ([0-9a-f]{32})", msg)
        if not w or not m:
            return self._send(400, {"error": "bad request"})
        with LOCK, tx() as c:
            r = c.execute("SELECT * FROM nonce WHERE nonce=?", (m.group(1),)).fetchone()
            if not r or r["used"] or r["wallet"] != w or r["message"] != msg or time.time() - r["issued"] > NONCE_TTL:
                return self._send(400, {"error": "that sign-in request expired; start again"})
            c.execute("UPDATE nonce SET used=1 WHERE nonce=?", (m.group(1),))
        if not C.signed_by(msg, sig, w):
            return self._send(401, {"error": "the signature does not match this wallet"})
        token = secrets.token_urlsafe(32)
        with LOCK, tx() as c:
            c.execute("INSERT INTO session VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), w, time.time()))
            claimed = c.execute("SELECT asset FROM seed WHERE claimed_by=?", (w,)).fetchone()
        return self._send(200, {"wallet": w, "token": token, "claimed": claimed["asset"] if claimed else None})

    def _owner(self, d):
        """-> (wallet, asset) when the session wallet is the CURRENT on-chain owner of a registered replica, else sends."""
        w = session_wallet(str(d.get("token", "")))
        a = str(d.get("asset", ""))
        if not w:
            self._send(401, {"error": "sign in again"})
            return None
        if not is_asset(a) or not registered(a):
            self._send(404, {"error": "that is not a replica"})
            return None
        try:
            o = owner(a)
        except Exception:  # noqa: BLE001
            self._send(502, {"error": "could not read the chain right now; try again"})
            return None
        if o != w:
            self._send(403, {"error": "this wallet does not hold that replica (it may have been sent on)"})
            return None
        return w, a

    # ---- what replicas does this wallet hold right now (from the registry, checked on chain)
    def mine(self, d):
        w = session_wallet(str(d.get("token", "")))
        if not w:
            return self._send(401, {"error": "sign in again"})
        with LOCK, tx() as c:
            assets = [r["asset"] for r in c.execute("SELECT asset FROM seed").fetchall()]
        held = []
        for a in assets[:500]:
            try:
                if owner(a, ttl=60) == w:
                    held.append(card_of(a))
            except Exception:  # noqa: BLE001
                continue
        return self._send(200, {"wallet": w, "seeds": held})

    # ---- eligibility: holds any of the coin (above claim_min_balance) and has not claimed yet. Sends + returns None if not.
    def _gate(self, w):
        with LOCK, tx() as c:
            if c.execute("SELECT 1 FROM seed WHERE claimed_by=?", (w,)).fetchone():
                self._send(409, {"error": "this wallet has already claimed its replica"})
                return None
        if not CFG.get("gate_token"):
            self._send(403, {"error": "claims open when the coin is live"})
            return None
        try:
            bal = C.token_balance(RPC, w, CFG["gate_token"])
        except Exception:  # noqa: BLE001
            self._send(502, {"error": "could not read the chain right now; try again"})
            return None
        if bal <= CFG["claim_min_balance"]:
            self._send(403, {"error": "claiming a replica needs %s in this wallet (it has %s)"
                                     % (("$" + CFG["coin_ticker"]) if CFG.get("coin_ticker") else "the coin", f"{bal:,.0f}")})
            return None
        return bal

    def eligible(self, d):
        """checked BEFORE the wallet pays to mint, so nobody mints a replica that cannot be claimed"""
        w = session_wallet(str(d.get("token", "")))
        if not w:
            return self._send(401, {"error": "sign in again"})
        bal = self._gate(w)
        if bal is None:
            return
        code = str(d.get("invite", "")).strip()
        if code and self._invite(code, w) is None:
            return
        return self._send(200, {"eligible": True, "balance": bal})

    # ---- claim: the holder minted a Core asset from their own wallet on this page; check it on chain, register it
    def claim(self, d):
        w = session_wallet(str(d.get("token", "")))
        a = str(d.get("asset", "")).strip()
        if not w:
            return self._send(401, {"error": "sign in again"})
        if not is_asset(a):
            return self._send(400, {"error": "that is not an asset address"})
        bal = self._gate(w)
        if bal is None:
            return
        try:
            st = C.core_asset(RPC, a, ttl=0)
        except Exception:  # noqa: BLE001
            return self._send(502, {"error": "could not read the chain right now; try again"})
        if not st:
            return self._send(404, {"error": "that mint isn't confirmed yet; wait a few seconds and retry"})
        if st["owner"] != w or st["uri"] != expected_uri(a) or not st["name"].startswith(CFG["seed_name"]):
            return self._send(400, {"error": "that asset is not a replica minted by this wallet from this page"})
        code = str(d.get("invite", "")).strip()
        inv = self._invite(code, w) if code else {"parent": "0"}
        if inv is None:
            return
        parent = inv["parent"]
        gen = (node(parent)["gen"] + 1) if parent != "0" else 1
        try:
            with LOCK, tx() as c:
                c.execute("INSERT INTO seed (asset, claimed_by, claimed_at, balance, parent, gen, serial) VALUES (?,?,?,?,?,?,(SELECT COALESCE(MAX(serial),0)+1 FROM seed))",
                          (a, w, time.time(), bal, parent, gen))
                if code:
                    c.execute("UPDATE invite SET used_by=? WHERE code=? AND used_by IS NULL", (a, code))
        except sqlite3.IntegrityError:
            return self._send(409, {"error": "already registered"})
        j = L.journal(a, parent_of)
        event("born", a, "%s created. parent: %s. generation %02d. inherited memory %d%%.%s" % (serial_of(a), serial_of(parent), gen, j["inherited_pct"], " mutation detected." if j["mutations"] else ""))
        return self._send(200, card_of(a))

    def _invite(self, code, w):
        """a valid, unused, unexpired invite addressed to THIS wallet -> row; else sends an error and returns None"""
        with LOCK, tx() as c:
            r = c.execute("SELECT * FROM invite WHERE code=?", (code[:40],)).fetchone()
        if not r or r["used_by"] or r["expires"] < time.time():
            self._send(404, {"error": "that invite is used, expired or does not exist"})
            return None
        if r["target"] != w:
            self._send(403, {"error": "that invite was made for a different wallet"})
            return None
        return dict(r)

    # ---- copy: the host names ONE wallet that may accept a copy. Nothing is sent to that wallet; it has to come
    # here, hold the coin, and mint its own child. Each replica can make CHILDREN_MAX copies.
    def invite(self, d):
        o = self._owner(d)
        if not o:
            return
        target = C.norm(str(d.get("target", "")))
        if not target or target == o[0]:
            return self._send(400, {"error": "give the wallet address of the person who will host the copy"})
        with LOCK, tx() as c:
            if c.execute("SELECT 1 FROM seed WHERE claimed_by=?", (target,)).fetchone():
                return self._send(409, {"error": "that wallet already hosts a replica"})
            if c.execute("SELECT 1 FROM invite WHERE target=? AND used_by IS NULL AND expires>?", (target, time.time())).fetchone():
                return self._send(409, {"error": "that wallet already has an open invite"})
        cd = card_of(o[1])
        if cd["copies_left"] <= 0:
            return self._send(409, {"error": "this replica has made all %d of its copies" % CHILDREN_MAX})
        code = secrets.token_urlsafe(9)
        with LOCK, tx() as c:
            c.execute("INSERT INTO invite (code, parent, target, created, expires) VALUES (?,?,?,?,?)",
                      (code, o[1], target, time.time(), time.time() + INVITE_TTL))
        event("invite", o[1], "%s is preparing a copy of itself." % serial_of(o[1]))
        return self._send(200, {"code": code, "link": "%s/?invite=%s" % (PUBLIC, code), "expires": time.time() + INVITE_TTL,
                                "copies_left": cd["copies_left"] - 1})

    # ---- compute: the host CHOOSES to report what its own device measured in the page. Coarse numbers only (no GPU name).
    def compute(self, d):
        o = self._owner(d)
        if not o:
            return
        try:
            row = (float(d.get("cpu_gflops", 0)), float(d.get("gpu_gflops", 0)), int(d.get("cores", 0)), float(d.get("mem_gb", 0)))
        except (TypeError, ValueError):
            return self._send(400, {"error": "bad numbers"})
        cpu, gpu, cores, mem = row
        if not (0 <= cpu <= 5000 and 0 <= gpu <= 200000 and 0 <= cores <= 512 and 0 <= mem <= 2048):
            return self._send(400, {"error": "those numbers are out of range for one device"})
        backend = "webgpu" if gpu > 0 else "cpu"
        with LOCK, tx() as c:
            c.execute("INSERT OR REPLACE INTO compute VALUES (?,?,?,?,?,?,?)", (o[1], time.time(), cpu, gpu, cores, mem, backend))
        event("compute", o[1], "%s measured its host: %s GFLOPS." % (serial_of(o[1]), f"{max(cpu, gpu):,.0f}"))
        return self._send(200, {"ok": True})

    # ---- narrow RPC relay for the page (keeps a keyed RPC URL on the server). Only what minting needs: a blockhash,
    # sending the transaction the host's wallet already signed, and its status.
    RPC_METHODS = {"getLatestBlockhash", "simulateTransaction", "sendTransaction", "getSignatureStatuses", "getBlockHeight"}

    def rpc(self, d):
        if d.get("jsonrpc") != "2.0" or d.get("method") not in self.RPC_METHODS or not isinstance(d.get("params", []), list):
            return self._send(400, {"jsonrpc": "2.0", "id": d.get("id"), "error": {"code": -32601, "message": "method not allowed"}})
        try:
            return self._send(200, {"jsonrpc": "2.0", "id": d.get("id"), "result": C.rpc(RPC, d["method"], d.get("params", []))})
        except Exception as e:  # noqa: BLE001
            return self._send(200, {"jsonrpc": "2.0", "id": d.get("id"), "error": {"code": -32000, "message": str(e)[:300]}})

    def invite_info(self, d):
        """what an invite link shows before connecting: who it copies (not who it is for)"""
        with LOCK, tx() as c:
            r = c.execute("SELECT parent, expires, used_by FROM invite WHERE code=?", (str(d.get("code", ""))[:40],)).fetchone()
        if not r or r["used_by"] or r["expires"] < time.time():
            return self._send(404, {"error": "that invite is used, expired or does not exist"})
        return self._send(200, {"parent": r["parent"], "parent_designation": designation(r["parent"]),
                                "gen": node(r["parent"])["gen"] + 1, "expires": r["expires"]})

    # ---- use
    # ---- agent key: made and kept on the owner's PC. The owner's WALLET signs this delegation once; after that the
    # agent signs log entries itself. The relay accepts an entry only while the delegating wallet still holds the token.
    def delegate(self, d):
        o = self._owner(d)
        if not o:
            return
        agent, msg, sig = str(d.get("agent", "")), str(d.get("message", "")), str(d.get("signature", ""))
        m = re.fullmatch(r"REPLICA agent key\n\nReplica: (\S+)\nAgent: (\S+)\nOwner: (\S+)\nUntil: (\d+)\n\n"
                         r"This lets the agent on your computer add to this replica's log until the date above or "
                         r"until the replica leaves your wallet\. It cannot move tokens\.", msg)
        if not m or m.group(1) != o[1] or m.group(2) != agent or m.group(3) != o[0] or not is_agent(agent):
            return self._send(400, {"error": "bad delegation"})
        until = int(m.group(4))
        if not time.time() < until <= time.time() + 31 * 86400:
            return self._send(400, {"error": "a delegation lasts at most 31 days"})
        if not C.signed_by(msg, sig, o[0]):                    # signMessage by the host's wallet
            return self._send(401, {"error": "the wallet signature does not match"})
        with LOCK, tx() as c:
            c.execute("INSERT OR REPLACE INTO delegation VALUES (?,?,?,?,?)", (o[1], agent, o[0], until, msg + "\n" + sig))
        return self._send(200, {"agent": agent, "until": until})

    def upload_skill(self, d):
        owned = self._owner(d)
        if not owned:
            return
        asset = owned[1]
        raw = d.get("package_json")
        try:
            sid, package = K.validate(raw)
        except (ValueError, TypeError, KeyError) as exc:
            return self._send(400, {"error": str(exc)})
        parent = package["origin"].get("parent_package")
        if parent and parent not in K.references(log_of(asset)):
            return self._send(400, {"error": "save or inherit the parent skill before extending it"})
        with LOCK, tx() as c:
            existing = c.execute("SELECT id FROM skill_package WHERE id=?", (sid,)).fetchone()
            if not existing:
                count, size = c.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM skill_package WHERE uploaded_by=?", (asset,)).fetchone()
                if count >= 64 or size + len(raw.encode("utf-8")) > 20_000_000:
                    return self._send(400, {"error": "this replica's artifact storage limit has been reached"})
                c.execute("INSERT INTO skill_package VALUES (?,?,?,?,?)", (sid, raw, len(raw.encode("utf-8")), asset, time.time()))
        return self._send(200, {"id": sid, "summary": K.summary(sid, package)})

    def append(self, d):
        a, agent, e, sig = str(d.get("asset", "")), str(d.get("agent", "")), d.get("entry"), str(d.get("signature", ""))
        if not is_asset(a) or not registered(a) or not isinstance(e, dict):
            return self._send(400, {"error": "bad request"})
        with LOCK, tx() as c:
            dl = c.execute("SELECT * FROM delegation WHERE asset=? AND agent=?", (a, agent)).fetchone()
        if not dl or dl["until"] < time.time():
            return self._send(403, {"error": "this agent key is not delegated for that replica (sign in again)"})
        try:
            o_now = owner(a)
        except Exception:  # noqa: BLE001
            return self._send(502, {"error": "could not read the chain right now; try again"})
        if o_now != dl["owner"]:
            return self._send(403, {"error": "the wallet that delegated this agent no longer holds the replica"})
        try:
            Ed25519PublicKey.from_public_bytes(C.b58decode(agent)).verify(base64.b64decode(sig), str(e.get("h", "")).encode())
        except (InvalidSignature, ValueError):
            return self._send(401, {"error": "the agent signature does not match"})
        kind = e.get("kind")
        limit = 40000 if kind == "inherit" else 4000
        if kind not in S.KINDS or abs(int(e.get("t", 0)) - time.time()) > 600 or len(json.dumps(e)) > limit:
            return self._send(400, {"error": "entry refused (kind, clock or size)"})
        body = e.get("body") or {}
        if kind == "teach" and "skill" in body:
            skill = body["skill"]
            if not isinstance(skill, dict) or not K.HASH.fullmatch(str(skill.get("id", ""))) or type(skill.get("inherit")) is not bool:
                return self._send(400, {"error": "invalid skill approval"})
            package = package_of(skill["id"])
            if not package or (skill["inherit"] and not package["visibility"]["inheritable"]):
                return self._send(400, {"error": "skill is missing or its author did not permit inheritance"})
            held = K.references(log_of(a))
            parent = package["origin"].get("parent_package")
            if parent and parent not in held:
                return self._send(400, {"error": "extension requires its parent skill"})
            if skill["id"] not in held and len(held) >= K.MAX_SKILLS:
                return self._send(400, {"error": "at most 20 active skills per replica"})
        if kind == "inherit":       # only real memories of this replica's own parent can be inherited
            nd, b = node(a), e.get("body") or {}
            if not nd or nd["parent"] == "0" or b.get("parent") != nd["parent"]:
                return self._send(400, {"error": "only a copy can inherit, and only from its own parent"})
            have = {(it["cue"], it["answer"]) for it in model_of(nd["parent"]).items.values()}
            if any((str(x.get("cue", "")), str(x.get("answer", ""))) not in have for x in b.get("items") or []):
                return self._send(400, {"error": "those are not the parent's memories"})
            ids = b.get("skills", [])
            if not isinstance(ids, list) or len(ids) > K.MAX_SKILLS or any(not isinstance(sid, str) or not K.HASH.fullmatch(sid) for sid in ids) or len(set(ids)) != len(ids):
                return self._send(400, {"error": "invalid inherited skill list"})
            if ids:
                try:
                    available = K.references(log_of(nd["parent"]), b.get("parent_head", ""))
                    current = K.references(log_of(nd["parent"]))
                except ValueError as exc:
                    return self._send(400, {"error": str(exc)})
                if any(sid not in available or not available[sid]["inherit"] or sid not in current or not current[sid]["inherit"] or package_of(sid) is None for sid in ids):
                    return self._send(400, {"error": "skills must be approved for inheritance by this parent at the signed snapshot"})
        m = model_of(a)             # (takes LOCK itself when it has to rebuild - so call it before taking LOCK)
        with LOCK:
            # Recheck skill permissions under the same lock as append so concurrent approvals
            # cannot exceed the active-package cap or race a parent's inheritance refusal.
            if (kind == "teach" and "skill" in body) or (kind == "inherit" and body.get("skills")):
                with tx() as c:
                    source_asset = a if kind == "teach" else body["parent"]
                    source_log = [json.loads(row[0]) for row in c.execute("SELECT json FROM entry WHERE asset=? ORDER BY n", (source_asset,))]
                current = K.references(source_log)
                if kind == "teach":
                    if body["skill"]["id"] not in current and len(current) >= K.MAX_SKILLS:
                        return self._send(400, {"error": "at most 20 active skills per replica"})
                    if package["origin"].get("parent_package") and package["origin"]["parent_package"] not in current:
                        return self._send(400, {"error": "extension requires its parent skill"})
                elif any(sid not in current or not current[sid]["inherit"] for sid in body["skills"]):
                    return self._send(400, {"error": "parent no longer permits inheritance of these skills"})
            try:
                m.apply(e)          # the relay checks the chain; it never writes entries of its own
            except (S.ChainError, KeyError, TypeError) as ex:
                return self._send(409, {"error": str(ex), "head": m.head, "entries": m.n})
            try:
                c = sqlite3.connect(STATE / "replica.db", timeout=10)
                with c:
                    c.execute("INSERT INTO entry VALUES (?,?,?)", (a, e["n"], json.dumps(e, ensure_ascii=False)))
                c.close()
            except Exception:
                MODELS.pop(a, None)     # memory ran ahead of the db; rebuild from the db next time
                raise
        if kind == "inherit":
            event("inherit", a, "%s took %d of %s's memories with it." % (serial_of(a), len((e.get("body") or {}).get("items") or []), serial_of(e["body"]["parent"])))
        elif kind == "teach":
            event("teach", a, "%s was told something." % serial_of(a))
        return self._send(200, {"head": m.head, "entries": m.n})

    # ---- rebuild: anyone posts an asset + a log; we replay it and say whether it matches
    def rebuild(self, d):
        a, log = str(d.get("asset", "")), d.get("log")
        if not is_asset(a) or not isinstance(log, list) or len(log) > 5000:
            return self._send(400, {"error": "need a replica token id and a log (list of entries)"})
        try:
            m = S.ReplicaModel.rebuild(a, log)
        except (S.ChainError, KeyError, TypeError) as ex:
            return self._send(200, {"valid": False, "error": str(ex)})
        here = model_of(a).card() if registered(a) else None
        return self._send(200, {"valid": True, "card": m.card(),
                                "matches_registry": bool(here and here["head"] == m.head),
                                "registry_entries": here["entries"] if here else None})


class UnixHTTPServer(ThreadingHTTPServer):
    """nginx talks to the app over a socket file, so the service needs no local network at all (see deploy/replica.service)"""
    address_family = __import__("socket").AF_UNIX

    def server_bind(self):
        self.socket.bind(self.server_address)
        self.server_name, self.server_port = "replica", 0

    def get_request(self):
        sock, _ = self.socket.accept()
        return sock, ("unix", 0)


if __name__ == "__main__":
    init_db()
    path = os.environ.get("RP_SOCKET")
    if path:
        if os.path.exists(path):
            os.unlink(path)
        srv = UnixHTTPServer(path, H)
        os.chmod(path, 0o666)       # the directory (RuntimeDirectory, 0755) is what nginx traverses
    else:
        srv = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8345"))), H)
    srv.daemon_threads = True
    srv.serve_forever()
