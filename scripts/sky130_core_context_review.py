"""Measure explicit core/LDNTM subjects on original and corrected SKY130 streams.

The original catalog advances only on its own freshly measured input identities.
The corrected streams carry a separate current 45-message application report;
the remaining original catalog is not silently transferred to those new files.
"""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import klayout.db as k
from icstudio import digital_sky130_catalog_context as context
from scripts import sky130_catalog_queue as queue
from scripts import sky130_grid_catalog_review as grid
from scripts import check_sky130_filled_replay as fixture

ROOT=queue.ROOT
OUTPUT=ROOT/'docs/validation/sky130-core-context-2026-10-15.json'
GRID='docs/validation/sky130-grid-catalog-2026-10-15.json'
GRID_SHA='fd51a2cb9cc93c26399b95ed6c5a11b916dc95ced93fdd1d257ec5fd71e63c94'
BOUNDARY='docs/validation/sky130-boundary-export-2026-10-15.json'
BOUNDARY_SHA='f4dde4c80783eb58a044ae24d9bda3034f44b71201937da42ad420414042b17b'


def source_proof(source,catalog):
    queue.validate_catalog(catalog);indexed={r['id']:r for r in catalog['rows']}
    raw={name:(Path(source)/name).read_bytes() for name in context.SOURCE['files']}
    for name,digest in context.SOURCE['files'].items():
        if queue.sha(raw[name])!=digest:raise ValueError('Changed catalog-context source: '+name)
    descriptions=list(csv.reader(io.StringIO(raw['docs/rules/layers/table-c4b-layer-description.csv'].decode())))
    row=next(r for r in descriptions if r and r[0]=='areaid.ce{81:2}')
    if row[1:4]!=['areaid core','areaid.cor','Memory core (memory cells and approved on-pitch only)']:
        raise ValueError('Changed memory-core selector.')
    layers=list(csv.reader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    for name,purpose,pair in (('areaid.ce','identifier','81:2'),('ldntm','drawing','11:44')):
        if [r[:3] for r in layers if r and r[0]==name]!=[[name,purpose,pair]]:
            raise ValueError('Changed catalog subject layer binding.')
    for key in context.CORE_IDS:
        if not re.search(r'\bin (core|COREID)\b',indexed[key]['description']):
            raise ValueError('The catalog no longer explicitly selects core: '+key)
    explicit={'r1132':'Unapproved cells contain areaid.ce layer','r1037':'ldntm not allowed outside areaid.ce',
        'r1485':'0 min. enclosure of ldntm by CLNTM','r1486':'ldntm must be enclosed by CLNTM'}
    for key,text in explicit.items():
        if indexed[key]['description']!=text:raise ValueError('Changed explicit subject message: '+key)
    ids=[key for entry in context.SUBJECTS.values() for key in entry['ids']]
    if len(ids)!=len(set(ids)) or len(ids)!=37:raise ValueError('Unexpected core/LDNTM subject set.')
    return dict(source=context.SOURCE,core_layer=row,bindings={key:indexed[key] for key in ids},
        interpretation='Complete absence of raw areaid.ce resolves only the explicitly core-selected targets and marker-approval message. '
        'Complete raw LDNTM absence resolves its own outside-core prohibition and two explicit LDNTM enclosure targets. '
        'A core-like name or suffix is insufficient; requirements to enclose other nonempty targets in core or generated masks remain open.')


def build(workspace=None):
    workspace=Path(workspace or ROOT.parents[1]);reader=queue.RetainedReader()
    catalog,baselines,_=grid.reconstruct(reader)
    latest=reader.read(GRID,GRID_SHA);boundary=reader.read(BOUNDARY,BOUNDARY_SHA)
    for name,digest in latest['inputs'].items():reader.read(name,digest)
    for name,digest in boundary['source_files'].items():
        if queue.sha((ROOT/name).read_bytes())!=digest:raise ValueError('Changed boundary proof implementation: '+name)
    cases=[];batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
        for entry in manifest['cases']:
            name=entry['case'];before=next(c for c in baselines if c['case']==name)
            previous=next(c for c in latest['cases'] if c['case']==name)
            if not before['gds_sha256']==previous['gds_sha256']==entry['gds_sha256']:raise ValueError('Changed original reference identity.')
            rows=queue.apply_decisions(before['rows'],previous['new_error_decisions'],catalog)
            if dict(Counter(r['disposition'] for r in rows))!=previous['error_counts']:raise ValueError('Grid baseline does not reconstruct.')
            original=k.Layout();original.read(str(folder/entry['gds']));raw=context.measure(original)
            changes=[]
            for subject,selection in context.SUBJECTS.items():
                if raw[subject]!=0:raise ValueError('Original reference subject is present; numerical/approval review is required.')
                for key in selection['ids']:
                    changes.append(dict(id=key,disposition='absent-operand',subject=subject,pair=list(selection['pair']),raw_shapes=0))
            rows=queue.apply_decisions(rows,changes,catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Reference work queues differ.')
            batches=current
            correction=next(c for c in boundary['cases'] if c['case']==name)
            path=workspace/'outputs/sky130-application-boundary-v1/linux'/name/'sky130-pin-export/final.gds'
            if queue.sha(path.read_bytes())!=correction['gds_sha256']:raise ValueError('Changed corrected reference identity.')
            fresh=context.audit(path)
            if any(fresh['raw_counts'][key]!=raw[key] for key in context.SUBJECTS):raise ValueError('Subject census differs between original and corrected streams.')
            cases.append(dict(case=name,original_gds_sha256=entry['gds_sha256'],original_raw_counts=raw,
                original_new_error_decisions=changes,original_error_counts=dict(Counter(r['disposition'] for r in rows)),
                corrected_gds_sha256=correction['gds_sha256'],corrected_catalog_context=fresh))
    sources=(Path(__file__),Path(context.__file__),ROOT/'icstudio/digital_sky130_boundaries.py',
        ROOT/'icstudio/digital_sky130_rules.py',ROOT/'icstudio/digital_sky130_rule_worker.py',
        ROOT/'tests/test_sky130_catalog_context.py',ROOT/'tests/test_sky130_application_rules.py')
    return dict(schema=1,chunk=6,status='explicit-core-subjects-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in sources},
        proof=proof,cases=cases,remaining_original_batches=[dict(id=b['id'],count=b['count'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Thirty-seven explicit catalog subjects are freshly absent on both original and corrected references. '
        'Only the original-stream catalog is advanced to 614 unreviewed entries. The corrected streams carry separate '
        'current application context for those 37 subjects and eight boundary prohibitions; earlier 905 decisions are not implicitly rebound.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path)
    parser.add_argument('--output',type=Path,default=OUTPUT);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    raw=(json.dumps(build(args.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if args.output.read_bytes()!=raw:raise ValueError('Saved core-context review differs.')
    else:args.output.write_bytes(raw)
    print(json.dumps({c['case']:c['original_error_counts'] for c in json.loads(raw)['cases']}))
