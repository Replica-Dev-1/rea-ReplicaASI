"""Offline REA worker. Only spool files are shared with the relay; no database or network access."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import time
import replica_runner as R
import replica_agent as N


def atomic(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    temporary.chmod(0o660);os.replace(temporary,path)


def process(path,spool,node,rea):
    jid=path.name.split('.')[0]
    if not re.fullmatch('[0-9a-f]{32}',jid) or path.is_symlink() or path.stat().st_size>1_600_000:
        path.unlink(missing_ok=True);return
    running=spool/(jid+'.running');cancel=spool/(jid+'.cancel')
    try:
        if cancel.exists():return
        job=json.loads(path.read_text(encoding='utf-8'))
        if job['id']!=jid or time.time()-job['created']>180:return
        source=job.pop('source').encode('utf-8')
        if len(source)>256_000 or N.digest(source)!=job['target']['sha256']:raise ValueError('invalid source')
        atomic(running,{})
        with tempfile.TemporaryDirectory(prefix='inspection-') as temporary:
            folder,result=R.inspect(job,job['target'],source,node,rea,Path(temporary)/'jobs')
            _,evidence=N.evidence_for(job,folder)
            modules=evidence['modules'];formats=sorted({m['module_format'] for m in modules if m['module_format'] in ('commonjs','esm','script','mixed','unknown')})
            exports=sum(m['export_relationships'] for m in modules if type(m.get('export_relationships')) is int)
            answer='REA inspected this source without executing it. Module format: '+(', '.join(formats) or 'not classified')+'. Observed export relationships: '+str(exports)+'. These are structural findings; they do not establish arbitrary runtime behavior.'
            result['finding']['answer']=answer
            result['finding']['source']['limitations']='Static inspection of one uploaded source file. Dependencies, execution behavior and unsupported file formats are outside this inspection.'
            result['report']='Your question: '+job['question']+'\n\n'+answer+'\n\nSource SHA-256: '+N.digest(source)+'\nREA evidence: '+evidence['evidence_id']+'\n\nModule evidence:\n'+json.dumps(modules,indent=2)+'\n\nThe uploaded program was not executed. Review this finding before saving it.'
            if not cancel.exists():atomic(spool/(jid+'.result.json'),{'result':result})
    except Exception:
        if not cancel.exists():atomic(spool/(jid+'.result.json'),{'error':'inspection failed'})
    finally:
        path.unlink(missing_ok=True);running.unlink(missing_ok=True);cancel.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--spool',required=True);p.add_argument('--node',required=True);p.add_argument('--rea',required=True);p.add_argument('--once',action='store_true');a=p.parse_args()
    spool=Path(a.spool);node,rea=R.rea_paths(a.node,a.rea)
    while True:
        (spool/'heartbeat').touch();(spool/'heartbeat').chmod(0o660)
        now=time.time()
        for path in spool.iterdir():
            if path.name!='heartbeat' and path.is_file() and now-path.stat().st_mtime>86400:path.unlink(missing_ok=True)
        jobs=sorted(spool.glob('*.job.json'),key=lambda f:f.stat().st_mtime)
        if jobs:process(jobs[0],spool,node,rea)
        if a.once:return
        time.sleep(1)


if __name__=='__main__':main()
