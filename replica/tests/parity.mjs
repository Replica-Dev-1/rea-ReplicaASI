// Python <-> JS parity for REPLICA (memory model, faces, inheritance). run: node tests/parity.mjs /opt/replica
// Builds a log in JS (teach/forget/agent/learn/fill, unicode, floats), has Python rebuild it, compares head,
// fingerprint, osub_seed phases, and recall answers + resonances on a question set.
import { execFileSync } from "child_process"; import fs from "fs"; import { createRequire } from "module";
const APP = process.argv[2] || "/opt/replica";
const R = createRequire(import.meta.url)(APP + "/static/replica.js");
const asset = "H2oKogqzWK956ezfKdaD2gSSBWaE4kUM1moTqQnuHHie";
let pass = 0, fail = 0;
const check = (n, c, x) => { c ? pass++ : fail++; console.log((c ? "PASS " : "FAIL ") + n + (x ? "  " + x : "")); };

const m = await R.Model.create(asset);
const log = [];
const add = async (kind, body) => { const e = await R.makeEntry(m.head, m.n, kind, body, 1760400000 + m.n); await m.apply(e); log.push(e); };
await add("teach", { cue: "What is my dog's name?", answer: "Juniper" });
await add("teach", { cue: "Où est la clé? \"quoted\" \\ back", answer: "Sous le paillasson — ✓ 日本" });
for (let i = 0; i < 30; i++) await add("teach", { cue: "What is note number " + i + " about?", answer: "note " + i });
await add("forget", { id: log[2].h.slice(0, 16) });
await add("agent", { strategy: "trend", mode: "paper", limits: { per_trade_usd: 25.5, per_day_usd: 100 } });
await add("learn", { strategy: "trend", weights: [0.25, 0.5, 0.125], equity: 1003.75, t: 3 });
await add("fill", { side: "buy", sol: 0.0125, price: 107.07874331952628, paper: true });
await add("learn", { tiny: [0.00001, 3.2e-7, 0.0001, 1e16, 1.5e17, 123456789012345.6, -0.00004321], one: 1, half: 0.5 });
fs.writeFileSync("/tmp/parity_log.json", JSON.stringify({ asset, log }));

const qs = ["What is my dog's name?", "dog name", "where is the key", "What is note number 7 about?", "note number 0", "How far is the moon?", "clé"];
const js = { card: await m.card(), recall: [] };
for (const q of qs) { const [it, r] = await m.recall(q); js.recall.push([it ? it.answer : null, r]); }
const ph = await R.osubSeed("replica-1:test");
const py = JSON.parse(execFileSync(APP + "/venv/bin/python", ["-c", `
import json, sys, numpy as np
sys.path.insert(0, ${JSON.stringify(APP + "/server")})
import replica_model as S
d = json.load(open("/tmp/parity_log.json", encoding="utf-8"))
m = S.ReplicaModel.rebuild(d["asset"], d["log"])
out = {"card": m.card(), "recall": []}
for q in json.loads(${JSON.stringify(JSON.stringify(qs))}):
    it, r = m.recall(q)
    out["recall"].append([it["answer"] if it else None, r])
v = S.osub_seed("replica-1:test")
out["ph"] = [float(v[0].real), float(v[0].imag), float(v[2047].real), float(v[2047].imag)]
out["state"] = m.state
print(json.dumps(out))
`], { encoding: "utf8" }));

check("osub_seed phases identical", Math.abs(py.ph[0] - ph.re[0]) < 1e-6 && Math.abs(py.ph[1] - ph.im[0]) < 1e-6 && Math.abs(py.ph[2] - ph.re[2047]) < 1e-6 && Math.abs(py.ph[3] - ph.im[2047]) < 1e-6,
  JSON.stringify([py.ph, [ph.re[0], ph.im[0], ph.re[2047], ph.im[2047]]]));
check("same head", py.card.head === js.card.head);
check("same fingerprint", py.card.fingerprint === js.card.fingerprint);
check("same name + counts", py.card.name === js.card.name && py.card.taught === js.card.taught && py.card.entries === js.card.entries, py.card.name + " / " + js.card.name);
qs.forEach((q, i) => check("recall " + JSON.stringify(q), py.recall[i][0] === js.recall[i][0] && Math.abs(py.recall[i][1] - js.recall[i][1]) < 1e-3,
  JSON.stringify([py.recall[i], js.recall[i]])));
check("agent state replays", py.state.agent.strategy === "trend" && py.state.fills.length === 1);
// faces + inherit: JS and Python must agree on identity and on a child's inherited model
const FJ = createRequire(import.meta.url)(APP + "/static/face.js");
const assets = [asset, "EprgJfSZ1JTtWqHGsVZZy99MgCVtMnf5uBsChGVnYQEd", "11111111111111111111111111111111", "So11111111111111111111111111111111111111112"];
const jsF = []; for (const a of assets) jsF.push(await FJ.identity(a));
const child = await R.Model.create("EprgJfSZ1JTtWqHGsVZZy99MgCVtMnf5uBsChGVnYQEd");
const inh = await R.makeEntry(child.head, 0, "inherit", { parent: asset, parent_head: m.head, items: m.taught().slice(-5).map(({ cue, answer }) => ({ cue, answer })) }, 1760400999);
await child.apply(inh);
fs.writeFileSync("/tmp/parity_inherit.json", JSON.stringify({ assets, log: [inh] }));
const py2 = JSON.parse(execFileSync(APP + "/venv/bin/python", ["-c", `
import json, sys
sys.path.insert(0, ${JSON.stringify(APP + "/server")})
import faces, replica_model as S
d = json.load(open("/tmp/parity_inherit.json", encoding="utf-8"))
m = S.ReplicaModel.rebuild(d["assets"][1], d["log"])
it, r = m.recall("note number 29")
print(json.dumps({"faces": [faces.identity(a) for a in d["assets"]], "card": m.card(), "ans": it["answer"] if it else None}))
`], { encoding: "utf8" }));
check("faces identical (4 addresses)", JSON.stringify(py2.faces) === JSON.stringify(jsF), jsF.map((f) => f.designation + " " + f.temperament).join(", "));
console.log(jsF[0].face.join("\n"));
const [cit] = await child.recall("note number 29");
check("inherit: same child model in both", py2.card.fingerprint === (await child.card()).fingerprint && py2.card.taught === child.items.size && py2.ans === (cit && cit.answer), py2.ans);
console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
