"""Replay the full reference catalog with fourteen global drawn-feature size bounds."""
import argparse,csv,io,json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from icstudio import digital_sky130_scribe_bounds as checks
from scripts import sky130_well_bound_review as previous_review

delivery=previous_review.delivery
ROOT=delivery.ROOT
PREVIOUS='docs/validation/sky130-well-bounds-2026-10-15.json'
PREVIOUS_SHA='491ace42e2777551aba3b34549f39efcf5b80a9d19483f9cb71aee79aafd0491'
OUTPUT=ROOT/'docs/validation/sky130-scribe-bounds-2026-10-15.json'


def source_proof(folder,catalog):
    raw={key:delivery.checked(Path(folder)/key,digest) for key,digest in checks.SOURCE['files'].items()}
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    mappings={}
    for name,pair in checks.LAYERS.items():
        found=[r for r in layers if r['Layer name']==name and 'drawing' in r['Purpose'].split(', ')]
        delivery.require(len(found)==1 and found[0]['GDS layer:datatype']=='%s:%s'%pair,
                         'Changed scribe-size drawn layer purpose.')
        delivery.require(('text' in found[0]['Purpose'].split(', '))==(name in checks.TEXT_LAYERS),
                         'Changed scribe-size text meaning.')
        mappings[name]=found[0]
    indexed={r['id']:r for r in catalog['rows']}
    errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    bindings={}
    for key,check in checks.CHECKS.items():
        literal='Wide '+check['target']+' >= 10.0x10.0um within 150.0 of scribe junction'
        delivery.require((indexed[key]['rule'],indexed[key]['description'])==('scribe.5',literal) and
                         (errors[key]['Name'],errors[key]['Description'])==('scribe.5',literal),
                         'Changed literal drawn scribe-size target.')
        bindings[key]=dict(catalog=indexed[key],check=check)
    delivery.require(len(bindings)==14,'Incomplete drawn scribe-size source binding.')
    return dict(source=checks.SOURCE,bindings=bindings,layer_purposes=mappings,interpretation=checks.SCOPE,
        proof='A connected feature with one bounding-box dimension below 10 um cannot contain a 10-by-10 um feature, including rotated squares. The whole drawing is measured without spatial exclusions or hierarchy-local splitting. This excludes the wide subject globally and therefore in any 150 um junction neighborhood. The converse is not used: a large box proves neither a wide region nor a nearby junction. Missing junction definitions cannot turn a candidate into a pass.',
        unresolved='No junction construction or generated-mask alias is inferred. The fourteen mask companion records r1390-r1403 are not included.')


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
                         'Fresh corrected replay differs from the well-bound baseline.')
        path=workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        report=checks.audit(path);checks.evaluate(report,row['gds_sha256'],row['top'])
        delivery.require(all(r['disposition']=='executed-reviewed' for r in report['rows']),
                         'Reference scribe-size bounds require further review.')
        row['rows']=delivery.apply_rows(row['rows'],report['rows'],catalog,'scribe_bounds',row['provenance'])
        row['counts']=dict(Counter(r['disposition'] for r in row['rows']))
        row['measurements']['scribe_bounds']=report
        row['remaining_batches']=delivery.queue.partition([r for r in row['rows'] if r['disposition']=='unreviewed'])
        if progress:progress(dict(case=row['case'],stage='scribe-size-bounds-replayed',counts=row['counts']))
    fresh.update(status='corrected-catalog-scribe-size-bounds-reviewed',predecessor=dict(path=PREVIOUS,sha256=PREVIOUS_SHA))
    fresh['proofs']['scribe_bounds']=proof
    for path in (Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_scribe_bounds.py'):
        fresh['source_files'][path.relative_to(ROOT).as_posix()]=delivery.sha(path)
    fresh['source_files']=dict(sorted(fresh['source_files'].items()))
    fresh['scope']+=' Fourteen drawn-layer scribe records satisfy a global sufficient size bound on every connected feature. No junction context or generated mask is inferred; candidate features remain unresolved in general designs.'
    return fresh


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--case',choices=delivery.queue.CASES)
    p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--check',action='store_true');a=p.parse_args()
    raw=(json.dumps(build(a.workspace,a.case,lambda r:print(json.dumps(r),flush=True)),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:delivery.require(a.output.read_bytes()==raw,'Saved scribe-size review differs from fresh execution.')
    else:a.output.write_bytes(raw)
