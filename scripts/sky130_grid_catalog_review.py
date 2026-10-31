"""Review explicit catalog grid subjects without accepting the broader x.1 rules.

The assumptions table supplies the 0.005 um drawn grid for the 35 named drawn
layers. Mask/edit/package operands are resolved only when raw shapes and texts
are absent: their conflicting unit wording is not silently corrected. Metop
aliases and the separate text-anchor diagnostics remain open.
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
from scripts import sky130_catalog_queue as queue
from scripts import sky130_grid_geometry as grid
from scripts import sky130_standard_cell_wl_review as wl
from scripts import check_sky130_filled_replay as fixture
from scripts.sky130_global_geometry import LAYER_MAP_PATH
from scripts.sky130_rule_inventory import validate_unreviewed, manual_rows

ROOT=queue.ROOT
OUTPUT=ROOT/'docs/validation/sky130-grid-catalog-2026-10-15.json'
PREVIOUS='docs/validation/sky130-standard-cell-wl-2026-10-15.json'
PREVIOUS_SHA='bfe5423c9e4efadf24e134f904e39eda4df016ebd60de9fc40ae33e80945d7fe'
GEOMETRY='docs/validation/sky130-geometry-reconciliation-2026-10-14.json'
GEOMETRY_SHA='6a61be0415cc68efd4e591428c1ac7e2531cac731e6396da953f4485104608d3'
PARENT='docs/rules/periphery/p018-x_dotdash.csv'
ASSUMPTIONS='docs/rules/assumptions/01-general.csv'
DRAWN=tuple('nwell diff dnwell tap lvtn hvtp hvi tunm poly npc nsdm psdm licon1 li1 mcon met1 via met2 vhvi via2 met3 via3 met4 via4 met5 nsm pad ldntm hvntm pnp capacitor ncm inductor rpm hvtr'.split())
PACKAGE={'pmm':(85,44),'rdl':(74,20),'pmm2':(77,20),'ubm':(127,21),'bump':(127,22)}
IDS=tuple('r'+str(i) for i in range(113) if not 35<=i<=42)
UNRESOLVED=tuple('r'+str(i) for i in (*range(35,43),*range(150,158)))


def reconstruct(reader):
    catalog,baselines=queue.reconstruct(reader)
    latest=reader.read(PREVIOUS,PREVIOUS_SHA)
    for name,digest in latest['inputs'].items():reader.read(name,digest)
    local=reader.read(wl.PREVIOUS,wl.PREVIOUS_SHA)
    for before in baselines:
        old=next(c for c in local['cases'] if c['case']==before['case'])
        current=next(c for c in latest['cases'] if c['case']==before['case'])
        if not before['gds_sha256']==old['gds_sha256']==current['gds_sha256']:
            raise ValueError('Changed retained layout identity.')
        rows=queue.apply_decisions(before['rows'],old['new_error_decisions'],catalog)
        rows=wl.apply_decisions(rows,current['new_error_decisions'],catalog)
        if dict(Counter(r['disposition'] for r in rows))!=current['error_counts']:
            raise ValueError('Latest standard-cell checkpoint does not reconstruct.')
        before.update(rows=rows,counts=current['error_counts'])
    return catalog,baselines,latest


def source_proof(source,catalog,inventory,retained_geometry):
    queue.validate_catalog(catalog);validate_unreviewed(inventory);grid.layer_metadata()
    files={}
    for name in (PARENT,ASSUMPTIONS,'docs/rules/errors.csv','docs/rules/gds_layers.csv'):
        raw=(Path(source)/name).read_bytes()
        if queue.sha(raw)!=inventory['source_files'][name]['sha256']:
            raise ValueError('Changed grid source: '+name)
        files[name]=queue.sha(raw)
    assumptions=list(csv.reader(io.StringIO((Path(source)/ASSUMPTIONS).read_text(encoding='utf-8'))))
    drawn=[r for r in assumptions if r and r[0]=='Grid Size - Drawn']
    if len(drawn)!=1 or drawn[0][2:4]!=['um','0.005']:
        raise ValueError('Changed explicit drawn-grid units or value.')
    parents=list(manual_rows((Path(source)/PARENT).read_bytes(),PARENT))[:2]
    known={r['id']:r for r in inventory['rule_rows']}
    for row,rule,value in zip(parents,('x.1a','x.1b'),('0.001','0.005')):
        if (row['rule']!=rule or row['value']!=value or row['unit']!='mm' or
                any(row[key]!=known[row['id']][key] for key in ('rule','description','value','unit','record'))):
            raise ValueError('Changed periphery grid discrepancy; review the new source.')
    layers=json.loads(LAYER_MAP_PATH.read_bytes())['layers'];by_pair={tuple(r['pair']):r['aliases'] for r in layers}
    mappings={}
    for record in retained_geometry['new_error_bindings'].values():
        if 'operand' not in record:continue
        mapping=(record['alias'],record['purpose'],tuple(record['pair']))
        if record['operand'] in mappings and mappings[record['operand']]!=mapping:
            raise ValueError('Inconsistent retained exact operand mapping.')
        mappings[record['operand']]=mapping
    bindings={};indexed={r['id']:r for r in catalog['rows']}
    for key in IDS:
        row=indexed[key];match=re.fullmatch(r'off (0\.00[15]) grid (\S+) vertex',row['description'])
        if match is None:raise ValueError('Changed explicit grid catalog description.')
        value,operand=match.groups();number=int(key[1:]);nm=5 if value=='0.005' else 1
        if row['rule']!=('x.1b' if nm==5 else 'x.1a'):raise ValueError('Changed grid catalog parent.')
        if number<35:
            if operand!=DRAWN[number] or nm!=5:raise ValueError('Changed exact drawn operand order.')
            matches=[(tuple(layer['pair']),a) for layer in layers for a in layer['aliases']
                     if a['name']==operand and 'drawing' in a['purpose'].split(', ') and a['source']=='published']
            if len(matches)!=1:raise ValueError('Ambiguous published drawn grid purpose.')
            pair,alias=matches[0];scope='drawn-vertices'
        else:
            if operand in PACKAGE:name,purpose,pair=operand,'drawing',PACKAGE[operand]
            elif operand in mappings:name,purpose,pair=mappings[operand]
            else:raise ValueError('Grid operand has no explicit retained mapping: '+operand)
            matches=[a for a in by_pair[pair] if a['name']==name and a['purpose'].replace(' ','').lower()==purpose]
            if not matches:raise ValueError('Changed retained mask/package purpose.')
            alias=next((a for a in matches if a['source']=='published'),matches[0]);scope='absence-only'
        expected_nm=1 if pair in grid.FINE_GRID else 5
        if expected_nm!=nm:raise ValueError('Diagnostic grid does not match the literal catalog grid.')
        bindings[key]=dict(operand=operand,pair=list(pair),grid_nm=nm,scope=scope,alias=alias,
                           source_record=row['record'],rule=row['rule'],description=row['description'])
    if len(bindings)!=105 or set(bindings)&set(UNRESOLVED):raise ValueError('Wrong reviewed grid set.')
    return dict(files=files,drawn_grid_source=dict(record=drawn[0],grid_nm=5),
        periphery_discrepancy=parents,layer_map_sha256=queue.sha(LAYER_MAP_PATH.read_bytes()),
        retained_aliases=dict(path=GEOMETRY,sha256=GEOMETRY_SHA),bindings=bindings,
        unresolved_alias_records=list(UNRESOLVED),
        interpretation='The explicitly named drawn vertex checks use the assumptions table 0.005 um grid. '
            'The periphery table still prints mm. Non-drawn records are accepted only for completely absent raw subjects, '
            'without choosing a disputed grid. Text anchors and the metop1-8 aliases remain separate; neither x.1 parent is promoted.')


def measure(layout):
    result=grid.check(layout)
    if any(r['violations'] for r in result['checks'] if r['rule'].startswith('profile.')):
        raise ValueError('Unsupported geometry for catalog vertex review.')
    return result


def decisions(measured,bindings):
    if set(bindings)!=set(IDS):raise ValueError('Missing or unrelated grid binding.')
    checks={r['rule']:r['violations'] for r in measured['checks']}
    expected={'profile.transforms','profile.path_semantics','profile.shape_semantics',
              'profile.known_purposes','profile.nonempty','grid.boundaries','grid.text_anchors'}
    if (len(checks)!=len(measured['checks']) or set(checks)!=expected or
            any(type(v)is not int or v<0 for v in checks.values())):
        raise ValueError('Missing, duplicate or invalid diagnostic check.')
    if any(v for key,v in checks.items() if key.startswith('profile.')):
        raise ValueError('Catalog decisions require supported input geometry.')
    layers={tuple(row['pair']):row for row in measured['layers']}
    if len(layers)!=len(measured['layers']):raise ValueError('Duplicate measured layer.')
    if (sum(r['shapes'] for r in layers.values())!=measured['geometry_shapes'] or
            sum(r['off_grid_vertices'] for r in layers.values())!=checks['grid.boundaries'] or
            sum(r['off_grid_texts'] for r in layers.values())!=checks['grid.text_anchors']):
        raise ValueError('Incomplete layer census or inconsistent diagnostic totals.')
    result=[]
    for key,binding in bindings.items():
        stats=layers.get(tuple(binding['pair']),dict(shapes=0,vertices=0,off_grid_vertices=0,texts=0,off_grid_texts=0))
        if 'grid_nm' in stats and stats['grid_nm']!=binding['grid_nm']:
            raise ValueError('Measured and catalog grids differ.')
        fields=('shapes','vertices','off_grid_vertices','texts','off_grid_texts')
        witness={field:stats[field] for field in fields}
        if any(type(v)is not int or v<0 for v in witness.values()):raise ValueError('Invalid grid measurement.')
        if stats['shapes']==stats['texts']==0:disposition,status='absent-operand','PASS'
        elif binding['scope']=='drawn-vertices' and stats['vertices']>0:
            disposition,status=('executed-reviewed','PASS') if stats['off_grid_vertices']==0 else ('unreviewed','FAIL')
        else:disposition,status='unreviewed','NEEDS_REVIEW'
        result.append(dict(id=key,binding=key,disposition=disposition,status=status,witness=witness))
    return result


def build():
    reader=queue.RetainedReader();catalog,baselines,previous=reconstruct(reader)
    geometry=reader.read(GEOMETRY,GEOMETRY_SHA);inventory=reader.read(wl.INVENTORY);cases=[];batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog,inventory,geometry)
        for entry in manifest['cases']:
            name=entry['case'];before=next(c for c in baselines if c['case']==name)
            prior=next(c for c in previous['cases'] if c['case']==name)
            if before['gds_sha256']!=entry['gds_sha256']:raise ValueError('Different reference layout.')
            layout=k.Layout();layout.read(str(folder/entry['gds']));measured=measure(layout)
            if measured['top']!=entry['top']:raise ValueError('Different reference top cell.')
            changes=decisions(measured,proof['bindings'])
            if any(r['status']!='PASS' for r in changes):raise ValueError('A reference grid subject fails or needs further review.')
            rows=queue.apply_decisions(before['rows'],changes,catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Reference work queues differ.')
            batches=current
            cases.append(dict(case=name,gds_sha256=entry['gds_sha256'],diagnostic=measured,
                new_error_decisions=changes,error_counts=dict(Counter(r['disposition'] for r in rows)),
                periphery_counts=prior['periphery_counts'],open_periphery=prior['open_periphery']))
    sources=(Path(__file__),Path(grid.__file__),Path(queue.__file__),Path(wl.__file__),Path(fixture.__file__),
             ROOT/'tests/test_sky130_grid_catalog.py',ROOT/'tests/test_sky130_grid_density.py')
    return dict(schema=1,chunk=6,status='explicit-catalog-grid-subjects-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in sources},
        bundle=dict(path=fixture.BUNDLE.relative_to(ROOT).as_posix(),sha256=fixture.BUNDLE_SHA256),proof=proof,cases=cases,
        remaining_batches=[dict(id=b['id'],count=b['count'],next_action=b['next_action'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Only 105 explicitly mapped vertex subjects are resolved: nonempty drawn vertices use the published 5 nm drawn grid; '
              'other records require complete raw shape/text absence. Sixteen metop grid/angle records, the broader periphery unit discrepancy '
              'and all seven text-anchor diagnostic findings remain open. No x.1 parent or application coverage is promoted.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    parser.add_argument('--output',type=Path,default=OUTPUT);args=parser.parse_args()
    raw=(json.dumps(build(),indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if args.output.read_bytes()!=raw:raise ValueError('Saved grid catalog review differs.')
    else:args.output.write_bytes(raw)
    print(json.dumps({c['case']:c['error_counts'] for c in json.loads(raw)['cases']}))
