/* replica.js - the replica model, run on the OWNER'S machine (browser or node). Port of replica_model.py.
   model = f(asset address, hash-chained log). osub_seed is reproduced exactly: sha256 -> numpy legacy MT19937 ->
   uniform(0, 2pi) phases, so a log rebuilds to the same head, fingerprint and answers in Python and here.
   Works in browsers (window.Replica) and node (module.exports). Async because sha256 comes from WebCrypto. */
(function (root) {
  "use strict";
  const VERSION = "replica-1", D = 2048, CUE_BAR = 0.55, MAX_ITEMS = 500, MAX_TEXT = 600, MAX_INHERIT = 40;
  const STOP = new Set(("a an the is are was were be of to in on at for and or what who whom which when where why how do does did " +
    "i you me my your it its this that these those please tell").split(" "));
  const ADJ = ["Amber", "Quiet", "Iron", "Salt", "Cedar", "Lantern", "North", "Slate", "Ember", "Hollow", "Tidal", "Copper",
    "Willow", "Signal", "Granite", "Morrow"];
  const NOUN = ["Heron", "Kestrel", "Loom", "Harbor", "Orchard", "Compass", "Fern", "Anvil", "Beacon", "Delta", "Lark",
    "Meridian", "Thicket", "Quarry", "Spindle", "Owl"];
  const subtle = (typeof crypto !== "undefined" && crypto.subtle) || require("crypto").webcrypto.subtle;
  const enc = new TextEncoder();

  async function sha256hex(s) {
    const b = new Uint8Array(await subtle.digest("SHA-256", typeof s === "string" ? enc.encode(s) : s));
    return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  }

  // ---- numpy.random.RandomState(seed).uniform(0, 2pi, n): MT19937 init_genrand + legacy 53-bit doubles
  function mtUniformPhases(seed, n) {
    const mt = new Uint32Array(624);
    mt[0] = seed >>> 0;
    for (let i = 1; i < 624; i++) {
      const p = mt[i - 1] ^ (mt[i - 1] >>> 30);
      mt[i] = (Math.imul(1812433253, p) + i) >>> 0;
    }
    let idx = 624;
    const next = () => {
      if (idx >= 624) {
        for (let k = 0; k < 624; k++) {
          const y = (mt[k] & 0x80000000) | (mt[(k + 1) % 624] & 0x7fffffff);
          mt[k] = mt[(k + 397) % 624] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
        }
        idx = 0;
      }
      let y = mt[idx++];
      y ^= y >>> 11; y ^= (y << 7) & 0x9d2c5680; y ^= (y << 15) & 0xefc60000; y ^= y >>> 18;
      return y >>> 0;
    };
    const out = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const a = next() >>> 5, b = next() >>> 6;
      out[i] = 2 * Math.PI * ((a * 67108864 + b) / 9007199254740992);
    }
    return out;
  }

  async function osubSeed(text) {   // -> {re, im} unit phasors (Float64Array x2)
    const h = await sha256hex(text.toLowerCase().trim());
    const seed = Number(BigInt("0x" + h) % 2147483648n);
    const th = mtUniformPhases(seed, D);
    const re = new Float64Array(D), im = new Float64Array(D);
    for (let i = 0; i < D; i++) { re[i] = Math.cos(th[i]); im[i] = Math.sin(th[i]); }
    return { re, im };
  }

  const tokens = (text) => (text.toLowerCase().match(/[a-z0-9]+/g) || []).filter((t) => !STOP.has(t));

  // canonical JSON == python json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)
  function canon(v) {
    if (v === null || typeof v !== "object") {
      if (typeof v === "number" && !Number.isInteger(v)) return pyFloat(v);
      return JSON.stringify(v);
    }
    if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
    return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
  }
  function pyFloat(x) {   // python repr(float): same shortest digits as JS, but scientific when exp < -4 or >= 16
    if (!isFinite(x)) throw new ChainError("numbers in the log must be finite");
    const [m, e] = x.toExponential().split("e"), E = parseInt(e, 10);
    if (E < -4 || E >= 16) return m + "e" + (E < 0 ? "-" : "+") + String(Math.abs(E)).padStart(2, "0");
    const s = String(x);
    return /[.e]/.test(s) ? s : s + ".0";
  }

  const genesis = (asset) => sha256hex(VERSION + ":genesis:" + asset);
  const entryHash = (e) => sha256hex(canon({ n: e.n, t: e.t, kind: e.kind, body: e.body, prev: e.prev }));
  async function makeEntry(prev, n, kind, body, t) {
    const e = { n, t: Math.floor(t === undefined ? Date.now() / 1000 : t), kind, body, prev };
    e.h = await entryHash(e);
    return e;
  }

  class ChainError extends Error {}

  class Model {
    constructor(asset) { this.asset = asset; this.items = new Map(); this.n = 0; this.head = null; this.state = {}; }
    static async create(asset) {
      const m = new Model(asset);
      m.head = await genesis(asset);
      const h = new Uint8Array(await subtle.digest("SHA-256", enc.encode(asset)));
      m.name = ADJ[h[0] % 16] + " " + NOUN[h[1] % 16];
      return m;
    }
    static async rebuild(asset, log) { const m = await Model.create(asset); for (const e of log) await m.apply(e); return m; }
    k(s) { return osubSeed(VERSION + ":" + this.asset + ":" + s); }
    async cueVec(text) {
      const ts = tokens(text);
      if (!ts.length) return null;
      const re = new Float64Array(D), im = new Float64Array(D);
      for (const t of ts) { const v = await this.k("tok:" + t); for (let i = 0; i < D; i++) { re[i] += v.re[i]; im[i] += v.im[i]; } }
      for (let i = 0; i < D; i++) { const a = Math.max(Math.hypot(re[i], im[i]), 1e-8 * ts.length); re[i] /= a; im[i] /= a; }
      return { re, im };
    }
    async apply(e) {
      if (e.prev !== this.head || e.n !== this.n || (await entryHash(e)) !== e.h) throw new ChainError("entry " + e.n + " does not continue this replica's chain");
      const b = e.body || {};
      if (e.kind === "teach" || e.kind === "inherit") {
        let pairs, ids;
        if (e.kind === "inherit") {   // a child's FIRST entry: a snapshot of its parent's memories
          if (e.n !== 0 || !Array.isArray(b.items) || b.items.length > MAX_INHERIT) throw new ChainError("inherit must be the first entry, with at most " + MAX_INHERIT + " memories");
          pairs = b.items.map((x) => [String(x.cue || ""), String(x.answer || "")]);
          ids = pairs.map((_, i) => e.h.slice(0, 12) + String(i).padStart(4, "0"));
        } else { pairs = [[String(b.cue || ""), String(b.answer || "")]]; ids = [e.h.slice(0, 16)]; }
        for (let i = 0; i < pairs.length; i++) {
          const cue = pairs[i][0].slice(0, MAX_TEXT), ans = pairs[i][1].slice(0, MAX_TEXT);
          const K = await this.cueVec(cue);
          if (!K || !ans.trim()) throw new ChainError("entry " + e.n + " teaches nothing");
          if (this.items.size >= MAX_ITEMS) throw new ChainError("this replica is full");
          this.items.set(ids[i], { id: ids[i], cue, answer: ans, K, t: e.t });
        }
        if (e.kind === "inherit") this.state.inherit = { parent: String(b.parent || ""), parent_head: String(b.parent_head || ""), count: pairs.length };
      } else if (e.kind === "forget") {
        if (!this.items.delete(String(b.id || ""))) throw new ChainError("entry " + e.n + " forgets an unknown item");
      } else if (e.kind === "agent" || e.kind === "learn" || e.kind === "fill") {
        // agent settings / strategy learning snapshots / trade fills: the latest of each kind is the live state
        if (e.kind === "fill") (this.state.fills = this.state.fills || []).push(b); else this.state[e.kind] = b;
      } else throw new ChainError("unknown entry kind " + e.kind);
      this.head = e.h; this.n += 1;
    }
    async recall(question) {
      const q = await this.cueVec(question);
      if (!q || !this.items.size) return [null, 0];
      let best = -1, arg = null;
      for (const it of this.items.values()) {
        let r = 0; for (let i = 0; i < D; i++) r += it.K.re[i] * q.re[i] + it.K.im[i] * q.im[i];
        r /= D; if (r > best) { best = r; arg = it; }
      }
      return best < CUE_BAR ? [null, best] : [arg, best];
    }
    async fingerprint() { return sha256hex(canon({ asset: this.asset, head: this.head, n: this.n, v: VERSION })); }
    async card() {
      return { asset: this.asset, name: this.name, version: VERSION, entries: this.n, taught: this.items.size,
        head: this.head, fingerprint: await this.fingerprint() };
    }
    taught() { return [...this.items.values()].sort((a, b) => a.t - b.t).map(({ id, cue, answer, t }) => ({ id, cue, answer, t })); }
  }

  const api = { VERSION, D, CUE_BAR, MAX_TEXT, Model, ChainError, makeEntry, entryHash, genesis, canon, tokens, osubSeed, sha256hex };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Replica = api;
})(typeof window !== "undefined" ? window : globalThis);
