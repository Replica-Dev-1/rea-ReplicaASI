const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const K = require('../static/skills.js');
const R = require('../static/replica.js');
const read = name => fs.readFileSync(path.join(__dirname,'../static/samples/search',name+'.skill.json'),'utf8');
test('portable packages bind the child to the exact parent bytes', async () => {
  const parent = await K.prepare(read('parent')), child = await K.prepare(read('child'));
  assert.equal(child.package.origin.parent_package,parent.id);
  assert.equal(parent.passed,20); assert.equal(child.passed,35);
  assert.equal(child.package.files.find(f=>f.path==='search.js').sha256,parent.package.files.find(f=>f.path==='search.js').sha256);
});
test('tampering, incomplete artifacts, private packages and failing reports are rejected', async () => {
  const p = JSON.parse(read('parent'));
  p.files[0].content += 'tamper'; await assert.rejects(K.prepare(JSON.stringify(p)),/digest/);
  p.files[0].sha256 = await K.digest(p.files[0].content); p.visibility.public=false;
  await assert.rejects(K.prepare(JSON.stringify(p)),/public/); p.visibility.public=true;
  const record = p.files.find(f=>f.role==='test-record'), data=JSON.parse(record.content);
  data.cases[0].passed=false; record.content=JSON.stringify(data); record.sha256=await K.digest(record.content);
  await assert.rejects(K.prepare(JSON.stringify(p)),/failed/);
});
test('signed technical lineage preserves package ids while prose memories are separate', async () => {
  const p=await K.prepare(read('parent')), a=await R.Model.create('parent'), b=await R.Model.create('child');
  const approval=await R.makeEntry(a.head,0,'teach',{cue:p.package.question,answer:p.package.finding.interpretation,skill:{id:p.id,inherit:true}},100);
  await a.apply(approval); assert.equal(K.references([approval])[0].id,p.id);
  const inherited=await R.makeEntry(b.head,0,'inherit',{parent:'parent',parent_head:a.head,items:[],skills:[p.id]},101);
  await b.apply(inherited); assert.equal(K.references([inherited])[0].id,p.id);
  const forget=await R.makeEntry(a.head,1,'forget',{id:approval.h.slice(0,16)},102);
  await a.apply(forget); assert.deepEqual(K.references([approval,forget]),[]);
  assert.equal(K.references([inherited])[0].id,p.id,'parent forgetting cannot mutate already inherited bytes');
});
