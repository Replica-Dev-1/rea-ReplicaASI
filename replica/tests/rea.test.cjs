const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const Rea = require('../static/rea.js');
const R = require('../static/replica.js');
const example = JSON.parse(fs.readFileSync(path.join(__dirname, '../integrations/rea/finding.example.json'), 'utf8'));
const raw = (change = {}) => JSON.stringify({ ...example, ...change });

test('rejects unsupported, incomplete, excessive and non-text findings', () => {
  for (const value of [null, {}, { schema: 'wrong' }, { ...example, source: null },
    { ...example, answer: '' }, { ...example, cue: 'x'.repeat(601) },
    { ...example, answer: { command: 'execute' } }, { ...example, cue: 'bad\u0000' },
    { ...example, source: { ...example.source, tool: 'bad;command' } }])
    assert.throws(() => Rea.prepare(JSON.stringify(value)));
  assert.throws(() => Rea.prepare(' '.repeat(12001)));
  assert.throws(() => Rea.prepare(raw({ answer: '\u65e5'.repeat(600) })));
});

test('only permitted data is retained and markup remains plain text', () => {
  const body = Rea.prepare(raw({ answer: '<script>alert(1)</script>', command: 'ignored' }));
  assert.equal(body.command, undefined);
  assert.equal(body.source.host_reviewed, true);
  assert.match(Rea.preview(body), /<script>/);
  assert.match(Rea.preview(body), /Limitations:/);
});

test('review does not append; explicit commit appends exactly once', async () => {
  const calls = [];
  const s = Rea.session(() => 'wallet:asset', async (...args) => calls.push(args));
  await assert.rejects(s.commit(), /Review/);
  s.stage(raw()); assert.equal(calls.length, 0);
  await s.commit(); assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'teach');
  assert.equal(calls[0][2], 'wallet:asset');
  await assert.rejects(s.commit(), /Review/);
});

test('rejects wallet changes, invalid replacement files and missing host', async () => {
  let context = 'wallet:asset', calls = 0;
  const s = Rea.session(() => context, async () => calls++);
  s.stage(raw()); context = 'other:asset';
  await assert.rejects(s.commit(), /changed/);
  s.stage(raw()); assert.throws(() => s.stage('invalid'));
  await assert.rejects(s.commit(), /Review/);
  context = null; assert.throws(() => s.stage(raw()), /Connect/);
  assert.equal(calls, 0);
});

test('blocks concurrent writes and consumes ambiguous failed imports', async () => {
  let finish;
  const s = Rea.session(() => 'w:a', () => new Promise(resolve => { finish = resolve; }));
  s.stage(raw()); const pending = s.commit();
  await assert.rejects(s.commit(), /progress/);
  assert.throws(() => s.stage(raw()), /progress/);
  finish(); await pending;
  const failed = Rea.session(() => 'w:a', async () => { throw new Error('connection lost'); });
  failed.stage(raw()); await assert.rejects(failed.commit(), /connection lost/);
  await assert.rejects(failed.commit(), /Review/);
});

test('signed finding replays in JS and Python with identical head and recall', async () => {
  const asset = 'H2oKogqzWK956ezfKdaD2gSSBWaE4kUM1moTqQnuHHie';
  const model = await R.Model.create(asset);
  const body = Rea.prepare(raw());
  const entry = await R.makeEntry(model.head, model.n, 'teach', body, 1760400000);
  await model.apply(entry);
  const [recalled] = await model.recall(body.cue);
  assert.equal(recalled.answer, body.answer);
  const python = `import sys,json\nsys.path.insert(0,sys.argv[1])\nimport replica_model as S\nd=json.load(sys.stdin)\nm=S.ReplicaModel.rebuild(d['asset'],[d['entry']])\nit,_=m.recall(d['entry']['body']['cue'])\nprint(json.dumps({'head':m.head,'answer':it['answer']}))`;
  const result = JSON.parse(execFileSync('python', ['-c', python, path.join(__dirname, '../server')],
    { input: JSON.stringify({ asset, entry }), encoding: 'utf8' }));
  assert.equal(result.head, model.head); assert.equal(result.answer, recalled.answer);
  const altered = JSON.parse(JSON.stringify(entry)); altered.body.source.evidence = 'tampered';
  const rebuilt = await R.Model.create(asset);
  await assert.rejects(rebuilt.apply(altered));
});
