"""Bind 44 numerical boundary-interaction checks to exact retained references."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_boundary_interactions as checks
from scripts import sky130_label_subject_review as labels
from scripts import sky130_catalog_queue as queue
from scripts import check_sky130_filled_replay as fixture

ROOT = queue.ROOT
LABELS = 'docs/validation/sky130-label-subjects-2026-10-15.json'
LABELS_SHA = '346291eb600c055674d5ed305de2109249b590ebcddb58aa388761591f66e495'
PREVIOUS = 'docs/validation/sky130-vpp-geometry-2026-10-15.json'
PREVIOUS_SHA = '7dc92a2f624aa7a04aae74735a46649398144308510d88fc2ff6e850582e8eaa'
OUTPUT = ROOT/'docs/validation/sky130-boundary-interactions-2026-10-15.json'


def reconstruct(reader):
    catalog, baselines, _ = labels.reconstruct(reader)
    stages = [reader.read(LABELS,LABELS_SHA), reader.read(PREVIOUS,PREVIOUS_SHA)]
    for stage in stages:
        for path,digest in stage['inputs'].items(): reader.read(path,digest)
        for before,prior in zip(baselines,stage['cases']):
            if before['case'] != prior['case'] or before['gds_sha256'] != prior['original_gds_sha256']:
                raise ValueError('Changed boundary-interaction predecessor identity.')
            rows=queue.apply_decisions(before['rows'],prior['original_new_error_decisions'],catalog)
            if dict(Counter(r['disposition'] for r in rows)) != prior['original_error_counts']:
                raise ValueError('Boundary-interaction predecessor does not reconstruct.')
            before.update(rows=rows,counts=prior['original_error_counts'])
    return catalog,baselines,stages[-1]


def source_proof(folder,catalog):
    raw={name:(Path(folder)/name).read_bytes() for name in checks.SOURCE['files']}
    for name,digest in checks.SOURCE['files'].items():
        if queue.sha(raw[name]) != digest: raise ValueError('Changed boundary-interaction source: '+name)
    indexed={r['id']:r for r in catalog['rows']}
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    for name,pair in checks.LAYERS.items():
        rows=[r for r in layers if r['Layer name']==name and 'drawing' in r['Purpose'].split(', ')]
        if [r['GDS layer:datatype'] for r in rows] != ['%s:%s'%pair]:
            raise ValueError('Changed boundary-interaction target purpose: '+name)
        if ('text' in rows[0]['Purpose'].split(', ')) != (name in checks.TEXT_ALLOWED):
            raise ValueError('Changed boundary-interaction text semantics.')
    c4b=raw['docs/rules/layers/table-c4b-layer-description.csv'].decode()
    for text in ('areaid.mt{81:10},areaid module cut','areaid.sl{81:1},areaid sealring'):
        if text not in c4b: raise ValueError('Changed explicit boundary purpose.')
    for key,check in checks.CHECKS.items():
        target=check['target']
        text=(target+' drawn layer cannot straddle areaid:ModuleCut' if check['boundary']=='module' else
              target+(' must not straddle SEALID' if check['operation']=='straddle' else ' must not overlap SEALID'))
        if indexed[key]['description'] != text or indexed[key]['rule'] != check['rule']:
            raise ValueError('Changed boundary-interaction catalog binding: '+key)
    if len(checks.CHECKS)!=44: raise ValueError('Changed selected boundary-interaction set.')
    return dict(source=checks.SOURCE,bindings={key:indexed[key] for key in checks.CHECKS},
                interpretation=checks.SCOPE,unresolved_package_scribe_records=['r1436','r1440','r1442','r1445','r1446'])


def build(workspace=None):
    workspace=Path(workspace or ROOT.parents[1]); reader=queue.RetainedReader()
    catalog,baselines,previous=reconstruct(reader); cases=[]; batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs'; manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
        for entry in manifest['cases']:
            name=entry['case']; before=next(c for c in baselines if c['case']==name)
            prior=next(c for c in previous['cases'] if c['case']==name)
            original=checks.audit(folder/entry['gds'])
            corrected=checks.audit(workspace/'outputs/sky130-application-boundary-v1/linux'/name/'sky130-pin-export/final.gds')
            if original['gds_sha256'] != before['gds_sha256'] or corrected['gds_sha256'] != prior['corrected_gds_sha256']:
                raise ValueError('Changed boundary-interaction reference identity.')
            for report in (original,corrected): checks.evaluate(report,report['gds_sha256'],report['top'])
            if original['measurements'] != corrected['measurements']:
                raise ValueError('Boundary interactions changed with die-outline removal.')
            rows=queue.apply_decisions(before['rows'],original['rows'],catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches != current: raise ValueError('Reference queues differ.')
            batches=current
            cases.append(dict(case=name,original_gds_sha256=original['gds_sha256'],original_measurement=original,
                original_new_error_decisions=original['rows'],original_error_counts=dict(Counter(r['disposition'] for r in rows)),
                corrected_gds_sha256=corrected['gds_sha256'],corrected_boundary_interactions=corrected))
    paths=[Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_boundary_interactions.py',
           ROOT/'icstudio/digital_sky130_rules.py',ROOT/'icstudio/digital_sky130_rule_worker.py',
           ROOT/'tests/test_sky130_application_rules.py']
    return dict(schema=1,chunk=6,status='selected-boundary-interactions-verified',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in paths},
        proof=proof,cases=cases,remaining_original_batches=[dict(id=b['id'],count=b['count'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Forty-four numerical boundary-interaction checks are mandatory in Finish and saved-result validation. '
              'These reference blocks have no module-cut or seal markers; their absence proves no supplied-boundary crossing, '
              'not completeness of a chip frame or an exemption from enclosure/spacing. Nonempty controls are separate. '
              'The original catalog retains 529 unreviewed records; historical decisions remain bound to their exact GDS.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path)
    p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--check',action='store_true');a=p.parse_args()
    raw=(json.dumps(build(a.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:
        if a.output.read_bytes()!=raw: raise ValueError('Saved boundary-interaction review differs.')
    else:a.output.write_bytes(raw)
    print(json.dumps({c['case']:c['original_error_counts'] for c in json.loads(raw)['cases']}))
