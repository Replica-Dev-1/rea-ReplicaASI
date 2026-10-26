/* Reviewed artifact packages only. Uploaded code is never evaluated in this page. */
(function (root) {
  "use strict";
  const MAX_BYTES = 1500000, HASH = /^[0-9a-f]{64}$/;
  const digest = async raw => Array.from(new Uint8Array(await ((root.crypto || require('crypto').webcrypto).subtle.digest('SHA-256', new TextEncoder().encode(raw)))), b => b.toString(16).padStart(2, '0')).join('');
  function references(log) {
    const refs = new Map();
    for (const entry of log) {
      const b = entry.body || {};
      if (entry.kind === 'teach' && b.skill && HASH.test(b.skill.id) && typeof b.skill.inherit === 'boolean')
        refs.set(b.skill.id, { id: b.skill.id, inherit: b.skill.inherit, memory: entry.h.slice(0, 16) });
      if (entry.kind === 'inherit') for (const id of (Array.isArray(b.skills) ? b.skills : []))
        if (HASH.test(id)) refs.set(id, { id, inherit: true, memory: null });
      if (entry.kind === 'forget') for (const [id, value] of refs) if (value.memory === b.id) refs.delete(id);
    }
    return [...refs.values()];
  }
  async function prepare(raw) {
    if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > MAX_BYTES) throw new Error('Package exceeds 1.5 MB.');
    const p = JSON.parse(raw);
    if (!p || p.schema !== 'replica-skill-v1' || typeof p.title !== 'string' || typeof p.question !== 'string' ||
        !p.finding || typeof p.finding.interpretation !== 'string' || p.question.length > 600 || p.finding.interpretation.length > 600)
      throw new Error('Unsupported or incomplete skill package.');
    if (!p.visibility || p.visibility.public !== true || typeof p.visibility.inheritable !== 'boolean') throw new Error('Only explicitly public packages can be saved here. Keep private work local.');
    if (!Array.isArray(p.files) || p.files.length > 32) throw new Error('Package must include its code, tests and evidence.');
    const paths = new Map();
    for (const f of p.files) {
      if (!f || typeof f.path !== 'string' || !/^[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*$/.test(f.path) || f.path.includes('..') || paths.has(f.path) || typeof f.content !== 'string') throw new Error('Invalid embedded file.');
      if (f.path.split('/').some(part => /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(part))) throw new Error('Reserved artifact filename.');
      if (await digest(f.content) !== f.sha256) throw new Error('File digest mismatch: ' + f.path);
      paths.set(f.path, f);
    }
    for (const role of ['implementation', 'tests', 'test-record', 'evidence'])
      if (!p.files.some(f => f.role === role)) throw new Error('Missing ' + role + ' file.');
    const recordFile = p.tests && paths.get(p.tests.record);
    if (!recordFile || recordFile.role !== 'test-record') throw new Error('Missing test record.');
    const record = JSON.parse(recordFile.content);
    if (!Array.isArray(record.cases) || !record.cases.length || record.cases.some(c => c.passed !== true)) throw new Error('Resolve failed checks before saving this skill.');
    return { id: await digest(raw), raw, package: p, passed: record.cases.length };
  }
  function preview(draft) {
    const p = draft.package;
    return p.title + ' · v' + p.version + '\n\nQuestion: ' + p.question + '\nTarget: ' + p.target.name + ' ' + p.target.version +
      '\nTarget SHA-256: ' + p.target.sha256 + '\n\nObserved:\n' + p.finding.observations.join('\n') +
      '\n\nInterpretation:\n' + p.finding.interpretation + '\n\nLimits:\n' + p.finding.limitations.join('\n') +
      '\n\nReported checks: ' + draft.passed + ' passed (author-supplied; the server does not run uploaded code)' +
      '\nRun locally: ' + p.tests.command + '\nRequirements: ' + p.requirements.join('; ') +
      '\nAuthor label: ' + p.origin.author + '\nExtends: ' + (p.origin.parent_package || 'original package') +
      '\n\nFiles:\n' + p.files.map(f => f.path + ' [' + f.role + '] ' + f.sha256).join('\n') + '\n\nPackage SHA-256: ' + draft.id;
  }
  function download(raw, name) {
    const url = URL.createObjectURL(new Blob([raw], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const api = { MAX_BYTES, digest, references, prepare, preview, download };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.ReplicaSkills = api;
})(typeof window !== 'undefined' ? window : globalThis);
