"""Bounded local native checks of six saved source-GUI guard projects, not installed acceptance."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest,load_project
from icstudio.layout_verification import reference,run
from scripts.qualify_ihp_guard_vias import verify_tool_profile,EXPECTED_PROFILE_SHA256

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gui',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True);ap.add_argument('--tool-profile',type=Path,required=True);a=ap.parse_args()
    gui=a.gui.resolve();r=json.loads((gui/'report.json').read_text());before=json.loads((gui/'source-before.json').read_text());after=json.loads((gui/'source-after.json').read_text())
    if file_digest(gui/'files.json')!=r['files_sha256']:raise ValueError('Changed GUI evidence inventory.')
    files=json.loads((gui/'files.json').read_text())
    if r['status']!='passed' or not r['source_unchanged'] or r['installed_acceptance'] or before!=after:raise ValueError('Requires unchanged passing source-GUI evidence, not an installed claim.')
    if any(file_digest(ROOT/name)!=sha for name,sha in before.items()):raise ValueError('GUI source identity differs.')
    if {(c['model'],c['rotation']) for c in r['lifecycle']}!={(m,a) for m in ('rsil','rppd','rhigh') for a in (0,90)} or len(r['lifecycle'])!=6:raise ValueError('Incomplete GUI cases.')
    if file_digest(a.tool_profile)!=EXPECTED_PROFILE_SHA256:raise ValueError('Unreviewed local tool profile.')
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen')};profile=json.loads(a.tool_profile.read_text());verify_tool_profile(profile,tools)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);records=[]
    for c in r['lifecycle']:
        saved=c['with_ports'];path=Path(saved['project']).resolve()
        if not path.is_relative_to(gui) or file_digest(path)!=saved['project_sha256']:raise ValueError('Changed GUI saved project.')
        p=load_project(path);refpath=Path(saved['reference']).resolve()
        if not refpath.is_relative_to(gui) or file_digest(refpath)!=files.get(refpath.relative_to(gui).as_posix()):raise ValueError('Changed or external GUI reference.')
        cell=next(x for x in p['cells'] if x['id']==p['top']);ref=reference(refpath.read_text(),cell['name']);folder=out/c['case'];result=run(p,p['top'],folder,tools,ref)
        records.append(dict(case=c['case'],status=result['status'],project_sha256=file_digest(path),reference_sha256=file_digest(refpath),report_sha256=file_digest(folder/'report.json')));print(c['case'],result['status'],result.get('error',''),flush=True)
    verify_tool_profile(profile,tools)
    unchanged=all(file_digest(ROOT/name)==sha for name,sha in before.items())
    result=dict(schema=1,status='PASS' if unchanged and all(x['status']=='passed' for x in records) else 'FAIL',source_unchanged=unchanged,source_gui_report_sha256=file_digest(gui/'report.json'),tool_profile_sha256=file_digest(a.tool_profile),runner_sha256=file_digest(Path(__file__)),installed_acceptance=False,qualified=False,chunk_complete=False,cases=records)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
