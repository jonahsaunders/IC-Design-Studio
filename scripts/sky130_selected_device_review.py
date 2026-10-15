"""Bind selected device checks and eight explicitly recommended catalog records."""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_selected_devices as checks
from scripts import sky130_boundary_interaction_review as previous_review
from scripts import sky130_catalog_queue as queue
from scripts import check_sky130_filled_replay as fixture
from scripts.sky130_rule_inventory import manual_rows

ROOT=queue.ROOT
PREVIOUS='docs/validation/sky130-boundary-interactions-2026-10-15.json'
PREVIOUS_SHA='eb6884f3730351f977cd77c6e86fea072b1c86e4a4afef44bdc84b81ef1e3cee'
OUTPUT=ROOT/'docs/validation/sky130-selected-devices-2026-10-15.json'
ADVISORY_SOURCES={
    'docs/rules/periphery-rules.rst':'a4fec57aa417caa1b52d67b684a6b17dfc1ed0b69724ffe121de421bd938d44e',
    'docs/rules/periphery/p040-m2_dotdash.csv':'edd28e2d9e3740575bf9e44df7dd31ab6443b376ff6e8978c2b9210647a5d24e'}
ADVISORIES={**{'s'+str(i):('x.18','docs/rules/periphery/p018-x_dotdash.csv',33) for i in range(5)},
    's5':('x.23f','docs/rules/periphery/p018-x_dotdash.csv',43),
    's6':('x.27','docs/rules/periphery/p018-x_dotdash.csv',47),
    's8':('m2.3c','docs/rules/periphery/p040-m2_dotdash.csv',6)}


def reconstruct(reader):
    catalog,baselines,_=previous_review.reconstruct(reader);previous=reader.read(PREVIOUS,PREVIOUS_SHA)
    for path,digest in previous['inputs'].items():reader.read(path,digest)
    for before,prior in zip(baselines,previous['cases']):
        if before['case']!=prior['case'] or before['gds_sha256']!=prior['original_gds_sha256']:
            raise ValueError('Changed selected-device predecessor identity.')
        rows=queue.apply_decisions(before['rows'],prior['original_new_error_decisions'],catalog)
        if dict(Counter(r['disposition'] for r in rows))!=prior['original_error_counts']:
            raise ValueError('Selected-device predecessor does not reconstruct.')
        before.update(rows=rows,counts=prior['original_error_counts'])
    return catalog,baselines,previous


def source_proof(folder,catalog):
    raw={name:(Path(folder)/name).read_bytes() for name in checks.SOURCE['files']|ADVISORY_SOURCES}
    for name,digest in (checks.SOURCE['files']|ADVISORY_SOURCES).items():
        if queue.sha(raw[name])!=digest:raise ValueError('Changed selected-device source: '+name)
    table=checks.SOURCE['device_table'];table_raw=(ROOT/table['path']).read_bytes()
    if queue.sha(table_raw)!=table['sha256']:raise ValueError('Changed device selection table.')
    values=list(csv.reader(io.StringIO(table_raw.decode()),delimiter='\t'));header=[s.strip() for s in values[0]]
    if len(set(header))!=len(header) or any(len(r)!=len(header) for r in values[1:]):
        raise ValueError('Ambiguous or incomplete device selection table.')
    table_rows={i:dict(record=i,**dict(zip(header,[s.strip() for s in r]))) for i,r in enumerate(values[1:],1)}
    selected={name:[table_rows[i] for i in ids] for name,ids in
              dict(vpp=range(44,54),pwell_resistor=(6,),pnp=(84,)).items()}
    for name,column in (('vpp','capacitor.dg'),('pwell_resistor','pwell.rs'),('pnp','pnp.dg')):
        if any(row[column]!='D' for row in selected[name]):raise ValueError('Device prerequisite is not a drawn layer.')
    if selected['pwell_resistor'][0]['Layout Model']!='xpwres' or selected['pnp'][0]['Layout Model']!='pnppar pnppar5x':
        raise ValueError('Changed explicit resistor/PNP selection.')
    if any('VPP' not in row['Name'] or 'xcmvpp' not in row['Layout Model'] for row in selected['vpp']):
        raise ValueError('Changed VPP device selection.')
    legend=raw['docs/rules/layers/table-f2a-lvs-key.rst'].decode()
    if '``D`` = DRAWN indicates that a layer is drawn by Design.' not in legend:
        raise ValueError('Changed device table drawn-layer meaning.')
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    aliases=dict(vpp=('capacitor','drawing'),pwell_resistor=('pwell','resistor'),pnp=('pnp','drawing'))
    for name,selection in checks.SUBJECTS.items():
        alias,purpose=aliases[name]
        if [r['GDS layer:datatype'] for r in layers if r['Layer name']==alias and purpose in r['Purpose'].split(', ')]!=['%s:%s'%selection['pair']]:
            raise ValueError('Changed mandatory drawn device purpose.')
    for name,pair in checks.LAYERS.items():
        if [r['GDS layer:datatype'] for r in layers if r['Layer name']==name and 'drawing' in r['Purpose'].split(', ')]!=['%s:%s'%pair]:
            raise ValueError('Changed implant geometry purpose.')
    indexed={r['id']:r for r in catalog['rows']};bindings={}
    # Each group is an explicit, fixed catalog selection. The full errors.csv
    # bytes are pinned, and each retained catalog row is checked against them.
    errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    for name,selection in checks.SUBJECTS.items():
        for key in selection['ids']:
            row=indexed[key];error=errors[key]
            if row['description']!=error['Description'] or row['rule']!=error['Name']:
                raise ValueError('Changed explicit device catalog record.')
            if name=='vpp' and not row['rule'].startswith('vpp.') or name=='pwell_resistor' and not row['rule'].startswith('pwres.'):
                raise ValueError('Wrong device family binding.')
            bindings[key]=dict(subject=name,record=row,device_table_records=[r['record'] for r in selected[name]])
    for key,text in {'r453':'0.095 min. extension of tunm beyond gate','r1061':'hvntm must be drawn inside hvi'}.items():
        if indexed[key]['description']!=text or indexed[key]['rule']!=checks.CHECKS[key]:
            raise ValueError('Changed explicit implant check.')
        bindings[key]=dict(record=indexed[key],operation='95 nm enclosure of tunm-overlapping gates' if key=='r453' else 'drawn hvntm minus hvi')
    tunm=list(manual_rows(raw['docs/rules/periphery/p027-tunm_dotdash.csv'],'docs/rules/periphery/p027-tunm_dotdash.csv'))
    if tunm[2]['rule']!='tunm.3' or tunm[2]['value']!='0.095' or tunm[3]['value']!='0.095' or tunm[3]['unit']!='µm':
        raise ValueError('Changed tunm enclosure value or adjoining outside-gate rule.')
    rr=raw['docs/rules/periphery-rules.rst'].decode().split('.. _RR:',1)[1].split('.. _AL:',1)[0]
    if 'Recommended rule at any IP level' not in rr:raise ValueError('Changed RR meaning.')
    advisory=[]
    for key,(rule,path,record) in ADVISORIES.items():
        parent=next(r for r in manual_rows(raw[path],path) if r['record']==record)
        if parent['rule']!=rule or parent['flags']!=['RR'] or indexed[key]['rule']!=rule:
            raise ValueError('Changed advisory parent; required rules cannot be waived.')
        advisory.append(dict(id=key,disposition='advisory',execution='not-claimed',
            parent={k:parent[k] for k in ('id','rule','description','flags','value','unit','source_sha256')},
            reason='Published RR flag: recommended rule at any IP level. Numerical execution is not claimed.'))
    return dict(source=checks.SOURCE,advisory_sources=ADVISORY_SOURCES,device_rows=selected,bindings=bindings,
                advisory_decisions=advisory,interpretation=checks.SCOPE)


