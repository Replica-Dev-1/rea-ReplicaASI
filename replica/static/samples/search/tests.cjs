// Run only after reviewing these sample files. No dependencies or network calls.
const assert = require('node:assert/strict');
const notes = require('./fixtures.json');
const reference = require('./target.cjs').findNotes;
const parent = require('./search.js').search;
const cases = [];
function check(name, fn, query, options, expected) {
  const actual = fn(notes, query, options).map(n => n.id);
  const passed = JSON.stringify(actual) === JSON.stringify(expected);
  cases.push({ name, input: { query, options }, expected, actual, passed });
}
const base = [
  ['empty query keeps order', '', {}, ['a','b','c','e']],
  ['title matches rank before body', 'blue', {}, ['b','a','c']],
  ['case is ignored', 'BLUE', {}, ['b','a','c']],
  ['surrounding space is ignored', ' blue ', {}, ['b','a','c']],
  ['partial words match', 'gard', {}, ['a','b','c']],
  ['tag filter is exact', 'blue', { tag: 'work' }, ['b','c']],
  ['archived notes excluded by default', 'archived', {}, []],
  ['archive opt-in', 'garden', { archived: true }, ['a','d','b','c']],
  ['unknown query has no results', 'moon', {}, []],
  ['unknown tag has no results', '', { tag: 'missing' }, []]
];
for (const [name,q,o,want] of base) {
  check('reference: ' + name, reference, q, o, want);
  check('reconstruction: ' + name, parent, q, o, want);
}
if (process.argv.includes('--child')) {
  const child = require('./child.js').search;
  for (const [name,q,o,want] of base) check('child regression: ' + name, child, q, o, want);
  check('child: terms across title and body', child, 'blue spring', {}, ['b','a']);
  check('child: fresh all-word query', child, 'garden sketches', {}, ['c']);
  check('child: limit after filtering', child, 'blue garden', { limit: 1 }, ['b']);
  check('child: zero limit', child, 'blue', { limit: 0 }, []);
  check('child: tag plus all words', child, 'blue garden', { tag: 'work' }, ['b','c']);
}
console.log(JSON.stringify({ schema: 'replica-test-record-v1', runner: process.version, scope: process.argv.includes('--child') ? 'parent regression and descendant extension' : 'reference and reconstruction', cases }, null, 2));
assert.ok(cases.every(c => c.passed), 'One or more sample checks failed');
