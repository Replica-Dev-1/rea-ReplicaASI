"""Native agent scope, evidence, execution and privacy boundaries. No model calls."""
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import replica_agent as N
import replica_runner as R


class NativeAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.node = shutil.which('node')

    def tearDown(self): self.tmp.cleanup()

    def task(self, source=b'module.exports = { scale: x => x * 3 };', question='Build a numeric helper.', suffix='a'):
        folder = self.root/'state/jobs'/(suffix*32)
        (folder/'input').mkdir(parents=True)
        (folder/'input/source.cjs').write_bytes(source)
        sha=hashlib.sha256(source).hexdigest()
        job={'id':suffix*32,'asset':'1'*32,'question':question,'target':{'label':'fixture','file':'source.cjs','sha256':sha}}
        evidence={'evidence_id':'ev_'+'b'*64,'normalized_result':{'statistics':{'parsed_javascript_files':1,'parse_failures':0},'graph':{'nodes':[
            {'kind':'javascript-module','observations':[{'observation_id':'fixture-observation','properties':{'semantic_role':'source-module','source_sha256':sha,'module_format':'commonjs','export_relationships':1},'evidence':{'artifact':{'sha256':sha},'state':'observed'}}]}
        ]}}}
        (folder/'rea-original.json').write_text(json.dumps(evidence))
        result={'report':'Inspection complete.','finding':{'answer':'Source inspected.','source':{'limitations':'Static only.'}}}
        return job,folder,result

    def execute(self, task, **kwargs):
        return N.run(*task,self.node,self.root/'builds',lambda *_:True,**kwargs)

    def test_numeric_reconstruction_runs_offline_and_is_identity_bound(self):
        if not self.node: self.skipTest('Node is required')
        task=self.task()
        (self.root/'state/connection.json').write_text('{"runner_token":"NEVER_INCLUDE_THIS"}')
        with patch.object(socket.socket,'connect',side_effect=AssertionError('No network allowed')):
            result=self.execute(task)
        package=json.loads(result['package_json']);N.skills.validate(result['package_json'])
        record=json.loads(next(f['content'] for f in package['files'] if f['role']=='test-record'))
        self.assertEqual(len(record['cases']),14)
        self.assertTrue(all(c['passed'] for c in record['cases']))
        self.assertNotIn('NEVER_INCLUDE_THIS',result['package_json'])
        self.assertNotIn(str(self.root),result['package_json'])
        receipt=json.loads(next(f['content'] for f in package['files'] if f['path']=='agent-receipt.json'))
        claimed=receipt.pop('sha256');self.assertEqual(claimed,N.digest(N.canonical(receipt)))
        self.assertEqual(receipt['asset'],task[0]['asset'])
        implementation=next(f['content'] for f in package['files'] if f['role']=='implementation')
        # Fresh independent values, beyond the generated check set.
        script=implementation+'\nfor(let n=-37;n<=37;n++) if(module.exports.scale(n/7)!==(n/7)*3) process.exit(1);'
        subprocess.run([self.node,'-e',script],check=True)

    def test_scope_and_source_instructions_cannot_start_code(self):
        for i,source in enumerate([b"require('node:fs').writeFileSync('bad','x');",b'module.exports={scale:x=>x*3}; process.exit(0);',b'module.exports={scale:x=>x/0};']):
            task=self.task(source,suffix='abc'[i])
            with patch.object(N.subprocess,'run') as execute:
                result=self.execute(task)
                execute.assert_not_called();self.assertNotIn('package_json',result)
                self.assertIn('No admitted build specialist',result['report'])
        self.assertEqual(N.choose({'question':'Build a rocket'},b'module.exports = { scale: x => x * 3 };')['outcome'],'decline')

    def test_rejects_changed_or_unbound_evidence(self):
        task=self.task();job,folder,_=task
        p=folder/'rea-original.json';e=json.loads(p.read_text());e['normalized_result']['graph']['nodes'][0]['observations'][0]['evidence']['artifact']['sha256']='c'*64;p.write_text(json.dumps(e))
        with self.assertRaises(ValueError):self.execute(task)
        (folder/'input/source.cjs').write_text('changed')
        with self.assertRaises(ValueError):self.execute(task)

    def test_declined_build_and_failed_checks_never_package(self):
        task=self.task()
        with patch.object(N.subprocess,'run') as execute:
            result=N.run(*task,self.node,self.root/'builds',lambda *_:False)
            execute.assert_not_called();self.assertNotIn('package_json',result)
        failure=subprocess.CompletedProcess([],1,b'{}',b'failed')
        with patch.object(N.subprocess,'run',return_value=failure):
            with self.assertRaises(ValueError):self.execute(task)
        self.assertFalse(list(self.root.rglob('skill.json')))

    def test_profiles_have_no_remote_fallback_and_can_disable_builds(self):
        profile=N.load_profile();path=self.root/'profile.json'
        for bad in [dict(profile,core='fallback'),dict(profile,language_model=True),dict(profile,endpoint='https://example.test'),dict(profile,specialists=['unknown'])]:
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):N.load_profile(path)
        profile['specialists']=['source-evidence'];path.write_text(json.dumps(profile))
        with patch.object(N.subprocess,'run') as execute:
            result=self.execute(self.task(),profile_path=path)
            execute.assert_not_called();self.assertNotIn('package_json',result)

    def test_parent_extension_checks_and_tamper_refusal(self):
        if not self.node:self.skipTest('Node is required')
        source=(ROOT/'samples/notes-target/search.cjs').read_bytes()
        parent=self.execute(self.task(source,'Build the notes search.'))
        path=self.root/'parent.skill.json';path.write_text(parent['package_json'],encoding='utf-8')
        child=self.execute(self.task(source,'Extend the notes search with all words and a limit.','b'),parent_path=path)
        p=json.loads(parent['package_json']);c=json.loads(child['package_json'])
        self.assertEqual(c['origin']['parent_package'],N.digest(parent['package_json'].encode()))
        for package,count in [(p,20),(c,35)]:
            record=json.loads(next(f['content'] for f in package['files'] if f['role']=='test-record'))
            self.assertEqual(len(record['cases']),count)
        file=next(f for f in p['files'] if f['path']=='search.js');file['content']+='\n// changed';file['sha256']=N.digest(file['content'].encode());path.write_text(json.dumps(p))
        with self.assertRaises(ValueError):N.load_parent(path)

    def test_cancellation_before_build_runs_nothing(self):
        def cancelled():raise ValueError('Task cancelled')
        with patch.object(N.subprocess,'run') as execute:
            with self.assertRaises(ValueError):self.execute(self.task(),heartbeat=cancelled)
            execute.assert_not_called()

    def test_runner_requires_whole_package_send_approval(self):
        from unittest.mock import Mock
        task=self.task();job,folder,result=task
        relay=Mock(site='https://example.test');prompts=[]
        def confirm(message,word):prompts.append((message,word));return word!='send'
        with patch.object(R,'selected_source',return_value=(job['target'],b'source')),patch.object(R,'inspect',return_value=(folder,result)),patch.object(N,'run',return_value=dict(result,package_json='fixture package')),patch.object(R,'protect'):
            R.run_job(relay,job,folder/'input/source.cjs','fixture','node','rea',folder.parent,confirm=confirm,builds=self.root/'builds')
        self.assertIn('ENTIRE skill package',prompts[-1][0])
        self.assertFalse(any(c.args[0]=='complete' for c in relay.call.call_args_list))


if __name__=='__main__':unittest.main()
