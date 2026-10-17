"""Replay the full corrected catalog and bind sixteen explicit empty targets."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_selected_targets as checks
from scripts import check_sky130_delivery_catalog as delivery

ROOT=delivery.ROOT
OUTPUT=ROOT/'docs/validation/sky130-selected-targets-2026-10-15.json'
PREVIOUS='docs/validation/sky130-delivery-catalog-2026-10-15.json'
PREVIOUS_SHA='1c581d1dfaef93b577221f9130dec1978de1251d3aa6951861a4abb8087fcf06'
LITERAL={
    'r1326':('pad.11','Bondpad should not have 90 degree corner'),
    'r1327':('pad.11','Bondpad should have 45 degree corner'),
    'r1328':('pad.11','Bondpad should have only 4 45 degree corner'),
    'r1329':('pad.11','Bondpad should have only 4 orthogonal edges'),
    'r1330':('pad.12','7.0 Min length of 45 degree bevel on Bond pad'),
    'r1331':('pad.13','8.8 Max length of 45 degree bevel on Bond pad'),
    'r1362':('pad.9.1','150.0um Max Width/Length of bond pad'),
    'r1369':('cupad.1','5 min. width of pad opening inside inductor'),
    'r1370':('cupad.2','0 min. enclosure of pad opening inside inductor by pmm'),
    'r1371':('cupad.2','pad opening inside inductor must be enclosed by pmm'),
    'r1372':('cupad.3','2.7 min. enclosure of pad opening inside inductor by met5'),
    'r1373':('cupad.3','pad opening inside inductor must be enclosed by met5'),
    'r1374':('cupad.4','10.75 min. enclosure of pmm  inside inductor by rdl'),
    'r1375':('cupad.4','pmm  inside inductor must be enclosed by rdl'),
    'r1476':('chvtpm.4','0 min. enclosure of ((LVnwell overlapping Var_channel) AND hvtp) by CLHVTPM'),
    'r1493':('chvntm.3','0.185 Min Enclosure of ndiff inside hvi by chvntm')}


def source_proof(folder,catalog):
    raw={name:delivery.checked(Path(folder)/name,digest) for name,digest in checks.SOURCE['files'].items()}
    table=checks.SOURCE['device_table'];table_raw=delivery.checked(ROOT/table['path'],table['sha256'])
    symbols=raw['docs/rules/layers/table-f2a-lvs-key.rst'].decode()
    delivery.require('``D`` = DRAWN indicates that a layer is drawn by Design.' in symbols, 'Changed F2a drawn-layer meaning.')
    devices=[]
    for i,row in enumerate(csv.DictReader(io.StringIO(table_raw.decode()),delimiter='\t'),1):
        row={key.strip():value.strip() for key,value in row.items()}
        if row['Category']=='INDUCTOR':devices.append(dict(record=i,**row))
    delivery.require([(r['record'],r['Name'],r['inductor:dg'],r['Layout Model']) for r in devices]==[
        (54,'Inductor','D','xind'),(55,'Cu Inductor','D','*xind4*'),(56,'Balun Inductor [#f15]_','D','*balun*')],
        'Changed captured inductor family inventory or required drawn identifier.')
    definitions={r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO(raw['docs/rules/layers/table-c3-device-lvs-other.csv'].decode()))}
    required={'bondPad':'pad:dg OUTSIDE areaid:ft', 'Var_channel':'poly AND tap AND (nwell NOT hvi) NOT areaid.ce', 'LVnwell':'nwell NOT hvi'}
    delivery.require(all(definitions.get(key)==value for key,value in required.items()), 'Changed explicit target definition.')
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    aliases={'pad_pin':('pad','pin'),'pad_label':('pad','label'),'pad_legacy_pin':('pad','pin'),
        'pad_center':('padCenter','drawing'),'pad_frame':('areaid.fe','identifier'),
        'inductor_label':('inductor','label'), **{'inductor_terminal'+str(n):('inductor','terminal'+str(n)) for n in (1,2,3)},
        'cfom_drawing':('cfom','drawing'),'chvntm_drawing':('chvntm','drawing'),'clvom_drawing':('clvom','drawing'),
        'areaid_hl':('areaid.hl','identifier'),'diff_hv':('diff','high voltage')}
    mappings={}
    for name,pair in checks.LAYERS.items():
        alias,purpose=aliases.get(name,(name,'mask' if name in ('cpdm','cp1m','cfom','chvntm','clvom') else 'drawing'))
        matches=[r for r in layers if r['Layer name']==alias and purpose in r['Purpose'].split(', ') and r['GDS layer:datatype']=='%s:%s'%pair]
        delivery.require(len(matches)==1,'Changed selected-target layer purpose: '+name)
        mappings[name]=matches[0]
    errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    indexed={r['id']:r for r in catalog['rows']};bindings={}
    for subject,group in checks.GROUPS.items():
        for key in group['ids']:
            delivery.require((indexed[key]['rule'],indexed[key]['description'])==LITERAL[key] and
                (errors[key]['Name'],errors[key]['Description'])==LITERAL[key], 'Changed literal target record.')
            bindings[key]=dict(record=indexed[key],subject=subject,raw_guards=list(group['raw']),
                              candidate_tokens=list(checks.HINTS[group['hints']]))
    delivery.require(set(bindings)==set(LITERAL), 'Incomplete selected-target source binding.')
    return dict(source=checks.SOURCE,bindings=bindings,definitions=required,inductor_device_rows=devices,
                layer_purposes=mappings,interpretation=checks.SCOPE,
                unresolved='ViaTop aliases, mask-derived hugePad and other pad variants remain unreviewed. These absence proofs do not implement nonempty pad or generated-mask rules.')


def build(workspace=None,case=None,progress=None):
    workspace=Path(workspace or ROOT.parents[1]).resolve()
    previous=json.loads(delivery.checked(ROOT/PREVIOUS,PREVIOUS_SHA))
    fresh=delivery.build(workspace,case,progress)
    catalog=json.loads((ROOT/delivery.queue.CATALOG).read_bytes())
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';delivery.fixture.unpack(delivery.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
    for row in fresh['cases']:
        original=delivery.pick(previous,row['case'])
        delivery.require(row['gds_sha256']==original['gds_sha256'] and row['counts']==original['counts'],
                         'Fresh corrected replay differs from the retained baseline.')
        path=workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        report=checks.audit(path);checks.evaluate(report,row['gds_sha256'],row['top'])
        delivery.require(report['unreviewed']==0,'Reference contains a selected target requiring further review.')
        row['rows']=delivery.apply_rows(row['rows'],report['rows'],catalog,'selected_targets',row['provenance'])
        row['counts']=dict(Counter(r['disposition'] for r in row['rows']))
        row['measurements']['selected_targets']=report
        row['remaining_batches']=delivery.queue.partition([r for r in row['rows'] if r['disposition']=='unreviewed'])
        if progress:progress(dict(case=row['case'],stage='selected-targets-replayed',counts=row['counts']))
    fresh.update(status='corrected-catalog-selected-targets-reviewed',predecessor=dict(path=PREVIOUS,sha256=PREVIOUS_SHA))
    fresh['proofs']['selected_targets']=proof
    for path in (Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_selected_targets.py'):
        fresh['source_files'][path.relative_to(ROOT).as_posix()]=delivery.sha(path)
    fresh['source_files']=dict(sorted(fresh['source_files'].items()))
    fresh['scope']+=' Sixteen additional explicit targets are absent with conservative raw/mask/intent guards; nonempty requirements stay unreviewed.'
    return fresh


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--case',choices=delivery.queue.CASES)
    p.add_argument('--output',type=Path,default=OUTPUT);p.add_argument('--check',action='store_true');a=p.parse_args()
    result=build(a.workspace,a.case,lambda row:print(json.dumps(row),flush=True))
    raw=(json.dumps(result,indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:delivery.require(a.output.read_bytes()==raw,'Saved target review differs from fresh execution.')
    else:a.output.write_bytes(raw)
