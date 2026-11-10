"""Materialize the three exact reviewed corner-safe templates, without native reruns."""
import argparse,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import load_project,file_digest
from scripts.ihp_guard_corner_conditioner import mask_identity
REPORT_SHA='46cf624f183d76bad3b8b33f0bf04f3e7a1c427d918c1d779b6a152e44de8111'

SAVED_PROJECT_SHA256={'rsil': '3ffa508d6d99c7404724d1068907150cd656e44d24c9143732e9bba6c2b115ab', 'rppd': '2026144ce5a66c41f3d5b567bbcf2186b288fe962239f8cf7b949085e8417ce5', 'rhigh': '98b2166ee0b2d0e8e0e3f6ccea0ba42358d96db487158d616b5a4608aa399016'}

def verify_saved_source(path,model):
    if file_digest(path)!=SAVED_PROJECT_SHA256[model]:raise ValueError('Changed authenticated saved template project, including ports/labels.')


def build(evidence):
    evidence=Path(evidence)
    if file_digest(evidence/'qualification.json')!=REPORT_SHA:raise ValueError('Unreviewed native source evidence.')
    report=json.loads((evidence/'qualification.json').read_text())
    if report['status']!='PASS' or not report['implementation_unchanged']:raise ValueError('Native source evidence did not pass.')
    templates={}
    for model in ('rsil','rppd','rhigh'):
        folder=evidence/(model+'-all100');row=json.loads((folder/'record.json').read_text());verify_saved_source(folder/'saved.icproj',model);p=load_project(folder/'saved.icproj')
        if row not in report['cases']:raise ValueError('Template case differs from authenticated aggregate.')
        if row['status']!='PASS' or mask_identity(p)!=row['conditioning']['conditioned_mask_sha256']:raise ValueError('Changed corrected template source.')
        if any(file_digest(folder/f"physical-{x['rotation']}"/'report.json')!=x['report_sha256'] for x in row['layouts']):raise ValueError('Native case report changed.')
        layers={l['name']:[l['gds'],l['datatype']] for l in p['pdk']['layers']};c=p['cells'][0]
        shapes=[dict(kind=s['kind'],layer=layers[s['layer']],points=s['points'],holes=s.get('holes',[])) for s in c['shapes']]
        ports=[dict(name=v['name'],layer=layers[v['layer']],point=v['point']) for v in c['layout_ports']]
        templates[model]=dict(shapes=shapes,ports=ports,mask_sha256=mask_identity(p),source_record_sha256=file_digest(folder/'record.json'),conditioning=row['conditioning'])
    return dict(schema=1,recipe='ihp-resistor-guard-corner-safe-v1',native_equivalence=False,qualified=False,source_report_sha256=REPORT_SHA,contract_sha256=report['contract_sha256'],tool_profile_sha256=report['tool_profile_sha256'],conditioner_sha256=file_digest(ROOT/'scripts/ihp_guard_corner_conditioner.py'),templates=templates)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--evidence',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(build(a.evidence),sort_keys=True,separators=(',',':'))+'\n');print(file_digest(a.output))
