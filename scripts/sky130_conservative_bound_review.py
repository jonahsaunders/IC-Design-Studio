"""Prove four catalog limits by stronger bounds and 18 explicit blockage absences."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_conservative_bounds as checks
from scripts import sky130_selected_device_review as previous_review
from scripts import sky130_catalog_queue as queue
from scripts import check_sky130_filled_replay as fixture
from scripts.sky130_rule_inventory import manual_rows

ROOT=queue.ROOT
PREVIOUS='docs/validation/sky130-selected-devices-2026-10-15.json'
PREVIOUS_SHA='728bcf21dbc246cfa25a87129098afebafa01a2663e210dc87691ea0f2919b81'
OUTPUT=ROOT/'docs/validation/sky130-conservative-bounds-2026-10-15.json'


def reconstruct(reader):
    catalog,baselines,_=previous_review.reconstruct(reader);previous=reader.read(PREVIOUS,PREVIOUS_SHA)
    for path,digest in previous['inputs'].items():reader.read(path,digest)
    for before,prior in zip(baselines,previous['cases']):
        if before['case']!=prior['case'] or before['gds_sha256']!=prior['original_gds_sha256']:
            raise ValueError('Changed conservative-bound predecessor identity.')
        rows=queue.apply_decisions(before['rows'],prior['original_new_error_decisions'],catalog)
        rows=previous_review.apply_advisories(rows,prior['advisory_decisions'],catalog)
        if dict(Counter(r['disposition'] for r in rows))!=prior['original_error_counts']:
            raise ValueError('Conservative-bound predecessor does not reconstruct.')
        before.update(rows=rows,counts=prior['original_error_counts'])
    return catalog,baselines,previous


def source_proof(folder,catalog):
    raw={name:(Path(folder)/name).read_bytes() for name in checks.SOURCE['files']}
    for name,digest in checks.SOURCE['files'].items():
        if queue.sha(raw[name])!=digest:raise ValueError('Changed conservative-bound source: '+name)
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    descriptions=list(csv.reader(io.StringIO(raw['docs/rules/layers/table-c4b-layer-description.csv'].decode())))
    indexed={r['id']:r for r in catalog['rows']}
    errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    bindings={}
    for name,selection in checks.BLOCKS.items():
        pair=selection['pair']
        if [r['GDS layer:datatype'] for r in layers if r['Layer name']==name and r['Purpose']=='block']!=['%s:%s'%pair]:
            raise ValueError('Changed published IP blockage purpose.')
        match=[r for r in descriptions if r and r[0]==name+'.be{%s:%s}'%pair]
        if len(match)!=1 or 'blockage layer used for IP integration' not in match[0][3] or match[0][5]!='DRC':
            raise ValueError('Changed explicit IP blockage meaning.')
        for key in selection['ids']:
            row=indexed[key];error=errors[key]
            if row['description']!=error['Description'] or row['rule']!=error['Name'] or name+'Block' not in row['description']:
                raise ValueError('Changed exact blockage catalog record.')
            bindings[key]=dict(record=row,pair=list(pair),definition=match[0],
                proof='Every raw shape on the mandatory block purpose is counted. Absence only; present blockages stay unreviewed.')
    expected=dict(r471=('nsd.c1a','0.38 min. width of nsdm (opposite parallel)'),
        r487=('psd.c1a','0.38 min. width of psdm (opposite parallel)'),
        r520=('poly.c3','poly.c3: 0.175 min. spacing of poly (except for poly.c2)'),
        r521=('poly.c2','poly.c2: 0.160 min. spacing of poly for poly core gap'))
    for name,pair in checks.LAYERS.items():
        if [r['GDS layer:datatype'] for r in layers if r['Layer name']==name and 'drawing' in r['Purpose'].split(', ')]!=['%s:%s'%pair]:
            raise ValueError('Changed conservative-bound drawn purpose.')
    poly='docs/rules/periphery/p028-poly_dotdash.csv';implant='docs/rules/periphery/p032-n_psd_dotdash.csv'
    parents={row['rule']:row for path in (poly,implant) for row in manual_rows(raw[path],path)}
    for key,value in (('poly.2','0.210'),('n/ psd.1','0.380')):
        if parents[key]['value']!=value or parents[key]['unit']!='µm':raise ValueError('Changed sufficient bound or unit.')
    for key,check in checks.CHECKS.items():
        row=indexed[key]
        if (row['rule'],row['description'])!=expected[key] or errors[key]['Description']!=row['description']:
            raise ValueError('Changed exact conservative-bound catalog record.')
        bound=checks.BOUNDS[check['layer']]
        if bound['nm']<check['required_nm']:raise ValueError('Bound is weaker than the catalog limit.')
        bindings[key]=dict(record=row,bound=bound,
            proof='All merged drawn implant widths satisfy 380 nm, including every opposite-parallel subset.' if key in ('r471','r487') else
                  'All merged drawn poly spacing and notches satisfy 210 nm; this implies both 175 nm and 160 nm without invoking exceptions.')
    return dict(source=checks.SOURCE,bindings=bindings,parents=parents,interpretation=checks.SCOPE)


def build(workspace=None):
    workspace=Path(workspace or ROOT.parents[1]);reader=queue.RetainedReader()
    catalog,baselines,previous=reconstruct(reader);cases=[];batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder);proof=source_proof(folder/'sources',catalog)
        for entry in manifest['cases']:
            name=entry['case'];before=next(c for c in baselines if c['case']==name);prior=next(c for c in previous['cases'] if c['case']==name)
            original=checks.audit(folder/entry['gds'])
            corrected=checks.audit(workspace/'outputs/sky130-application-boundary-v1/linux'/name/'sky130-pin-export/final.gds')
            if original['gds_sha256']!=before['gds_sha256'] or corrected['gds_sha256']!=prior['corrected_gds_sha256']:
                raise ValueError('Changed conservative-bound reference identity.')
            for report in (original,corrected):
                checks.evaluate(report,report['gds_sha256'],report['top'])
                if Counter(r['disposition'] for r in report['rows'])!={'executed-reviewed':4,'absent-operand':18}:
                    raise ValueError('Reference does not establish every selected bound or blockage absence.')
            if original['measurements']!=corrected['measurements']:raise ValueError('Bound subjects changed during outline correction.')
            rows=queue.apply_decisions(before['rows'],original['rows'],catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Reference queues differ.')
            batches=current
            cases.append(dict(case=name,original_gds_sha256=original['gds_sha256'],original_measurement=original,
                original_new_error_decisions=original['rows'],original_error_counts=dict(Counter(r['disposition'] for r in rows)),
                corrected_gds_sha256=corrected['gds_sha256'],corrected_conservative_bounds=corrected))
    paths=[Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_conservative_bounds.py',
           ROOT/'icstudio/digital_sky130_rules.py',ROOT/'icstudio/digital_sky130_rule_worker.py',ROOT/'tests/test_sky130_application_rules.py']
    return dict(schema=1,chunk=6,status='conservative-bounds-and-ip-blockage-absence-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in paths},
        proof=proof,cases=cases,remaining_original_batches=[dict(id=b['id'],count=b['count'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Four limits are implied by passing stronger all-geometry checks; 18 explicit IP blockage subjects are absent. '
              'Failure of a sufficient bound leaves the actual rule unreviewed. Present blockage semantics and generated masks '
              'are not implemented. The original catalog retains 463 unreviewed records; chunk 6 remains incomplete.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--check',action='store_true');a=p.parse_args();raw=(json.dumps(build(a.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:
        if a.output.read_bytes()!=raw:raise ValueError('Saved conservative-bound review differs.')
    else:a.output.write_bytes(raw)
    print(json.dumps({c['case']:c['original_error_counts'] for c in json.loads(raw)['cases']}))
