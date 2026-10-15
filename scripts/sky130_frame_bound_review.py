"""Bind frame-margin measurements to exact catalog records without waiving missing context."""
import argparse,csv,io,json
from pathlib import Path
from tempfile import TemporaryDirectory
from icstudio import digital_sky130_frame_bounds as checks
from scripts import check_sky130_delivery_catalog as delivery

ROOT=delivery.ROOT
PREVIOUS='docs/validation/sky130-selected-targets-2026-10-15.json'
PREVIOUS_SHA='230efaf45aa2e74b19d4a5a366c9ce9f00fe1f223293584b75315505a221a2f4'
OUTPUT=ROOT/'docs/validation/sky130-frame-bounds-2026-10-15.json'


def source_proof(folder,catalog):
    raw={key:delivery.checked(Path(folder)/key,digest) for key,digest in checks.SOURCE['files'].items()}
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    for name,pair in (checks.LAYERS|checks.BOUNDARIES).items():
        alias={'frame':'areaid.ft','die':'areaid.dt'}.get(name,name)
        purpose='identifier' if name in checks.BOUNDARIES else 'drawing'
        found=[r for r in layers if r['Layer name']==alias and purpose in r['Purpose'].split(', ')]
        delivery.require(len(found)==1 and found[0]['GDS layer:datatype']=='%s:%s'%pair,'Changed frame-bound layer purpose.')
        if name in checks.LAYERS:
            delivery.require(('text' in found[0]['Purpose'].split(', '))==(name!='tap'),'Changed target text semantics.')
    manual={r['Name']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/periphery/p043-nsm_dotdash.csv'].decode()))}
    for name in ('nsm.3a','nsm.3b'):
        r=manual['('+name+')'];delivery.require(r['Value']=='3.000' and r['Unit']=='µm','Changed frame-bound threshold.')
    delivery.require(':drc_tag:`areaid.ft`' in manual['(nsm.3a)']['Description'] and
                     ':drc_tag:`areaid.dt`' in manual['(nsm.3b)']['Description'],'Changed frame/die meaning.')
    c4=raw['docs/rules/layers/table-c4b-layer-description.csv'].decode()
    delivery.require('areaid.ft{81:12},areaid frameRect' in c4 and 'areaid.dt{81:11},areaid die cut' in c4,
                     'Changed supplied boundary context.')
    indexed={r['id']:r for r in catalog['rows']}
    errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    bindings={}
    for key,check in checks.CHECKS.items():
        target=check['target'];rule=check['rule']
        literal=('3 min. enclosure of '+target+'_not_NSM3a_exempt by frameBndr' if check['boundary']=='frame' else
                 '3 min. spacing of '+target+'_not_NSM3b_exempt & dieCut')
        delivery.require((indexed[key]['rule'],indexed[key]['description'])==(rule,literal) and
                         (errors[key]['Name'],errors[key]['Description'])==(rule,literal),'Changed literal frame-bound target.')
        bindings[key]=dict(catalog=indexed[key],manual=manual['('+rule+')'],check=check)
    delivery.require(len(bindings)==18,'Incomplete frame-bound binding.')
    return dict(source=checks.SOURCE,bindings=bindings,interpretation=checks.SCOPE,
        proof='No exemptions are subtracted: each published selected target is a subset of its complete drawn layer. A square dilation contains the Euclidean radius-3um dilation. Satisfying these stronger bounds proves the selected requirement; failure does not disprove an exempted or Euclidean-only case.')


def build(workspace=None):
    workspace=Path(workspace or ROOT.parents[1]);previous=json.loads(delivery.checked(ROOT/PREVIOUS,PREVIOUS_SHA))
    catalog=json.loads((ROOT/delivery.queue.CATALOG).read_bytes())
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';delivery.fixture.unpack(delivery.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
    cases=[]
    for prior in previous['cases']:
        name=prior['case'];path=workspace/'outputs/sky130-application-boundary-v1/linux'/name/'sky130-pin-export/final.gds'
        report=checks.audit(path);checks.evaluate(report,prior['gds_sha256'],prior['top'])
        old={r['id']:r for r in prior['rows']}
        delivery.require(all(old[r['id']]['disposition']=='unreviewed' and r['disposition']=='unreviewed' and
                         r['reason']=='missing-boundary-context' for r in report['rows']),
                         'Reference frame context differs; review before changing coverage.')
        cases.append(dict(case=name,gds_sha256=prior['gds_sha256'],report=report,retained_catalog_counts=prior['counts'],
                          new_catalog_decisions=0))
    paths=[Path(__file__),Path(checks.__file__),ROOT/'icstudio/model.py',ROOT/'tests/test_sky130_frame_bounds.py',
           ROOT/'icstudio/digital_sky130_rule_worker.py',ROOT/'icstudio/digital_sky130_rules.py',ROOT/'tests/test_sky130_application_rules.py']
    return dict(schema=1,chunk=6,status='frame-bound-integration-reviewed',qualified=False,chunk_complete=False,
        predecessor=dict(path=PREVIOUS,sha256=PREVIOUS_SHA,scope='Retained complete reference catalog; this command reruns only frame bounds.'),
        source_files={p.relative_to(ROOT).as_posix():delivery.sha(p) for p in paths},proof=proof,cases=cases,
        scope='Eighteen numerical sufficient-bound checks are implemented for explicit frame/die context. All eighteen stay unreviewed on these blocks because their required markers are absent. Catalog totals do not change. Nonempty controls establish checker behavior, not reference-chip compliance.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--check',action='store_true');a=p.parse_args();raw=(json.dumps(build(a.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:delivery.require(a.output.read_bytes()==raw,'Saved frame-bound review differs.')
    else:a.output.write_bytes(raw)
