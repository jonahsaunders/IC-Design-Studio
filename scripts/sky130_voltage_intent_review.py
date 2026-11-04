"""Check explicit nominal reference voltage intent against retained physical data.

The zero-HV-source result is conditional on the new, declared reference contract.
It is not a transient simulation, a general HV propagator, or foundry ERC.
"""
import argparse
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from icstudio.digital_macro import verify_inputs
from icstudio.digital_platform import validate as validate_platform
from scripts import sky130_voltage_contract as voltage
from scripts import sky130_selected_subject_review as previous
from scripts.sky130_rule_inventory import manual_rows, validate_unreviewed

ROOT=previous.ROOT
sha=previous.sha
require=voltage.require
CONTRACT=ROOT/'docs/qualification/sky130-reference-voltage-contract.json'
OUTPUT=ROOT/'docs/validation/sky130-voltage-intent-2026-10-14.json'
LAYERS={'hvi':(75,20),'areaid.hl':(81,63),'diff.hv':(65,8),'vhvi':(74,21),'uhvi':(74,22)}
LABELS=('hv_bb','hv_lv','shv_nwell')
RULES=('hvnwell.11','hv.X.1','hv.X.4')
LIB='sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib'
CDL='sky130hd/cdl/sky130hd.cdl'
SCOPE=('Conditional absence of HV targets in the three exact nominal 0–1.8 V HD reference contracts. '
       'No transient voltages, supply integrity, arbitrary designs, nonempty HV propagation, '
       'foundry ERC or complete physical qualification is established.')


def read(path):
    return json.loads(Path(path).read_bytes())


def authenticated(path, digest):
    raw=Path(path).read_bytes()
    import hashlib
    require(hashlib.sha256(raw).hexdigest()==digest,'Changed authenticated input: '+str(path))
    return raw


def source_proof(source, inventory):
    validate_unreviewed(inventory)
    files={};parents={}
    names=('docs/rules/hv.rst',previous.marker.nsm.DEFINITION,
           'docs/rules/periphery/p047-hvnwell_dotdash.csv','docs/rules/periphery/p054-hv_dotdash_dotdash.csv')
    for name in names:
        raw=authenticated(Path(source)/name,inventory['source_files'][name]['sha256'])
        files[name]=inventory['source_files'][name]['sha256']
        if '/periphery/' in name:
            known={r['id']:r for r in inventory['rule_rows']}
            for row in manual_rows(raw,name):
                require(all(row[key]==known[row['id']][key] for key in ('rule','record','description','flags','value','unit')),
                        'Source requirement changed.')
                if row['rule'] in RULES:parents[row['rule']]=known[row['id']]
    require(set(parents)==set(RULES),'Missing exact voltage requirement.')
    definitions={r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO(
        (Path(source)/previous.marker.nsm.DEFINITION).read_text(encoding='utf-8')))}
    require(definitions['hv_source/drain']=='= (diff andNot poly) that overlaps diff.hv'
            and definitions['HV_nwell']=='(nwell AND hvi) OR (nwell overlapping areaid.hl)',
            'Changed HV target definition.')
    text=(Path(source)/names[0]).read_text(encoding='utf-8')
    require('High Voltage is defined as a voltage outside the range of GND to Vcc.' in text
            and 'Beginning with taggedhvSRCDRN' in text,'Changed HV source/propagation methodology.')
    previous.layer_metadata()
    layers={tuple(r['pair']):r['aliases'] for r in read(previous.LAYER_MAP_PATH)['layers']}
    aliases={}
    for name,pair in LAYERS.items():
        expected=('diff','high voltage') if name=='diff.hv' else (name,'identifier' if name=='areaid.hl' else 'drawing')
        selected=[a for a in layers[pair] if (a['name'],a['purpose'])==expected and a['source']=='published']
        require(len(selected)==1,'Changed voltage layer purpose: '+name)
        aliases[name]=dict(pair=list(pair),**selected[0])
    return dict(files=files,parents=parents,aliases=aliases,layer_map_sha256=sha(previous.LAYER_MAP_PATH),
                definitions={name:definitions[name] for name in ('hv_source/drain','HV_nwell')},
                interpretation=SCOPE)


def measure(layout):
    diagnostic=previous.device.grid.check(layout)
    require(not any(r['violations'] for r in diagnostic['checks'] if r['rule'].startswith('profile.')),
            'Unsupported geometry for HV-source measurement.')
    top=layout.top_cell();counts={}
    for name,pair in LAYERS.items():
        shapes=top.begin_shapes_rec(layout.layer(*pair));count=0
        while not shapes.at_end():count+=1;shapes.next()
        counts[name]=count
    labels={name:0 for name in LABELS}
    for layer in layout.layer_indexes():
        shapes=top.begin_shapes_rec(layer)
        while not shapes.at_end():
            shape=shapes.shape()
            if shape.is_text():
                # Conservative normalization prevents disguised exception tags
                # from supporting a claim that the reference has no HV intent.
                name=shape.text.string.strip().casefold()
                if name in labels:labels[name]+=1
            shapes.next()
    return dict(top=top.name,raw_layers=counts,exception_labels=labels)


