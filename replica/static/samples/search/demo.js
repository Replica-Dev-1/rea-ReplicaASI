(async () => {
  const $ = id => document.getElementById(id);
  try {
    const [notes, parentRaw, childRaw] = await Promise.all([fetch('fixtures.json').then(r => r.json()), fetch('parent.skill.json').then(r => r.text()), fetch('child.skill.json').then(r => r.text())]);
    const packages = { parent: await ReplicaSkills.prepare(parentRaw), child: await ReplicaSkills.prepare(childRaw) };
    function paint() {
      const child = $('version').value === 'child', draft = packages[child ? 'child' : 'parent'], p = draft.package;
      $('limit').disabled = !child;
      const results = (child ? ReplicaSearchChild : ReplicaSearch).search(notes, $('query').value, { tag: $('tag').value, archived: $('archived').checked, ...(child ? { limit: Math.max(0, Number($('limit').value)) } : {}) });
      $('results').textContent = '';
      if (!results.length) $('results').textContent = 'No matching notes.';
      for (const note of results) { const item = document.createElement('p'); item.textContent = note.title + ' — ' + note.body + ' [' + note.tags.join(', ') + ']'; $('results').appendChild(item); }
      $('counts').textContent = draft.passed + ' checks passed in the recorded Node run. Test code and exact inputs/outputs are included.';
      $('explanation').textContent = 'Observed:\n' + p.finding.observations.join('\n') + '\n\nInterpretation:\n' + p.finding.interpretation + '\n\nLimits:\n' + p.finding.limitations.join('\n');
      $('checks').textContent = p.files.find(f => f.path === p.tests.record).content;
      $('files').textContent = '';
      for (const f of p.files) { const d = document.createElement('details'), s = document.createElement('summary'), pre = document.createElement('pre'); s.textContent = f.path + ' · ' + f.role; pre.className = 'note rea-preview skill-preview'; pre.textContent = f.content; d.append(s, pre); $('files').appendChild(d); }
      $('download').onclick = () => ReplicaSkills.download(draft.raw, (child ? 'child' : 'parent') + '.skill.json');
    }
    $('lineage').textContent = 'Parent v1.0.0\n' + packages.parent.id + '\n  ↓ inherited search.js unchanged; fresh task adds all-word matching\nDescendant v1.1.0\n' + packages.child.id;
    for (const id of ['version','query','tag','archived','limit']) $(id).addEventListener('input', paint);
    paint();
  } catch (e) { $('status').textContent = e.message; }
})();
