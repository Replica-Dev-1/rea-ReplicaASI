"""Real REA, native build, private queue, signed save, inheritance and extension in temporary state."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import test_skills as base
sys.path.insert(0, str(base.ROOT/'tools'))
import replica_runner as R


class NativeFlow(base.SkillsFlow):
    test_inspect_build_test_save_inherit_extend = None

    def investigate(self, wallet, token, asset, question, local, parent=None):
        auth={'token':token,'asset':asset}
        _,offer=self.call('/api/runner/offer',auth)
        _,paired=self.call('/api/runner/pair',{'code':offer['code'],'name':'native fixture'})
        relay=R.Relay(self.url,paired['runner_token'],local_test=True)
        source=base.ROOT/'samples/notes-target/search.cjs'
        identity,_=R.selected_source(source,'notes fixture')
        relay.call('poll',target=identity)
        code,queued=self.call('/api/runner/enqueue',{**auth,'runner_id':paired['runner_id'],'question':question})
        self.assertEqual(code,200)
        job=relay.call('poll',target=identity)['job']
        node,rea=R.rea_paths(None,None)
        folder=R.run_job(relay,job,source,'notes fixture',node,rea,local/'state/jobs',confirm=lambda *_:True,builds=local/'builds',parent=parent)
        self.assertIsNotNone(folder)
        code,reply=self.call('/api/runner/get',{**auth,'job_id':queued['job_id']});self.assertEqual(code,200)
        raw=reply['result']['package_json']
        self.assertNotIn(str(local),raw)
        return raw

    @unittest.skipUnless(os.environ.get('REA_INTEGRATION')=='1','set REA_INTEGRATION=1 for real REA')
    def test_native_parent_copy_and_descendant_extension(self):
        first,second=base.Wallet(),base.Wallet()
        ta,tb=self.login(first),self.login(second)
        a=self.claim(first,ta);agent_a=self.delegate(first,ta,a);ma=base.S.ReplicaModel(a)
        with tempfile.TemporaryDirectory() as temporary:
            local=Path(temporary)
            raw=self.investigate(first,ta,a,'Build the notes search.',local/'parent')
            pid,parent=base.K.validate(raw)
            self.assertEqual(self.call('/api/replica/'+a+'/log')[1]['log'],[],'private build cannot publish')
            self.assertEqual(self.call('/api/skills',{'token':ta,'asset':a,'package_json':raw})[0],200)
            body={'cue':parent['question'],'answer':parent['finding']['interpretation'],'skill':{'id':pid,'inherit':True}}
            self.assertEqual(self.append(agent_a,ma,'teach',body)[0],200)
            _,invite=self.call('/api/invite',{'token':ta,'asset':a,'target':second.address})
            b=self.claim(second,tb,invite['code']);agent_b=self.delegate(second,tb,b);mb=base.S.ReplicaModel(b)
            inherited={'parent':a,'parent_head':ma.head,'items':[{'cue':i['cue'],'answer':i['answer']} for i in ma.taught()],'skills':[pid]}
            self.assertEqual(self.append(agent_b,mb,'inherit',inherited)[0],200)
            downloaded=self.call('/api/skills/'+pid)[1]['package_json']
            self.assertEqual(downloaded,raw)
            path=local/'inherited.skill.json';path.write_text(downloaded,encoding='utf-8')
            child_raw=self.investigate(second,tb,b,'Extend the notes search with all words and a limit.',local/'child',parent=path)
            cid,child=base.K.validate(child_raw)
            self.assertEqual(child['origin']['parent_package'],pid)
            self.assertNotEqual(child['origin']['author'],parent['origin']['author'])
            self.assertEqual(self.call('/api/skills',{'token':tb,'asset':b,'package_json':child_raw})[0],200)
            self.assertEqual(self.append(agent_b,mb,'teach',{'cue':child['question'],'answer':child['finding']['interpretation'],'skill':{'id':cid,'inherit':True}})[0],200)
            held=self.call('/api/replica/'+b+'/skills')[1]['skills']
            self.assertEqual({s['id'] for s in held},{pid,cid})
            for package,count in [(parent,20),(child,35)]:
                record=json.loads(next(f['content'] for f in package['files'] if f['role']=='test-record'))
                self.assertEqual(len(record['cases']),count);self.assertTrue(all(c['passed'] for c in record['cases']))
        print('PASS real REA -> native parent build (20 checks) -> private review -> signed save -> exact copy -> native descendant extension (35 checks). Temporary wallets and database only.')


if __name__=='__main__':unittest.main()
