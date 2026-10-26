"""Owner-authorized hosted REA queue. Source is data; execution belongs to a separate offline worker."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
import runner as J

SCHEMA = """CREATE TABLE IF NOT EXISTS hosted_rea_job
(id TEXT PRIMARY KEY, owner TEXT, asset TEXT, question TEXT, target TEXT, state TEXT, created REAL, result TEXT DEFAULT '{}', error TEXT DEFAULT '');"""
MAX_SOURCE = 256_000


def atomic(path, value):
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(4))
    with temporary.open('x', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False)
    # The spool directory has setgid so new files inherit its worker group.
    # The relay intentionally cannot call chown in its service sandbox.
    temporary.chmod(0o660)
    os.replace(temporary, path)


class Service:
    def __init__(self, lock, tx, owner, validate_skill, spool, sample):
        self.lock, self.tx, self.owner, self.validate_skill = lock, tx, owner, validate_skill
        self.spool, self.sample = Path(spool), Path(sample)

    def available(self):
        try: return time.time() - (self.spool/'heartbeat').stat().st_mtime < 90
        except OSError: return False

    def collect(self, c, row):
        jid=row['id']; state=row['state']
        if state not in ('queued','running'): return
        output=self.spool/(jid+'.result.json')
        if output.is_file() and not output.is_symlink() and output.stat().st_size <= 200_000:
            try:
                data=json.loads(output.read_text(encoding='utf-8'))
                if data.get('error'):
                    c.execute("UPDATE hosted_rea_job SET state='failed',error=? WHERE id=?",('REA could not complete this inspection. Try a smaller supported source file.',jid))
                else:
                    clean=J.result(data['result'],self.validate_skill)
                    if clean['finding']['cue']!=row['question'] or 'package_json' in clean: raise ValueError('wrong result')
                    target=json.loads(row['target']);source=clean['finding']['source']
                    if source['target']!=target['label'][:55]+'/'+target['file'] or 'source sha256 '+target['sha256'] not in source['evidence']:raise ValueError('wrong source')
                    c.execute("UPDATE hosted_rea_job SET state='review',result=? WHERE id=?",(json.dumps(clean),jid))
                output.unlink(missing_ok=True)
            except (ValueError,KeyError,TypeError,AttributeError,J.Refused):
                c.execute("UPDATE hosted_rea_job SET state='failed',error='Invalid inspection result.' WHERE id=?",(jid,))
                output.unlink(missing_ok=True)
        elif time.time()-row['created']>180:
            c.execute("UPDATE hosted_rea_job SET state='failed',error='Inspection timed out. Start a new task.' WHERE id=?",(jid,))
            atomic(self.spool/(jid+'.cancel'),{})
        elif (self.spool/(jid+'.running')).exists():
            c.execute("UPDATE hosted_rea_job SET state='running' WHERE id=?",(jid,))

    def handle(self,h,action,d):
        try:
            if not isinstance(d,dict):raise J.Refused(400,'Expected an inspection request.')
            auth=h._owner(d)
            if not auth:return
            wallet,asset=auth
            if self.owner(asset,ttl=0)!=wallet:raise J.Refused(403,'Ownership changed.')
            if action not in ('start','list','get','cancel'):raise J.Refused(404,'Unknown inspection action.')
            now=time.time()
            with self.lock,self.tx() as c:
                c.execute('DELETE FROM hosted_rea_job WHERE created<?',(now-86400,))
                rows=c.execute('SELECT * FROM hosted_rea_job WHERE owner=? AND asset=? ORDER BY created DESC LIMIT 20',(wallet,asset)).fetchall()
                for row in rows:self.collect(c,row)
                if action=='start':
                    if not self.available():raise J.Refused(503,'The REA worker is temporarily unavailable. Try again shortly.')
                    if d.get('consent') is not True:raise J.Refused(400,'Approve sending this source for private inspection first.')
                    if c.execute("SELECT 1 FROM hosted_rea_job WHERE asset=? AND state IN ('queued','running')",(asset,)).fetchone():raise J.Refused(409,'This replica already has an inspection running.')
                    if c.execute('SELECT COUNT(*) FROM hosted_rea_job WHERE asset=? AND created>?',(asset,now-86400)).fetchone()[0]>=20:raise J.Refused(429,'Daily inspection limit reached.')
                    if c.execute("SELECT COUNT(*) FROM hosted_rea_job WHERE state IN ('queued','running') AND created>?",(now-180,)).fetchone()[0]>=8:raise J.Refused(429,'Inspection queue is full. Try again shortly.')
                    question=J.text(d.get('question'),600)
                    if d.get('sample') is True:
                        source=self.sample.read_text(encoding='utf-8');name='search.cjs'
                    else:
                        source=d.get('source');name=d.get('filename')
                        if not isinstance(source,str) or not source.strip() or '\x00' in source:raise J.Refused(400,'Choose a UTF-8 source file.')
                    if len(source.encode('utf-8'))>MAX_SOURCE:raise J.Refused(400,'Source files must be 256 KB or smaller.')
                    target=J.target({'label':'Website inspection','file':name,'sha256':hashlib.sha256(source.encode()).hexdigest()})
                    jid=secrets.token_hex(16)
                    job={'id':jid,'asset':asset,'question':question,'target':target,'source':source,'created':now}
                    c.execute("INSERT INTO hosted_rea_job(id,owner,asset,question,target,state,created) VALUES(?,?,?,?,?,'queued',?)",(jid,wallet,asset,question,json.dumps(target),now))
                    atomic(self.spool/(jid+'.job.json'),job)
                    return h._send(200,{'job_id':jid})
                if action in ('get','cancel'):
                    row=c.execute('SELECT * FROM hosted_rea_job WHERE id=? AND owner=? AND asset=?',(d.get('job_id'),wallet,asset)).fetchone()
                    if not row:raise J.Refused(404,'Inspection not found.')
                    if action=='cancel':
                        atomic(self.spool/(row['id']+'.cancel'),{})
                        for suffix in ('.job.json','.result.json'):(self.spool/(row['id']+suffix)).unlink(missing_ok=True)
                        c.execute("UPDATE hosted_rea_job SET state='cancelled',result='{}' WHERE id=?",(row['id'],))
                        return h._send(200,{'ok':True})
                    return h._send(200,{'result':json.loads(row['result'])})
                rows=c.execute('SELECT id,question,target,state,created,result,error FROM hosted_rea_job WHERE owner=? AND asset=? ORDER BY created DESC LIMIT 20',(wallet,asset)).fetchall()
                return h._send(200,{'available':self.available(),'jobs':[dict(r)|{'target':json.loads(r['target']),'result':json.loads(r['result'])} for r in rows]})
        except J.Refused as error:return h._send(error.status,{'error':error.message})
