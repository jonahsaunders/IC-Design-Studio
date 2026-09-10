"""Pinned SKY130 subset acceptance: good inverter and deliberate physical faults.

Run on a host with durable I/O and installed Magic, Netgen and ngspice. Missing
engines or unavailable durable storage produce a blocked report, never a pass.
"""
import argparse,json,os,shutil,sys,traceback,subprocess,platform,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,digest,save_project
from icstudio.build_info import WORKFLOW_SOURCE_HASH


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pdk',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    for name in ('magic','netgen','ngspice'):ap.add_argument('--'+name,default=shutil.which(name))
    a=ap.parse_args();out=a.out.resolve()
    if out.exists() and any(out.iterdir()):ap.error('Use a new, empty qualification output directory.')
    out.mkdir(parents=True,exist_ok=True)
    report={'workflow_hash':WORKFLOW_SOURCE_HASH,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'platform':platform.platform(),'status':'blocked','cases':[],'limitations':['This qualifies only the listed pinned-process fixtures, never arbitrary designs.']}
    try:
        from icstudio.process_adapters import SKY130
        manifest=a.pdk/'package.json'
        lock=json.loads((ROOT/'examples/sky130-qualification-lock.json').read_text())
        if file_digest(manifest)!=lock['manifest_sha256']:raise ValueError('The pinned SKY130 package manifest changed. Recreate it with scripts/prepare_sky130_qualification.py.')
        m=json.loads(manifest.read_text())
        for relative,expected in m['files'].items():
            target=(a.pdk/relative).resolve()
            if not target.is_relative_to(a.pdk.resolve()) or file_digest(target)!=expected:raise ValueError('Locked process file changed: '+relative)
        tech=m['technology'];tech['package_root']=str(a.pdk.resolve());tech['package_lock']={'id':m['id'],'revision':m['revision'],'files':m['files']}
        if (m['id'],m['revision'],digest(m['files']))!=(lock['id'],lock['revision'],lock['files_hash']):
            raise ValueError('Use the committed SKY130 qualification lock. Other packages need a separate qualification record.')
        assets=SKY130.engine_assets(tech)
        report['process']={'id':m['id'],'revision':m['revision'],'files_hash':digest(m['files']),'engine_assets':{k:{'path':str(v.relative_to(a.pdk.resolve())),'sha256':file_digest(v)} for k,v in assets.items()}}
        tools={name:getattr(a,name) for name in ('magic','netgen','ngspice')};missing=[name for name,path in tools.items() if not path or not Path(path).is_file()]
        report['missing_tools']=missing
        if not missing:
            from icstudio.engines import execute
            version=execute([tools['magic'],'--version'],out,timeout=15)
            required,actual=magic_versions(assets['technology'].read_text(),version)
            report['magic_version']={'required':required,'actual':actual}
        try:
            with (out/'durability.dat').open('wb') as f:f.write(b'qualification durability probe');f.flush();os.fsync(f.fileno())
            report['durability']={'status':'passed'}
        except OSError as e:report['durability']={'status':'blocked','errno':e.errno,'error':str(e)}
        from icstudio.sky130_layout import reference_project,generate_inverter,layers
        from icstudio.layout import rect
        from icstudio.physical import erase,connectivity
        from icstudio.silicon_flow import run
        p,cid=reference_project(tech);generate_inverter(p,cid);cases=[('nominal',p,None)]
        q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);c['shapes'].append(rect(layers(tech)['m1'],10000,0,100,100));cases.append(('narrow-metal',q,'drc'))
        q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);erase(c,layers(tech)['m1'],[1400,3000,1900,3500]);cases.append(('route-open',q,'lvs'))
        q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);poly=next(s for s in c['shapes'] if s['layer']==layers(tech)['poly'] and s.get('generated_device'));poly['points'][1][0]+=50;cases.append(('wrong-channel-length',q,'lvs'))
        for name,design,failed_stage in cases:
            item={'name':name,'expected_failure_stage':failed_stage,'design_hash':digest(design),'status':'not_run'}
            item['native_terminal_findings']=[i['code'] for i in connectivity(design,cid)['issues']]
            if not missing and report['durability']['status']=='passed':
                save_project(design,out/(name+'.icproj'));result=run(design,cid,out/name,tools)
                accepted=accept_result(result,failed_stage,out/name)
                item.update(status='passed' if accepted else 'failed',engine_report=name+'/report.json')
            else:item['reason']='Missing external engines or blocked durable storage.'
            report['cases'].append(item)
        report['status']='passed' if all(c['status']=='passed' for c in report['cases']) else 'failed' if any(c['status']=='failed' for c in report['cases']) else 'blocked'
    except Exception as e:report.update(status='failed',error=str(e),traceback=traceback.format_exc())
    (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


def magic_versions(technology,version_output):
    required=re.search(r'(?m)^\s*requires\s+magic-(\d+\.\d+\.\d+)',technology)
    actual=re.search(r'\b(\d+\.\d+\.\d+)\b',version_output)
    if not required or not actual:raise ValueError('Cannot establish the Magic version required by the locked technology.')
    if tuple(map(int,actual[1].split('.')))<tuple(map(int,required[1].split('.'))):
        raise ValueError('The pinned PDK requires Magic '+required[1]+' or newer; found '+actual[1]+'. Build scripts/build_physical_engines.py first.')
    return required[1],actual[1]


def accept_result(result,failed_stage,directory):
    """A tool/setup error must never masquerade as a detected physical fault."""
    if failed_stage is None:return result['status']=='passed'
    stages=result.get('stages',[])
    failed=next((i for i,s in enumerate(stages) if s['status']=='failed'),None)
    if failed is None or stages[failed]['name']!=failed_stage:return False
    if any(s['status']!='passed' for s in stages[:failed]):return False
    if any(s['status']!='not_run' for s in stages[failed+1:]):return False
    if failed_stage=='drc':return result.get('drc_count',0)>0 and (directory/'drc/findings.tsv').is_file()
    if failed_stage=='lvs':
        log=directory/'lvs/lvs.log'
        if not log.is_file():return False
        text=log.read_text(errors='replace').lower()
        return any(marker in text for marker in ('netlists do not match','circuits do not match','property errors','disconnected node:','(no matching pin)'))
    return False


if __name__=='__main__':raise SystemExit(main())
