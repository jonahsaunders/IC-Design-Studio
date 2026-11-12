"""Validate three exact IHP fill references without claiming PDK signoff."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
CASES={'counter','uart','apb'}
RECIPE='ihp-signal-clearance-block-fill-v1'
METALS={'Metal1','Metal2','Metal3','Metal4','Metal5','TopMetal1','TopMetal2'}
SUPPLEMENT={'AFil.c.Cont','AFil.c.GatPoly','AFil.d.NWell','AFil.d.nBuLay',
            'AFil.i.crossing','AFil.i.clearance','AFil.j.nSD_block','AFil.j.SalBlock',
            'GFil.e.NWell','GFil.e.nBuLay','scope.block_boundaries','scope.800um_chip_windows'}
SUPPLEMENT|={f'exclusion.{n}.nofill' for n in (1,5,8,10,30,50,67,126,134)}
SUPPLEMENT|={f'exclusion.{n}.metal' for n in (8,10,30,50,67,126,134)}
SOURCE_FILES={'icstudio/'+name+'.py' for name in ('digital_ihp_fill','digital_ihp_geometry',
    'digital_ihp_fill_worker','digital_ihp_inventory','digital_physical','digital_flow',
    'digital_identity','digital_platform','digital_rc','digital_macro','digital_runtime','digital_implementation','digital_reports')}


def require(condition,message):
    if not condition:raise ValueError('IHP fill acceptance: '+message)


def identity(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(entry,root):
    path=(root/entry['path']).resolve()
    require(path.is_relative_to(root.resolve()) and identity(entry.get('sha256')) and
            path.is_file() and sha(path)==entry['sha256'],'changed or missing portable evidence')
    return json.loads(path.read_text(encoding='utf-8'))


def capacitance(report):
    require(report.get('status')=='cell-capacitance-subnetwork-identical' and
            report.get('qualified') is False and report['maximum_raw_change_af']==0 and
            report['total_native_residue_change_af']==0 and report['native_overlap_residues']==[] and
            report['internal_nodes']>0 and report['compared_pairs']>0,
            'the complete protected circuit capacitance must be exactly unchanged')


def timing(report, disconnected=()):
    require(report['status']=='PASS' and report['unconstrained'] is False and
            report['incomplete_reasons']==[] and report['electrical_status']=='No reported violations' and
            report['paths'] and {p['check'] for p in report['paths']}=={'setup','hold'},'incomplete or failed timing')
    summary=report['summary']
    for kind in ('setup','hold'):
        slack=summary[kind+'_worst_slack_ns']
        require(type(slack) in (float,int) and math.isfinite(slack) and slack>=0 and
                summary[kind+'_reported_violations']==0 and summary[kind+'_total_negative_slack_ns']==0,
                'timing or electrical limits failed')
    annotation=report['parasitic_annotation']
    require(all(annotation.get(k)==[] for k in ('connected_unannotated_drivers','partially_unannotated_drivers')) and
            set(annotation['unannotated_drivers'])==set(annotation['disconnected_outputs'])==set(disconnected),
            'incomplete extracted parasitic annotation')


def validate_reference(row):
    case=row['case'];require(case in CASES,'unknown reference')
    final,original=row['artifacts'],row['original_artifacts']
    require(set(final)=={'gds','lef','spef','netlist','checkpoint'} and
            set(original)=={'gds','spef','netlist','checkpoint'} and
            all(identity(h) for h in [*final.values(),*original.values()]),'invalid artifact identities')
    require(all(final[k]==original[k] for k in ('spef','netlist','checkpoint')),'nominal circuit model changed')
    worker=row['worker']
    require(worker['status']=='generated_and_verified' and worker['qualified'] is False and
            worker['recipe']==RECIPE and worker['source_gds_sha256']==original['gds'] and
            worker['filled_gds_sha256']==final['gds'] and worker['checkpoint_sha256']==final['checkpoint'] and
            type(worker['markers']) is int and worker['markers']==0 and worker['signal_clearance_nm']==9000,
            'geometry, native rule result or circuit clearance changed')
    require(all(worker.get(k) is True for k in ('physical_devices_identical','native_lumped_resistance_identical','original_circuit_masks_preserved')),
            'missing circuit preservation proof')
    capacitance(worker['capacitance'])
    for layer in ('8','10','30','50','67','126','134'):
        low,high=(25,70) if layer in ('126','134') else (35,60)
        require(low<=worker['density_percent'][layer]<=high,'metal density outside native bounds')
    supplement=row['supplement'];checks=supplement['checks']
    require(supplement['passed'] is True and supplement['qualified'] is False and
            supplement['full_800um_windows_applicable'] is False and
            len(checks)==len(SUPPLEMENT) and {c['rule'] for c in checks}==SUPPLEMENT and
            all(c['status'] in ('pass','not_applicable') and type(c['violations']) is int and c['violations']==0 for c in checks),
            'supplemental rule coverage is incomplete')
    require(supplement['bounds_nm']==[0,0,200000,200000] if case=='counter' else
            supplement['bounds_nm']==[0,0,400000,400000],'reference footprint changed')
    inv=row['invariance']
    require(inv['status']=='complete-circuit-subnetwork-preserved' and inv['filled_gds_sha256']==final['gds'] and
            len(inv['results'])==2 and {r['engine'] for r in inv['results']}=={'stock','corrected'},'missing independent extractor comparison')
    for item in inv['results']:
        capacitance(item['capacitance'])
        require(item['physical_device_records_identical'] is True and item['native_lumped_signal_resistance_identical'] is True,
                'changed device or lumped resistance')
    field=row['field']
    require(field['status']=='same-frozen-mesh-roundoff-only' and field['pairs']==dict(counter=8291,uart=139236,apb=119245)[case] and
            all(type(field[k]) in (int,float) and math.isfinite(field[k]) for k in ('maximum_change_af','total_absolute_change_af','minimum_capacitance_af')) and
            0<=field['maximum_change_af']<=1e-10 and 0<=field['total_absolute_change_af']<=1e-7 and
            field['minimum_capacitance_af']>=-1e-10,'changed local fields on the fixed original resistor mesh')
    lvs=row['lvs'];reference=row['lvs_reference']
    require(lvs['status']=='native-device-and-port-match' and lvs['matched'] is True and lvs['port_labels_match'] is True and
            not lvs.get('invalid_for_acceptance',False) and lvs['qualified'] is False and lvs['source_gds_sha256']==final['gds'] and
            row['lvs_label_audit']['mask_preservation'] is True and
            reference['source_artifacts']['checkpoint']['sha256']==original['checkpoint'], 'strict device/port connectivity is incomplete')
    require(row['formal']['status']=='PASS' and row['formal']['netlist_sha256']==final['netlist'] and identity(row['formal']['result_sha256']),
            'formal proof does not cover the final circuit')
    physical=row['physical_checks']
    require(physical['status']=='PASS' and physical['issues']==[] and physical['checkpoint_sha256']==final['checkpoint'],
            'antenna or power connectivity failed')
    app=row['application'];lef=row['lef']
    require(app['status']=='application-fill-and-export-pass' and lef['status']=='native-export-abstract-pass' and
            lef['ports_and_dimensions_identical'] is True and lef['gds_sha256']==final['gds'] and lef['lef_sha256']==final['lef'] and
            identity(lef['macro_sha256']) and set(lef['layers'])==METALS and
            all(v['missing_area_nm2']==0 and v['fill_polygons']>0 and v['original_obstructions_preserved'] is True for v in lef['layers'].values()),
            'application export or native abstract readback failed')
    runs=row['timing']['results']
    disconnected=[f'clkload{i}/Y' for i in range(dict(counter=0,uart=1,apb=6)[case])]
    require(row['verified_unconnected_outputs']==disconnected,'unannotated outputs need independent empty-pin evidence')
    require(len(runs)==9 and {(r['corner'],r['state']) for r in runs}=={(c,s) for c in ('typ','slow','fast') for s in ('original','filled','fault')},
            'missing actual timing scenario or load-fault control')
    for corner in ('typ','slow','fast'):
        before=next(r for r in runs if r['corner']==corner and r['state']=='original')
        after=next(r for r in runs if r['corner']==corner and r['state']=='filled')
        fault=next(r for r in runs if r['corner']==corner and r['state']=='fault')
        require(before['timing']==after['timing'] and
                all(r['netlist_sha256']==final['netlist'] and r['returncode']==0 for r in (before,after,fault)) and
                before['spef_sha256']==after['spef_sha256']==final['spef'] and
                before['library_sha256']==after['library_sha256']==fault['library_sha256'] and
                before['constraints_sha256']==after['constraints_sha256']==fault['constraints_sha256'], 'timing inputs changed')
        timing(before['timing'],disconnected);timing(after['timing'],disconnected)
        require(fault['timing']['status']=='FAIL' and fault['spef_sha256']!=final['spef'] and row['timing']['fault']['added_cap_pf']==1000.,
                'the deliberate load fault was not rejected')
    app_timing=row['application_timing']
    require(app_timing['status']=='PASS' and len(app_timing['corners'])==3 and
            {c['corner'] for c in app_timing['corners']}=={'typical','slow','fast'},'application timing handoff incomplete')
    for report in app_timing['corners']:timing(report,disconnected)
    require(row['application_timing_binding']['status']=='application-timing-pass','missing final application timing')
    require(row['evidence_files'] and all(identity(h) for h in row['evidence_files'].values()),'unbound raw evidence')


def validate(record,root=ROOT,source_snapshot=None):
    root=Path(root)
    require(record.get('schema')==1 and record.get('chunk')==5 and record.get('status')=='reference_gate_complete' and
            record.get('qualified') is False and record.get('full_transistor_rc_acceptance')=='not_claimed' and record.get('limitations'),
            'invalid reference scope or unsupported process qualification')
    sources=record['source_files'];require(SOURCE_FILES<=sources.keys(),'missing application source binding')
    snapshot=bound(source_snapshot,root) if source_snapshot else None
    if snapshot:
        require(snapshot.get('schema')==1 and snapshot.get('scope')=='historical-tested-source-only' and
                re.fullmatch('[0-9a-f]{40}',snapshot.get('source_commit','')) and snapshot.get('files') and
                bound(snapshot['acceptance_record'],root)==record,
                'historical source snapshot has a different acceptance scope')
        require(set(snapshot['files'])<=sources.keys(),'unknown historical source')
    for name,digest in sources.items():
        captured=snapshot['files'].get(name) if snapshot else None
        path=(root/captured['path']).resolve() if captured else (root/name).resolve()
        require(path.is_relative_to(root.resolve()) and identity(digest) and
                (not captured or captured['sha256']==digest) and sha(path)==digest,'changed source: '+name)
    rows=[bound(e,root) for e in record['references']]
    require(len(rows)==3 and {r['case'] for r in rows}==CASES,'missing reference')
    for row in rows:
        validate_reference(row)
        for name,digest in row['worker']['application_sources'].items():
            require(sources.get('icstudio/'+name)==digest,'worker differs from delivered source')
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(set(record['audits'])=={'win32','linux'},'both operating system audits required')
    for system,entry in record['audits'].items():
        audit=bound(entry,root)
        require(audit['status']=='three-final-ihp-references-audited' and audit['system']==system and audit['references_sha256']==digest and
                audit['auditor_sha256']==sources['scripts/audit_ihp_fill_release.py'],'OS audits differ')
    archive=record['archive']
    require(archive['verified'] is True and identity(archive['sha256']) and identity(archive['manifest_sha256']) and archive['logical_files']>0,
            'evidence archive is not verified')
    return dict(status='reference_gate_complete',chunk=5,chunk_complete=True,references=3,process_qualification='unqualified',
                source_scope='historical-tested-source-only' if snapshot else 'current-source')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',type=Path,default=ROOT/'docs/validation/ihp-fill-closure-2026-10-11.json')
    parser.add_argument('--source-snapshot',type=Path,help='Explicit historical tested-source manifest')
    args=parser.parse_args()
    snapshot=None
    if args.source_snapshot:
        snapshot=dict(path=args.source_snapshot.resolve().relative_to(ROOT).as_posix(),sha256=sha(args.source_snapshot))
    elif args.record.resolve()==(ROOT/'docs/validation/ihp-fill-closure-2026-10-11.json').resolve():
        matrix=json.loads((ROOT/'docs/qualification/pdk-matrix.json').read_text(encoding='utf-8'))
        snapshot=matrix['execution_acceptance']['5'].get('historical_source_snapshot')
    print(json.dumps(validate(json.loads(args.record.read_text(encoding='utf-8')),source_snapshot=snapshot),indent=2))
