"""Real private queue HTTP flow; temporary state and synthetic wallets, never production writes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import sys
import unittest
from unittest.mock import patch

import test_skills as base
from test_skills import Wallet, A, OWN, ROOT
sys.path.insert(0, str(ROOT / 'tools'))

spec = importlib.util.spec_from_file_location("companion", ROOT / "tools/replica_runner.py")
companion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(companion)


class RunnerFlow(base.SkillsFlow):
    test_inspect_build_test_save_inherit_extend = None

    def test_private_owner_bound_investigation(self):
        first, other = Wallet(), Wallet()
        token = self.login(first)
        asset = self.claim(first, token)
        auth = {"token": token, "asset": asset}
        other_token = self.login(other)
        self.assertEqual(self.call('/api/runner/offer', {"token": other_token, "asset": asset})[0], 403)
        _, offer = self.call('/api/runner/offer', auth)
        code, paired = self.call('/api/runner/pair', {"code": offer['code'], "name": "test computer"})
        self.assertEqual(code, 200)
        self.assertEqual(self.call('/api/runner/pair', {"code": offer['code'], "name": "replay"})[0], 403)
        runner = {"runner_token": paired['runner_token']}
        rid = paired['runner_id']
        identity = {"label": "notes", "file": "search.cjs", "sha256": "a" * 64}
        self.assertEqual(self.call('/api/runner/poll', {**runner, "target": {**identity, "file": "../secret.js"}})[0], 400)
        self.assertEqual(self.call('/api/runner/poll', {**runner, "target": identity})[0], 200)
        _, listed = self.call('/api/runner/list', auth)
        self.assertTrue(listed['runners'][0]['online'])
        self.assertNotIn('runner_token', json.dumps(listed))
        question = "How does this file search notes?"
        _, queued = self.call('/api/runner/enqueue', {**auth, "runner_id": rid, "question": question})
        jid = queued['job_id']
        self.assertEqual(self.call('/api/runner/enqueue', {**auth, "runner_id": rid, "question": question})[0], 409)
        _, work = self.call('/api/runner/poll', {**runner, "target": identity})
        self.assertEqual(work['job']['id'], jid)
        self.assertIsNone(self.call('/api/runner/poll', {**runner, "target": identity})[1]['job'], 'claimed task cannot replay')
        finding = {"schema": "replica-rea-finding-v1", "cue": question, "answer": "Source inspected; runtime behavior remains untested.",
                   "source": {"version": "6.8.0", "tool": "analyze_javascript_application", "target": "notes/search.cjs", "evidence": "source sha256 " + 'a'*64, "limitations": "Static inspection only."}}
        result = {"report": "Private inspection summary.", "finding": finding}
        self.assertEqual(self.call('/api/runner/complete', {**runner, 'job_id': jid, 'result': {**result, 'package_json': '{}'}})[0], 400)
        self.assertEqual(self.call('/api/runner/complete', {**runner, 'job_id': jid, 'result': result})[0], 200)
        self.assertEqual(self.call('/api/runner/list', {"token": other_token, "asset": asset})[0], 403)
        _, own = self.call('/api/runner/list', auth)
        self.assertEqual(own['jobs'][0]['result']['report'], result['report'])
        self.assertEqual(self.call('/api/replica/' + asset + '/log')[1]['log'], [], 'a private result must not publish memory')
        self.assertEqual(self.call('/api/runner/list')[0], 404, 'no public GET access')
        raw = (ROOT/'static/samples/search/parent.skill.json').read_text(encoding='utf-8')
        self.assertEqual(self.call('/api/runner/complete', {**runner, 'job_id': jid, 'result': {**result, 'package_json': raw}})[0], 200)
        _, own = self.call('/api/runner/list', auth)
        self.assertTrue(own['jobs'][0]['has_package'])
        self.assertNotIn('package_json', own['jobs'][0]['result'])
        self.assertEqual(self.call('/api/runner/get', {**auth, 'job_id': jid})[1]['result']['package_json'], raw)
        self.assertEqual(self.call('/api/skills/' + hashlib.sha256(raw.encode()).hexdigest())[0], 404, 'private package is not publicly stored')
        self.assertEqual(self.call('/api/runner/cancel', {**auth, 'job_id': jid})[0], 200)
        self.assertEqual(self.call('/api/runner/complete', {**runner, 'job_id': jid, 'result': result})[0], 409)
        self.assertEqual(self.call('/api/runner/get', {**auth, 'job_id': jid})[1]['result'], {})
        # Transferring the replica never transfers access to its old owner's computer or private jobs.
        OWN[asset] = other.address
        self.assertEqual(self.call('/api/runner/poll', {**runner, 'target': identity})[0], 403)
        self.assertEqual(self.call('/api/runner/list', {"token": other_token, "asset": asset})[1], {'runners': [], 'jobs': []})
        OWN[asset] = first.address
        self.assertEqual(self.call('/api/runner/revoke', {**auth, 'runner_id': rid})[0], 200)
        self.assertEqual(self.call('/api/runner/poll', {**runner, 'target': identity})[0], 403)
        _, offer = self.call('/api/runner/offer', auth)
        with A.LOCK, A.tx() as c:
            c.execute('UPDATE runner_pair SET expires=?', (time.time()-1,))
        self.assertEqual(self.call('/api/runner/pair', {'code': offer['code'], 'name': 'expired'})[0], 403)

    @unittest.skipUnless(os.environ.get('REA_INTEGRATION') == '1', 'set REA_INTEGRATION=1 to execute the real pinned REA tool')
    def test_real_rea_round_trip(self):
        wallet = Wallet(); token = self.login(wallet); asset = self.claim(wallet, token)
        auth = {'token': token, 'asset': asset}
        _, offer = self.call('/api/runner/offer', auth)
        _, paired = self.call('/api/runner/pair', {'code': offer['code'], 'name': 'real REA test'})
        relay = companion.Relay(self.url, paired['runner_token'], local_test=True)
        source = ROOT/'samples/notes-target/search.cjs'
        identity, _ = companion.selected_source(source, 'reference notes')
        relay.call('poll', target=identity)
        _, queued = self.call('/api/runner/enqueue', {**auth, 'runner_id': paired['runner_id'], 'question': 'How does the search work?'})
        job = relay.call('poll', target=identity)['job']
        node, rea = companion.rea_paths(None, None)
        with tempfile.TemporaryDirectory() as tmp:
            folder = companion.run_job(relay, job, source, 'reference notes', node, rea, Path(tmp), confirm=lambda *_: True)
            self.assertIsNotNone(folder)
            self.assertTrue((folder/'rea-original.json').is_file())
            self.assertTrue((folder/'build-brief.txt').is_file())
            _, result = self.call('/api/runner/get', {**auth, 'job_id': queued['job_id']})
            self.assertIn('ev_', result['result']['finding']['source']['evidence'])
            self.assertNotIn(str(Path(tmp)), json.dumps(result))
            self.assertNotIn('function search', json.dumps(result), 'raw source stays local')
            self.assertEqual(self.call('/api/replica/'+asset+'/log')[1]['log'], [])


class CompanionLimits(unittest.TestCase):
    def test_declined_or_changed_source_never_starts_rea(self):
        class Relay:
            site = "https://replicaasi.com"
            def __init__(self): self.calls = []
            def call(self, action, **kwargs): self.calls.append(action); return {}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'app.js'; source.write_text('export const value = 1;')
            identity, _ = companion.selected_source(source, 'project')
            job = {'id': 'a'*32, 'question': 'Inspect this file.', 'target': identity}
            relay = Relay()
            with patch.object(companion, 'inspect') as inspect:
                self.assertIsNone(companion.run_job(relay, job, source, 'project', 'node', 'rea', Path(tmp)/'jobs', confirm=lambda *_: False))
                inspect.assert_not_called()
                self.assertEqual(relay.calls, ['fail'])
                source.write_text('export const value = 2;')
                self.assertIsNone(companion.run_job(relay, job, source, 'project', 'node', 'rea', Path(tmp)/'jobs', confirm=lambda *_: True))
                inspect.assert_not_called()

    def test_https_and_source_scope(self):
        for site in ['http://replicaasi.com', 'https://user:password@replicaasi.com', 'https://replicaasi.com/path', 'https://replicaasi.com/?key=x']:
            with self.assertRaises(ValueError): companion.Relay(site)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'app.js';path.write_text('export const value = 1;')
            identity, data = companion.selected_source(path, 'chosen project')
            self.assertEqual(identity['sha256'], hashlib.sha256(data).hexdigest())
            self.assertNotIn(tmp, json.dumps(identity))
            path.write_bytes(b'x' * (companion.MAX_SOURCE+1))
            with self.assertRaises(ValueError): companion.selected_source(path, 'chosen project')
            with self.assertRaises(ValueError): companion.selected_source(Path(tmp), 'chosen project')


if __name__ == '__main__':
    unittest.main()
