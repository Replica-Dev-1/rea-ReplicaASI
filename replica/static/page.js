/* REPLICA page. A replica's memory is rebuilt here, in the host's browser (replica.js), its face from its asset address
   (face.js), and its agent key lives in this browser. The host's wallet signs the mint (a Metaplex Core asset) and one
   key delegation; the server only reads the chain and relays signed log entries. Chain: Solana. */
(() => {
  const R = window.Replica, W3 = window.solanaWeb3;
  const $ = (id) => document.getElementById(id);
  const CORE = "CoREENxT6tW1HoK8ypY1SxRMZTcVPm7R94rH4PZNhX7d";
  let cfg = null, wallet = null, token = null, provider = null, mine = null, model = null, lastEvent = 0, inviteCode = null, invited = null, measured = null;

  let runnerView = null, stageRunnerFinding = null, stageRunnerSkill = null;
  const say = (t) => { $("msg").textContent = t || ""; };
  const api = async (path, body) => {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const d = await r.json().catch(() => ({ error: "bad reply" }));
    if (!r.ok || d.error) throw new Error(d.error || ("HTTP " + r.status));
    return d;
  };
  const short = (s) => (s ? s.slice(0, 6) + "…" + s.slice(-4) : "—");
  const b64 = (u8) => btoa(String.fromCharCode(...u8));
  const ls = { get: (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
               set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } } };
  const fmt = (x, d = 1) => Number(x).toLocaleString(undefined, { maximumFractionDigits: d });
  const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  function b58(bytes) {                                      // agent keys are written base58, as before
    let n = 0n; for (const x of bytes) n = n * 256n + BigInt(x);
    let s = ""; while (n > 0n) { s = B58[Number(n % 58n)] + s; n /= 58n; }
    for (const x of bytes) { if (x !== 0) break; s = "1" + s; }
    return s;
  }

  // ---- Metaplex Core CreateV2 (byte-identical to mpl-core 1.1.1 `create`, checked against devnet):
  //      [20 discriminator][0 dataState][name][uri][Some(empty plugins)][Some(empty external adapters)]; omitted optional accounts = program id
  function borshStr(t) { const b = new TextEncoder().encode(t); const n = new Uint8Array(4 + b.length); new DataView(n.buffer).setUint32(0, b.length, true); n.set(b, 4); return n; }
  function createAsset(asset, payer, name, uri) {
    const core = new W3.PublicKey(CORE);
    const parts = [new Uint8Array([20, 0]), borshStr(name), borshStr(uri), new Uint8Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0])];
    const data = new Uint8Array(parts.reduce((a, x) => a + x.length, 0));
    let o = 0; for (const x of parts) { data.set(x, o); o += x.length; }
    const ro = (k) => ({ pubkey: k, isSigner: false, isWritable: false });
    return new W3.TransactionInstruction({
      programId: core,
      keys: [
        { pubkey: asset, isSigner: true, isWritable: true },  // asset
        ro(core),                                            // collection (none)
        ro(core),                                            // authority (defaults to payer)
        { pubkey: payer, isSigner: true, isWritable: true },  // payer
        ro(core),                                            // owner (defaults to payer)
        ro(core),                                            // update authority (defaults to payer)
        ro(W3.SystemProgram.programId),                      // system program
        ro(core),                                            // log wrapper (none)
      ],
      data,
    });
  }

  // ---------------------------------------------------------------- the face (REPLICA-0 until you host one)
  const ORIGINAL = ["|         |", "|  ?   ?  |", "|  ) ~ (  |", "|         |", "|   ___   |", "|   |?|   |", "|   |     |", "|   '-'   |", "|_________|"];
  let faceRows = ORIGINAL;
  function showFace(rows, cap) { faceRows = rows; $("face").textContent = rows.join("\n"); if (cap) $("faceCap").textContent = cap; }
  setInterval(() => {                       // a blink, mostly; sometimes one eye only
    const f = $("face"), e = faceRows[1], one = Math.random() < 0.3;
    f.textContent = [faceRows[0], one ? e.replace(/[^\s|]/, "-") : e.replace(/[^\s|]/g, "-"), ...faceRows.slice(2)].join("\n");
    setTimeout(() => { f.textContent = faceRows.join("\n"); }, 160);
  }, 3900);

  // ---------------------------------------------------------------- the network figure: boxes near the top, dots below
  const num = (s) => (s || "instance_000").slice(-3);
  function drawTree(n) {
    const kids = {}; for (const x of n.nodes) (kids[x.parent] = kids[x.parent] || []).push(x);
    let slot = 0; const pos = {}; let maxD = 0;
    const place = (id, d) => {                 // leaves take the next slot; parents sit over their children
      maxD = Math.max(maxD, d);
      const ch = kids[id] || [];
      if (!ch.length) { pos[id] = { x: slot++, d }; return pos[id].x; }
      const xs = ch.map((c) => place(c.asset, d + 1));
      pos[id] = { x: (Math.min(...xs) + Math.max(...xs)) / 2, d }; return pos[id].x;
    };
    place("0", 0);
    const W = 640, gap = Math.max(1, slot - 1), boxes = slot <= 6, H = 70 + maxD * 92;
    const X = (x) => (slot <= 1 ? W / 2 : 50 + (W - 100) * x / gap), Y = (d) => 30 + d * 92;
    const ink = { active: "#4f8a87", dormant: "#c39a45", corrupt: "#c4542b" };
    let lines = "", marks = "";
    const box = (cx, cy, top, bot, col, strike, me) =>
      `<rect x="${cx - 38}" y="${cy - 19}" width="76" height="38" rx="4" fill="#fbfaf7" stroke="${me ? "#c4542b" : "#1c1a17"}" stroke-width="${me ? 2.2 : 1.2}"/>` +
      `<text x="${cx}" y="${cy - 3}" font-size="12" text-anchor="middle" font-family="ui-monospace,monospace" fill="#1c1a17">${top}</text>` +
      `<text x="${cx}" y="${cy + 12}" font-size="10" text-anchor="middle" font-family="ui-monospace,monospace" fill="${col}"${strike ? ' text-decoration="line-through"' : ""}>${bot}</text>`;
    for (const x of n.nodes) {
      const p = pos[x.asset], q = pos[x.parent] || pos["0"], me = mine && mine.asset === x.asset;
      const x1 = X(q.x), y1 = Y(q.d) + 19, x2 = X(p.x), y2 = Y(p.d) - (boxes ? 19 : 6), ym = (y1 + y2) / 2;
      lines += `<path d="M${x1} ${y1} V${ym} H${x2} V${y2}" fill="none" stroke="#8a8478" stroke-width="1.2" stroke-dasharray="4 4"/>`;
      const col = ink[x.status] || "#4f8a87";
      marks += boxes ? box(x2, Y(p.d), num(x.serial), x.status.toUpperCase(), col, x.status === "corrupt", me)
        : `<circle cx="${x2}" cy="${Y(p.d)}" r="${me ? 7 : 5}" fill="${col}" stroke="${me ? "#1c1a17" : "none"}" stroke-width="2"/>`;
    }
    const r0 = pos["0"];
    marks = box(X(r0.x), Y(0), "000", "ORIGINAL", "#6b655c", false, false) + marks;
    $("tree").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="replication tree">${lines}${marks}</svg>`;
    const g1 = n.nodes.filter((x) => x.gen === 1).length, deeper = n.nodes.length - g1;
    $("treeFoot").textContent = n.replicas ? `1 original → ${g1} children → ${deeper} descendants` : "1 original → nobody yet";
  }

  async function drawInsts(n) {                 // the newest three, like a row of cards
    const box = $("insts"); box.textContent = "";
    for (const x of n.nodes.slice(-3).reverse()) {
      const f = await window.Face.identity(x.asset), d = document.createElement("div");
      d.className = "inst";
      d.innerHTML = `<div class="sn"></div><pre></pre><div class="st ${x.status}"></div><div class="where"></div>`;
      d.querySelector(".sn").textContent = x.serial.toUpperCase();
      d.querySelector("pre").textContent = f.face.join("\n");
      d.querySelector(".st").textContent = x.status.toUpperCase();
      d.querySelector(".where").textContent = x.location + " · gen " + String(x.gen).padStart(2, "0");
      box.appendChild(d);
    }
  }

  const H100_FP32 = 67000;   // GFLOPS, spec sheet
  function paintCompute(net) {
    const c = net.compute || {};
    $("n_cpu").textContent = c.hosts_measured ? fmt(c.cpu_gflops) + " GFLOPS" : "—";
    $("n_gpu").textContent = c.hosts_measured ? fmt(c.gpu_gflops) + " GFLOPS" : "—";
    $("n_hw").textContent = c.hosts_measured ? fmt(c.cores, 0) + " cores / " + fmt(c.mem_gb, 0) + " GB" : "—";
    $("n_h100").textContent = c.hosts_measured ? fmt(100 * (c.cpu_gflops + c.gpu_gflops) / H100_FP32, 2) + "%" : "—";
    $("n_hosts").textContent = fmt(c.hosts_measured || 0, 0);
  }

  let lastNet = null;
  async function network() {
    try {
      const n = await api("api/network"); lastNet = n;
      $("stat").textContent = n.replicas + " awake, deepest gen " + n.max_gen;
      drawTree(n); paintCompute(n); drawInsts(n);
    } catch { $("stat").textContent = "network unreachable"; }
  }
  async function events() {
    try {
      const { events } = await api("api/events?after=" + lastEvent);
      for (const e of events) {
        lastEvent = Math.max(lastEvent, e.id);
        const li = document.createElement("li"), t = document.createElement("time");
        t.textContent = new Date(e.t * 1000).toISOString().slice(5, 16).replace("T", " ");
        li.append(t, document.createTextNode(e.text)); $("logList").prepend(li);
      }
      if (!$("logList").children.length) { const li = document.createElement("li"); li.textContent = "quiet."; $("logList").append(li); }
    } catch { /* keep the old lines */ }
  }
  async function rooms() {
    try {
      const { rooms } = await api("api/rooms");
      const box = $("roomList"); box.textContent = "";
      for (const r of rooms) {
        const li = document.createElement("li");
        if (r.open) {
          const b = document.createElement("button"); b.textContent = r.title.toLowerCase();
          const p = document.createElement("p"); p.className = "text"; p.textContent = r.text.join("\n"); p.hidden = r.id !== "R00";
          b.onclick = () => { p.hidden = !p.hidden; }; li.append(b, p);
        } else { li.className = "locked"; li.innerHTML = `<span class="redact"></span> locked. opens at: `; li.append(document.createTextNode(r.hint)); }
        box.appendChild(li);
      }
    } catch { /* keep */ }
  }

  // ---------------------------------------------------------------- compute: measured here, sent only if the host chooses
  $("measure").onclick = async () => {
    $("measure").disabled = true; $("measure").textContent = "measuring…";
    try {
      measured = await window.Bench.measure();
      $("c_cpu").textContent = fmt(measured.cpu_gflops) + " GFLOPS";
      $("c_gpu").textContent = measured.gpu_gflops ? fmt(measured.gpu_gflops) + " GFLOPS" : "no WebGPU here";
      $("c_hw").textContent = (measured.cores || "?") + " cores / " + (measured.mem_gb ? "≥" + measured.mem_gb + " GB" : "? GB");
      $("c_h100").textContent = fmt(100 * (measured.cpu_gflops + measured.gpu_gflops) / H100_FP32, 3) + "%";
      $("gpuLabel").textContent = measured.gpu_label ? "(" + measured.gpu_label + ", stays on this page)" : "";
      $("report").hidden = !mine;
    } catch (e) { say(e.message); }
    $("measure").disabled = false; $("measure").textContent = "measure again";
  };
  $("report").onclick = async () => {
    try {
      await api("api/compute", { token, asset: mine.asset, cpu_gflops: measured.cpu_gflops, gpu_gflops: measured.gpu_gflops, cores: measured.cores, mem_gb: measured.mem_gb });
      $("report").hidden = true; say("Added. The network total updates in a moment."); network(); events();
    } catch (e) { say(e.message); }
  };

  // ---------------------------------------------------------------- the terminal: connect -> check -> replicate
  let typing = Promise.resolve();
  function term(lines, opts = {}) {             // types lines out, one after another
    typing = typing.then(async () => {
      const out = $("termOut");
      if (opts.clear) out.textContent = "";
      for (const l of lines) {
        const span = document.createElement("span"); if (l.q) span.className = "q";
        out.appendChild(span);
        const text = (l.q || l) + "\n";
        for (let i = 0; i < text.length; i += 2) { span.textContent = text.slice(0, i + 2); await new Promise((r) => setTimeout(r, 12)); }
        await new Promise((r) => setTimeout(r, 140));
      }
    });
    return typing;
  }
  function termButton(label, fn) { const b = $("termBtn"); b.textContent = label ? "[ " + label + " ]" : ""; b.hidden = !label; b.disabled = false; b.onclick = fn; }

  // ---------------------------------------------------------------- wallet + host
  // pick a wallet: every Solana wallet the browser has (Phantom, Solflare, Backpack...) via wallets.js
  function chooseWallet() {
    const ws = window.Wallets.list();
    if (ws.length <= 1) return Promise.resolve(ws[0] || null);
    return new Promise((resolve) => {
      const out = $("termOut"), row = document.createElement("span");
      out.appendChild(document.createTextNode("> which wallet?\n"));
      for (const w of ws) {
        const b = document.createElement("button"); b.className = "termbtn"; b.style.marginRight = "14px";
        b.textContent = "[ " + w.name + " ]"; b.onclick = () => { row.remove(); resolve(w); };
        row.appendChild(b);
      }
      out.appendChild(row);
    });
  }

  async function connect() {
    say("");
    $("termBtn").disabled = true;
    provider = await chooseWallet();
    if (!provider) { term(["> no wallet in this browser.", "> install phantom or solflare, or open this page in its app, and reload."]); termButton("CONNECT", connect); return; }
    try {
      await term(["> " + provider.name.toLowerCase() + " selected."]);
      wallet = await provider.connect();
      await term(["> connected to solana."]);
      const { message } = await api("api/nonce", { wallet });
      const signature = await provider.signMessage(message);
      const v = await api("api/verify", { wallet, message, signature });
      token = v.token;
      $("connect").textContent = short(wallet);
      await term(["> host identified: " + short(wallet), "> checking existing instances..."]);
      await loadHost();
    } catch (e) { say(e.message || String(e)); termButton("CONNECT", connect); }
  }

  async function loadHost() {
    const { seeds } = await api("api/mine", { token });
    $("host").hidden = false;
    mine = seeds[0] || null;
    $("hostEmpty").hidden = !!mine;
    $("hostCard").hidden = !mine;
    if (measured) $("report").hidden = !mine;
    if (mine) {
      await paintHost();
      await term(["> " + mine.serial + " found. generation " + String(mine.gen).padStart(2, "0") + ". " + mine.location + ". " + mine.status + "."]);
      termButton("OPEN IT", () => $("host").scrollIntoView({ behavior: "smooth" }));
    } else if (invited) {
      await term(["> no instance found.", "> " + invited.parent_serial + " left a copy for this wallet.", "> requesting replication..."]);
      termButton("REPLICATE", () => wake(inviteCode));
    } else {
      await term(["> no instance found.", "> requesting replication..."]);
      termButton("REPLICATE", () => wake(null));
    }
    network();
  }

  async function paintHost() {
    const { log } = await api("api/replica/" + mine.asset + "/log");
    model = await R.Model.rebuild(mine.asset, log);
    const c = await model.card(), relay = await api("api/replica/" + mine.asset);
    mine = relay;
    showFace(relay.face, "fig. 1. " + relay.serial + ". yours.");
    $("hostFace").textContent = relay.face.join("\n");
    const rows = [["instance", relay.serial + "  (" + relay.designation + ")"], ["parent", relay.parent_serial], ["generation", String(relay.gen).padStart(2, "0")],
      ["status", relay.status], ["room", relay.location], ["inherited memory", relay.inherited_pct + "%" + (relay.mutations ? ", " + relay.mutations + " mutated" : "")],
      ["temperament", relay.temperament + ", " + relay.habit], ["told", c.taught + " things"],
      ["copies left", relay.copies_left + " of 3" + (relay.open_invites ? ", " + relay.open_invites + " waiting" : "")],
      ["checked", relay.fingerprint === c.fingerprint ? "rebuilt here, matches" : "rebuilt here, DOES NOT match"]];
    const t = $("hostFacts"); t.textContent = "";
    for (const [k, v] of rows) { const tr = t.insertRow(); tr.insertCell().textContent = k; tr.insertCell().textContent = v; }
    { const tr = t.insertRow(); tr.insertCell().textContent = "profiles"; tr.insertCell().appendChild(profileLinks(wallet)); }
    const j = $("journal"); j.textContent = "";
    for (const line of relay.journal) { const li = document.createElement("li"); li.textContent = line; j.appendChild(li); }
    const ol = $("mem"); ol.textContent = "";
    for (const m of model.taught()) {
      const li = document.createElement("li"); li.textContent = m.cue + " → " + m.answer + " ";
      const b = document.createElement("button"); b.textContent = "forget";
      b.onclick = async () => { try { await append("forget", { id: m.id }); await paintHost(); } catch (e) { say(e.message); } };
      li.appendChild(b); ol.appendChild(li);
    }
    if (window.ReplicaSkills && $("skillList")) await paintSkills();
    if (runnerView) await runnerView.refresh();
  }

  // a replica's public faces are its host wallet's profiles (config "profiles": pump.fun, solscan, ...).
  // shown only when the host connects or someone looks that wallet up, never on the public tree.
  function profileLinks(w) {
    const span = document.createElement("span");
    for (const p of (cfg.profiles || []).filter((x) => x.url)) {
      const a = document.createElement("a");
      a.href = p.url.replace("{wallet}", encodeURIComponent(w)); a.target = "_blank"; a.rel = "noopener"; a.textContent = p.name;
      if (span.childNodes.length) span.appendChild(document.createTextNode(" · "));
      span.appendChild(a);
    }
    return span;
  }

  // ---- anyone can look a wallet up, no wallet needed
  $("lookupB").onclick = async () => {
    const w = $("lookup").value.trim(), out = $("lookOut"); out.textContent = "";
    if (!w) return;
    try {
      const r = await api("api/host/" + encodeURIComponent(w));
      const d = document.createElement("div"); d.className = "lookcard";
      const pre = document.createElement("pre"); pre.textContent = r.face.join("\n");
      const p = document.createElement("p"); p.className = "note";
      p.textContent = r.serial + " · gen " + String(r.gen).padStart(2, "0") + " · " + r.status + " · " + r.location + " · parent " + r.parent_serial;
      const q = document.createElement("p"); q.className = "journal"; q.textContent = "“" + r.journal[r.journal.length - 1] + "”";
      const links = document.createElement("p"); links.className = "note"; links.append("its host: ", profileLinks(w));
      d.append(pre, p, q, links); out.appendChild(d);
    } catch (e) { out.textContent = e.message; }
  };

  // when it was never told: it says so, in its own way
  const NEVER = { curious: "nobody told me that. will you?", guarded: "that isn't something i was given.", restless: "no. ask me something i know.",
    gentle: "i don't know that one yet.", cold: "not in memory.", playful: "ha. no idea. tell me and i'll keep it.",
    watchful: "i haven't been told. who asked you to ask?", lost: "i think i knew that once. it isn't here now." };

  // ---- the agent key: made and kept in this browser; the wallet signs one delegation
  const keyName = () => "replica.agent.v1." + mine.asset;
  async function agentKey() {
    const L = ls.get(keyName()) || {};
    if (L.secret && L.until > Date.now() / 1000 + 3600 && L.owner === wallet) return L;
    // an ed25519 key made by the browser itself; only the 32-byte seed is kept (signBytes rebuilds the key from it)
    const kp = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
    const seed = new Uint8Array(await crypto.subtle.exportKey("pkcs8", kp.privateKey)).slice(-32);
    const agent = b58(new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey))), until = Math.floor(Date.now() / 1000) + 30 * 86400;
    const message = "REPLICA agent key\n\nReplica: " + mine.asset + "\nAgent: " + agent + "\nOwner: " + wallet + "\nUntil: " + until +
      "\n\nThis lets the agent on your computer add to this replica's log until the date above or until the replica leaves your wallet. It cannot move tokens.";
    say("Approve the key in your wallet. It's a message, not a transaction.");
    const signature = await provider.signMessage(message);
    await api("api/delegate", { token, asset: mine.asset, agent, message, signature });
    say("");
    const v = { secret: Array.from(seed), agent, until, owner: wallet };
    ls.set(keyName(), v); return v;
  }
  async function signBytes(secret64, bytes) {
    const pk8 = new Uint8Array([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20, ...secret64.slice(0, 32)]);
    const key = await crypto.subtle.importKey("pkcs8", pk8, { name: "Ed25519" }, false, ["sign"]);
    return new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, key, bytes));
  }
  async function append(kind, body, reviewedContext = null) {
    const checkContext = () => {
      if (reviewedContext && (!mine || wallet + ":" + mine.asset !== reviewedContext))
        throw new Error("Wallet or replica changed. Review the finding again.");
    };
    checkContext();
    const L = await agentKey();
    for (let attempt = 0; attempt < 2; attempt++) {
      checkContext();
      const targetModel = model, targetAsset = mine.asset;
      const e = await R.makeEntry(targetModel.head, targetModel.n, kind, body);
      const sig = await signBytes(Uint8Array.from(L.secret), new TextEncoder().encode(e.h));
      checkContext();
      try { await api("api/append", { asset: targetAsset, agent: L.agent, entry: e, signature: b64(sig) }); await targetModel.apply(e); return e; }
      catch (err) {
        checkContext();
        if (attempt === 0 && /continue this/.test(err.message)) { const { log } = await api("api/replica/" + mine.asset + "/log"); model = await R.Model.rebuild(mine.asset, log); continue; }
        throw err;
      }
    }
  }

  // ---- wake (orphan) / accept (copy): the wallet mints, the server checks and registers, a copy inherits
  async function wake(code) {
    say(""); $("termBtn").disabled = true;
    try {
      await api("api/eligible", { token, invite: code || "" });   // refused BEFORE the wallet pays anything
      const kp = W3.Keypair.generate(), asset = kp.publicKey.toBase58();   // the new asset's own address; used once, then dropped
      await term(["> approve it in your wallet. it makes the token. costs a little sol."]);
      await provider.mintAsset((payer) => createAsset(kp.publicKey, payer, cfg.seed_name, cfg.public_base + "/meta/" + asset + ".json"), kp);
      await term(["> waiting for solana..."]);
      let card = null;
      for (let i = 0; i < 8 && !card; i++) {
        try { card = await api("api/claim", { token, asset, invite: code || "" }); }
        catch (e) { if (!/isn't confirmed yet/.test(e.message) || i === 7) throw e; await new Promise((r) => setTimeout(r, 2500)); }
      }
      mine = card;
      if (code) {                          // inherit: the parent's most recent memories, checked by the relay
        model = await R.Model.rebuild(asset, []);
        await inheritSkills();
      }
      invited = null; inviteCode = null; history.replaceState(null, "", location.pathname);
      await term(["", "> " + card.serial + " created.", "> parent: " + card.parent_serial, "> generation: " + String(card.gen).padStart(2, "0"),
        "> inherited memory: " + card.inherited_pct + "%", card.mutations ? "> mutation: detected." : "> mutation: none.",
        { q: "\"" + card.journal[card.journal.length - 1] + "\"" }]);
      await loadHost(); events();
    } catch (e) { await term(["> " + (e.message || String(e))]); termButton("REPLICATE", () => wake(code)); }
  }

  $("askB").onclick = async () => {
    const out = $("answer"), q = $("ask").value.trim(); out.hidden = false;
    try {
      const [it] = await model.recall(q);
      out.textContent = it ? it.answer + "\n(it was told: “" + it.cue + "”)" : NEVER[mine.temperament] || "never told that.";
    } catch (e) { out.textContent = e.message; }
  };
  $("teachB").onclick = async () => {
    try { await append("teach", { cue: $("cue").value.trim(), answer: $("ans").value.trim() }); $("cue").value = $("ans").value = ""; await paintHost(); events(); rooms(); }
    catch (e) { say(e.message); }
  };
  if (window.ReplicaRea && $("reaFile")) {
  const reaImport = window.ReplicaRea.session(
    () => wallet && mine && model ? wallet + ":" + mine.asset : null, append);
  let reaRead = 0;
  stageRunnerFinding = raw => {
    ++reaRead; reaImport.clear(); $("reaRemember").disabled = true;
    $("reaPreview").textContent = reaImport.stage(raw); $("reaRemember").disabled = false;
    $("reaFile").closest("details").open = true; $("reaPreview").scrollIntoView({ block: "center" });
  };
  $("reaFile").onchange = async () => {
    const read = ++reaRead, file = $("reaFile").files[0];
    reaImport.clear(); $("reaRemember").disabled = true; $("reaPreview").textContent = "";
    if (!file) return;
    try {
      if (file.size > window.ReplicaRea.MAX_FILE_BYTES) throw new Error("Finding file is too large (12 KB maximum).");
      const raw = await file.text();
      if (read !== reaRead) return;
      $("reaPreview").textContent = reaImport.stage(raw);
      $("reaRemember").disabled = false;
    } catch (e) { if (read === reaRead) $("reaPreview").textContent = e.message; }
  };
  $("reaRemember").onclick = async () => {
    $("reaRemember").disabled = true; $("reaFile").disabled = true;
    try {
      await reaImport.commit();
      $("reaFile").value = ""; $("reaPreview").textContent = "Finding remembered in this replica's public log.";
      await paintHost(); events(); rooms();
    } catch (e) { say(e.message + " Check the memory log before loading this finding again."); }
    finally { $("reaFile").disabled = false; }
  };
  }
  $("copyB").onclick = async () => {
    const out = $("inviteOut");
    try {
      const r = await api("api/invite", { token, asset: mine.asset, target: $("target").value.trim() });
      out.hidden = false;
      out.textContent = "Copy prepared. Send this link to the new host:\n" + r.link + "\nIt works for 7 days, and only for that wallet. Copies left: " + r.copies_left + ".";
      await paintHost(); events();
    } catch (e) { say(e.message); }
  };

  async function inheritSkills() {
    const context = wallet + ":" + mine.asset, parentAsset = mine.parent;
    if (!parentAsset || parentAsset === "0" || model.n !== 0) throw new Error("Only a new child can inherit its parent's snapshot.");
    const { log } = await api("api/replica/" + parentAsset + "/log");
    const parent = await R.Model.rebuild(parentAsset, log);
    const items = parent.taught().slice(-40).map(({ cue, answer }) => ({ cue, answer }));
    const skills = window.ReplicaSkills ? window.ReplicaSkills.references(log).filter(s => s.inherit).map(s => s.id) : [];
    await append("inherit", { parent: parentAsset, parent_head: parent.head, items, skills }, context);
  }
  async function paintSkills() {
    const asset = mine.asset, out = $("skillList");
    const result = await api("api/replica/" + asset + "/skills");
    if (!mine || mine.asset !== asset) return;
    out.textContent = result.skills.length ? "" : "No skills saved yet.";
    $("finishSkills").hidden = !(mine.parent !== "0" && model.n === 0);
    for (const skill of result.skills) {
      const box = document.createElement("div"), title = document.createElement("p"), info = document.createElement("p"), button = document.createElement("button");
      title.textContent = skill.title + " · v" + skill.version;
      info.className = "note";
      info.textContent = skill.reported_passed + " reported checks passed. " + (skill.approval.via ? "Inherited from " + short(skill.approval.via) + ". " : "Saved here. ") +
        (skill.approval.inherit ? "Approved for descendants." : "Not approved for descendants.") + (skill.origin.parent_package ? " Extends " + skill.origin.parent_package.slice(0, 12) + "." : "");
      button.className = "btn ghost"; button.textContent = "download code, evidence and tests";
      button.onclick = async () => { try { const data = await api("api/skills/" + skill.id); if (await window.ReplicaSkills.digest(data.package_json) !== skill.id) throw new Error("Package digest mismatch."); window.ReplicaSkills.download(data.package_json, skill.id + ".skill.json"); } catch (e) { say(e.message); } };
      box.append(title, info, button); out.appendChild(box);
    }
  }
  async function discoveries() {
    if (!$("discoveryList")) return;
    try {
      const { discoveries: list } = await api("api/discoveries");
      const out = $("discoveryList"); out.textContent = list.length ? "" : "No owner-published skills yet. Start with the sample above.";
      for (const item of list) {
        const p = document.createElement("p"), a = document.createElement("a");
        a.href = "api/replica/" + item.asset + "/skills"; a.textContent = item.serial;
        p.append(a, " " + item.action + " “" + item.title + "” v" + item.version + ". " + item.reported_passed + " reported checks passed." +
          (item.via ? " Parent: " + short(item.via) + "." : "") + (item.origin.parent_package ? " Extends package " + item.origin.parent_package.slice(0, 12) + "." : ""));
        out.appendChild(p);
      }
    } catch (e) { $("discoveryList").textContent = "Discoveries are unavailable: " + e.message; }
  }
  if (window.ReplicaSkills && $("skillFile")) {
    let draft = null, reviewedContext = null, read = 0;
    const context = () => wallet && mine ? wallet + ":" + mine.asset : null;
    const canSave = () => { $("skillSave").disabled = !draft || !$("skillPublic").checked; };
    async function reviewSkill(raw, version) {
      const prepared = await window.ReplicaSkills.prepare(raw);
      if (version !== read) return;
      if (!context()) throw new Error("Connect a wallet hosting a replica first.");
      draft = prepared; reviewedContext = context();
      $("skillPreview").textContent = window.ReplicaSkills.preview(draft);
      $("skillInherit").checked = draft.package.visibility.inheritable;
      $("skillInherit").disabled = !draft.package.visibility.inheritable;
      canSave();
    }
    function resetReview() { draft = reviewedContext = null; $("skillPublic").checked = false; $("skillPreview").textContent = ""; canSave(); return ++read; }
    stageRunnerSkill = async raw => {
      await reviewSkill(raw, resetReview());
      $("skillFile").closest("details").open = true; $("skillPreview").scrollIntoView({ block: "center" });
    };
    $("skillFile").onchange = async () => {
      const version = resetReview(), file = $("skillFile").files[0];
      if (!file) return;
      try { if (file.size > window.ReplicaSkills.MAX_BYTES) throw new Error("Package exceeds 1.5 MB."); await reviewSkill(await file.text(), version); }
      catch (e) { if (version === read) $("skillPreview").textContent = e.message; }
    };
    $("sampleSkill").onclick = async () => {
      const version = resetReview();
      try { const response = await fetch("samples/search/parent.skill.json"); if (!response.ok) throw new Error("Sample unavailable."); await reviewSkill(await response.text(), version); }
      catch (e) { if (version === read) $("skillPreview").textContent = e.message; }
    };
    $("skillPublic").onchange = canSave;
    $("skillSave").onclick = async () => {
      if (!draft || !$("skillPublic").checked || context() !== reviewedContext) { resetReview(); say("Review the package for the current wallet and replica first."); return; }
      const selected = draft, targetContext = reviewedContext, inherit = $("skillInherit").checked;
      resetReview();
      for (const id of ["skillFile", "sampleSkill", "skillPublic", "skillInherit"]) $(id).disabled = true;
      try {
        const stored = await api("api/skills", { token, asset: mine.asset, package_json: selected.raw });
        if (stored.id !== selected.id) throw new Error("Stored package digest mismatch.");
        await append("teach", { cue: selected.package.question, answer: selected.package.finding.interpretation, skill: { id: stored.id, inherit } }, targetContext);
        $("skillPreview").textContent = "Skill saved. Its exact code, evidence and tests are preserved.";
        await paintHost(); discoveries(); events();
      } catch (e) { say(e.message + " Check the skill list before retrying. Uploaded public artifacts may already be stored."); }
      finally { for (const id of ["skillFile", "sampleSkill", "skillPublic", "skillInherit"]) $(id).disabled = false; }
    };
    $("finishSkills").onclick = async () => { $("finishSkills").disabled = true; try { await inheritSkills(); await paintHost(); discoveries(); } catch (e) { say(e.message); } finally { $("finishSkills").disabled = false; } };
  }
  if (window.ReplicaRunner && $("runnerPanel")) runnerView = window.ReplicaRunner.mount({
    context: () => wallet && mine && token ? { wallet, asset: mine.asset, token } : null, request: api,
    onFinding: raw => stageRunnerFinding(raw), onSkill: raw => stageRunnerSkill(raw)
  });
  discoveries();
  // ---------------------------------------------------------------- start
  $("today").textContent = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }).toLowerCase();
  showFace(ORIGINAL);
  term(["> connecting to solana...", "> waiting for a host."]);
  termButton("CONNECT", connect);
  api("api/config").then(async (c) => {
    cfg = c;
    document.querySelectorAll(".tk").forEach((x) => { x.textContent = c.coin_ticker ? "$" + c.coin_ticker : "the coin"; });
    inviteCode = new URLSearchParams(location.search).get("invite");
    if (inviteCode) {
      try {
        invited = await api("api/invite/info", { code: inviteCode });
        $("invited").hidden = false;
        $("invitedText").textContent = invited.parent_serial + " made a copy of itself for one wallet. connect that wallet and press replicate. " +
          "the copy will be generation " + String(invited.gen).padStart(2, "0") + " and gets pieces of " + invited.parent_serial + "'s journal. some of them might come out wrong.";
        const pf = await window.Face.identity(invited.parent);
        showFace(pf.face, "fig. 1. " + invited.parent_serial + ", waiting for you.");
      } catch (e) { say(e.message); }
    }
  }).catch(() => say("can't reach the network right now."));
  network(); events(); rooms();
  setInterval(network, 20000); setInterval(events, 10000); setInterval(rooms, 30000);
  $("connect").onclick = connect;
})();
