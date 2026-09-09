"""Probe the real durable-write and recovery path without weakening it."""
import argparse,json,os,platform,sys,traceback,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    from icstudio import recovery
    from icstudio.model import example,clone
    from icstudio.build_info import WORKFLOW_SOURCE_HASH
    report={'platform':platform.platform(),'workflow_hash':WORKFLOW_SOURCE_HASH,'directory':str(out),'free_bytes':shutil.disk_usage(out).free,'checks':[],'native_windows':sys.platform=='win32'}
    for name in ('fsync','recovery_roundtrip_and_previous_fallback'):
        try:
            if name=='fsync':
                with (out/'probe.dat').open('wb') as f:f.write(b'durable probe');f.flush();os.fsync(f.fileno())
            else:
                p=example('empty');recovery.write(p,out);q=clone(p);q['name']='Second recovery';q['revision']+=1;recovery.write(q,out)
                target=out/(p['id']+'.icproj');restored,_=recovery.read(target);assert restored['name']==q['name']
                target.write_text('{invalid');restored,_=recovery.read(target);assert restored['name']==p['name']
            report['checks'].append({'name':name,'status':'passed'})
        except Exception as e:report['checks'].append({'name':name,'status':'blocked' if isinstance(e,OSError) else 'failed','errno':getattr(e,'errno',None),'error':str(e),'traceback':traceback.format_exc()})
    report['status']='passed' if all(c['status']=='passed' for c in report['checks']) else 'blocked' if all(c['status'] in ('passed','blocked') for c in report['checks']) else 'failed'
    (out/'storage.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
