"""Accept six exact GF180 fill references, never general process signoff."""
import hashlib
import json
import math
from pathlib import Path

if __package__:
    from .check_gf180_density_acceptance import validate as validate_native, require, identity
else:
    from check_gf180_density_acceptance import validate as validate_native, require, identity

CASES = {v+'-'+d for v in ('c','d') for d in ('counter','uart','apb')}
REMAINING = {
    'Foundry acceptance limits for local metal density and clipped die-edge windows',
    'Independent full native geometry, antenna and final-layout LVS',
    'Post-fill extraction, timing and foundry acceptance',
    'Foundry/reticle approval of the declared reference floorplan',
}
SOURCE_FIELDS = {
    'checker_sha256':'scripts/check_gf180_fill.py',
    'applicability_checker_sha256':'scripts/gf180_fill_applicability.py',
    'comp_space_checker_sha256':'scripts/gf180_comp_sites.py',
    'boundary_comp_space_checker_sha256':'scripts/gf180_comp_boundary_sites.py',
    'boundary_checker_sha256':'scripts/gf180_fill_boundaries.py',
    'pattern_checker_sha256':'scripts/gf180_fill_patterns.py',
    'manual_lock_sha256':'examples/gf180-fill-manual-lock.json',
    'coverage_manual_lock_sha256':'examples/gf180-fill-coverage-lock.json',
    'pattern_manual_lock_sha256':'examples/gf180-fill-pattern-lock.json',
    'boundary_manual_lock_sha256':'examples/gf180-boundary-manual-lock.json',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(entry, root):
    path = (root/entry['path']).resolve()
    require(path.is_relative_to(root.resolve()) and identity(entry.get('sha256'))
            and sha(path)==entry['sha256'], 'stale or external closure dependency.')
    return json.loads(path.read_text(encoding='utf-8'))


def validate_supplement(report, floorplan, plan, pattern_hash, negative, row, native):
    case=row['case']; size=200 if case.endswith('counter') else 400
    coords=[0,0,size*1000,size*1000]
    require(row['macro_sha256']==native['macro_sha256'] and identity(row.get('gds_sha256')),
            'supplement is not bound to the accepted production macro.')
    require(report.get('schema')==9 and report.get('failed_checks')==0 and
            report.get('qualified') is False and report.get('status')=='checks_passed_coverage_incomplete',
            'supplemental reference failed or claims process qualification.')
    require(report['gds_sha256']==row['gds_sha256'] and report['variant']==case[0].upper()
            and report['bounds_um']==[0,0,size,size] and report['area_um2']==size*size,
            'changed reference footprint, variant or GDS.')
    checks=report['checks']
    require(len(checks)==108 and all(c['status']=='passed' and type(c['violations']) is int
                                    and c['violations']==0 for c in checks), 'incomplete supplemental rule execution.')
    require(set(report['unqualified_requirements'])==REMAINING, 'unexpected unresolved fill requirement.')
    rules=report['rule_applicability']['rules']
    require(len(rules)==8 and {r['rule'] for r in rules}=={
        'DCF.8b','DCF.11b','DCF.13-row','DCF.9','DCF.7a/7b/7c/7d',
        'DPF.1-prime-die/7','vendor-memory-fill','DE.1'} and
        all(r['status']=='not_applicable_absent_operand' for r in rules),
        'conditional fill operands need additional qualification.')
    require(floorplan['original_die_nm']==floorplan['prime_die_nm']==coords and
            floorplan['original_core_um']==[20,20,size-20,size-20] and
            floorplan['design_gds_sha256']==row['gds_sha256'] and
            floorplan['design_project_sha256']==row['project_sha256'] and
            all(floorplan[key]==[] for key in ('frames','slm_regions','frame_cells')),
            'reference floorplan changed the design or introduced unchecked scope.')
    streets=[[-40000,-40000,size*1000+40000,0],[-40000,size*1000,size*1000+40000,size*1000+40000],
             [-40000,0,0,size*1000],[size*1000,0,size*1000+40000,size*1000]]
    require(plan['gds_sha256']==row['gds_sha256'] and
            plan['scribe_boxes_nm']==floorplan['scribe_boxes_nm']==streets and
            plan['regions']==[dict(name='reference-prime-die',kind='prime_die',bounds_nm=coords)],
            'incomplete or changed reference streets.')
    proof=report['boundary_comp_space']
    require(proof['status']=='no_legal_comp_square_in_declared_prime_die' and
            proof['no_legal_square_proven'] is True and proof['original_bounds_nm']==coords and
            proof['dcf7a_minimum_nm']==26000 and
            proof['admissible_whole_square_bounds_nm']==[26000,26000,size*1000-26000,size*1000-26000] and
            proof['circuit_clearance_proof']['no_legal_square_proven'] is True and
            proof['circuit_clearance_proof']['possible_origin_regions']==0,
            'missing complete-domain COMP absence proof.')
    require(report['boundary_checks']['status']=='declared_boundary_checks_passed' and
            negative['status']=='failed' and any(c['rule']=='DCF.7a' and c['violations']>0
                                                for c in negative['checks']), 'missing boundary fault rejection.')
    require(report['pattern_plan_sha256']==pattern_hash and
            report['drawing_patterns']['layers']['m1']['status']=='declared_recipe_passed',
            'missing written metal pattern acceptance.')
    for name,data in report['metal_density_windows'].items():
        require(name in {'m1','m2','m3','m4','m5'} and data['window_um']==200 and data['step_um']==100
                and data['anchor_um']==[0,0] and data['local_limits_percent'] is None,
                'changed local measurement method or invented local threshold.')
        expected=[[x,y,min(x+200,size),min(y+200,size)] for y in range(0,size,100) for x in range(0,size,100)]
        require([w['bounds_um'] for w in data['windows']]==expected and data['full_windows']==(size//100-1)**2,
                'local density window coverage incomplete.')
        for w in data['windows']:
            x0,y0,x1,y1=w['bounds_um']; area=(x1-x0)*(y1-y0)
            require(w['area_um2']==area and math.isfinite(w['material_area_um2']) and
                    0<=w['material_area_um2']<=area and
                    math.isclose(w['measured_percent'],100*w['material_area_um2']/area,abs_tol=1e-9),
                    'invalid local density measurement.')
    require(set(report['metal_density_windows'])=={'m1','m2','m3','m4','m5'}, 'missing local metal layer.')


def validate(record, root):
    root=Path(root)
    require(record.get('schema')==2 and record.get('chunk')==4 and
            record.get('status')=='reference_gate_complete' and record.get('qualified') is False,
            'missing full fill coverage acceptance schema.')
    native=bound(record['native_acceptance'],root);validate_native(native,root)
    require(record.get('backend_sha256')==native['backend_sha256'], 'closure backend differs.')
    for name,digest in native['source_files'].items():
        require(sha(root/'icstudio'/name)==digest, 'application changed since production acceptance: '+name)
    sources=record['source_files']
    require(set(SOURCE_FIELDS.values())<=set(sources), 'missing checker source bindings.')
    for name,digest in sources.items():
        require(identity(digest) and sha(root/name)==digest, 'closure checker changed: '+name)
    require(record['local_density_policy']=='pinned-drm13.3-measurement-global-threshold-v1' and
            record['electrical_acceptance']=='final-device-and-supply-lvs_formal-equivalence_three-corner-extracted-sta' and
            record['full_transistor_rc_acceptance']=='not_claimed' and record.get('limitations'),
            'acceptance method or scope changed.')
    rows=record['references'];require(len(rows)==6 and {r['case'] for r in rows}==CASES,'missing closure reference.')
    original={r['case']:r for r in native['references']}
    for row in rows:
        files={name:bound(entry,root) for name,entry in row['files'].items()}
        require(set(files)=={'report','floorplan','boundary','pattern','negative'},'incomplete portable evidence.')
        report=files['report']
        for field,path in SOURCE_FIELDS.items():
            require(report[field]==sources[path], 'supplement uses a different checker: '+field)
        require(report['boundary_checks']['plan_sha256']==row['files']['boundary']['sha256'] and
                report['boundary_comp_space']['boundary_plan_sha256']==row['files']['boundary']['sha256'] and
                report['boundary_checks']['floorplan_source_sha256']==row['files']['floorplan']['sha256'] and
                files['boundary']['floorplan_source']['sha256']==row['files']['floorplan']['sha256'],
                'boundary source bindings differ.')
        validate_supplement(report,files['floorplan'],files['boundary'],row['files']['pattern']['sha256'],
                            files['negative'],row,original[row['case']])
    require(set(record['os_audits'])=={'windows','linux'},'both OS closure audits required.')
    for audit in record['os_audits'].values():
        require(audit['status']=='six-final-fill-reference-audits-passed' and identity(audit['sha256']) and
                audit['references_sha256']==hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'OS closure audits differ.')
    archive=record['archive']
    require(identity(archive['sha256']) and archive['verified'] is True and archive['members']>0,
            'closure evidence archive is not verified.')
    return dict(status='reference_gate_complete',chunk=4,chunk_complete=True,
                references=6,process_qualification='unqualified')
