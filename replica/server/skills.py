"""Versioned public skill artifacts. Validation never executes uploaded code."""
from __future__ import annotations
import hashlib
import json
import re

SCHEMA = "replica-skill-v1"
MAX_BYTES = 1_500_000
MAX_SKILLS = 20
HASH = re.compile(r"^[0-9a-f]{64}$")
PATH = re.compile(r"^[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*$")

def text(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(label + " must be nonempty bounded text")
    return value

def validate(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("skill package exceeds 1.5 MB")
    p = json.loads(raw)
    if not isinstance(p, dict) or p.get("schema") != SCHEMA:
        raise ValueError("unsupported skill package")
    for name, size in [("title", 120), ("question", 600), ("version", 40)]:
        text(p.get(name), name, size)
    target = p.get("target")
    if not isinstance(target, dict) or not HASH.fullmatch(str(target.get("sha256", ""))):
        raise ValueError("target digest is required")
    text(target.get("name"), "target name", 160)
    text(target.get("version"), "target version", 80)
    finding = p.get("finding")
    if not isinstance(finding, dict):
        raise ValueError("finding is required")
    text(finding.get("interpretation"), "interpretation", 600)
    for key in ("observations", "limitations"):
        values = finding.get(key)
        if not isinstance(values, list) or not 1 <= len(values) <= 20:
            raise ValueError(key + " must be a nonempty list")
        for value in values:
            text(value, key, 1000)
    visibility = p.get("visibility")
    if not isinstance(visibility, dict) or visibility.get("public") is not True or type(visibility.get("inheritable")) is not bool:
        raise ValueError("only explicitly public packages can be saved; keep private work local")
    origin = p.get("origin")
    if not isinstance(origin, dict) or not isinstance(origin.get("author"), str):
        raise ValueError("origin is required")
    text(origin["author"], "author", 160)
    parent = origin.get("parent_package")
    if parent is not None and (not isinstance(parent, str) or not HASH.fullmatch(parent)):
        raise ValueError("invalid parent package")
    requirements = p.get("requirements")
    if not isinstance(requirements, list) or len(requirements) > 20:
        raise ValueError("requirements must be a bounded list")
    for item in requirements:
        text(item, "requirement", 300)
    files = p.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 32:
        raise ValueError("need 1-32 embedded files")
    paths = {}
    roles = set()
    for file in files:
        if not isinstance(file, dict):
            raise ValueError("invalid file")
        name = text(file.get("path"), "file path", 160)
        if not PATH.fullmatch(name) or ".." in name or name.startswith("/") or name in paths:
            raise ValueError("file paths must be unique safe relative names")
        reserved = {"CON", "PRN", "AUX", "NUL"} | {prefix + str(i) for prefix in ("COM", "LPT") for i in range(1, 10)}
        if any(part.split(".")[0].upper() in reserved for part in name.split("/")):
            raise ValueError("reserved device names are not valid artifact paths")
        content = text(file.get("content"), "file content", 1_000_000)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if file.get("sha256") != digest:
            raise ValueError("file digest mismatch: " + name)
        role = file.get("role")
        if role not in {"target", "implementation", "tests", "test-record", "evidence", "license", "instructions"}:
            raise ValueError("unsupported file role")
        paths[name] = file
        roles.add(role)
    if not {"implementation", "tests", "test-record", "evidence"} <= roles:
        raise ValueError("code, tests, test record and portable evidence are required")
    evidence = p.get("evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20:
        raise ValueError("portable evidence references required")
    for ref in evidence:
        if not isinstance(ref, dict) or ref.get("path") not in paths or paths[ref["path"]]["role"] != "evidence":
            raise ValueError("evidence must reference embedded evidence files")
        text(ref.get("description"), "evidence description", 500)
    tests = p.get("tests")
    if not isinstance(tests, dict) or tests.get("record") not in paths or paths[tests["record"]]["role"] != "test-record":
        raise ValueError("embedded test record required")
    text(tests.get("command"), "test command", 300)
    record = json.loads(paths[tests["record"]]["content"])
    cases = record.get("cases") if isinstance(record, dict) else None
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise ValueError("test record needs bounded test cases")
    for case in cases:
        if not isinstance(case, dict) or case.get("passed") is not True:
            raise ValueError("only packages reporting all checks passed can be saved")
        text(case.get("name"), "test name", 200)
    # A report is evidence supplied by its author, not a server attestation of correctness.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), p

def summary(package_id, package):
    record = next(f for f in package["files"] if f["path"] == package["tests"]["record"])
    return {"id": package_id, "title": package["title"], "version": package["version"],
            "question": package["question"], "finding": package["finding"],
            "target": package["target"], "origin": package["origin"], "visibility": package["visibility"],
            "requirements": package["requirements"], "reported_passed": len(json.loads(record["content"])["cases"])}

def references(log, head=None):
    """Derive approved package ownership from signed log data, optionally at a historical head."""
    refs = {}
    found = head is None
    for e in log:
        b = e.get("body") or {}
        if e.get("kind") == "teach" and isinstance(b.get("skill"), dict) and isinstance(b["skill"].get("id"), str) and HASH.fullmatch(b["skill"]["id"]) and type(b["skill"].get("inherit")) is bool:
            s = b["skill"]
            refs[s["id"]] = {"id": s["id"], "inherit": s["inherit"], "via": None,
                              "entry": e["h"], "memory_id": e["h"][:16]}
        elif e.get("kind") == "inherit":
            for sid in b.get("skills", []) if isinstance(b.get("skills", []), list) else []:
                if not isinstance(sid, str) or not HASH.fullmatch(sid):
                    continue
                refs[sid] = {"id": sid, "inherit": True, "via": b["parent"], "entry": e["h"], "memory_id": None}
        elif e.get("kind") == "forget":
            refs = {sid: value for sid, value in refs.items() if value["memory_id"] != b.get("id")}
        if head is not None and e["h"] == head:
            found = True
            break
    if not found:
        raise ValueError("parent snapshot is not in its signed log")
    return refs
