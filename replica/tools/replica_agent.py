"""Standalone, bounded Replica specialists. No model, remote core or network client."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

from replica_package import assemble
import skills

ROOT = Path(__file__).resolve().parents[1]
VERSION = "replica-specialists-1"
NOTE_SOURCE = "cad49e7df07d784f19292714a72bba5f9253c9af7cec79820a2774bbf8f07f1d"
BUILD_WORDS = re.compile(r"\b(build|rebuild|reconstruct|implement|make|create|extend|add)\b", re.I)
ARITHMETIC = re.compile(r"\s*(?:['\"]use strict['\"];?\s*)?module\.exports\s*=\s*\{\s*([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*)\s*=>\s*\2\s*([+*/-])\s*(-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)\s*\}\s*;?\s*", re.ASCII)
SPECIALISTS = {"source-evidence", "numeric-helper", "notes-search", "notes-search-extension"}


def load_profile(path=None):
    path = Path(path) if path else ROOT / "agents/replica/agent.json"
    if path.is_symlink() or path.stat().st_size > 10_000:
        raise ValueError("Invalid local agent profile.")
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or set(profile) != {"schema", "name", "core", "language_model", "specialists"} or profile.get("schema") != "replica-agent-profile-v1":
        raise ValueError("Unsupported agent profile; endpoints and remote settings are not accepted.")
    if profile["core"] != "never" or profile["language_model"] is not False:
        raise ValueError("This runtime has no language model or core fallback.")
    if not isinstance(profile["name"], str) or not 1 <= len(profile["name"]) <= 80 or any(ord(c) < 32 for c in profile["name"]):
        raise ValueError("Choose a bounded agent name.")
    enabled = profile["specialists"]
    if not isinstance(enabled, list) or not enabled or any(not isinstance(x, str) or x not in SPECIALISTS for x in enabled) or len(set(enabled)) != len(enabled):
        raise ValueError("Only admitted local specialists can be enabled.")
    return profile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def evidence_for(job, folder):
    name = job["target"]["file"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:js|cjs|mjs|jsx|ts|tsx)", name):
        raise ValueError("Invalid source identity.")
    source = folder / "input" / name
    if source.is_symlink() or source.stat().st_size > 1_000_000:
        raise ValueError("Invalid source snapshot.")
    data = source.read_bytes()
    if digest(data) != job["target"]["sha256"]:
        raise ValueError("Source changed after inspection.")
    path = folder / "rea-original.json"
    if path.is_symlink() or path.stat().st_size > 8_000_000:
        raise ValueError("Invalid REA evidence.")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or not isinstance(raw.get("normalized_result"), dict):
        raise ValueError("Invalid REA evidence shape.")
    normal = raw.get("normalized_result", {})
    if not re.fullmatch(r"ev_[0-9a-f]{64}", raw.get("evidence_id", "")):
        raise ValueError("Missing REA evidence identity.")
    stats = normal.get("statistics", {})
    if not isinstance(stats, dict) or type(stats.get("parsed_javascript_files")) is not int or stats.get("parsed_javascript_files") != 1 or type(stats.get("parse_failures")) is not int or stats.get("parse_failures") != 0 or normal.get("integrity_contradictions"):
        raise ValueError("REA evidence is incomplete or contradictory.")
    modules = []
    graph = normal.get("graph", {})
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise ValueError("REA module graph is missing.")
    for node in graph["nodes"]:
        if not isinstance(node, dict):
            raise ValueError("Invalid REA graph node.")
        if node.get("kind") != "javascript-module":
            continue
        observations = node.get("observations", [])
        if not isinstance(observations, list):
            raise ValueError("Invalid REA observations.")
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError("Invalid REA observation.")
            props = observation.get("properties", {})
            proof = observation.get("evidence", {})
            if not isinstance(props, dict) or not isinstance(proof, dict) or not isinstance(proof.get("artifact", {}), dict):
                raise ValueError("Invalid REA proof.")
            if (props.get("semantic_role") == "source-module" and props.get("source_sha256") == digest(data)
                    and proof.get("artifact", {}).get("sha256") == digest(data) and proof.get("state") == "observed"):
                modules.append({"observation_id": observation.get("observation_id"),
                                "module_format": props.get("module_format"),
                                "export_relationships": props.get("export_relationships"),
                                "source_sha256": digest(data)})
    if not modules:
        raise ValueError("REA evidence does not identify the selected source module.")
    # Explicit portable allowlist; no original paths or arbitrary source excerpts.
    evidence = {"schema": "replica-native-evidence-v1", "rea_version": "6.8.0", "evidence_id": raw["evidence_id"],
                "source_sha256": digest(data), "modules": modules,
                "limitations": ["Portable structural excerpt; static analysis is not a behavior test."]}
    return data, evidence


def choose(job, source, parent=None):
    question = job["question"]
    if not BUILD_WORDS.search(question):
        return {"specialist": "source-evidence", "outcome": "inspect", "reason": "No build requested. Source evidence is available; runtime behavior is not established."}
    if digest(source) == NOTE_SOURCE and re.search(r"\b(search|notes?)\b", question, re.I):
        if parent:
            return {"specialist": "notes-search-extension", "outcome": "build", "reason": "Known notes-search parent; add all-word matching and a result limit using the bundled recipe."}
        if re.search(r"\b(extend|limit|all.words?|descendant)\b", question, re.I):
            return {"specialist": "source-evidence", "outcome": "decline", "reason": "The notes extension requires a reviewed parent package selected with --parent."}
        return {"specialist": "notes-search", "outcome": "build", "reason": "Exact reference-source digest recognized; reconstruct the bounded notes search using the bundled recipe."}
    match = ARITHMETIC.fullmatch(source.decode("utf-8"))
    if match and not parent and re.search(r"\b(helper|function|numeric|number|arithmetic|double|scale|multiply|divide|subtract|increment|decrement)\b", question, re.I):
        name, variable, operator, literal = match.groups()
        value = float(literal)
        if math.isfinite(value) and abs(value) <= 1_000_000 and not (operator == "/" and value == 0):
            return {"specialist": "numeric-helper", "outcome": "build", "name": name, "operator": operator, "constant": literal,
                    "reason": "Recognized one CommonJS arrow function with one arithmetic operation and a bounded constant. Numeric inputs only."}
    return {"specialist": "source-evidence", "outcome": "decline", "reason": "No admitted build specialist covers this source and request. No code was executed and no external fallback was used."}


def load_parent(path):
    if path is None:
        return None
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > skills.MAX_BYTES:
        raise ValueError("Invalid parent package file.")
    raw = path.read_text(encoding="utf-8")
    sid, package = skills.validate(raw)
    if not package["visibility"]["inheritable"] or package["origin"]["parent_package"] is not None:
        raise ValueError("Choose an inheritable parent search package, not an extension.")
    approved = json.loads((ROOT / "static/samples/search/parent.skill.json").read_text(encoding="utf-8"))
    files = {f["path"]: f for f in package["files"]}
    for original in approved["files"]:
        if original["role"] in ("target", "implementation", "tests", "license"):
            if files.get(original["path"], {}).get("sha256") != original["sha256"]:
                raise ValueError("The extension specialist does not cover this parent implementation.")
    if package["target"]["sha256"] != NOTE_SOURCE:
        raise ValueError("Parent source does not match the supported notes application.")
    return sid, package


def numeric_recipe(plan):
    operator, literal, name = plan["operator"], plan["constant"], plan["name"]
    implementation = "'use strict';\nmodule.exports = { [" + json.dumps(name) + "]: value => {\n" + \
        "  if (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > 1000000) throw new RangeError('Use a finite number between -1000000 and 1000000');\n" + \
        "  return value " + operator + " " + literal + ";\n}};\n"
    constant = float(literal)
    rows = []
    for value in [-1000000, -7, -0.5, 0, 0.125, 3, 999999, 1000000]:
        expected = {"+": lambda: value + constant, "-": lambda: value - constant,
                    "*": lambda: value * constant, "/": lambda: value / constant}[operator]()
        if not math.isfinite(expected):
            raise ValueError("Arithmetic result outside the supported finite domain.")
        rows.append({"input": value, "expected": expected})
    tests = """'use strict';
