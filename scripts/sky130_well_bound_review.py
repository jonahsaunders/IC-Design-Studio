"""Replay the corrected reference catalog with three drawn-well sufficient bounds."""
import argparse,csv,io,json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from icstudio import digital_sky130_well_bounds as checks
from icstudio import digital_sky130_frame_bounds as frame
from scripts import sky130_selected_target_review as previous_review

delivery=previous_review.delivery
ROOT=delivery.ROOT
PREVIOUS='docs/validation/sky130-selected-targets-2026-10-15.json'
PREVIOUS_SHA='230efaf45aa2e74b19d4a5a366c9ce9f00fe1f223293584b75315505a221a2f4'
OUTPUT=ROOT/'docs/validation/sky130-well-bounds-2026-10-15.json'
LITERAL={
    'r923':('pwde.6','1.00 min. enclosure of pwde_uhvi by dnwell_uhvi'),
    'r924':('pwbm.5','0.84 min. spacing of pwbm_holes'),
    'r931':('uhvi.3','pwbmNotLOWVTID must be enclosed by uhvi')}


def source_proof(folder,catalog):
    raw={key:delivery.checked(Path(folder)/key,digest) for key,digest in checks.SOURCE['files'].items()}
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    mappings={}
    for name,pair in checks.LAYERS.items():
        found=[r for r in layers if r['Layer name']==name and r['Purpose']=='drawing']
        delivery.require(len(found)==1 and found[0]['GDS layer:datatype']=='%s:%s'%pair,
                         'Changed well-bound drawn layer purpose.')
        mappings[name]=found[0]
    delivery.require(mappings['pwde']['Description']=='Regions to receive p-well drain-extended implants' and
        mappings['pwbm']['Description']=='Regions (in UHVI) blocked from p-well implant (DE MOS devices only)',
        'Changed drawn implant semantics.')
    manual={r['Name']:r for key,value in raw.items() if '/periphery/' in key
            for r in csv.DictReader(io.StringIO(value.decode()))}
    names={'r923':'(pwdem.6)','r924':'(pwbm.5)','r931':'(uhvi.3.-)'}
    meanings={
        'r923':'Min enclosure of pwdem:dg by deep nwell inside UHVI',
        'r924':'Min Space between two pwbm holes inside UHVI',
        'r931':'pwbm.dg must be enclosed by UHVI (exempt inside :drc_tag:`areaid.lw`)'}
    indexed={r['id']:r for r in catalog['rows']}
    errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    bindings={}
    for key,literal in LITERAL.items():
        r=manual[names[key]]
        delivery.require((indexed[key]['rule'],indexed[key]['description'])==literal and
                         (errors[key]['Name'],errors[key]['Description'])==literal,'Changed literal well-bound target.')
        delivery.require(r['Description']==meanings[key] and r['Value']==r['Unit']=='N/A',
                         'Changed manual well-bound context.')
        bindings[key]=dict(catalog=indexed[key],manual=r,check=checks.CHECKS[key])
    return dict(source=checks.SOURCE,bindings=bindings,layer_purposes=mappings,interpretation=checks.SCOPE,
        proof='The catalog names pwde, matching the drawn implant GDS name. The manual calls the corresponding drain-extended implant pwdem; it supplies UHV selection context but no numerical value. The 1.00 and 0.84 um limits come only from the pinned finite catalog literals. Whole drawn PWDE within DNWELL intersect UHVI proves enclosure for the UHV subset. Whole merged PWBM holes include every selected hole pair; no UHVI clipping is performed before finding holes. Whole PWBM enclosure proves enclosure of PWBM with LOWVTID subtracted. Square dilation is stronger than Euclidean distance; no failed bound is promoted as a foundry violation.')


def build(workspace=None,case=None,progress=None):
    workspace=Path(workspace or ROOT.parents[1]).resolve()
    previous=json.loads(delivery.checked(ROOT/PREVIOUS,PREVIOUS_SHA))
    fresh=previous_review.build(workspace,case,progress)
    catalog=json.loads((ROOT/delivery.queue.CATALOG).read_bytes())
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';delivery.fixture.unpack(delivery.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
    for row in fresh['cases']:
        original=delivery.pick(previous,row['case'])
        delivery.require(row['gds_sha256']==original['gds_sha256'] and row['counts']==original['counts'],
                         'Fresh corrected replay differs from the selected-target baseline.')
        path=workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        report=checks.audit(path);checks.evaluate(report,row['gds_sha256'],row['top'])
        delivery.require(report['unreviewed']==0,'Reference well bounds require further review.')
        row['rows']=delivery.apply_rows(row['rows'],report['rows'],catalog,'well_bounds',row['provenance'])
        row['counts']=dict(Counter(r['disposition'] for r in row['rows']))
        row['measurements']['well_bounds']=report
        frame_report=frame.audit(path);frame.evaluate(frame_report,row['gds_sha256'],row['top'])
        delivery.require(all(r['reason']=='missing-boundary-context' for r in frame_report['rows']),
                         'Reference frame context changed; review catalog decisions.')
        row['measurements']['frame_bounds']=frame_report
        row['remaining_batches']=delivery.queue.partition([r for r in row['rows'] if r['disposition']=='unreviewed'])
        if progress:progress(dict(case=row['case'],stage='well-bounds-replayed',counts=row['counts']))
    fresh.update(status='corrected-catalog-well-bounds-reviewed',predecessor=dict(path=PREVIOUS,sha256=PREVIOUS_SHA))
    fresh['proofs']['well_bounds']=proof
    for path in (Path(__file__),Path(checks.__file__),Path(frame.__file__),ROOT/'tests/test_sky130_well_bounds.py',
                 ROOT/'icstudio/digital_sky130_rule_worker.py',ROOT/'icstudio/digital_sky130_rules.py',
                 ROOT/'tests/test_sky130_application_rules.py'):
        fresh['source_files'][path.relative_to(ROOT).as_posix()]=delivery.sha(path)
    fresh['source_files']=dict(sorted(fresh['source_files'].items()))
    fresh['scope']+=' Three well bounds have no targets on the references. Nonempty controls separately establish sufficient-bound behavior. Eighteen frame bounds are also measured and remain unreviewed for missing boundary context.'
    return fresh


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--case',choices=delivery.queue.CASES)
    p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--check',action='store_true');a=p.parse_args()
    raw=(json.dumps(build(a.workspace,a.case,lambda r:print(json.dumps(r),flush=True)),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:delivery.require(a.output.read_bytes()==raw,'Saved well-bound review differs from fresh execution.')
    else:a.output.write_bytes(raw)
