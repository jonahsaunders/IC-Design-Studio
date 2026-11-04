"""Bind selected catalog subjects to fresh, exact raw-layout measurements.

This review does not infer voltage intent from missing tags, qualify nonempty
special devices, or resolve generated mask and complete-chip requirements.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import klayout.db as k
from scripts import sky130_device_intent_review as device
from scripts import sky130_marker_reconciliation as marker
from scripts.sky130_rule_errors import validate as validate_catalog
from scripts.sky130_rule_inventory import manual_rows, validate_unreviewed
from scripts.sky130_block_applicability import NAMED_CELL_GROUPS, named_cell_counts
from scripts.sky130_global_geometry import layer_metadata, LAYER_MAP_PATH

ROOT = device.ROOT
sha = device.sha
OUTPUT = ROOT/'docs/validation/sky130-selected-subjects-2026-10-14.json'
LAYERS = {
    'hvi': (75,20), 'areaid.hl': (81,63), 'areaid.mt': (81,10),
    'areaid.re': (81,125), 'areaid.analog': (81,79),
    'diff.resistor': (65,13), 'poly.resistor': (66,13), 'lvtn': (125,44),
    'rpm': (86,20), 'dnwell': (64,18), 'areaid.po': (81,81),
}
CONDITIONS = {
    'marked_hv': ('hvi','areaid.hl'), 'module': ('areaid.mt',),
    'rfdiode': ('areaid.re',), 'analog': ('areaid.analog',),
    'diff_res': ('diff.resistor',), 'poly_res': ('poly.resistor',),
    'lowvt': ('lvtn',), 'varactor': ('poly_tap_intersections',),
    'slotted': ('slotted_licon','rpm'),
    'phv_cells': ('phv_contact_exception_cells',),
    'nshort_cells': ('nshort_contact_exception_cells',),
    'mcon_cells': ('m1_contact_exception_cells',),
    'li_cells': ('li_vpp_exception_cells',),
    'photo': ('dnwell','areaid.po'),
}
REASONS = {
    'marked_hv': 'C3 Hdiff/Htap/Hnwell require HVI; HV_nwell also admits areaid.hl. Both selectors are empty. Separate voltage identification and tag propagation remain open.',
    'module': 'The source selects the larger contact options inside areaid.mt; that entire raw identifier is empty.',
    'rfdiode': 'The radio-frequency diode rules constrain areaid.re itself or wells selected by it; the raw identifier is empty.',
    'analog': 'The rectangular-geometry requirement selects diffusion/tap enclosed by areaid.analog; that raw region is empty.',
    'diff_res': 'The source explicitly selects the diff resistor purpose, which is empty.',
    'poly_res': 'The source explicitly selects the poly resistor purpose, which is empty.',
    'lowvt': 'The selected PMOS gate must overlap LVTN; the entire raw LVTN layer is empty.',
    'varactor': 'C3 Var_channel contains poly AND tap. Their complete merged intersection is empty, so every selected channel and its containing tap/well are absent.',
    'slotted': 'C3 defines slotted_licon as exactly 0.19 by 2.0 micrometres. There are no such contacts and raw RPM is empty. No nonempty contact-size semantics are qualified.',
    'phv_cells': 'None of the exact source-listed PHV exception cells exists in the complete hierarchy.',
    'nshort_cells': 'None of the exact source-listed nshort exception cells exists in the complete hierarchy.',
    'mcon_cells': 'None of the exact source-listed special mcon cells exists in the complete hierarchy.',
    'li_cells': 'No cell matches the source-listed s8rf2_xcmvpp_hd5_* trailing-wildcard family.',
    'photo': 'C3 photoDiode requires dnwell overlapping areaid.po; both raw operands are empty.',
}
# Explicit IDs, parent rules and catalog spellings. No prefix matching, shared
# names or summary counts confer coverage on any other record.
GROUPS = (
    ('p018-x_dotdash','x.2a','x.2a',(123,),'analog'),
    ('p018-x_dotdash','x.10','x.10',(259,),'diff_res'),
    ('p018-x_dotdash','x.10','x.10',(260,),'poly_res'),
    ('p047-hvnwell_dotdash','hvnwell.8','nwell.8',(495,),'marked_hv'),
    ('p047-hvnwell_dotdash','hvnwell.9','nwell.9',(497,),'marked_hv'),
    ('p047-hvnwell_dotdash','hvnwell.10','nwell.10',(498,),'marked_hv'),
    *[('p048-hvdifftap_dotdash','hvdifftap.'+rule,'difftap.'+rule,ids,'marked_hv')
      for rule,ids in (('14',(499,)),('14a',(500,)),('15a',(501,)),('15b',(502,)),
        ('16',(503,504)),('17',(505,)),('18',(506,)),('19',(507,)),('20',(508,)),
        ('21',(509,)),('22',(510,)),('23',(511,)),('24',(512,)))],
    ('p049-hvpoly_dotdash','hvpoly.13','poly.13',(514,),'marked_hv'),
    ('p049-hvpoly_dotdash','hvpoly.14','poly.14',(515,),'marked_hv'),
    ('p028-poly_dotdash','poly.1b','poly.1b',(517,),'lowvt'),
    ('p032-npc_dotdash','npc.5','npc.5',(710,),'slotted'),
    ('p034-licon_dotdash','licon.10','licon.10',(724,),'varactor'),
    ('p034-licon_dotdash','licon.11c','licon.11c',(731,732),'phv_cells'),
    ('p034-licon_dotdash','licon.11d','licon.11d',(733,734),'nshort_cells'),
    ('p034-licon_dotdash','licon.1b','licon.1b/c',(738,739,740),'slotted'),
    ('p034-licon_dotdash','licon.1c','licon.1b/c',(741,742),'slotted'),
    ('p034-licon_dotdash','licon.2b','licon.2b',(743,),'slotted'),
    ('p034-licon_dotdash','licon.2c','licon.2c',(744,),'slotted'),
    ('p034-licon_dotdash','licon.2d','licon.2d',(745,),'slotted'),
    ('p035-li_dotdash_dotdash','li.1a.-','li.1a',(766,),'li_cells'),
    ('p035-li_dotdash_dotdash','li.3a.-','li.3a',(769,),'li_cells'),
    ('p038-m1_dotdash','m1.4a','m1.4a',(793,794),'mcon_cells'),
    *[('p039-via_dotdash','via.'+rule,'via.'+rule,ids,'module')
      for rule,ids in (('1b',(803,)),('4b',(810,811)),('4c',(812,813)),('5b',(815,)),('5c',(816,)))],
    *[('p030-varac_dotdash','varac.'+str(i),'varac.'+str(i),(828+i,),'varactor') for i in range(1,8)],
    ('p031-photo_dotdash','photo.11','photo.11',(846,),'photo'),
    ('p041-via2_dotdash','via2.1d','via2.1d',(847,),'module'),
    ('p041-via2_dotdash','via2.4a','via2.4a',(857,858),'module'),
    ('p042-via3_dotdash','via3.1a','via3.1a',(870,),'module'),
    *[('p057-rfdiode_dotdash_dotdash','rfdiode.'+str(i)+'.-','rfdiode.'+str(i),(946+i,),'rfdiode') for i in range(1,4)],
)
DEFINITIONS = {
    'Hdiff': 'Diffusion AND Hvi', 'Htap': 'Tap AND  Hvi', 'Hnwell': 'Nwell AND Hvi',
    'Var_channel': 'poly AND tap AND (nwell NOT hvi) NOT areaid.ce',
    'VaracTap': 'Tap overlapping Var_channel',
    'slotted_licon': 'licon1.dg of size 0.19um x 2.0um',
    'photoDiode': 'deep nwell overlapping areaid.po. Die+frame utility will use the mask data of dnwell in the implementation of this definition',
}


def bindings(catalog, inventory):
    validate_catalog(catalog); validate_unreviewed(inventory)
    indexed={r['id']:r for r in catalog['rows']}; result={}
    for section, rule, spelling, numbers, condition in GROUPS:
        source='docs/rules/periphery/'+section+'.csv'
        parents=[r for r in inventory['rule_rows'] if r['source']==source and r['rule']==rule]
        if len(parents)!=1: raise ValueError('Missing exact source parent: '+source+' '+rule)
        parent=parents[0]
        if condition in ('phv_cells','nshort_cells','mcon_cells','li_cells'):
            expected=NAMED_CELL_GROUPS[CONDITIONS[condition][0]]
            selected=(('s8rf2_xcmvpp_hd5_*',) if condition=='li_cells' and
                      's8rf2_xcmvpp_hd5_*' in parent['description'] else
                      tuple(re.findall(r'"([^"]+)"',parent['description'])))
            if selected!=expected:raise ValueError('Changed exact special-cell selector.')
        for number in numbers:
            key='r'+str(number); row=indexed[key]
            if row['rule']!=spelling or key in result: raise ValueError('Changed literal catalog binding: '+key)
            result[key]=dict(rule=row['rule'],description=row['description'],parent=parent['id'],
                parent_rule=rule,source_sha256=parent['source_sha256'],condition=condition,
                operands=list(CONDITIONS[condition]),reason=REASONS[condition])
    return result


def source_proof(source, catalog, inventory):
    relations=bindings(catalog,inventory); files={}
    sources={'docs/rules/periphery/'+r[0]+'.csv' for r in GROUPS}|{marker.nsm.DEFINITION}
    for name in sorted(sources):
        path=Path(source)/name
        if sha(path)!=inventory['source_files'][name]['sha256']: raise ValueError('Changed selected-subject source.')
        files[name]=sha(path)
        if name!=marker.nsm.DEFINITION:
            known={r['id']:r for r in inventory['rule_rows']}
            for row in manual_rows(path.read_bytes(),name):
                if any(row[key]!=known[row['id']][key] for key in ('rule','description','record','flags','value','unit')):
                    raise ValueError('Source and inventory differ.')
    defs={r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO((Path(source)/marker.nsm.DEFINITION).read_text(encoding='utf-8')))}
    if any(defs.get(key)!=value for key,value in DEFINITIONS.items()): raise ValueError('Changed C3 definition.')
    # Preserve the full HV_nwell definition, including thin-oxide wells tagged HL.
    if defs['HV_nwell']!='(nwell AND hvi) OR (nwell overlapping areaid.hl)':
        raise ValueError('Changed HV_nwell selector.')
    layer_metadata();layers={tuple(r['pair']):r['aliases'] for r in json.loads(LAYER_MAP_PATH.read_bytes())['layers']}
    aliases={}
    for name,pair in LAYERS.items():
        if name=='areaid.analog':expected=('areaid','analog','installed')
        elif name.endswith('.resistor'):expected=(name.split('.')[0],'resistor','published')
        else:expected=(name,'identifier' if name.startswith('areaid.') else 'drawing','published')
        matches=[a for a in layers[pair] if (a['name'],a['purpose'],a['source'])==expected]
        if len(matches)!=1:raise ValueError('Changed selected-subject layer purpose.')
        aliases[name]=dict(pair=list(pair),**matches[0])
    return dict(files=files,definitions={**DEFINITIONS,'HV_nwell':defs['HV_nwell']},
                layer_map_sha256=sha(LAYER_MAP_PATH),aliases=aliases,bindings=relations,
                named_cells={key:NAMED_CELL_GROUPS[key] for key in
                             ('phv_contact_exception_cells','nshort_contact_exception_cells','m1_contact_exception_cells','li_vpp_exception_cells')})


def measure(layout):
    diagnostic=device.grid.check(layout)
    if any(r['violations'] for r in diagnostic['checks'] if r['rule'].startswith('profile.')):
        raise ValueError('Unsupported geometry for exact selected-subject measurement.')
    top=layout.top_cell(); counts={}
    for key,pair in LAYERS.items():
        iterator=top.begin_shapes_rec(layout.layer(*pair)); count=0
        while not iterator.at_end(): count+=1; iterator.next()
        counts[key]=count
    region=lambda pair:k.Region(top.begin_shapes_rec(layout.layer(*pair))).merged()
    counts['poly_tap_intersections']=(region((66,20))&region((65,44))).count()
    counts['slotted_licon']=sum(p.is_box() and sorted((p.bbox().width(),p.bbox().height()))==[190,2000]
                                  for p in region((66,44)).each())
    counts.update({key:value for key,value in named_cell_counts([c.name for c in layout.each_cell()]).items()
                   if key in {v for values in CONDITIONS.values() for v in values}})
    return dict(top=top.name,counts=counts)


def decisions(measurement, relations):
    counts=measurement['counts']; required={v for values in CONDITIONS.values() for v in values}
    if set(counts)!=required or any(type(v)is not int or v<0 for v in counts.values()):
        raise ValueError('Incomplete or invalid selected-subject measurements.')
    return {key:dict(disposition='absent-operand' if all(counts[p]==0 for p in r['operands']) else 'unreviewed',
                     witnesses={p:counts[p] for p in r['operands']},binding=r)
            for key,r in relations.items()}


def read(name):
    return json.loads((ROOT/'docs/validation'/name).read_bytes())


def baseline(case, catalog):
    original=next(c for c in read('sky130-geometry-reconciliation-2026-10-14.json')['cases'] if c['case']==case)
    rows=deepcopy(original['rows']); indexed={r['id']:r for r in rows}
    for name in ('sky130-nsm-reconciliation-2026-10-14.json','sky130-marker-reconciliation-2026-10-14.json',
                 'sky130-waffle-density-2026-10-14.json','sky130-esd-fuse-2026-10-14.json'):
        data=next(c for c in read(name)['cases'] if c['case']==case)
        for row in data['new_error_decisions']:
            if indexed[row['id']]['disposition']!='unreviewed': raise ValueError('Overlapping preceding decisions.')
            indexed[row['id']].update(row)
        if dict(Counter(r['disposition'] for r in rows))!=data.get('error_counts',data.get('counts')):
            raise ValueError('Preceding catalog counts do not reconstruct.')
    prior=next(c for c in json.loads(device.OUTPUT.read_bytes())['cases'] if c['case']==case)
    for row in prior['new_decisions']:
        key=row['error_id']
        if indexed[key]['disposition']!='unreviewed': raise ValueError('Overlapping device decision.')
        indexed[key].update(disposition=row['decision']['disposition'])
    if dict(Counter(r['disposition'] for r in rows))!=prior['error_counts']:
        raise ValueError('Device-intent counts do not reconstruct.')
    validate_rows(rows,catalog)
    return rows,prior


def validate_rows(rows,catalog):
    if len(rows)!=len(catalog['rows']) or any(any(r[key]!=s[key] for key in ('id','rule','record'))
                                            for r,s in zip(rows,catalog['rows'])):
        raise ValueError('Missing, duplicate or changed catalog ledger records.')


def reconcile(rows,catalog,relations,measurement,manual):
    validate_rows(rows,catalog); marker.validate_scope(manual)
    indexed={r['id']:r for r in rows}; parents={r['id']:r for r in manual['rows']}
    result=deepcopy(rows); changed={r['id']:r for r in result}; choices=decisions(measurement,relations)
    for key,relation in relations.items():
        parent=parents[relation['parent']]
        if (indexed[key]['disposition']!='unreviewed' or parent['rule']!=relation['parent_rule']
                or parent['source_sha256']!=relation['source_sha256']):
            raise ValueError('Changed or overlapping parent/binding.')
        if choices[key]['disposition']=='absent-operand':
            if parent['disposition']!='absent-operand': raise ValueError('Parent absence not established.')
            changed[key].update(choices[key])
    return result


def build():
    prior=json.loads(device.OUTPUT.read_bytes()); audit=read('sky130-device-intent-audit-2026-10-14.json')
    if sha(device.OUTPUT)!=audit['data']['sha256'] or prior['chunk_complete'] is not False:
        raise ValueError('Changed device-intent predecessor.')
    reproduced=device.previous.build()
    if (json.dumps(reproduced,indent=2,ensure_ascii=False)+'\n').encode()!=device.previous.OUTPUT.read_bytes():
        raise ValueError('Earlier catalog evidence no longer reproduces.')
    if prior['predecessor']!=dict(path=device.previous.OUTPUT.relative_to(ROOT).as_posix(),sha256=sha(device.previous.OUTPUT)):
        raise ValueError('Device review is bound to different preceding evidence.')
    for name,digest in prior['source_files'].items():
        if sha(ROOT/name)!=digest: raise ValueError('Changed retained device-intent source.')
    catalog=json.loads((ROOT/marker.nsm.geometry.previous.CATALOG).read_bytes())
    inventory=json.loads((ROOT/marker.nsm.geometry.previous.PERIPHERY).read_bytes())
    manual=json.loads(marker.nsm.scope.OUTPUT.read_bytes()); cases=[]
    fixture=marker.nsm.fixture
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs'; manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog,inventory)
        for entry in manifest['cases']:
            path=folder/entry['gds']; digest=sha(path); layout=k.Layout(); layout.read(str(path))
            measurement=measure(layout)
            if sha(path)!=digest or digest!=entry['gds_sha256']: raise ValueError('Changed selected-subject layout.')
            rows,preceding=baseline(entry['case'],catalog)
            parent=next(c for c in manual['cases'] if c['case']==entry['case'])
            if parent['gds_sha256']!=digest or preceding['execution']['gds_sha256']!=digest or measurement['top']!=entry['top']:
                raise ValueError('Different layout used by catalog/parent/device evidence.')
            result=reconcile(rows,catalog,proof['bindings'],measurement,parent)
            changes=[r for r,before in zip(result,rows) if r!=before]
            if {r['id'] for r in changes}!=set(proof['bindings']): raise ValueError('Not all selected reference subjects are absent.')
            cases.append(dict(case=entry['case'],gds_sha256=digest,measurement=measurement,
                new_error_decisions=changes,error_counts=dict(Counter(r['disposition'] for r in result)),
                periphery_counts=preceding['periphery_counts']))
    inputs=[device.OUTPUT,ROOT/'docs/validation/sky130-device-intent-audit-2026-10-14.json',marker.nsm.scope.OUTPUT,
        marker.nsm.geometry.OUTPUT,marker.nsm.OUTPUT,marker.OUTPUT,
        ROOT/'docs/validation/sky130-waffle-density-2026-10-14.json',device.previous.OUTPUT,
        ROOT/marker.nsm.geometry.previous.CATALOG,ROOT/marker.nsm.geometry.previous.PERIPHERY]
    sources=[Path(__file__),ROOT/'tests/test_sky130_selected_subjects.py',Path(device.grid.__file__),
             ROOT/'scripts/sky130_block_applicability.py']
    return dict(schema=1,chunk=6,status='partial-selected-subject-review',qualified=False,chunk_complete=False,
                inputs={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
                source_files={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
                bundle=manifest,proof=proof,cases=cases,
                scope='Fresh raw/derived selector measurements bind only literal catalog records. The 13 periphery execution reviews and missing x.20 definition are unchanged. Voltage intent, generated masks, grid, frame, RF map and other catalog/density obligations remain open.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    report=build();raw=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if OUTPUT.read_bytes()!=raw: raise ValueError('Saved selected-subject review differs.')
    else: OUTPUT.write_bytes(raw)
    print(json.dumps({c['case']:c['error_counts'] for c in report['cases']}))
