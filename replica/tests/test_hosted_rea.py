"""Website upload, real REA worker, private result and ownership gates; temporary state only."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_skills as base
sys.path.insert(0,str(base.ROOT/'tools'))
import replica_runner as R
import hosted_rea_worker as W

class HostedFlow(base.SkillsFlow):
    test_inspect_build_test_save_inherit_extend=None

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.spool=Path(self.tmp.name)
        self.patch=patch.object(base.A.HOSTED_REA,'spool',self.spool);self.patch.start()
        (self.spool/'heartbeat').touch()

    def tearDown(self):self.patch.stop();self.tmp.cleanup()

    def test_consent_limits_cancel_and_owner(self):
        first,other=base.Wallet(),base.Wallet();token=self.login(first);asset=self.claim(first,token)
        auth={'token':token,'asset':asset};start={**auth,'sample':True,'question':'Inspect the notes search.','consent':True}
        self.assertEqual(self.call('/api/rea/start',{**start,'token':''})[0],401)
        self.assertEqual(self.call('/api/rea/start',{**start,'consent':False})[0],400)
        self.assertEqual(self.call('/api/rea/start',{**start,'sample':False,'filename':'../secret.js','source':'const x=1;'})[0],400)
        self.assertEqual(self.call('/api/rea/start',{**start,'sample':False,'filename':'a.js','source':'x'*256001})[0],400)
        code,data=self.call('/api/rea/start',start);self.assertEqual(code,200);jid=data['job_id']
        self.assertTrue((self.spool/(jid+'.job.json')).exists())
        self.assertEqual(self.call('/api/rea/start',start)[0],409)
        self.assertEqual(self.call('/api/rea/get',{'token':self.login(other),'asset':asset,'job_id':jid})[0],403)
        self.assertEqual(self.call('/api/rea/cancel',{**auth,'job_id':jid})[0],200)
        self.assertFalse((self.spool/(jid+'.job.json')).exists())
        self.assertEqual(self.call('/api/rea/get',{**auth,'job_id':jid})[1]['result'],{})
        base.OWN[asset]=other.address
        self.assertEqual(self.call('/api/rea/list',auth)[0],403)

    @unittest.skipUnless(os.environ.get('REA_INTEGRATION')=='1','real REA enabled explicitly')
    def test_website_upload_to_real_rea_findings(self):
        wallet=base.Wallet();token=self.login(wallet);asset=self.claim(wallet,token);auth={'token':token,'asset':asset}
        # If this uploaded source were executed, the sentinel would be created.
        sentinel=self.spool/'MUST_NOT_EXIST'
        source="require('node:fs').writeFileSync("+json.dumps(str(sentinel))+", 'executed'); module.exports = { double: x => x * 2 };"
        code,data=self.call('/api/rea/start',{**auth,'sample':False,'filename':'probe.cjs','source':source,'question':'Inspect exports without executing this program.','consent':True})
        self.assertEqual(code,200);jid=data['job_id'];node,rea=R.rea_paths(None,None)
        W.process(self.spool/(jid+'.job.json'),self.spool,node,rea)
        self.assertFalse(sentinel.exists());self.assertFalse((self.spool/(jid+'.job.json')).exists())
        code,listing=self.call('/api/rea/list',auth);self.assertEqual(code,200)
        job=next(j for j in listing['jobs'] if j['id']==jid)
        self.assertEqual(job['state'],'review',job)
        self.assertIn('export relationships',job['result']['finding']['answer'])
        self.assertNotIn(str(self.spool),json.dumps(job))
        self.assertNotIn(source,json.dumps(job))
        self.assertEqual(self.call('/api/replica/'+asset+'/log')[1]['log'],[])
        self.assertFalse((self.spool/(jid+'.result.json')).exists())
        print('PASS website upload -> real REA -> private findings; uploaded code not executed, raw source deleted, no public memory write.')

if __name__=='__main__':unittest.main()
