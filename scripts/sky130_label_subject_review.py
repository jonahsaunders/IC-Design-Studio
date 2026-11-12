"""Bind explicit label and raw-target absence on original and corrected references."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from icstudio import digital_sky130_catalog_labels as subjects
from scripts import sky130_catalog_queue as queue
from scripts import sky130_grid_catalog_review as grid
from scripts import check_sky130_filled_replay as fixture

ROOT=queue.ROOT
OUTPUT=ROOT/'docs/validation/sky130-label-subjects-2026-10-15.json'
PREVIOUS='docs/validation/sky130-core-context-2026-10-15.json'
PREVIOUS_SHA='b3fb813d1b15b33210be66ef61d0b5ce91e1918ac933426359df4bad02ccc1d6'
GRID='docs/validation/sky130-grid-catalog-2026-10-15.json'
GRID_SHA='fd51a2cb9cc93c26399b95ed6c5a11b916dc95ced93fdd1d257ec5fd71e63c94'


def reconstruct(reader):
    catalog,baselines,_=grid.reconstruct(reader)
    vertex=reader.read(GRID,GRID_SHA);previous=reader.read(PREVIOUS,PREVIOUS_SHA)
    for data in (vertex,previous):
        for name,digest in data['inputs'].items():reader.read(name,digest)
    for before in baselines:
        v=next(c for c in vertex['cases'] if c['case']==before['case'])
        p=next(c for c in previous['cases'] if c['case']==before['case'])
        if not before['gds_sha256']==v['gds_sha256']==p['original_gds_sha256']:
            raise ValueError('Changed retained original-stream identity.')
        rows=queue.apply_decisions(before['rows'],v['new_error_decisions'],catalog)
        if dict(Counter(r['disposition'] for r in rows))!=v['error_counts']:raise ValueError('Grid baseline does not reconstruct.')
        rows=queue.apply_decisions(rows,p['original_new_error_decisions'],catalog)
        if dict(Counter(r['disposition'] for r in rows))!=p['original_error_counts']:raise ValueError('Core baseline does not reconstruct.')
        before.update(rows=rows,counts=p['original_error_counts'])
    return catalog,baselines,previous


def source_proof(source,catalog):
    queue.validate_catalog(catalog);indexed={r['id']:r for r in catalog['rows']}
    raw={name:(Path(source)/name).read_bytes() for name in subjects.SOURCE['files']}
    for name,digest in subjects.SOURCE['files'].items():
        if queue.sha(raw[name])!=digest:raise ValueError('Changed label-subject source: '+name)
    layers=list(csv.reader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    aliases={'low_tap_density':'areaid.ld','injection':'areaid.ij','prune':'LVS prune','capm':'capm','cap2m':'cap2m','pad':'pad'}
    for name,entry in subjects.RAW.items():
        purpose='identifier' if name in ('low_tap_density','injection') else 'drawing'
        if [r[2] for r in layers if r and r[0]==aliases[name] and purpose in r[1].split(', ')]!=['%d:%d'%entry['pair']]:
            raise ValueError('Changed explicit raw target purpose.')
    parents=raw['docs/rules/periphery/p018-x_dotdash.csv'].decode()
    messages={}
    for prefix,entry in subjects.LABELS.items():
        if prefix=='condiode':continue
        layer='met'+prefix[1:] if prefix.startswith('m') else prefix
        for token in entry['tokens']:
            if token not in parents:raise ValueError('Missing published label token.')
        texts=[f'Floating {prefix}_float or {prefix}_tie text not over {layer}',
            f'{layer} marked with {prefix}_float not floating',
            f'Floating {layer} marked with {prefix}_tie at chiplevel without connecting',
            f'Metal on {layer} is texted as both tied and floating (Chip level)']
        messages.update(zip(entry['ids'],texts))
    messages.update({'r1207':'condiode label must be in isolated pwell',
        's7':'partnum*block pcell should be used instead of partnum* pcells',
        'r380':'prune must overlap areaidMTorSC','r326':'0.42 min. enclosure of capm by moduleCutAREA',
        'r327':'0.42 min. spacing of moduleCutAREA & cap2m','r328':'0.42 min. enclosure of cap2m by moduleCutAREA',
        'r1404':'pad inside frame or moduleCut without text label',
        's72':'areaid.ld not allowed within 50.0 um of ESDID','s73':'areaid.ij not allowed within 150.0 um of ESDID'})
    selected={key for group in subjects.GROUPS.values() for entry in group.values() for key in entry['ids']}
    if set(messages)!=selected or len(selected)!=37:raise ValueError('Changed explicit selected message set.')
    for key,text in messages.items():
        if indexed[key]['description']!=text:raise ValueError('Changed literal message: '+key)
    return dict(source=subjects.SOURCE,bindings={key:indexed[key] for key in messages},
        normalization='NFKC, casefold, remove whitespace; any embedded token prevents an absence claim. All purposes and reachable cells are searched.',
        interpretation='Absence concerns the actual selected target, never an enclosing module/frame region. '
        'Partnum-cell naming is separate from the whole-chip part-number requirement. '
        'Seven unmarked floating-net messages, redundant vias, substrate straddling and chip identity remain open.')


def build(workspace=None):
    workspace=Path(workspace or ROOT.parents[1]);reader=queue.RetainedReader()
    catalog,baselines,previous=reconstruct(reader);cases=[];batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder);proof=source_proof(folder/'sources',catalog)
        for entry in manifest['cases']:
            name=entry['case'];before=next(c for c in baselines if c['case']==name)
            prior=next(c for c in previous['cases'] if c['case']==name)
            if before['gds_sha256']!=entry['gds_sha256']:raise ValueError('Changed original reference.')
            original=subjects.audit(folder/entry['gds'])
            if original['counts']!={'absent-operand':37}:raise ValueError('Selected reference subject requires further review.')
            changes=original['rows'];rows=queue.apply_decisions(before['rows'],changes,catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Original reference queues differ.')
            batches=current
            path=workspace/'outputs/sky130-application-boundary-v1/linux'/name/'sky130-pin-export/final.gds'
            corrected=subjects.audit(path)
            if corrected['gds_sha256']!=prior['corrected_gds_sha256']:raise ValueError('Changed corrected reference.')
            if original['census']!=corrected['census']:raise ValueError('Subject census differs between original and corrected streams.')
            cases.append(dict(case=name,original_gds_sha256=entry['gds_sha256'],original_measurement=original,
                original_new_error_decisions=changes,original_error_counts=dict(Counter(r['disposition'] for r in rows)),
                corrected_gds_sha256=corrected['gds_sha256'],corrected_catalog_labels=corrected))
    sources=(Path(__file__),Path(subjects.__file__),ROOT/'icstudio/digital_sky130_rules.py',
        ROOT/'icstudio/digital_sky130_rule_worker.py',ROOT/'tests/test_sky130_catalog_labels.py',ROOT/'tests/test_sky130_application_rules.py')
    return dict(schema=1,chunk=6,status='explicit-label-subjects-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in sources},
        proof=proof,cases=cases,remaining_original_batches=[dict(id=b['id'],count=b['count'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Thirty-seven explicit label, named-cell and raw-layer targets are absent on both original and corrected streams. '
        'The original-stream catalog advances to 577 unreviewed entries. Corrected streams retain this separate new mandatory '
        '37-message report alongside the 45-message core/boundary context. Historical full-catalog decisions remain source-specific.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--check',action='store_true');a=p.parse_args();raw=(json.dumps(build(a.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:
        if a.output.read_bytes()!=raw:raise ValueError('Saved label-subject review differs.')
    else:a.output.write_bytes(raw)
    print(json.dumps({c['case']:c['original_error_counts'] for c in json.loads(raw)['cases']}))
