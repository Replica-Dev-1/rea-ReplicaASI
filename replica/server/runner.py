"""Private, owner-bound queue for outbound local REA workers. No remote shell commands."""
import hashlib
import json
import re
import secrets
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS runner_pair (hash TEXT PRIMARY KEY, owner TEXT, asset TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS runner (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE, owner TEXT, asset TEXT,
    name TEXT, created REAL, expires REAL, revoked INT DEFAULT 0, seen REAL DEFAULT 0, target TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS investigation (id TEXT PRIMARY KEY, runner TEXT, owner TEXT, asset TEXT,
    question TEXT, target TEXT, state TEXT, created REAL, updated REAL, result TEXT DEFAULT '{}', error TEXT DEFAULT '');
"""
HASH = re.compile(r"^[0-9a-f]{64}$")
ACTIVE = ("queued", "running")


class Refused(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or re.search(r"[\x00-\x08\x0b-\x1f\x7f]", value):
        raise Refused(400, "invalid text")
    return value.strip()


def digest(value):
    return hashlib.sha256(text(value, 100).encode()).hexdigest()


def target(value):
    if not isinstance(value, dict):
        raise Refused(400, "a selected source file is required")
    result = {"label": text(value.get("label"), 80), "file": text(value.get("file"), 100), "sha256": text(value.get("sha256"), 64)}
    if not HASH.fullmatch(result["sha256"]) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:js|cjs|mjs|jsx|ts|tsx)", result["file"]):
        raise Refused(400, "invalid source identity")
    return result


def result(value, validate_skill):
    if not isinstance(value, dict):
        raise Refused(400, "invalid result")
    report = text(value.get("report"), 12000)
    finding = value.get("finding")
    if not isinstance(finding, dict) or finding.get("schema") != "replica-rea-finding-v1":
        raise Refused(400, "invalid finding")
    source = finding.get("source")
    if not isinstance(source, dict):
        raise Refused(400, "missing evidence")
    clean = {"schema": finding["schema"], "cue": text(finding.get("cue"), 600), "answer": text(finding.get("answer"), 600),
             "source": {key: text(source.get(key), size) for key, size in
                        [("version", 40), ("tool", 80), ("target", 160), ("evidence", 400), ("limitations", 300)]}}
    if clean["source"]["tool"] != "analyze_javascript_application":
        raise Refused(400, "unsupported investigation tool")
    clean["source"]["provider"] = "rea"
    # Match the browser's signed-log size budget before accepting a review result.
    body = {"cue": clean["cue"], "answer": clean["answer"], "source": clean["source"] | {"host_reviewed": True}}
    if len(json.dumps(body, ensure_ascii=True)) + 100 > 3000:
        raise Refused(400, "finding is too long; shorten it before sending")
    output = {"report": report, "finding": clean}
    if value.get("package_json") is not None:
        raw = value["package_json"]
        validate_skill(raw)
        output["package_json"] = raw
    return output


class Service:
    def __init__(self, lock, tx, owner, validate_skill):
        self.lock, self.tx, self.owner, self.validate_skill = lock, tx, owner, validate_skill

    def handle(self, handler, action, data):
        try:
            if not isinstance(data, dict):
                raise Refused(400, "object required")
            return handler._send(200, self.perform(handler, action, data))
        except Refused as e:
            return handler._send(e.status, {"error": e.message})
        except AlreadySent:
            return None

    def perform(self, h, action, d):
        now = time.time()
        # Expired tasks are never replayed automatically: a lost response must not rerun a tool.
        with self.lock, self.tx() as c:
            c.execute("DELETE FROM runner_pair WHERE expires<?", (now,))
            c.execute("DELETE FROM investigation WHERE updated<?", (now - 7 * 86400,))
            c.execute("UPDATE investigation SET state='failed',error='Runner timed out; start a new task.',updated=? WHERE state='running' AND updated<?", (now, now - 1800))
            c.execute("UPDATE investigation SET state='cancelled',error='Task expired.',updated=? WHERE state='queued' AND created<?", (now, now - 86400))
        if action == "pair":
            code = digest(d.get("code"))
            with self.lock, self.tx() as c:
                offer = c.execute("SELECT * FROM runner_pair WHERE hash=? AND expires>?", (code, now)).fetchone()
            if not offer or self.owner(offer["asset"], ttl=0) != offer["owner"]:
                raise Refused(403, "pairing code expired or no longer authorized")
            name = text(d.get("name"), 80)
            credential, rid = secrets.token_urlsafe(32), secrets.token_hex(16)
            with self.lock, self.tx() as c:
                if c.execute("SELECT COUNT(*) FROM runner WHERE asset=? AND revoked=0 AND expires>?", (offer["asset"], now)).fetchone()[0] >= 3:
                    raise Refused(409, "disconnect an existing runner first (maximum three)")
                if c.execute("DELETE FROM runner_pair WHERE hash=? AND expires>?", (code, now)).rowcount != 1:
                    raise Refused(403, "pairing code already used")
                c.execute("INSERT INTO runner(id,token_hash,owner,asset,name,created,expires) VALUES(?,?,?,?,?,?,?)",
                          (rid, digest(credential), offer["owner"], offer["asset"], name, now, now + 30 * 86400))
            return {"runner_id": rid, "runner_token": credential, "asset": offer["asset"], "expires": now + 30 * 86400}

        if action in ("offer", "list", "get", "enqueue", "cancel", "revoke"):
            auth = h._owner(d)
            if not auth:
                # _owner already sent its response.
                raise AlreadySent()
            wallet, asset = auth
            if self.owner(asset, ttl=0) != wallet:
                raise Refused(403, "replica ownership changed")
            if action == "offer":
                code = secrets.token_urlsafe(24)
                with self.lock, self.tx() as c:
                    c.execute("DELETE FROM runner_pair WHERE asset=?", (asset,))
                    c.execute("INSERT INTO runner_pair VALUES(?,?,?,?)", (digest(code), wallet, asset, now + 600))
                return {"code": code, "expires": now + 600}
            if action == "list":
                with self.lock, self.tx() as c:
                    runners = c.execute("SELECT id,name,seen,target,expires FROM runner WHERE owner=? AND asset=? AND revoked=0 AND expires>? ORDER BY created DESC", (wallet, asset, now)).fetchall()
                    jobs = c.execute("SELECT id,runner,question,target,state,created,updated,result,error FROM investigation WHERE owner=? AND asset=? ORDER BY created DESC LIMIT 20", (wallet, asset)).fetchall()
                summaries = []
                for j in jobs:
                    output = json.loads(j["result"])
                    has_package = bool(output.pop("package_json", None))
                    summaries.append(dict(j) | {"target": json.loads(j["target"]), "result": output, "has_package": has_package})
                return {"runners": [dict(r) | {"target": json.loads(r["target"]), "online": now-r["seen"] < 45} for r in runners], "jobs": summaries}
            with self.lock, self.tx() as c:
                if action == "get":
                    row = c.execute("SELECT result FROM investigation WHERE id=? AND owner=? AND asset=?", (d.get("job_id"), wallet, asset)).fetchone()
                    if not row:
                        raise Refused(404, "task not found")
                    return {"result": json.loads(row["result"])}
                if action == "cancel":
                    if not c.execute("UPDATE investigation SET state='cancelled',result='{}',error='Cancelled by owner.',updated=? WHERE id=? AND owner=? AND asset=?", (now, d.get("job_id"), wallet, asset)).rowcount:
                        raise Refused(404, "task not found")
                    return {"cancelled": True}
                runner = c.execute("SELECT * FROM runner WHERE id=? AND owner=? AND asset=? AND revoked=0 AND expires>?", (d.get("runner_id"), wallet, asset, now)).fetchone()
                if not runner:
                    raise Refused(404, "runner not found")
                if action == "revoke":
                    c.execute("UPDATE runner SET revoked=1 WHERE id=?", (runner["id"],))
                    c.execute("UPDATE investigation SET state='cancelled',result='{}',updated=?,error='Runner disconnected.' WHERE runner=?", (now, runner["id"]))
                    return {"revoked": True}
                if runner["seen"] < now - 45 or runner["target"] == "{}":
                    raise Refused(409, "start the local runner and select a source file first")
                if c.execute("SELECT COUNT(*) FROM investigation WHERE asset=? AND (state IN ('queued','running') OR created>?)", (asset, now - 86400)).fetchone()[0] >= 20:
                    raise Refused(429, "daily task limit reached (20)")
                if c.execute("SELECT 1 FROM investigation WHERE runner=? AND state IN ('queued','running')", (runner["id"],)).fetchone():
                    raise Refused(409, "this runner already has an active task")
                jid = secrets.token_hex(16)
                c.execute("INSERT INTO investigation(id,runner,owner,asset,question,target,state,created,updated) VALUES(?,?,?,?,?,?,'queued',?,?)",
                          (jid, runner["id"], wallet, asset, text(d.get("question"), 600), runner["target"], now, now))
                return {"job_id": jid}

        if action not in ("poll", "complete", "fail", "heartbeat"):
            raise Refused(404, "unknown runner action")
        token_hash = digest(d.get("runner_token"))
        with self.lock, self.tx() as c:
            runner = c.execute("SELECT * FROM runner WHERE token_hash=? AND revoked=0 AND expires>?", (token_hash, now)).fetchone()
        if not runner or self.owner(runner["asset"], ttl=0) != runner["owner"]:
            raise Refused(403, "runner disconnected, expired, or replica transferred")
        prepared = result(d.get("result"), self.validate_skill) if action == "complete" else None
        chosen = target(d.get("target")) if action == "poll" else None
        with self.lock, self.tx() as c:
            # Recheck revocation after the ownership/network lookup and validation.
            if not c.execute("SELECT 1 FROM runner WHERE id=? AND revoked=0 AND expires>?", (runner["id"], now)).fetchone():
                raise Refused(403, "runner disconnected")
            c.execute("UPDATE runner SET seen=? WHERE id=?", (now, runner["id"]))
            if action == "poll":
                c.execute("UPDATE runner SET target=? WHERE id=?", (json.dumps(chosen), runner["id"]))
                job = c.execute("SELECT * FROM investigation WHERE runner=? AND state='queued' ORDER BY created LIMIT 1", (runner["id"],)).fetchone()
                if not job:
                    return {"job": None}
                c.execute("UPDATE investigation SET state='running',updated=? WHERE id=? AND state='queued'", (now, job["id"]))
                return {"job": {key: job[key] for key in ("id", "question", "asset")} | {"target": json.loads(job["target"])}}
            job = c.execute("SELECT * FROM investigation WHERE id=? AND runner=?", (d.get("job_id"), runner["id"])).fetchone()
            if not job or job["state"] not in ("running", "review"):
                raise Refused(409, "task cancelled, expired, or unavailable")
            if action == "heartbeat":
                c.execute("UPDATE investigation SET updated=? WHERE id=?", (now, job["id"]))
                return {"active": True}
            if action == "complete":
                if prepared["finding"]["cue"] != job["question"]:
                    raise Refused(400, "finding question must match the requested task")
                c.execute("UPDATE investigation SET state='review',result=?,error='',updated=? WHERE id=?", (json.dumps(prepared), now, job["id"]))
                return {"state": "review"}
            c.execute("UPDATE investigation SET state='failed',error=?,updated=? WHERE id=?", (text(d.get("error"), 300), now, job["id"]))
            return {"state": "failed"}


class AlreadySent(Exception):
    pass
