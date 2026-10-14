"""Explicit marker/derived-operand absence proofs for selected SKY130 records.

Each catalog ID has a reviewed source parent and an empty-subject condition.
Enclosure rules require the target absent, not merely the enclosing layer.
No operating-voltage intent or non-empty device qualification is inferred.
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

from icstudio.digital_sky130_scope import validate as validate_scope
from scripts import sky130_nsm_reconciliation as nsm
from scripts.sky130_global_geometry import layer_metadata, LAYER_MAP_PATH, LAYER_MAP_SHA256
from scripts.sky130_rule_inventory import manual_rows
from scripts.sky130_rule_errors import validate as validate_catalog

ROOT=nsm.ROOT
OUTPUT=ROOT/'docs/validation/sky130-marker-reconciliation-2026-10-14.json'
LAYERS={
    'dnwell':((64,18),'dnwell','drawing','published'),
    'lvtn':((125,44),'lvtn','drawing','published'),
    'hvtr':((18,20),'hvtr','drawing','published'),
    'hvi':((75,20),'hvi','drawing','published'),
    'rdl':((74,20),'rdl','drawing','installed'),
    'pad':((76,20),'pad','drawing, text','published'),
    'ccu1m':((93,0),'ccu1m','mask','installed'),
    'rpm':((86,20),'rpm','drawing','published'),
    'tunm':((80,20),'tunm','drawing','published'),
    'hvntm':((125,20),'hvntm','drawing','published'),
    'vhvi':((74,21),'vhvi','drawing','published'),
    'areaid.en':((81,57),'areaid.en','identifier','published'),
    'ncm':((92,44),'ncm','drawing','published'),
    'nwell':((64,20),'nwell','drawing','published'),
}
PROOFS={
    'dnwell':(('dnwell',),'Every selected deep-well subject is the raw deep well or a subset of it. Empty deep well also has no separate-net spacing or straddle interactions.'),
    'nwell_holes':(('nwell_holes',),'The required enclosed target is the hole of the merged drawn nwell. It is measured directly; empty dnwell alone is insufficient.'),
    'lvtn':(('lvtn',),'The selected subjects contain drawn LVTN or its holes; the entire raw layer is empty. The separate gate-enclosure obligation lvtn.4b is not included.'),
    'hvtr':(('hvtr',),'Width, spacing and no-overlap require HVTR geometry. The separate PFET-enclosure obligation hvtr.3 is not included.'),
    'hvi':(('hvi',),'Width, spacing and no-overlap use HVI or a subset; HVI is empty. This does not establish correct voltage identification.'),
    'rdl':(('rdl','pad','ccu1m'),'All RDL, PAD and CCU1M mask shapes are empty. PAD is explicitly required absent for pad-enclosure; RDL absence alone cannot discharge that target.'),
    'rpm':(('rpm',),'Raw RPM is empty. C3 defines prec_resistor through intersection with RPM, so the resistor target is also empty. No non-empty resistor or terminal geometry is qualified.'),
    'tunm':(('tunm',),'The selected TUNM width/spacing/area/containment/straddle subjects require TUNM. The tunm.3 gate-extension record is deliberately excluded pending target interpretation.'),
    'hvntm':(('hvntm','hvi'),'Both HVNTM and HVI are empty. HVI emptiness discharges the explicitly HVI-selected diffusion and ESD-tap enclosure targets; HVNTM emptiness alone would not.'),
    'vhvi':(('vhvi',),'C3 VHVGate, VHVPoly and VHVSourceDrain require VHVI. With no such geometry there is no selected root for the listed connectivity propagation. Independent voltage/tagging intent remains unproved.'),
    'extended_drain':(('areaid.en',),'C3 drain-extended gates, sources and drains require areaid.en; its absence discharges only the explicitly selected subjects. The ambiguous angle records and extd.3 catalog target are excluded.'),
    'ncm':(('ncm',),'The selected width/spacing/area subjects are NCM or its holes. The separate P+ diffusion enclosure obligations ncm.3 and ncm.4 are not included.'),
}
# Literal catalog IDs and exact parent names within pinned source files.
# No catalog candidate matching or name/prefix propagation creates coverage.
FAMILIES={
    'p020-dnwell_dotdash':('dnwell',(
        ('dnwell.2',(393,)),('dnwell.3',(394,)),('dnwell.4',(395,)),('dnwell.7',(397,)))),
    'p021-nwell_dotdash':('dnwell',(
        ('nwell.5',(401,402)),('nwell.7',(404,)))),
    'p024-lvtn_dotdash':('lvtn',(
        ('lvtn.1a',(412,)),('lvtn.2',(413,)),('lvtn.3a',(414,)),('lvtn.3b',(415,)),
        ('lvtn.9',(417,418)),('lvtn.10',(419,)),('lvtn.12',(420,)),('lvtn.13',(421,)),('lvtn.14',(422,)))),
    'p024-hvtr_dotdash':('hvtr',(('hvtr.1',(423,)),('hvtr.2',(424,425)))),
    'p047-hvi_dotdash':('hvi',(('hvi.1',(491,)),('hvi.2a',(492,)),('hvi.4',(493,)),('hvi.5',(494,)))),
    'p045-rdl_dotdash':('rdl',(
        ('rdl.1',(1273,)),('rdl.2',(1274,1275)),('rdl.3',(1276,)),('rdl.4',(1277,)),('rdl.5',(1278,)),('rdl.6',(1279,)))),
    'p029-rpm_dotdash':('rpm',(
        ('rpm.3',(1048,)),('rpm.4',(1049,1050)),('rpm.5',(1051,1052)),('rpm.6',(1053,1054)),
        ('rpm.7',(1055,)),('rpm.8',(1056,)),('rpm.9',(1057,1058)))),
    'p027-tunm_dotdash':('tunm',(
        ('tunm.1',(451,)),('tunm.2',(452,)),('tunm.4',(454,)),('tunm.5',(455,)),
        ('tunm.6a',(456,)),('tunm.7',(457,)),('tunm.8',(458,)))),
    'p049-hvntm_dotdash':('hvntm',(
        ('hvntm.1',(1062,)),('hvntm.2',(1063,)),('hvntm.3',(1064,)),('hvntm.4',(1065,1066)),
        ('hvntm.5',(1067,1068)),('hvntm.6a',(1069,1070)),('hvntm.6b',(1071,)),
        ('hvntm.7',(1072,1073)),('hvntm.9',(1074,)),('hvntm.10',(1075,)))),
    'p055-vhvi_dotdash_dotdash':('vhvi',(
        ('vhvi.vhv.5',(1155,)),('vhvi.1.-',(1156,)),('vhvi.2.-',(1157,)),('vhvi.3.-',(1158,)),
        ('vhvi.4.-',(1159,)),('vhvi.5.-',(1160,)),('vhvi.6.-',(1161,)),('vhvi.7.-',(1162,)),('vhvi.8.-',(1163,)))),
    'p050-denmos_dotdash':('extended_drain',(
        ('denmos.1',(901,)),('denmos.2',(902,)),('denmos.3',(903,)),('denmos.4',(904,)),
        ('denmos.5',(905,)),('denmos.6',(906,)),('denmos.7',(907,)),('denmos.10',(909,)),
        ('denmos.11',(910,)),('denmos.12',(911,)),('denmos.13',(912,913)))),
    'p051-depmos_dotdash':('extended_drain',(
        ('depmos.1',(915,)),('depmos.2',(916,)),('depmos.3',(917,)),('depmos.4',(918,)),
        ('depmos.5',(919,)),('depmos.6',(920,)),('depmos.7',(921,)),('depmos.12',(925,926)))),
    'p025-ncm_dotdash':('ncm',(('ncm.1',(1025,)),('ncm.2a',(1026,)),('ncm.7',(1027,)),('ncm.8',(1028,)))),
}
DEFINITIONS={
    'prec_resistor':'rpm AND (poly overlapping poly.rs) AND psdm',
    'de_nFet_drain':'((isolated tap) AND areaid.en) overlapping nwell',
    'de_nFET_gate':'deFET_gate overlapping (diff NOT dnwell)',
    'de_nFet_source':'(diff AND areaid.en) overlapping de_nFET_gate',
    'de_pFet_drain':'((isolated tap) AND areaid.en) not overlapping nwell',
    'de_pFET_gate':'deFET_gate overlapping (diff AND dnwell)',
    'de_pFet_source':'(diff AND areaid.en) overlapping de_pFET_gate',
    'deFET_gate':'(poly AND areaid.en) not overlapping pwm ; For CAD flows that do not have pwm layer, it is (poly AND areaid.en)',
    'VHVGate':'VHVPoly AND diff',
    'VHVPoly':'Poly OVERLAP vhvi:dg',
    'VHVSourceDrain':'(Diff AND tap) And vhvi NOT poly NOT diff:rs',
}


def parent_witnesses(rule,proof):
    if rule in ('rpm.3','rpm.4','rpm.5','rpm.9'):return ('prec_resistor',)
    if rule in ('hvntm.3','hvntm.7'):return (str(LAYERS['hvi'][0]),)
    if rule=='rdl.3':return (str(LAYERS['rdl'][0]),str(LAYERS['pad'][0]))
    if rule=='rdl.5':return (str(LAYERS['rdl'][0]),str(LAYERS['ccu1m'][0]))
    if proof=='nwell_holes':return ('nwell_holes',)
    key='areaid.en' if proof=='extended_drain' else proof
    return (str(LAYERS[key][0]),)


def bindings(catalog,inventory):
    validate_catalog(catalog)
    source={r['id']:r for r in catalog['rows']};result={}
    def add(section,rule,ids,proof):
        name='docs/rules/periphery/'+section+'.csv'
        parents=[r for r in inventory['rule_rows'] if r['source']==name and r['rule']==rule]
        if len(parents)!=1:raise ValueError('Missing/ambiguous reviewed source parent.')
        parent=parents[0]
        for number in ids:
            key='r'+str(number);row=source[key]
            if key in result or row['rule']!=rule.removesuffix('.-'):
                raise ValueError('Changed or duplicated literal marker binding.')
            result[key]=dict(rule=row['rule'],description=row['description'],parent=parent['id'],
                             parent_rule=rule,source_sha256=parent['source_sha256'],proof=proof,
                             parent_witnesses=list(parent_witnesses(rule,proof)))
    for section,(proof,rows) in FAMILIES.items():
        for rule,ids in rows:add(section,rule,ids,proof)
    add('p021-nwell_dotdash','nwell.6',(403,),'nwell_holes')
    if len(result)!=98:raise ValueError('Unexpected reviewed marker-binding inventory.')
    return result


def source_proof(source,inventory,catalog):
    source=Path(source);relations=bindings(catalog,inventory)
    paths={'docs/rules/periphery/'+name+'.csv' for name in FAMILIES}|{nsm.DEFINITION}
    files={};indexed={r['id']:r for r in inventory['rule_rows']}
    for name in sorted(paths):
        raw=(source/name).read_bytes();digest=nsm.sha(source/name)
        if digest!=inventory['source_files'][name]['sha256']:raise ValueError('Changed marker source: '+name)
        files[name]=digest
        if name!=nsm.DEFINITION:
            for row in manual_rows(raw,name):
                if any(indexed[row['id']].get(key)!=row[key] for key in
                       ('record','rule','description','flags','value','unit','source','source_sha256')):
                    raise ValueError('Marker inventory differs from captured source bytes.')
    definitions={r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO((source/nsm.DEFINITION).read_text(encoding='utf-8')))}
    if any(definitions.get(name)!=algorithm for name,algorithm in DEFINITIONS.items()):
        raise ValueError('Changed derived marker operand definition.')
    layer_metadata();layers={tuple(r['pair']):r for r in json.loads(LAYER_MAP_PATH.read_bytes())['layers']}
    aliases={}
    for key,(pair,name,purpose,provenance) in LAYERS.items():
        if not any(a['name']==name and a['purpose']==purpose and a['source']==provenance for a in layers[pair]['aliases']):
            raise ValueError('Changed marker-purpose mapping: '+key)
        aliases[key]=dict(pair=list(pair),name=name,purpose=purpose,source=provenance)
    return dict(files=files,definitions=DEFINITIONS,aliases=aliases,layer_map_sha256=LAYER_MAP_SHA256,
                conditions={key:dict(empty=list(inputs),reason=reason) for key,(inputs,reason) in PROOFS.items()},bindings=relations,
                discrepancies=[dict(id='r415',catalog_value_um='0.19',periphery_value_um='0.235',
                    status='numeric-disagreement-unresolved',scope='Empty LVTN proves absence under either threshold. No numeric checker or non-empty acceptance is claimed.')],
                exclusions=['r416','r426','r453','r908','r922','r930','r1047',*['r'+str(i) for i in range(988,1024)]])


def measure(layout):
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:
        raise ValueError('Expected one top and a 1 nm database unit.')
    top=layout.top_cell()
    for index in {top.cell_index(),*top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            transform=instance.cplx_trans
            if transform.mag!=1 or transform.angle%90!=0:
                raise ValueError('Unsupported transform for exact nwell-hole measurement.')
    counts={}
    for name,(pair,_,_,_) in LAYERS.items():
        iterator=top.begin_shapes_rec(layout.layer(*pair));count=0
        while not iterator.at_end():
            shape=iterator.shape()
            if name=='nwell' and not (shape.is_box() or shape.is_polygon() or shape.is_simple_polygon() or shape.is_text()):
                raise ValueError('Unsupported nwell shape semantics.')
            count+=1;iterator.next()
        counts[name]=count
    wells=k.Region(top.begin_shapes_rec(layout.layer(64,20))).merged()
    counts['nwell_holes']=sum(polygon.holes() for polygon in wells.each())
    return dict(top=top.name,counts=counts,measurement='All recursively referenced shapes per raw operand, including texts/paths. Nwell holes are measured in the exact merged polygon union; only unit orthogonal transforms and box/polygon nwell geometry are admitted.')


def absent(measurement,proof):
    counts=measurement['counts']
    if set(counts)!=set(LAYERS)|{'nwell_holes'} or any(type(v)is not int or v<0 for v in counts.values()):
        raise ValueError('Missing or invalid marker measurements.')
    return all(counts[name]==0 for name in PROOFS[proof][0])


def audit(path):
    before=nsm.sha(path);layout=k.Layout();layout.read(str(path));result=measure(layout)
    if nsm.sha(path)!=before:raise ValueError('Marker input changed during measurement.')
    return dict(**result,gds_sha256=before,checker_sha256=nsm.sha(__file__))


def preceding(geometry_case,nsm_case):
    result=deepcopy(geometry_case);rows={r['id']:r for r in result['rows']}
    for change in nsm_case['new_error_decisions']:
        if rows[change['id']]['disposition']!='unreviewed':raise ValueError('NSM delta would replace earlier coverage.')
        rows[change['id']].update(change)
    result['counts']=dict(Counter(r['disposition'] for r in result['rows']))
    if result['counts']!=nsm_case['counts'] or result['gds_sha256']!=nsm_case['measurement']['gds_sha256']:
        raise ValueError('NSM predecessor does not reconstruct exactly.')
    return result


def reconcile(catalog,inventory,baseline,corrected,measurement):
    relations=bindings(catalog,inventory);validate_scope(corrected)
    result=deepcopy(baseline);rows={r['id']:r for r in result['rows']}
    source={r['id']:r for r in catalog['rows']};parents={r['id']:r for r in corrected['rows']}
    if (len(rows)!=len(result['rows']) or set(rows)!=set(source)
            or result['counts']!=dict(Counter(r['disposition'] for r in rows.values()))
            or any(any(row.get(k)!=source[key][k] for k in ('id','record','rule')) for key,row in rows.items())):
        raise ValueError('Changed complete error ledger inventory or counts.')
    if (baseline['case']!=corrected['case'] or baseline['gds_sha256']!=corrected['gds_sha256']
            or baseline['gds_sha256']!=measurement['gds_sha256'] or baseline['top']!=measurement['top']
            or measurement['checker_sha256']!=nsm.sha(__file__)):
        raise ValueError('Mismatched marker evidence identity.')
    for key,binding in relations.items():
        parent=parents[binding['parent']]
        if (rows[key]['disposition']!='unreviewed' or parent['rule']!=binding['parent_rule']
                or parent['source_sha256']!=binding['source_sha256'] or parent['source']!=binding['parent'].rsplit('#',1)[0]
                or parent['record']!=int(binding['parent'].rsplit('#',1)[1])):
            raise ValueError('Changed or already reviewed marker parent/record.')
        if absent(measurement,binding['proof']):
            if (parent['disposition']!='absent-operand' or parent['witnesses']!={key:0 for key in binding['parent_witnesses']}
                    or any(type(v)is not int or v!=0 for v in parent['witnesses'].values())):
                raise ValueError('Historical parent does not support the fresh absence.')
            rows[key].update(disposition='absent-operand',binding=key,description=binding['description'],
                             parent=binding['parent'],absence_proof=binding['proof'])
    result['counts']=dict(Counter(r['disposition'] for r in result['rows']))
    return result


def build(progress=None):
    prior=nsm.build()
    if (json.dumps(prior,indent=2,ensure_ascii=False)+'\n').encode()!=nsm.OUTPUT.read_bytes():
        raise ValueError('NSM predecessor no longer reproduces.')
    old=json.loads(nsm.geometry.OUTPUT.read_bytes());manual=json.loads(nsm.scope.OUTPUT.read_bytes())
    catalog=json.loads((ROOT/nsm.geometry.previous.CATALOG).read_bytes())
    inventory=json.loads((ROOT/nsm.geometry.previous.PERIPHERY).read_bytes())
    cases=[]
    with TemporaryDirectory() as temporary:
        folder=Path(temporary)/'inputs';manifest=nsm.fixture.unpack(nsm.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',inventory,catalog)
        for entry in manifest['cases']:
            name=entry['case'];old_case=next(r for r in old['cases'] if r['case']==name)
            nsm_case=next(r for r in prior['cases'] if r['case']==name)
            corrected=next(r for r in manual['cases'] if r['case']==name)
            baseline=preceding(old_case,nsm_case);measurement=audit(folder/entry['gds'])
            result=reconcile(catalog,inventory,baseline,corrected,measurement)
            changes=[r for r,before in zip(result['rows'],baseline['rows']) if r!=before]
            if {r['id'] for r in changes}!=set(proof['bindings']):raise ValueError('Exact references do not establish the reviewed marker absence.')
            cases.append(dict(case=name,measurement=measurement,counts=result['counts'],
                              periphery_counts=corrected['counts'],new_error_decisions=changes))
            if progress:progress(dict(case=name,new_absence_decisions=len(changes),counts=result['counts']))
    inputs=[nsm.OUTPUT,nsm.geometry.OUTPUT,nsm.scope.OUTPUT,ROOT/nsm.geometry.previous.CATALOG,
            ROOT/nsm.geometry.previous.PERIPHERY,LAYER_MAP_PATH]
    sources=[Path(__file__),ROOT/'tests/test_sky130_marker_reconciliation.py']
    return dict(schema=1,chunk=6,status='partial-marker-operand-review',qualified=False,chunk_complete=False,
                execution_mode='fresh-recursive-raw-and-nwell-hole-measurement-and-source-reconciliation',
                bundle=prior['bundle'],inputs={p.relative_to(ROOT).as_posix():nsm.sha(p) for p in inputs},
                source_files={p.relative_to(ROOT).as_posix():nsm.sha(p) for p in sources},proof=proof,cases=cases,
                scope='Exactly 98 explicit catalog records gain measured absent-subject decisions. All other records, periphery states and application policies remain unchanged. No non-empty device qualification, numeric-discrepancy resolution, voltage-intent acceptance, fresh native/full-profile run, final electrical acceptance or chunk completion is claimed.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    report=build(progress=lambda row:print(json.dumps(row),flush=True));raw=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if OUTPUT.read_bytes()!=raw:raise ValueError('Saved marker review differs from current evidence.')
    else:OUTPUT.write_bytes(raw)
    print(json.dumps(dict(status=report['status'],qualified=False,chunk_complete=False)))


if __name__=='__main__':main()
