"""Exercise the default RF n-well binding through fresh-project installation.

Three geometries at three corners and three sampled temperatures; independent
explicit calls and polarity/width faults. These are samples, not safe ratings.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest, save_project
from icstudio.pdks import PDKRegistry
from icstudio.project_hub import inventory, build_project
from scripts.sky130_rf_source import PROMOTED, REVISION
from scripts.qualify_sky130_rf_application import qualify as application


def qualify(executable, output, pilot=False):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    registry=PDKRegistry(out/'registry')
    rows,notes=inventory(registry)
    if notes:raise ValueError('Default package inventory has diagnostics: '+str(notes))
    row=next(r for r in rows if r['id']=='sky130A' and r['status']=='Available offline')
    project=build_project(registry,row,'RF default acceptance','empty')['project']
    source=Path(project['pdk']['package_root'])
    bundled=ROOT/'icstudio/assets/pdks/sky130A/package.json'
    if (project['pdk']['revision']!=REVISION or file_digest(bundled)!=PROMOTED
            or json.loads((source/'package.json').read_bytes())!=json.loads(bundled.read_bytes())):
        raise ValueError('Fresh project did not select the reviewed RF default.')
    save_project(project,out/'fresh.icproj')
    conditions=[('nominal',27)] if pilot else [(c,t) for c in ('nominal','ss','ff') for t in (27,-40,125)]
    result=application(executable,source,out/'application',models=('ps2nw',),conditions=conditions,default_binding=True)
    report=dict(status=result['status'],chunk_complete=False,qualified=False,default_promoted=True,
        scope=__doc__,host=sys.platform,revision=REVISION,manifest_sha256=PROMOTED,
        installed_manifest_sha256=file_digest(source/'package.json'),
        engine_sha256=file_digest(executable),runner_sha256=file_digest(__file__),
        application_report_sha256=file_digest(out/'application/report.json'),
        conditions=len(conditions),geometries=3,independent_analysis_comparisons=2*len(conditions),
        compared_device_vectors=6*len(conditions),compared_samples=168*len(conditions),
        detected_faulted_instances=6*len(conditions),automatic_runtime_checks=len(result['automatic_runtime_checks']),
        limitations=['Sampled model integration; no continuous operating envelope or safe ratings.',
                    'No new substrate/parasitic, statistical, measured-silicon or physical qualification.',
                    'The pw2dn candidate remains unavailable in the default; its isolation is unresolved.',
                    'Source application acceptance; installed-release acceptance is separate.'])
    (out/'report.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--ngspice',required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--pilot',action='store_true')
    a=ap.parse_args();print(json.dumps(qualify(a.ngspice,a.output,a.pilot),indent=2))