const fn = require('./implementation.cjs')[NAME];
const cases = ROWS.map(({input,expected}) => { const actual=fn(input); return {name:'numeric input '+input,input,expected,actual,passed:actual===expected}; });
for (const [label,input] of [['string','2'],['null',null],['NaN',NaN],['infinity',Infinity],['above domain',1000001],['below domain',-1000001]]) {
  let passed=false; try { fn(input); } catch(error) { passed=error instanceof RangeError; }
  cases.push({name:'decline '+label,passed});
}
console.log(JSON.stringify({schema:'replica-test-record-v1',runner:process.version,cases}));
if (!cases.every(c=>c.passed)) process.exitCode=1;
""".replace("NAME", json.dumps(name)).replace("ROWS", json.dumps(rows))
    return {"implementation.cjs": ("implementation", implementation), "tests.cjs": ("tests", tests)}, []


def recipe(plan):
    if plan["specialist"] == "numeric-helper":
        return numeric_recipe(plan)
    variant = "child" if plan["specialist"] == "notes-search-extension" else "parent"
    package = json.loads((ROOT / ("static/samples/search/" + variant + ".skill.json")).read_text(encoding="utf-8"))
    skills.validate(json.dumps(package))
    files = {f["path"]: (f["role"], f["content"]) for f in package["files"] if f["role"] in ("target", "implementation", "tests", "license")}
    return files, ["--child"] if variant == "child" else []


def run(job, folder, result, node, builds, confirm, parent_path=None, heartbeat=lambda: None, profile_path=None):
    if not re.fullmatch(r"[0-9a-f]{32}", job.get("id", "")) or not isinstance(job.get("question"), str) or not 1 <= len(job["question"]) <= 600:
        raise ValueError("Invalid task identity.")
    asset = job.get("asset", "")
    if not isinstance(asset, str) or not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", asset):
        raise ValueError("Standalone agents require the paired replica's asset identity.")
    folder = Path(folder)
    profile = load_profile(profile_path)
    source, evidence = evidence_for(job, folder)
    parent = load_parent(parent_path)
    plan = choose(job, source, parent)
    if plan["specialist"] not in profile["specialists"]:
        plan = {"specialist": "scope-gate", "outcome": "decline", "reason": "The required specialist is not enabled in this replica's local profile. No fallback was used."}
    identity = digest((VERSION + ":" + asset).encode())
    receipt = {"schema": "replica-agent-receipt-v1", "version": VERSION, "asset": asset, "agent_id": identity,
               "job": job["id"], "source_sha256": digest(source), "evidence_id": evidence["evidence_id"],
               "parent_package": parent[0] if parent else None, "profile": profile, "profile_sha256": digest(canonical(profile)), "plan": plan}
    receipt["sha256"] = digest(canonical(receipt))
    (folder / "agent-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    updated = copy.deepcopy(result)
    updated["report"] += "\n\nReplica specialist: " + plan["specialist"] + "\n" + plan["reason"]
    if plan["outcome"] != "build":
        updated["finding"]["answer"] = plan["reason"]
        return updated
    print("\nSpecialist: " + plan["specialist"] + "\n" + plan["reason"], flush=True)
    if not confirm("Build this supported feature and run the bundled checks locally? No source is sent to a model or external agent service.", "build"):
        return updated
    heartbeat()
    builds = Path(builds).resolve()
    if builds.is_relative_to(folder.resolve().parent.parent):
        raise ValueError("Build directory must be outside private runner state.")
    workspace = builds / (job["id"] + "-" + str(time.time_ns()))
    workspace.mkdir(parents=True, exist_ok=False)
    files, arguments = recipe(plan)
    if "target.cjs" in files and digest(files["target.cjs"][1].encode()) != digest(source):
        raise ValueError("Bundled recipe does not match inspected source.")
    files["reference.txt"] = ("target", source.decode("utf-8"))
    files["evidence.json"] = ("evidence", json.dumps(evidence, indent=2))
    files["agent-receipt.json"] = ("evidence", json.dumps(receipt, indent=2))
    for name, (_, content) in files.items():
        (workspace / name).write_text(content, encoding="utf-8", newline="\n")
    # Only fixed, bundled recipes or constrained numeric generation are executed. Never a supplied package command.
    environment = {k: v for k, v in os.environ.items() if k not in ("NODE_OPTIONS", "NODE_PATH")}
    executed = subprocess.run([node, "tests.cjs", *arguments], cwd=workspace, env=environment,
                              capture_output=True, timeout=20, check=False)
    heartbeat()
    if executed.returncode or len(executed.stdout) > 200_000:
        raise ValueError("Specialist checks failed. No skill package was created.")
    record = json.loads(executed.stdout)
    cases = record.get("cases", [])
    expected_count = {"numeric-helper": 14, "notes-search": 20, "notes-search-extension": 35}[plan["specialist"]]
    if len(cases) != expected_count or not all(isinstance(c, dict) and c.get("passed") is True for c in cases):
        raise ValueError("Specialist did not produce passing checks.")
    record["executed_by"] = VERSION
    files["test-record.json"] = ("test-record", json.dumps(record, indent=2))
    (workspace / "test-record.json").write_text(files["test-record.json"][1], encoding="utf-8")
    interpretation = ("Numeric helper reconstructed from the admitted one-operation source form. It accepts only finite numeric inputs from -1000000 to 1000000."
                      if plan["specialist"] == "numeric-helper" else
                      "Known notes-search recipe rebuilt and checked. " + ("The extension adds all-word matching and result limits." if parent else "Search filters archived notes and tags, ignores case and ranks title matches first."))
    spec = {"schema": "replica-skill-v1", "title": "Replica " + plan["specialist"], "version": "1.0.0", "question": job["question"],
            "target": {"name": job["target"]["label"][:55] + "/" + job["target"]["file"], "version": digest(source)[:12], "sha256": digest(source)},
            "finding": {"observations": ["REA identified the selected source module by its exact digest.", plan["reason"], str(len(cases)) + " checks executed and passed locally."],
                        "interpretation": interpretation, "limitations": ["Bounded native specialist, not general-purpose code generation.", "Notes search uses an authored recipe for the exact included sample; numeric reconstruction accepts only the documented source form.", "The relay does not independently certify this local test record."]},
            "files": [{"path": name, "role": role} for name, (role, _) in files.items()],
            "evidence": [{"path": "evidence.json", "description": "Portable excerpt from this task's REA inspection."}, {"path": "agent-receipt.json", "description": "Replica identity, specialist decision, parent linkage and evidence digest."}],
            "tests": {"command": "node tests.cjs" + (" --child" if arguments else ""), "record": "test-record.json"},
            "origin": {"author": "Replica standalone specialist " + identity[:16], "parent_package": parent[0] if parent else None},
            "requirements": ["Node.js 24.22.1 tested", "Review package files before running them."], "visibility": {"public": True, "inheritable": True}}
    (workspace / "skill-spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    raw = assemble(workspace / "skill-spec.json")
    (workspace / "skill.json").write_text(raw, encoding="utf-8", newline="\n")
    updated["package_json"] = raw
    updated["finding"]["answer"] = interpretation
    updated["finding"]["source"]["limitations"] = "Locally executed specialist checks cover only the declared scope. The relay validates structure and hashes, not independent correctness."
    updated["report"] += "\n" + str(len(cases)) + " checks passed. Review every file before upload.\n" + interpretation
    print("Review the complete package: " + str(workspace / "skill.json"), flush=True)
    return updated
