"""Isolated runner for hash-authenticated, reviewed SKY130 checker sources."""
import importlib
import json
from pathlib import Path
import sys

from .digital_sky130_rules import resources, evaluate, require, SCOPE
from .digital_sky130_rules_lock import PROFILES, FILES, RECIPE
from .model import atomic_write, file_digest


def execute(request):
    output = Path(request['output']); output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, recipe=RECIPE, status='FAIL', qualified=False, chunk_complete=False, scope=SCOPE,
                  policy=request['policy'], gds_sha256=request['gds_sha256'],
                  checkpoint_sha256=request['checkpoint_sha256'], top=request['top'],
                  platform_fingerprint=request['platform_fingerprint'], profiles={})
    def save(name, value):
        atomic_write(output/name, json.dumps(value, indent=2)+'\n')
    try:
        policy = request['policy']; base = Path(request['resources']).resolve()
        resources(base, policy['preparation_sha256'])
        require(not any(name == 'scripts' or name.startswith('scripts.') for name in sys.modules),
                'Run SKY130 checkers in a fresh interpreter to avoid another helper namespace.')
        sys.dont_write_bytecode = True; sys.path.insert(0, str(base/'helpers'))
        from scripts import sky130_rule_execution as execution
        gds = Path(request['gds']); checkpoint = Path(request['checkpoint'])
        def unchanged():
            require(file_digest(gds) == request['gds_sha256'] and
                    file_digest(checkpoint) == request['checkpoint_sha256'], 'SKY130 inputs changed during checking.')
        unchanged()
        review = execution.applicability(gds, base/'sources'); save('applicability.json', review)
        errors = []
        for name, expected in PROFILES.items():
            try:
                value = importlib.import_module('scripts.'+expected['module']).audit(gds)
                report['profiles'][name] = value; save(name+'.json', value)
                if value['status'] != 'PASS':
                    errors.append(name+' failed')
            except Exception as error:
                errors.append(name+': '+str(error)); save(name+'.json', dict(status='ERROR', error=str(error)))
            unchanged()
            print('SKY130 '+name+': '+report['profiles'].get(name, {}).get('status', 'ERROR'), flush=True)
        require(not errors, '; '.join(errors))
        profiles = report['profiles']
        review = execution.bind(review, profiles['raw_geometry'])
        for bind, key in [(execution.bind_geometry, 'low_voltage_geometry'),
                          (execution.bind_interconnect, 'interconnect_geometry'),
                          (execution.bind_wide, 'wide_metal_geometry'),
                          (execution.bind_global, 'global_geometry'),
                          (execution.bind_connectivity, 'floating_connectivity')]:
            review = bind(review, profiles[key])
        review['checker_sha256'] = FILES['helpers/scripts/sky130_rule_execution.py']
        from .digital_sky130_scope import correct
        review = correct(review)
        from .digital_sky130_frame_scope import correct as correct_frame_scope
        review = correct_frame_scope(review)
        from .digital_sky130_pad_scope import correct as correct_pad_scope
        review = correct_pad_scope(review)
        from .digital_sky130_catalog_context import audit as catalog_context
        report['catalog_context'] = catalog_context(gds)
        save('catalog_context.json', report['catalog_context'])
        from .digital_sky130_catalog_labels import audit as catalog_labels
        report['catalog_labels'] = catalog_labels(gds)
        save('catalog_labels.json', report['catalog_labels'])
        from .digital_sky130_vpp import audit as vpp_geometry
        report['vpp_geometry'] = vpp_geometry(gds)
        save('vpp_geometry.json', report['vpp_geometry'])
        from .digital_sky130_boundary_interactions import audit as boundary_interactions
        report['boundary_interactions'] = boundary_interactions(gds)
        save('boundary_interactions.json', report['boundary_interactions'])
        from .digital_sky130_selected_devices import audit as selected_devices
        report['selected_devices'] = selected_devices(gds)
        save('selected_devices.json', report['selected_devices'])
        from .digital_sky130_conservative_bounds import audit as conservative_bounds
        report['conservative_bounds'] = conservative_bounds(gds)
        save('conservative_bounds.json', report['conservative_bounds'])
        from .digital_sky130_device_roots import audit as device_roots
        report['device_roots'] = device_roots(gds)
        save('device_roots.json', report['device_roots'])
        from .digital_sky130_special_subjects import audit as special_subjects
        report['special_subjects'] = special_subjects(gds)
        save('special_subjects.json', report['special_subjects'])
        from .digital_sky130_selected_targets import audit as selected_targets
        report['selected_targets'] = selected_targets(gds)
        save('selected_targets.json', report['selected_targets'])
        from .digital_sky130_frame_bounds import audit as frame_bounds
        report['frame_bounds'] = frame_bounds(gds)
        save('frame_bounds.json', report['frame_bounds'])
        from .digital_sky130_well_bounds import audit as well_bounds
        report['well_bounds'] = well_bounds(gds)
        save('well_bounds.json', report['well_bounds'])
        from .digital_sky130_scribe_bounds import audit as scribe_bounds
        report['scribe_bounds'] = scribe_bounds(gds)
        save('scribe_bounds.json', report['scribe_bounds'])
        from .digital_sky130_seal_geometry import audit as seal_geometry
        report['seal_geometry'] = seal_geometry(gds)
        save('seal_geometry.json', report['seal_geometry'])
        from .digital_sky130_family_targets import audit as family_targets
        report['family_targets'] = family_targets(gds)
        save('family_targets.json', report['family_targets'])
        from .digital_sky130_package_boundaries import audit as package_boundaries
        report['package_boundaries'] = package_boundaries(gds)
        save('package_boundaries.json', report['package_boundaries'])
        from .digital_sky130_metal_width_bounds import audit as metal_width_bounds
        report['metal_width_bounds'] = metal_width_bounds(gds)
        save('metal_width_bounds.json', report['metal_width_bounds'])
        from .digital_sky130_module_absence import audit as module_absence
        report['module_absence'] = module_absence(gds)
        save('module_absence.json', report['module_absence'])
        from .digital_sky130_diecut_absence import audit as diecut_absence
        report['diecut_absence'] = diecut_absence(gds)
        save('diecut_absence.json', report['diecut_absence'])
        from .digital_sky130_waffle_windows import audit as waffle_windows
        report['waffle_windows'] = waffle_windows(gds)
        save('waffle_windows.json', report['waffle_windows'])
        from .digital_sky130_dummy_partners import audit as dummy_partners
        report['dummy_partners'] = dummy_partners(gds)
        save('dummy_partners.json', report['dummy_partners'])
        from .digital_sky130_alignment import audit as alignment
        report['alignment'] = alignment(gds)
        save('alignment.json', report['alignment'])
        from .digital_sky130_oxide_density import audit as oxide_density
        report['oxide_density'] = oxide_density(gds, request.get('density_bounds_nm'))
        save('oxide_density.json', report['oxide_density'])
        report.update(status='reviewed-profiles-pass', ledger=review,
                      coverage=dict(rows=len(review['rows']), counts=review['counts'], complete=False))
        unchanged(); resources(base, policy['preparation_sha256'])
        evaluate(report, request['gds_sha256'], request['checkpoint_sha256'], request['top'],
                 request['platform_fingerprint'], policy)
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        save('report.json', report)
    return report
