"""Authenticate retained coverage and freshly measure three metal-width bounds."""
import argparse,copy,csv,io,json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from icstudio import digital_sky130_metal_width_bounds as checks
from scripts import sky130_family_package_review as previous_review
from scripts import sky130_retained_catalog as retained

delivery=previous_review.delivery
ROOT=delivery.ROOT
PREVIOUS='docs/validation/sky130-family-package-2026-10-15.json'
PREVIOUS_SHA='c217dcab9c14c96a402c9e513b66a5e36aa6653b502314e6444a4f7a28959cda'
OUTPUT=ROOT/'docs/validation/sky130-metal-width-2026-10-15.json'


def source_proof(folder,catalog):
    raw={key:delivery.checked(Path(folder)/key,digest) for key,digest in checks.SOURCE['files'].items()}
    mapping=checks.SOURCE['layer_map'];metadata=json.loads(delivery.checked(ROOT/mapping['path'],mapping['sha256']))
    native=checks.SOURCE['native'];native_raw=delivery.checked(ROOT/native['path'],native['sha256'])
    delivery.require(metadata['sources']['native']['sha256']==native['sha256'],'Changed native fill provenance.')
    lines=[' '.join(s.split()) for s in native_raw.decode().splitlines()]
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    mappings={}
    for n,(name,layer) in enumerate(checks.LAYERS.items(),1):
        found=[r for r in layers if r['Layer name']==name and r['Purpose']=='drawing, text']
        delivery.require(len(found)==1 and found[0]['GDS layer:datatype']=='%s:%s'%layer['drawing'],'Changed metal drawing purpose.')
        fill=[r for r in metadata['layers'] if tuple(r['pair'])==layer['fill'] and any(
            a['name']=='MET'+str(n)+'FILL' and a['purpose']=='fill' and a['source']=='native' for a in r['aliases'])]
        delivery.require(len(fill)==1,'Changed native fill purpose.')
        output=[f'layer MET{n} allm{n}','calma %s %s'%layer['drawing']]
        output_fill=[f'layer MET{n}FILL m{n}fill',f'labels m{n}fill','calma %s %s'%layer['fill']]
        for block in (output,output_fill):
            delivery.require(sum(lines[i:i+len(block)]==block for i in range(len(lines)))==1,'Changed native output construction.')
        guarded={tuple(r['pair']) for r in metadata['layers'] if any(a['name'] in (name,'cmm'+str(n)) for a in r['aliases'])
                 and tuple(r['pair'])!=layer['drawing'] and tuple(r['pair']) not in
                 {(layer['drawing'][0],d) for d in checks.ANNOTATIONS}}
        delivery.require(guarded==set(layer['guards']),'Incomplete alternate metal-purpose guard set.')
        mappings[name]=dict(drawing=found[0],fill=fill[0],native_output=output,native_fill_output=output_fill,
            guards=[r for r in metadata['layers'] if tuple(r['pair']) in guarded])
    indexed={r['id']:r for r in catalog['rows']};errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    bindings={}
    for key,check in checks.CHECKS.items():
        literal=str(check['limit_nm']//1000)+' max width of '+check['target']+' under pad metal'
        delivery.require((indexed[key]['rule'],indexed[key]['description'])==('pad.19',literal) and
            (errors[key]['Name'],errors[key]['Description'])==('pad.19',literal),'Changed literal maximum-width rule.')
        bindings[key]=dict(catalog=indexed[key],check=check)
    return dict(source=checks.SOURCE,bindings=bindings,layer_purposes=mappings,interpretation=checks.SCOPE,
        proof='Every connected conductor is contained in a strip whose width is at most the source maximum. A subset beneath any pad stays in that strip, so cannot have greater local thickness. Bounding boxes are measured after complete drawn/fill union. Large boxes and alternate input purposes remain unresolved; neither absent pads nor an invented pad boundary supplies the proof.',
        unresolved='No under-pad minimum-width/spacing, pad selector, mask-generation or package acceptance is inferred.')


def build(workspace=None,case=None,progress=None):
    workspace=Path(workspace or ROOT.parents[1]).resolve()
    previous,authentication=retained.load()
    fresh=copy.deepcopy(previous)
    delivery.require(case is None or case in delivery.queue.CASES,'Unknown reference case.')
    fresh['selected_cases']=[case] if case else list(delivery.queue.CASES)
    fresh['cases']=[r for r in fresh['cases'] if r['case'] in fresh['selected_cases']]
    fresh['source_files']=dict(authentication['authenticated_sources'])
    fresh['inputs'].update({PREVIOUS:PREVIOUS_SHA,retained.AUDIT:retained.AUDIT_SHA})
    fresh['retained_baseline']=authentication
    fresh['verification_mode']='authenticated-baseline-plus-fresh-metal-width'
    catalog=json.loads((ROOT/delivery.queue.CATALOG).read_bytes())
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';delivery.fixture.unpack(delivery.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
    for row in fresh['cases']:
        path=workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        delivery.require(delivery.sha(path)==row['gds_sha256'],'Layout differs from authenticated baseline.')
        report=checks.audit(path);checks.evaluate(report,row['gds_sha256'],row['top'])
        delivery.require(all(r['disposition']=='executed-reviewed' for r in report['rows']),'Reference metal-width bound needs review.')
        row['rows']=delivery.apply_rows(row['rows'],report['rows'],catalog,'metal_width_bounds',row['provenance'])
        row['counts']=dict(Counter(r['disposition'] for r in row['rows']));row['measurements']['metal_width_bounds']=report
        row['remaining_batches']=delivery.queue.partition([r for r in row['rows'] if r['disposition']=='unreviewed'])
        if progress:progress(dict(case=row['case'],stage='retained-catalog-with-fresh-metal-width',counts=row['counts']))
    fresh.update(status='corrected-catalog-metal-width-reviewed',predecessor=dict(path=PREVIOUS,sha256=PREVIOUS_SHA))
    fresh['proofs']['metal_width_bounds']=proof
    for path in (Path(__file__),Path(checks.__file__),Path(retained.__file__),ROOT/'tests/test_sky130_retained_catalog.py',
                 ROOT/'tests/test_sky130_metal_width_bounds.py',ROOT/checks.SOURCE['native']['path']):
        fresh['source_files'][path.relative_to(ROOT).as_posix()]=delivery.sha(path)
    fresh['source_files']=dict(sorted(fresh['source_files'].items()))
    fresh['scope']=(authentication['execution']+' Three under-pad maximum-width records satisfy stronger global bounds on '
        'all drawn-plus-native-fill conductors; no pad selector is inferred. The authenticated catalog retains 1,193 '
        'prior reference-specific decisions, including explicit exemptions, advisories and absence proofs. '
        'Its previous source proofs and measurements are retained verbatim, not described as fresh geometry execution. '
        'No complete-chip, required density, new extraction or foundry acceptance is inferred.')
    return fresh


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path)
    p.add_argument('--case',choices=delivery.queue.CASES);p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--check',action='store_true');a=p.parse_args()
    raw=(json.dumps(build(a.workspace,a.case,lambda r:print(json.dumps(r),flush=True)),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:delivery.require(a.output.read_bytes()==raw,'Saved metal-width review differs.')
    else:a.output.write_bytes(raw)
