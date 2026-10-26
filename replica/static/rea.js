/* REA findings are untrusted data. Only a host-reviewed teach entry is imported. */
(function (root) {
  "use strict";
  const SCHEMA = "replica-rea-finding-v1", MAX_FILE_BYTES = 12000;
  function text(value, name, max) {
    if (typeof value !== "string" || !value.trim() || value.length > max || /[\u0000-\u0008\u000b-\u001f\u007f]/.test(value))
      throw new Error(name + " must be nonempty text, at most " + max + " characters.");
    return value.trim();
  }
  function prepare(raw) {
    if (typeof raw !== "string" || new TextEncoder().encode(raw).length > MAX_FILE_BYTES)
      throw new Error("Finding file is too large (12 KB maximum).");
    const data = JSON.parse(raw);
    if (!data || data.schema !== SCHEMA) throw new Error("Unsupported REA finding format.");
    const source = data.source;
    if (!source || typeof source !== "object" || Array.isArray(source)) throw new Error("Missing evidence source.");
    const body = {
      cue: text(data.cue, "Question", 600), answer: text(data.answer, "Answer", 600),
      source: {
        provider: "rea", version: text(source.version, "REA version", 40),
        tool: text(source.tool, "Tool", 80), target: text(source.target, "Target", 160),
        evidence: text(source.evidence, "Evidence", 400), limitations: text(source.limitations, "Limitations", 300),
        host_reviewed: true
      }
    };
    if (!/^[a-z0-9_]+$/.test(body.source.tool)) throw new Error("Invalid REA tool name.");
    // Python's relay measures ensure_ascii JSON including spaces; leave room for the entry envelope.
    const ascii = JSON.stringify(body).replace(/[\u007f-\uffff]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
    if (ascii.length + 100 > 3000) throw new Error("Finding is too long for the signed memory log; shorten it.");
    return body;
  }
  function preview(body) {
    const s = body.source;
    return "Question: " + body.cue + "\nAnswer: " + body.answer + "\n\nREA: " + s.version +
      "\nTool: " + s.tool + "\nTarget: " + s.target + "\nEvidence: " + s.evidence + "\nLimitations: " + s.limitations;
  }
  // Dependency injection keeps the review gate testable without a wallet or network.
  function session(getContext, append) {
    let draft = null, context = null, busy = false;
    function clear() { draft = context = null; }
    return {
      clear,
      stage(raw) {
        if (busy) throw new Error("An import is already in progress.");
        clear();
        const current = getContext();
        if (!current) throw new Error("Connect the wallet hosting this replica first.");
        const body = prepare(raw);
        draft = body; context = current;
        return preview(body);
      },
      async commit() {
        if (busy) throw new Error("An import is already in progress.");
        if (!draft) throw new Error("Review a finding first.");
        if (getContext() !== context) { clear(); throw new Error("Wallet or replica changed. Review the finding again."); }
        busy = true;
        // Consume before signing: an ambiguous network failure requires reviewing the log before retrying.
        const body = draft, target = context; clear();
        try { return await append("teach", body, target); } finally { busy = false; }
      }
    };
  }
  const api = { SCHEMA, MAX_FILE_BYTES, prepare, preview, session };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ReplicaRea = api;
})(typeof window !== "undefined" ? window : globalThis);