def decisions(measurement, contract_check):
    require(set(measurement['raw_layers'])==set(LAYERS) and set(measurement['exception_labels'])==set(LABELS),
            'Incomplete HV-source measurements.')
    values=[*measurement['raw_layers'].values(),*measurement['exception_labels'].values()]
    require(all(type(value)is int and value>=0 for value in values),'Invalid HV-source count.')
    require(contract_check.get('status')=='nominal-voltage-contract-consistent'
            and contract_check.get('power_net_hv')==[] and contract_check.get('qualified') is False,
            'Voltage contract must be checked before interpreting absent HV tags.')
    disposition='execution-review-required' if any(values) else 'absent-operand'
    return {rule:dict(disposition=disposition,condition='declared-nominal-reference-voltage-contract',
                     reason=('No declared HV sources, raw HV selectors or exception labels under the checked nominal contract; '
                             'the published propagation starts from HV-tagged diffusion.') if not any(values)
                            else 'An HV selector or exception label requires explicit review.') for rule in RULES}


def case_audit(outputs, entry, contract, capture, archive_files, baseline):
    case=entry['case'];finish=outputs/'sky130-filled-electrical-v1'/case/'finish'
    files={}
    def captured(name):
        path=finish/name;key=path.relative_to(outputs.parent).as_posix();record=archive_files[key]
        raw=authenticated(path,record['sha256']);require(len(raw)==record['bytes'],'Changed captured input size.')
        files[key]=dict(sha256=record['sha256'],bytes=record['bytes'])
        return raw
    result=json.loads(captured('result.json'));job=json.loads(captured('input.json'))
    require(sha(finish/'result.json')==baseline['finish_result_sha256'],'Changed final implementation.')
    cfg=verify_inputs(result,job);platform=validate_platform(cfg['platform']);art=result['digital_result']['artifacts']
    require(platform['corners']=={'typical':[LIB]} and platform['corner']=='typical'
            and result['digital_result']['platform']['fingerprint']==platform['fingerprint'],
            'Unsupported library corner or platform identity.')
    for key in ('top','gds_sha256','checkpoint_sha256'):
        expected=cfg['top'] if key=='top' else art[key.split('_')[0]]['sha256']
        require(contract[key]==entry[key]==baseline[key]==expected,'Contract/layout/checkpoint identity differs.')
    for key in ('gds','checkpoint'):
        require(sha(finish/art[key]['path'])==art[key]['sha256'],'Changed final physical artifact.')
    locked={r['path']:r for r in platform['files']}
    texts={}
    for name in (LIB,CDL):
        raw=captured('platform/'+name)
        require(sha(finish/'platform'/name)==locked[name]['sha256'] and len(raw)==locked[name]['bytes'],
                'Library bytes differ from the captured platform.')
        texts[name]=raw.decode().replace('\r\n','\n')
    cells=voltage.liberty(texts[LIB]);physical=voltage.empty_physical_cells(texts[CDL])
    require(not set(cells)&set(physical),'Ambiguous physical master metadata.');cells.update(physical)
    database=json.loads(captured('filled/database.json'))
    native_root=outputs/('sky130-filled-capacitance-v'+str(2 if case=='counter' else 3))/case/'filled'
    inventory=json.loads(authenticated(native_root/'inventory.json',capture['files']['filled/inventory.json']))
    native_path=native_root/(entry['top']+'.ext');native_sha=capture['files']['filled/'+entry['top']+'.ext']
    require(sha(native_path)==native_sha,'Changed retained native circuit.')
    native=previous.device.circuit.headers(native_path)
    checked=voltage.validate(contract,inventory,database,cells,native)
    require(sha(native_path)==native_sha,'Native circuit changed while reading.')
    return dict(contract_check=checked,authenticated_files=files,
                inventory_sha256=capture['files']['filled/inventory.json'],native_ext_sha256=native_sha,
                platform_fingerprint=platform['fingerprint'])


