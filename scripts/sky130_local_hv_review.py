"""Review local and nominal-HV catalog subjects on the exact filled layouts.

Fresh measurements can prove specific selected subjects absent. They do not
qualify nonempty resistor, pad or HV circuits. hugePad stays open because its
mask-derived operand and conflicting area wording are not resolved.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from icstudio import digital_sky130_pad_scope as pad_scope
from scripts import sky130_catalog_queue as queue
from scripts import sky130_grid_geometry as grid
from scripts import check_sky130_filled_replay as fixture
from scripts.sky130_global_geometry import layer_metadata, LAYER_MAP_PATH
from scripts.sky130_rule_inventory import validate_unreviewed, manual_rows

ROOT = queue.ROOT
OUTPUT = ROOT/'docs/validation/sky130-local-hv-2026-10-15.json'
INVENTORY = 'docs/qualification/sky130-rule-inventory.json'
VOLTAGE = 'docs/validation/sky130-voltage-intent-2026-10-14.json'
ISOLATION = 'docs/validation/sky130-isolation-options-2026-10-14.json'
ISOLATION_SHA = '5c284df0743c4207282d2c37f561a3e701d0d8ddfb3a6dfc2425b0364a11d33c'
DEFINITION = 'docs/rules/layers/table-c3-device-lvs-other.csv'
LAYERS = {
    'poly.resistor': (66,13), 'diff.resistor': (65,13), 'li1.resistor': (67,13),
    'rpm': (86,20), 'urpm': (79,20), 'pad': (76,20),
    'hvi': (75,20), 'areaid.hl': (81,63), 'diff.hv': (65,8),
    'vhvi': (74,21), 'uhvi': (74,22),
}
HV_OPERANDS = ('hvi','areaid.hl','diff.hv','vhvi','uhvi','hv_bb_labels','hv_lv_labels','shv_nwell_labels')
CONDITIONS = {
    'butting': ('tap_interacting_diff',),
    'poly_resistor': ('poly.resistor','rpm','urpm'),
    'diff_resistor': ('diff.resistor',), 'li_resistor': ('li1.resistor',),
    'drawn_pad': ('pad',), 'urpm': ('urpm',), 'nominal_hv': HV_OPERANDS,
}
REASONS = {
    'butting': 'No merged diffusion and tap polygons touch or overlap, including corner contacts; the selected abutting edges are absent.',
    'poly_resistor': 'All poly-resistor purpose, RPM and URPM raw shapes are absent. This covers the resistor selectors, not just poly:rs alone.',
    'diff_resistor': 'The complete raw diff:resistor purpose selected by the rule is absent.',
    'li_resistor': 'The complete raw li1:resistor purpose is absent; no ESD exemption is used.',
    'drawn_pad': 'The complete raw pad:drawing purpose is absent. This does not discharge mask-derived hugePad.',
    'urpm': 'The exact published URPM drawing purpose is absent. This is a direct catalog binding, not an RPM rule-name substitution.',
    'nominal_hv': 'Under the authenticated nominal reference contract, no raw HV selector or normalized HV exception label exists. The C3 HV diffusion seed and its propagated subjects are absent.',
}
GROUPS = (
    *((f'difftap.{i}', f'difftap.{i}', (432+i,), 'butting') for i in range(4,8)),
    ('poly.3','poly.3',(522,),'poly_resistor'),
    ('poly.9','poly.9',(528,529,530),'poly_resistor'),
    ('poly.15','poly.15',(534,),'diff_resistor'),
    ('li.7.-','li.7',(774,),'li_resistor'),
    ('pad.2','pad.2',(899,),'drawn_pad'),
    (None,'urpm.1a',(1039,),'urpm'), (None,'urpm.2',(1046,),'urpm'),
    ('hv.nwell.1','hv.nwell.1',(496,),'nominal_hv'),
    *((f'hv.diff.{suffix}', f'hv.diff.{suffix}', ids, 'nominal_hv')
      for suffix, ids in (('1a',(1164,)),('1b',(1165,1166)),('2',(1167,)),
                          ('3a',(1168,)),('3b',(1169,1170)))),
    *((f'hv.poly.{suffix}', f'hv.poly.{suffix}', ids, 'nominal_hv')
      for suffix, ids in (('1',(1171,1172,1173)),('2',(1174,)),('3',(1175,)),
                          ('4',(1176,)),('6a',(1177,)),('6b',(1178,)))),
)
DEFINITIONS = {
    'hv_source/drain': '= (diff andNot poly) that overlaps diff.hv',
    'hvFET_gate': '= FET_gate butting hv_source/drain',
    'hvPoly': '= poly electrically connected to hv_source/drain',
    'prec_resistor': 'rpm AND (poly overlapping poly.rs) AND psdm',
    'hugePad': 'pad.mk with width > 100um',
}


def source_proof(source, catalog, inventory):
    queue.validate_catalog(catalog); validate_unreviewed(inventory)
    indexed = {r['id']:r for r in catalog['rows']}
    relations = {}; parents = {}
    for parent_rule, spelling, numbers, condition in GROUPS:
        parent = None
        if parent_rule is not None:
            matches = [r for r in inventory['rule_rows'] if r['rule']==parent_rule]
            if len(matches)!=1: raise ValueError('Missing exact local/HV source parent.')
            parent = matches[0]; parents[parent['id']] = parent
        for number in numbers:
            row = indexed['r'+str(number)]
            if row['rule'] != spelling or row['id'] in relations:
                raise ValueError('Changed or duplicate literal catalog binding.')
            relations[row['id']] = dict(rule=spelling, description=row['description'],
                parent=None if parent is None else {key:parent[key] for key in
                    ('id','rule','source','source_sha256','record')},
                condition=condition, operands=list(CONDITIONS[condition]), reason=REASONS[condition])
    sources = {r['source'] for r in parents.values()} | {
        DEFINITION, 'docs/rules/hv.rst', 'docs/rules/errors.csv', 'docs/rules/gds_layers.csv', pad_scope.ROW['source']}
    files = {}
    for name in sorted(sources):
        raw = (Path(source)/name).read_bytes(); digest = queue.sha(raw)
        if digest != inventory['source_files'][name]['sha256']:
            raise ValueError('Changed local/HV source: '+name)
        files[name] = digest
        if '/periphery/' in name:
            known = {r['id']:r for r in inventory['rule_rows']}
            for row in manual_rows(raw,name):
                if any(row[key]!=known[row['id']][key] for key in ('rule','description','record','flags','value','unit')):
                    raise ValueError('Source/inventory requirement differs.')
    definitions = {r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO(
        (Path(source)/DEFINITION).read_text(encoding='utf-8')))}
    if any(definitions.get(name)!=text for name,text in DEFINITIONS.items()):
        raise ValueError('Changed local/HV/C3 target definition.')
    text = (Path(source)/'docs/rules/hv.rst').read_text(encoding='utf-8')
    if 'Beginning with taggedhvSRCDRN' not in text:
        raise ValueError('Changed published HV propagation starting point.')
    layer_metadata(); layers = {tuple(r['pair']):r['aliases'] for r in json.loads(LAYER_MAP_PATH.read_bytes())['layers']}
    aliases = {}
    for name,pair in LAYERS.items():
        expected = ((name.split('.')[0],'resistor') if name.endswith('.resistor') else
                    ('diff','high voltage') if name=='diff.hv' else
                    ('areaid.hl','identifier') if name=='areaid.hl' else
                    ('pad','drawing, text') if name=='pad' else (name,'drawing'))
        matches = [a for a in layers[pair] if (a['name'],a['purpose'])==expected and a['source']=='published']
        if len(matches)!=1: raise ValueError('Changed exact selected layer purpose.')
        aliases[name] = dict(pair=list(pair),**matches[0])
    pad_parent = next(r for r in inventory['rule_rows'] if r['id']==pad_scope.ROW['id'])
    if (pad_parent['description']!='Max area of hugePad NOT top_metal' or
            indexed['r900']['description']!='hugepad with area less than 30000.0 not allowed'):
        raise ValueError('Changed hugePad discrepancy; review the new source.')
    return dict(files=files, definitions=DEFINITIONS, aliases=aliases, bindings=relations,
                layer_map_sha256=queue.sha(LAYER_MAP_PATH.read_bytes()),
                unresolved_hugepad=dict(parent=pad_scope.ROW, error_id='r900', reason=pad_scope.REASON))


def measure(layout):
    diagnostic = grid.check(layout)
    if any(r['violations'] for r in diagnostic['checks'] if r['rule'].startswith('profile.')):
        raise ValueError('Unsupported geometry for local/HV subject measurement.')
    top = layout.top_cell(); counts = {}
    for name,pair in LAYERS.items():
        iterator=top.begin_shapes_rec(layout.layer(*pair)); count=0
        while not iterator.at_end(): count+=1; iterator.next()
        counts[name]=count
    region=lambda pair:k.Region(top.begin_shapes_rec(layout.layer(*pair))).merged()
    counts['tap_interacting_diff']=region((65,44)).interacting(region((65,20))).count()
    labels={name:0 for name in ('hv_bb','hv_lv','shv_nwell')}
    for index in layout.layer_indexes():
        iterator=top.begin_shapes_rec(index)
        while not iterator.at_end():
            shape=iterator.shape()
            if shape.is_text():
                label=shape.text.string.strip().casefold()
                if label in labels: labels[label]+=1
            iterator.next()
    counts.update({key+'_labels':count for key,count in labels.items()})
    return dict(top=top.name, counts=counts,
                measurement='All recursive raw shapes, conservative merged tap/diff interactions, and normalized labels on every purpose.')


def decisions(measurement, relations, nominal):
    counts=measurement['counts']; required=set(LAYERS)|{'tap_interacting_diff',*HV_OPERANDS}
    if set(counts)!=required or any(type(v)is not int or v<0 for v in counts.values()):
        raise ValueError('Incomplete or invalid local/HV measurements.')
    if (nominal.get('status')!='nominal-voltage-contract-consistent' or
            nominal.get('qualified') is not False or nominal.get('power_net_hv')!=[]):
        raise ValueError('Authenticated nominal contract required before interpreting HV absence.')
    return {key:dict(disposition='absent-operand' if all(counts[p]==0 for p in r['operands']) else 'unreviewed',
                     witnesses={p:counts[p] for p in r['operands']}, binding=r)
            for key,r in relations.items()}


def periphery(reader, name, inventory, isolation):
    pick=lambda path:next(c for c in reader.read(path)['cases'] if c['case']==name)
    base=pick(queue.PREFIX+'scope-corrections-2026-10-14.json')
    rows=deepcopy(base['rows']); indexed={r['id']:r for r in rows}
    esd=pick(queue.PREFIX+'esd-fuse-2026-10-14.json')
    for row in esd['new_periphery_decisions']: indexed[row['id']].update(row)
    device=pick(queue.PREFIX+'device-intent-2026-10-14.json')
    for change in device['new_decisions']:
        row=indexed[change['parent']['id']]
        if row!=change['parent']: raise ValueError('Changed retained device parent.')
        row.update(deepcopy(change['decision']),semantic_review='sky130-device-intent-2026-10-14')
    voltage=pick(VOLTAGE)
    for rule,choice in voltage['decisions'].items():
        row=next(r for r in rows if r['rule']==rule)
        row.update(deepcopy(choice),semantic_review='sky130-voltage-intent-2026-10-14')
    choice=isolation['new_periphery_decision']; indexed[choice['id']].update(deepcopy(choice))
    if (len(rows)!=len(inventory['rule_rows']) or any(
            any(row[key]!=original[key] for key in ('id','rule','source','source_sha256','record'))
            for row,original in zip(rows,inventory['rule_rows'])) or
            dict(Counter(r['disposition'] for r in rows))!=isolation['periphery_counts']):
        raise ValueError('Latest periphery decisions do not reconstruct.')
    return pad_scope.correct(dict(rows=rows,counts=isolation['periphery_counts']))


def build():
    reader=queue.RetainedReader(); catalog,baselines=queue.reconstruct(reader)
    isolation=reader.read(ISOLATION,ISOLATION_SHA)
    for name,digest in isolation['inputs'].items(): reader.read(name,digest)
    voltage=reader.read(VOLTAGE)
    for name,digest in voltage['inputs'].items(): reader.read(name,digest)
    inventory=reader.read(INVENTORY); cases=[]; batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs'; manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog,inventory)
        for entry in manifest['cases']:
            name=entry['case']; before=next(c for c in baselines if c['case']==name)
            iso=next(c for c in isolation['cases'] if c['case']==name)
            volts=next(c for c in voltage['cases'] if c['case']==name)
            if not before['gds_sha256']==iso['gds_sha256']==volts['gds_sha256']==entry['gds_sha256']:
                raise ValueError('Mismatched reference/contract/retained layout.')
            gds=folder/entry['gds']; layout=k.Layout(); layout.read(str(gds)); measured=measure(layout)
            if measured['top']!=entry['top'] or queue.sha(gds.read_bytes())!=entry['gds_sha256']:
                raise ValueError('Changed reference measurement input.')
            nominal=volts['execution']['contract_check']
            choices=decisions(measured,proof['bindings'],nominal)
            manual=periphery(reader,name,inventory,iso); parents={r['id']:r for r in manual['rows']}
            for relation in proof['bindings'].values():
                parent=relation['parent']
                if parent and (any(parents[parent['id']][key]!=value for key,value in parent.items()) or
                               parents[parent['id']]['disposition']!='absent-operand'):
                    raise ValueError('Parent source/absence not established.')
            if any(c['disposition']!='absent-operand' for c in choices.values()):
                raise ValueError('A local/HV subject is present; this reference needs further review.')
            changes=[dict(id=key,**choice) for key,choice in choices.items()]
            rows=queue.apply_decisions(before['rows'],changes,catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and current!=batches: raise ValueError('Reference queues differ.')
            batches=current
            cases.append(dict(case=name,gds_sha256=entry['gds_sha256'],measurement=measured,
                nominal_contract=dict(path=VOLTAGE,sha256=reader.digests[VOLTAGE],checked=nominal),
                new_error_decisions=changes,error_counts=dict(Counter(r['disposition'] for r in rows)),
                new_periphery_decision=parents[pad_scope.ROW['id']],periphery_counts=manual['counts'],
                open_periphery=[r for r in manual['rows'] if r['disposition'] in ('execution-review-required','definition-required')]))
    sources=(Path(__file__),Path(pad_scope.__file__),Path(grid.__file__),
             ROOT/'scripts/sky130_catalog_queue.py',ROOT/'tests/test_sky130_local_hv_review.py',
             ROOT/'tests/test_sky130_pad_scope.py')
    return dict(schema=1,chunk=6,status='local-and-nominal-hv-subjects-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in sources},
        bundle=dict(path=fixture.BUNDLE.relative_to(ROOT).as_posix(),sha256=fixture.BUNDLE_SHA256),
        proof=proof,pad_scope_review=pad_scope.REVIEW,cases=cases,
        remaining_batches=[dict(id=b['id'],count=b['count'],next_action=b['next_action'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Fresh exact-reference measurements resolve only 29 literal catalog subjects as absent. No nonempty rule is qualified. '
              'The mask-derived hugePad obligation is reopened in the periphery ledger. Nominal voltage assumptions remain conditional; '
              'RF selection, generated masks, grid, frame, pin-spacing and other required catalog/density checks remain open.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    parser.add_argument('--output',type=Path,default=OUTPUT);args=parser.parse_args()
    data=build(); raw=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if args.output.read_bytes()!=raw: raise ValueError('Saved local/HV review differs.')
    else: args.output.write_bytes(raw)
    print(json.dumps({c['case']:dict(catalog=c['error_counts'],periphery=c['periphery_counts']) for c in data['cases']}))