def apply_advisories(rows,decisions,catalog):
    if len(decisions)!=len(ADVISORIES) or {r['id'] for r in decisions}!=set(ADVISORIES):
        raise ValueError('Incomplete or unrelated advisory decision set.')
    result=deepcopy(rows);indexed={r['id']:r for r in result}
    for decision in decisions:
        key=decision['id'];row=indexed[key];rule,path,record=ADVISORIES[key];parent=decision.get('parent',{})
        if row['disposition']!='unreviewed' or decision.get('disposition')!='advisory' or decision.get('execution')!='not-claimed' or \
                parent.get('id')!=path+'#'+str(record) or parent.get('rule')!=rule or parent.get('flags')!=['RR']:
            raise ValueError('Overlapping or invalid advisory decision.')
        row.update(decision)
    queue.validate_rows(result,catalog);return result


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
                raise ValueError('Changed selected-device reference identity.')
            for report in (original,corrected):
                checks.evaluate(report,report['gds_sha256'],report['top'])
                if any(r['disposition']!='absent-operand' for r in report['rows']):raise ValueError('Reference requires a selected device review.')
            if original['measurements']!=corrected['measurements']:raise ValueError('Device subjects changed during outline correction.')
            rows=queue.apply_decisions(before['rows'],original['rows'],catalog)
            rows=apply_advisories(rows,proof['advisory_decisions'],catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Reference queues differ.')
            batches=current
            cases.append(dict(case=name,original_gds_sha256=original['gds_sha256'],original_measurement=original,
                original_new_error_decisions=original['rows'],advisory_decisions=proof['advisory_decisions'],
                original_error_counts=dict(Counter(r['disposition'] for r in rows)),corrected_gds_sha256=corrected['gds_sha256'],
                corrected_selected_devices=corrected))
    paths=[Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_selected_devices.py',
           ROOT/'icstudio/digital_sky130_rules.py',ROOT/'icstudio/digital_sky130_rule_worker.py',ROOT/'tests/test_sky130_application_rules.py',
           ROOT/checks.SOURCE['device_table']['path']]
    return dict(schema=1,chunk=6,status='selected-device-requirements-and-advisories-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in paths},
        proof=proof,cases=cases,remaining_original_batches=[dict(id=b['id'],count=b['count'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Thirty-six selected device/implant records are absent on the exact reference streams. Two implant checks '
              'execute numerically on nonempty controls; present VPP, pwell resistor and PNP candidates retain unresolved rules. '
              'Eight RR records are explicitly advisory, not executed passes. The original catalog retains 485 unreviewed records. '
              'Required geometry, mask generation, density and chip-context obligations remain open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--check',action='store_true');a=p.parse_args();raw=(json.dumps(build(a.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:
        if a.output.read_bytes()!=raw:raise ValueError('Saved selected-device review differs.')
    else:a.output.write_bytes(raw)
    print(json.dumps({c['case']:c['original_error_counts'] for c in json.loads(raw)['cases']}))
