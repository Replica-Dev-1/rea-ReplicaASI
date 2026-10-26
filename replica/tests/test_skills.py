"""Real HTTP handler, synthetic wallets, temporary database; no real chain requests."""
import base64, hashlib, json, os, secrets, socket, sys, tempfile, threading, time, unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
socket.AF_UNIX = getattr(socket, 'AF_UNIX', -1)
state = tempfile.TemporaryDirectory(prefix='replica-skills-test-')
cfg = json.loads((ROOT / 'server/config.json').read_text())
cfg.update(gate_token='So11111111111111111111111111111111111111112', public_base='http://test.invalid')
Path(state.name, 'config.json').write_text(json.dumps(cfg))
os.environ.update(RP_STATE=state.name, RP_CONFIG=str(Path(state.name, 'config.json')), RP_PUBLIC='http://test.invalid')
import app as A
import chain as C
import replica_model as S
import skills as K
OWN = {}
C.core_asset = lambda url, a, ttl=20: {'owner': OWN[a], 'name': 'REPLICA', 'uri': A.expected_uri(a), 'update_authority': None} if a in OWN else None
C.token_balance = lambda *args: 1.0

class Wallet:
    def __init__(self):
        self.key = Ed25519PrivateKey.generate()
        self.address = C.b58encode(self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    def sign(self, value):
        return base64.b64encode(self.key.sign(value.encode())).decode()

class SkillsFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.init_db()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), A.H)
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); state.cleanup()
    def call(self, path, data=None):
        req = Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type':'application/json'})
        try:
            with urlopen(req, timeout=10) as response: return response.status, json.load(response)
        except HTTPError as response: return response.code, json.load(response)
    def login(self, wallet):
        _, nonce = self.call('/api/nonce', {'wallet':wallet.address})
        code, result = self.call('/api/verify', {'wallet':wallet.address,'message':nonce['message'],'signature':wallet.sign(nonce['message'])})
        self.assertEqual(code,200); return result['token']
    def claim(self, wallet, token, invite=''):
        asset = C.b58encode(secrets.token_bytes(32)); OWN[asset] = wallet.address
        code, _ = self.call('/api/claim', {'token':token,'asset':asset,'invite':invite})
        self.assertEqual(code,200); return asset
    def delegate(self, wallet, token, asset):
        agent = Wallet(); until = int(time.time()) + 3600
        message = f"REPLICA agent key\n\nReplica: {asset}\nAgent: {agent.address}\nOwner: {wallet.address}\nUntil: {until}\n\nThis lets the agent on your computer add to this replica's log until the date above or until the replica leaves your wallet. It cannot move tokens."
        self.assertEqual(self.call('/api/delegate', {'token':token,'asset':asset,'agent':agent.address,'message':message,'signature':wallet.sign(message)})[0],200)
        return agent
    def append(self, agent, model, kind, body):
        e = S.make_entry(model.head,model.n,kind,body)
        code, result = self.call('/api/append', {'asset':model.asset,'agent':agent.address,'entry':e,'signature':agent.sign(e['h'])})
        if code == 200: model.apply(e)
        return code, result
    def test_inspect_build_test_save_inherit_extend(self):
        parent_raw = (ROOT / 'static/samples/search/parent.skill.json').read_text(encoding='utf-8')
        child_raw = (ROOT / 'static/samples/search/child.skill.json').read_text(encoding='utf-8')
        parent_id, parent = K.validate(parent_raw); child_id, child = K.validate(child_raw)
        a,b,c = Wallet(),Wallet(),Wallet()
        ta,tb,tc = self.login(a),self.login(b),self.login(c)
        asset_a = self.claim(a,ta); agent_a = self.delegate(a,ta,asset_a); ma = S.ReplicaModel(asset_a)
        upload = {'token':ta,'asset':asset_a,'package_json':parent_raw}
        self.assertEqual(self.call('/api/skills', {**upload,'token':''})[0],401)
        self.assertEqual(self.call('/api/skills', {**upload,'token':tc})[0],403)
        self.assertEqual(self.call('/api/skills', {**upload,'package_json':child_raw})[0],400, 'extension without parent must fail')
        broken = json.loads(parent_raw); broken['files'][0]['content'] += 'changed'
        self.assertEqual(self.call('/api/skills', {**upload,'package_json':json.dumps(broken)})[0],400)
        private = json.loads(parent_raw); private['visibility']['public'] = False
        self.assertEqual(self.call('/api/skills', {**upload,'package_json':json.dumps(private)})[0],400)
        failed = json.loads(parent_raw)
        record = next(f for f in failed['files'] if f['role']=='test-record'); r=json.loads(record['content']); r['cases'][0]['passed']=False
        record['content']=json.dumps(r); record['sha256']=hashlib.sha256(record['content'].encode()).hexdigest()
        self.assertEqual(self.call('/api/skills', {**upload,'package_json':json.dumps(failed)})[0],400)
        traversal = json.loads(parent_raw); traversal['files'][0]['path']='../escape.js'
        self.assertEqual(self.call('/api/skills', {**upload,'package_json':json.dumps(traversal)})[0],400)
        status, saved = self.call('/api/skills', upload); self.assertEqual(status,200); self.assertEqual(saved['id'],parent_id)
        self.assertEqual(self.call('/api/replica/'+asset_a+'/skills')[1]['skills'],[], 'upload is not signed approval')
        self.assertEqual(self.append(agent_a,ma,'teach',{'cue':parent['question'],'answer':parent['finding']['interpretation'],'skill':{'id':'0'*64,'inherit':True}})[0],400)
        approval={'cue':parent['question'],'answer':parent['finding']['interpretation'],'skill':{'id':parent_id,'inherit':True}}
        self.assertEqual(self.append(agent_a,ma,'teach',approval)[0],200)
        self.assertEqual(self.call('/api/replica/'+asset_a+'/skills')[1]['skills'][0]['id'],parent_id)
        self.assertEqual(self.call('/api/skills/'+parent_id)[1]['package_json'],parent_raw)
        _, invite=self.call('/api/invite',{'token':ta,'asset':asset_a,'target':b.address})
        asset_b=self.claim(b,tb,invite['code']); agent_b=self.delegate(b,tb,asset_b); mb=S.ReplicaModel(asset_b)
        items=[{'cue':i['cue'],'answer':i['answer']} for i in ma.taught()]
        inherited={'parent':asset_a,'parent_head':ma.head,'items':items,'skills':[parent_id]}
        self.assertEqual(self.append(agent_b,mb,'inherit',{**inherited,'skills':['0'*64]})[0],400)
        self.assertEqual(self.append(agent_b,mb,'inherit',{**inherited,'parent_head':'0'*64})[0],400)
        # A later refusal prevents an old snapshot from bypassing the parent's current choice.
        self.assertEqual(self.append(agent_a,ma,'teach',{**approval,'skill':{'id':parent_id,'inherit':False}})[0],200)
        self.assertEqual(self.append(agent_b,mb,'inherit',inherited)[0],400)
        self.assertEqual(self.append(agent_a,ma,'teach',approval)[0],200)
        inherited['parent_head']=ma.head
        self.assertEqual(self.append(agent_b,mb,'inherit',inherited)[0],200)
        held=self.call('/api/replica/'+asset_b+'/skills')[1]['skills']
        self.assertEqual(held[0]['id'],parent_id); self.assertEqual(held[0]['approval']['via'],asset_a)
        self.assertEqual(mb.recall(parent['question'])[0]['answer'],parent['finding']['interpretation'])
        # Descendant extends the actual inherited package, with separate bytes and test record.
        self.assertEqual(self.call('/api/skills',{'token':tb,'asset':asset_b,'package_json':child_raw})[0],200)
        self.assertEqual(self.append(agent_b,mb,'teach',{'cue':child['question'],'answer':child['finding']['interpretation'],'skill':{'id':child_id,'inherit':True}})[0],200)
        held=self.call('/api/replica/'+asset_b+'/skills')[1]['skills']; self.assertEqual(len(held),2)
        self.assertEqual(held[1]['origin']['parent_package'],parent_id)
        records=self.call('/api/discoveries')[1]['discoveries']
        self.assertTrue(any(x['asset']==asset_b and x['action']=='inherited' and x['id']==parent_id for x in records))
        self.assertTrue(any(x['asset']==asset_b and x['origin']['parent_package']==parent_id for x in records))
        OWN[asset_b]=c.address
        self.assertEqual(self.call('/api/skills',{'token':tb,'asset':asset_b,'package_json':child_raw})[0],403)
        self.assertEqual(self.append(agent_b,mb,'teach',approval)[0],403)
        print('Verified owner approval, immutable artifacts, copy consent, inheritance, descendant extension and transfer enforcement.')

if __name__=='__main__': unittest.main()
