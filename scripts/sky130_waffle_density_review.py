"""Prove the false antecedent of 48 explicit waffle-drop density records.

An empty waffle-drop layer covers zero percent of every possible window.
This proof needs no guessed window origin, edge clipping or chip boundary.
It never accepts a nonempty waiver layer or substitutes drawn metal density.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from scripts import sky130_marker_reconciliation as marker
from scripts.sky130_global_geometry import layer_metadata, LAYER_MAP_PATH, LAYER_MAP_SHA256
from scripts.sky130_rule_inventory import manual_rows
from scripts.sky130_rule_errors import validate as validate_catalog

ROOT=marker.ROOT
OUTPUT=ROOT/'docs/validation/sky130-waffle-density-2026-10-14.json'
PAIRS=((62,24),(105,52),(107,24),(112,4))
SOURCES=('p038-m1_dotdash','p040-m2_dotdash','p042-m3_dotdash','p044-m4_dotdash')
BANDS=(('70','100%'),('65','80-100%'),('60','60-80%'),('50','50-60%'),('40','40-50%'),('30','30-40%'))
sha=marker.nsm.sha


def bindings(catalog,inventory):
    validate_catalog(catalog);rows={r['id']:r for r in catalog['rows']};result={}
    for index,source in enumerate(SOURCES):
        metal=index+1;name='docs/rules/periphery/'+source+'.csv'
        parent=next(r for r in inventory['rule_rows'] if r['source']==name and r['record']==1)
        if parent['rule']!=f'm{metal}.-' or parent['flags']!=['RC']:
            raise ValueError('Changed required waffle-drop density parent.')
        for offset,(density,coverage) in enumerate(BANDS):
            description=f'<{density}% metal density when 700x700 window {coverage} covered by mm{metal}.waffledrop'
            for key in (f'r{1210+6*index+offset}',f's{44+6*index+offset}'):
                row=rows[key]
                if row['rule']!=f'm{metal}.x.1' or row['description']!=description:
                    raise ValueError('Changed literal waffle-drop density catalog record.')
                result[key]=dict(parent=parent['id'],parent_rule=parent['rule'],source_sha256=parent['source_sha256'],
                    rule=row['rule'],description=description,pair=list(PAIRS[index]),
                    proof='Empty raw waffle-drop layer has zero coverage in every window; each published antecedent requires at least 30%.')
    return result


def source_proof(source,inventory,catalog):
    result=bindings(catalog,inventory);files={}
    for section in SOURCES:
        name='docs/rules/periphery/'+section+'.csv';path=Path(source)/name;raw=path.read_bytes()
        if sha(path)!=inventory['source_files'][name]['sha256']:raise ValueError('Changed density source.')
        parents={r['id']:r for r in inventory['rule_rows'] if r['source']==name}
        for row in manual_rows(raw,name):
            if any(row[key]!=parents[row['id']][key] for key in ('rule','record','description','flags','value','unit','source_sha256')):
                raise ValueError('Density source and inventory differ.')
        files[name]=sha(path)
    layer_metadata();layers={tuple(r['pair']):r for r in json.loads(LAYER_MAP_PATH.read_bytes())['layers']}
    for index,pair in enumerate(PAIRS):
        if not any(a['name']==f'cmm{index+1}' and a['purpose']=='waffle drop' and a['source']=='published' for a in layers[pair]['aliases']):
            raise ValueError('Waffle-drop layer mapping changed.')
    return dict(files=files,bindings=result,layer_map_sha256=LAYER_MAP_SHA256,
        exclusions=['r1141: vpp_over_MOSCAP selector remains unreviewed; C3 contains unfinished cell-name definitions.',
                    'No nonempty waffle-drop window-density execution or chip-boundary acceptance.'])


def measure(layout):
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:raise ValueError('Expected one top and 1 nm units.')
    counts={}
    for pair in PAIRS:
        iterator=layout.top_cell().begin_shapes_rec(layout.layer(*pair));count=0
        while not iterator.at_end():count+=1;iterator.next()
        counts[str(pair)]=count
    return dict(top=layout.top_cell().name,counts=counts)


def audit(path):
    before=sha(path);layout=k.Layout();layout.read(str(path));result=measure(layout)
    if sha(path)!=before:raise ValueError('Density input changed during measurement.')
    return dict(**result,gds_sha256=before,checker_sha256=sha(__file__))


def preceding(geometry,nsm,previous):
    result=marker.preceding(geometry,nsm);rows={r['id']:r for r in result['rows']}
    for change in previous['new_error_decisions']:
        if rows[change['id']]['disposition']!='unreviewed':raise ValueError('Overlapping marker predecessor.')
        rows[change['id']].update(change)
    result['counts']=dict(Counter(r['disposition'] for r in result['rows']))
    if result['counts']!=previous['counts'] or result['gds_sha256']!=previous['measurement']['gds_sha256']:
        raise ValueError('Marker predecessor does not reconstruct.')
    return result


def reconcile(catalog,inventory,baseline,manual,measurement):
    relations=bindings(catalog,inventory);marker.validate_scope(manual)
    result=deepcopy(baseline);rows={r['id']:r for r in result['rows']};source={r['id']:r for r in catalog['rows']}
    if (len(rows)!=len(result['rows']) or set(rows)!=set(source) or
            baseline['counts']!=dict(Counter(r['disposition'] for r in rows.values())) or
            any(any(r[key]!=source[name][key] for key in ('id','record','rule')) for name,r in rows.items())):
        raise ValueError('Incomplete or changed catalog ledger.')
    counts=measurement['counts']
    if set(counts)!={str(p) for p in PAIRS} or any(type(v)is not int or v<0 for v in counts.values()):
        raise ValueError('Invalid raw waffle-drop measurements.')
    if (baseline['case']!=manual['case'] or baseline['gds_sha256']!=manual['gds_sha256'] or
            baseline['gds_sha256']!=measurement['gds_sha256'] or baseline['top']!=measurement['top'] or
            measurement['checker_sha256']!=sha(__file__)):
        raise ValueError('Density evidence input identity differs.')
    parents={r['id']:r for r in manual['rows']}
    for key,binding in relations.items():
        pair=str(tuple(binding['pair']));parent=parents[binding['parent']]
        if rows[key]['disposition']!='unreviewed' or parent['rule']!=binding['parent_rule'] or parent['source_sha256']!=binding['source_sha256']:
            raise ValueError('Changed or previously reviewed density record.')
        if counts[pair]==0:
            if parent['disposition']!='absent-operand' or parent.get('witnesses')!={pair:0} or type(parent['witnesses'][pair])is not int:
                raise ValueError('Previous parent lacks matching absence evidence.')
            rows[key].update(disposition='absent-operand',binding=key,parent=binding['parent'],
                             description=binding['description'],absence_proof=binding['proof'])
    result['counts']=dict(Counter(r['disposition'] for r in result['rows']))
    return result


def build():
    previous=marker.build()
    if (json.dumps(previous,indent=2,ensure_ascii=False)+'\n').encode()!=marker.OUTPUT.read_bytes():
        raise ValueError('Marker predecessor no longer reproduces.')
    nsm=json.loads(marker.nsm.OUTPUT.read_bytes());geometry=json.loads(marker.nsm.geometry.OUTPUT.read_bytes())
    manual=json.loads(marker.nsm.scope.OUTPUT.read_bytes())
    catalog=json.loads((ROOT/marker.nsm.geometry.previous.CATALOG).read_bytes())
    inventory=json.loads((ROOT/marker.nsm.geometry.previous.PERIPHERY).read_bytes());cases=[]
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=marker.nsm.fixture.unpack(marker.nsm.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',inventory,catalog)
        for entry in manifest['cases']:
            name=entry['case'];pick=lambda data:next(r for r in data['cases'] if r['case']==name)
            baseline=preceding(pick(geometry),pick(nsm),pick(previous));measurement=audit(folder/entry['gds'])
            result=reconcile(catalog,inventory,baseline,pick(manual),measurement)
            changes=[r for r,before in zip(result['rows'],baseline['rows']) if r!=before]
            if {r['id'] for r in changes}!=set(proof['bindings']):raise ValueError('Reference does not establish all 48 absences.')
            cases.append(dict(case=name,measurement=measurement,counts=result['counts'],new_error_decisions=changes))
    paths=[marker.OUTPUT,marker.nsm.OUTPUT,marker.nsm.geometry.OUTPUT,marker.nsm.scope.OUTPUT,
           ROOT/marker.nsm.geometry.previous.CATALOG,ROOT/marker.nsm.geometry.previous.PERIPHERY,LAYER_MAP_PATH]
    return dict(schema=1,status='partial-waffle-density-review',qualified=False,chunk_complete=False,
        source_files={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),ROOT/'tests/test_sky130_waffle_density.py']},
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in paths},bundle=previous['bundle'],proof=proof,cases=cases,
        scope='48 exact block/chip catalog records have empty waffle-drop antecedents on these input layouts. No numeric density execution, complete-chip qualification, remaining catalog interpretation or complete chunk 6 acceptance is implied.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    raw=(json.dumps(build(),indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if OUTPUT.read_bytes()!=raw:raise ValueError('Saved density review differs.')
    else:OUTPUT.write_bytes(raw)
    print('48 explicit density antecedents absent on each filled reference; chunk remains incomplete.')
