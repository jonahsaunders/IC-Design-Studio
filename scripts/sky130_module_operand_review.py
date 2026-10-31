"""Bind empty module operands only to spacing and overlap catalog records."""
import argparse,csv,io,json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from icstudio import digital_sky130_module_absence as checks
from scripts import sky130_metal_width_review as previous_review

delivery=previous_review.delivery
ROOT=delivery.ROOT
PREVIOUS='docs/validation/sky130-metal-width-2026-10-15.json'
PREVIOUS_SHA='dc2bf2368356b30d63a0da93fd30ab61741b6196c9b421023c70f21f1fda3c5c'
OUTPUT=ROOT/'docs/validation/sky130-module-operand-2026-10-15.json'


def source_proof(folder,catalog):
    delivery.require(checks.MODULE==(81,10),'Changed module census purpose.')
    raw={key:delivery.checked(Path(folder)/key,digest) for key,digest in checks.SOURCE['files'].items()}
    def rows(key):return list(csv.DictReader(io.StringIO(raw[key].decode())))
    layers=rows('docs/rules/gds_layers.csv')
    marker=[r for r in layers if r['Layer name']=='areaid.mt']
    delivery.require(len(marker)==1 and marker[0]==dict(zip(
        ('Layer name','Purpose','GDS layer:datatype','Description'),
        ('areaid.mt','identifier','81:10','Location of e-test modules within the frame'))),'Changed module marker purpose.')
    descriptions=list(csv.reader(io.StringIO(raw['docs/rules/layers/table-c4b-layer-description.csv'].decode())))
    c4=[r for r in descriptions if r and r[0]=='areaid.mt{81:10}']
    delivery.require(len(c4)==1 and c4[0][1:3]==['areaid module cut','areaid.mod'] and
        'Also used in drc/cldrc for rules to cell edge.' in c4[0][3],'Changed module-cut description.')
    manual=rows('docs/rules/periphery/p018-x_dotdash.csv')
    ordinary=[r for r in manual if r['Name']=='(x.\\n12a\\n12b\\n12c)']
    huge=[r for r in manual if r['Name']=='(x.12d)']
    overlap=[r for r in manual if r['Name']=='(x.16)']
    delivery.require(len(ordinary)==1 and 'Spacing of :drc_tag:`areaid.mt` to any non-ID layer' in ordinary[0]['Description'] and
        'Enclosure of any non-ID layer by :drc_tag:`areaid.mt`' in ordinary[0]['Description'],'Changed x.12 operand semantics.')
    delivery.require(len(huge)==2 and all(r['Description'].startswith('Spacing of :drc_tag:`areaid.mt` to huge_metX') for r in huge),
        'Changed x.12d module-spacing operand.')
    delivery.require(len(overlap)==1 and overlap[0]['Description'].startswith('Die must not overlap :drc_tag:`areaid.mt`'),
        'Changed x.16 module-overlap operand.')
    indexed={r['id']:r for r in catalog['rows']};errors={r['ID']:r for r in rows('docs/rules/errors.csv')}
    bindings={}
    for key,check in checks.CHECKS.items():
        literal=(check['limit_um']+' min. spacing of moduleCutAREA & '+check['other_operand']
                 if check['operation']=='spacing' else 'extentDie must not overlap moduleCutAREA')
        delivery.require((indexed[key]['rule'],indexed[key]['description'])==(check['rule'],literal) and
            (errors[key]['Name'],errors[key]['Description'])==(check['rule'],literal),'Changed literal binary module record: '+key)
        bindings[key]=dict(catalog=indexed[key],check=check)
    return dict(source=checks.SOURCE,module_marker=marker[0],module_description=c4[0],
        manual=ordinary+huge+overlap,bindings=bindings,interpretation=checks.SCOPE,
        proof='Each bound message names moduleCutAREA as an operand of spacing or overlap. The matching manual operation explicitly uses areaid.mt, and both GDS and C4 bind that marker to 81:10. An empty known operand gives no pairs or intersections regardless of the unknown other operand. No construction for q0/q1, huge_metX or extentDie is assumed.',
        unresolved='The x.12 enclosure companions and every present-module case remain unresolved; absent boundaries cannot satisfy enclosure or establish full-chip context.')


def build(workspace=None,case=None,progress=None):
    workspace=Path(workspace or ROOT.parents[1]).resolve()
    previous=json.loads(delivery.checked(ROOT/PREVIOUS,PREVIOUS_SHA))
    fresh=previous_review.build(workspace,case,progress);catalog=json.loads((ROOT/delivery.queue.CATALOG).read_bytes())
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';delivery.fixture.unpack(delivery.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
    for row in fresh['cases']:
        original=delivery.pick(previous,row['case'])
        delivery.require(row['gds_sha256']==original['gds_sha256'] and row['counts']==original['counts'],
            'Metal-width replay differs from preceding reference catalog.')
        path=workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        report=checks.audit(path);checks.evaluate(report,row['gds_sha256'],row['top'])
        delivery.require(all(r['disposition']=='absent-operand' for r in report['rows']),'Reference module operand is present.')
        row['rows']=delivery.apply_rows(row['rows'],report['rows'],catalog,'module_absence',row['provenance'])
        row['counts']=dict(Counter(r['disposition'] for r in row['rows']));row['measurements']['module_absence']=report
        row['remaining_batches']=delivery.queue.partition([r for r in row['rows'] if r['disposition']=='unreviewed'])
        if progress:progress(dict(case=row['case'],stage='empty-module-operand-reviewed',counts=row['counts']))
    fresh.update(status='corrected-catalog-module-operand-reviewed',predecessor=dict(path=PREVIOUS,sha256=PREVIOUS_SHA),
        verification_mode='authenticated-baseline-plus-fresh-metal-width-and-module')
    fresh['inputs'][PREVIOUS]=PREVIOUS_SHA
    fresh['proofs']['module_absence']=proof
    for path in (Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_module_absence.py'):
        fresh['source_files'][path.relative_to(ROOT).as_posix()]=delivery.sha(path)
    fresh['source_files']=dict(sorted(fresh['source_files'].items()))
    fresh['scope']=fresh['scope'].replace('Only the new metal-width checker executes here.',
        'The three metal-width checks and the module census execute here.')
    fresh['scope']+=' The module census is freshly executed: 35 binary spacing/overlap records have an empty known module operand. Enclosure companions and present-module geometry remain unresolved.'
    fresh['retained_baseline']['execution']='The family/package catalog and its 1193 decisions are authenticated retained results. Three metal-width checks and the 35-record module census execute freshly. Current application, export and regression validation is recorded separately.'
    return fresh


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path)
    p.add_argument('--case',choices=delivery.queue.CASES);p.add_argument('--output',type=Path,default=OUTPUT);a=p.parse_args()
    a.output.write_bytes((json.dumps(build(a.workspace,a.case,lambda r:print(json.dumps(r),flush=True)),indent=2,ensure_ascii=False)+'\n').encode())