def build(outputs, electrical_manifest):
    outputs=Path(outputs);electrical_record=read(ROOT/'docs/validation/sky130-filled-electrical-2026-10-14.json')
    archive=json.loads(authenticated(electrical_manifest,electrical_record['archive']['manifest_sha256']))
    preceding=read(previous.OUTPUT);audit=read(ROOT/'docs/validation/sky130-selected-subjects-audit-2026-10-14.json')
    require(sha(previous.OUTPUT)==audit['data']['sha256'] and preceding['chunk_complete'] is False,
            'Changed selected-subject predecessor.')
    for name,digest in preceding['inputs'].items():authenticated(ROOT/name,digest)
    device=read(previous.device.OUTPUT)
    captures=read(ROOT/'docs/validation/sky130-fill-progress-2026-10-11.json')
    contracts=read(CONTRACT)
    require(contracts['schema']==1 and contracts['origin']=='qualification-reference-design-contract'
            and contracts['qualified'] is False and [c['case'] for c in contracts['cases']]==['counter','uart','apb'],
            'Missing explicit reference contracts.')
    inventory=read(ROOT/previous.marker.nsm.geometry.previous.PERIPHERY)
    cases=[];fixture=previous.marker.nsm.fixture
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',inventory)
        for entry in manifest['cases']:
            name=entry['case'];contract=next(c for c in contracts['cases'] if c['case']==name)
            capture_ref=next(c for c in captures['references'] if c['case']==name)['native_circuit_capture']
            capture=json.loads(authenticated(ROOT/capture_ref['path'],capture_ref['sha256']))
            variant=next(v for v in capture['variants'] if v['variant']=='filled')
            require(variant['source_gds_sha256']==entry['gds_sha256'] and variant['checkpoint_sha256']==contract['checkpoint_sha256'],
                    'Capture belongs to a different physical reference.')
            entry=dict(entry,checkpoint_sha256=variant['checkpoint_sha256'])
            baseline=next(c for c in electrical_record['application_cases'] if c['case']==name)
            execution=case_audit(outputs,entry,contract,capture,archive['files'],baseline)
            earlier=next(c for c in device['cases'] if c['case']==name)['execution']
            require(execution['native_ext_sha256']==earlier['native_ext_sha256']
                    and execution['contract_check']['native_models']==earlier['native_models'],
                    'Voltage review differs from full drawn/native device census.')
            gds=folder/entry['gds'];layout=k.Layout();layout.read(str(gds));measurement=measure(layout)
            require(measurement['top']==entry['top'] and sha(gds)==entry['gds_sha256'],'Changed HV-source layout.')
            selected=decisions(measurement,execution['contract_check'])
            parent=next(c for c in preceding['cases'] if c['case']==name)
            counts=dict(parent['periphery_counts'])
            old=next(c for c in read(ROOT/'docs/validation/sky130-esd-fuse-2026-10-14.json')['cases'] if c['case']==name)
            for rule,decision in selected.items():
                previous_row=next(r for r in old['open_periphery'] if r['rule']==rule)
                require(previous_row['disposition']=='execution-review-required'
                        and previous_row['id']==proof['parents'][rule]['id'],'Changed periphery predecessor.')
                if decision['disposition']=='absent-operand':
                    counts['execution-review-required']-=1;counts['absent-operand']+=1
            cases.append(dict(case=name,gds_sha256=entry['gds_sha256'],checkpoint_sha256=entry['checkpoint_sha256'],
                execution=execution,measurement=measurement,decisions=selected,capture_record=capture_ref,
                periphery_counts=counts,error_counts=parent['error_counts']))
    inputs=[CONTRACT,previous.OUTPUT,ROOT/'docs/validation/sky130-selected-subjects-audit-2026-10-14.json',
            previous.device.OUTPUT,ROOT/'docs/validation/sky130-fill-progress-2026-10-11.json',
            ROOT/'docs/validation/sky130-filled-electrical-2026-10-14.json',
            ROOT/'docs/validation/sky130-esd-fuse-2026-10-14.json',ROOT/previous.marker.nsm.geometry.previous.PERIPHERY]
    sources=[Path(__file__),Path(voltage.__file__),ROOT/'tests/test_sky130_voltage_contract.py',
             ROOT/'tests/test_sky130_voltage_intent.py',Path(previous.device.circuit.__file__),
             Path(previous.device.grid.__file__)]
    return dict(schema=1,chunk=6,status='conditional-nominal-voltage-intent-reviewed',qualified=False,chunk_complete=False,
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
        source_files={p.relative_to(ROOT).as_posix():sha(p) for p in sources},bundle=manifest,
        electrical_manifest_sha256=sha(electrical_manifest),proof=proof,cases=cases,scope=SCOPE)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outputs',type=Path,required=True)
    parser.add_argument('--electrical-manifest',type=Path,required=True)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    data=build(args.outputs,args.electrical_manifest);raw=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:require(OUTPUT.read_bytes()==raw,'Saved voltage-intent review differs.')
    else:OUTPUT.write_bytes(raw)
    print(json.dumps({c['case']:c['periphery_counts'] for c in data['cases']}))
