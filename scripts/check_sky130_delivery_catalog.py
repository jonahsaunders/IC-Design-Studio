"""Replay every reviewed catalog decision on the exact corrected reference GDS.

Historical reports are authenticated for comparison and for explicitly retained
native/nominal-voltage inputs. Catalog decisions are rebuilt from fresh geometry
and source bindings, never copied from an older layout by changing its hash.
This reference qualification tool does not qualify arbitrary application jobs.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import klayout.db as k
from icstudio import digital_sky130_pins as pins
from icstudio.digital_sky130_scope import correct
from scripts import check_sky130_filled_replay as fixture
from scripts import sky130_catalog_queue as queue
from scripts import sky130_rule_execution as execution
from scripts import sky130_geometry_reconciliation as geometry
from scripts import sky130_density_rule_scope as density_scope
from scripts import sky130_nsm_reconciliation as nsm
from scripts import sky130_marker_reconciliation as marker
from scripts import sky130_waffle_density_review as waffle
from scripts import sky130_esd_fuse_review as esd
from scripts import sky130_device_intent_review as device
from scripts import sky130_selected_subject_review as subjects
from scripts import sky130_local_hv_review as local
from scripts import sky130_voltage_intent_review as voltage
from scripts import sky130_standard_cell_wl_review as wl
from scripts import sky130_grid_catalog_review as grid
from scripts import sky130_core_context_review as core
from scripts import sky130_label_subject_review as labels
from scripts import sky130_vpp_review as vpp
from scripts import sky130_boundary_interaction_review as boundary
from scripts import sky130_selected_device_review as selected
from scripts import sky130_conservative_bound_review as bounds
from scripts import sky130_device_root_review as roots
from scripts import sky130_special_subject_review as special

ROOT = queue.ROOT
LATEST = 'docs/validation/sky130-special-subjects-2026-10-15.json'
LATEST_SHA = 'de56639479b74c96da332c872171d2562b979a8c80ff05b6bb80a38abe4cd33c'
OUTPUT = ROOT/'docs/validation/sky130-delivery-catalog-2026-10-15.json'
INVENTORIES = dict(
    counter='205a32cad25105dd78073adb7dcf0b8c1878670d82fc904a626d6237e12ad59c',
    uart='dc781ac94a231e78af37669f6b1a97ff0970515ffb59858b4f0877a21ee5f262',
    apb='ba1f33789e13c846a8958423be89a17cfdc6867ef9885f31cb2aeb4861faf3ca')
BOUNDARY_IDS = {'r1252','r1253','r1254','r1255','s68','s69','s70','s71'}
CURRENT = (
    ('catalog_context', core, core.context),
    ('catalog_labels', labels, labels.subjects),
    ('vpp_geometry', vpp, vpp.vpp),
    ('boundary_interactions', boundary, boundary.checks),
    ('selected_devices', selected, selected.checks),
    ('conservative_bounds', bounds, bounds.checks),
    ('device_roots', roots, roots.checks),
    ('special_subjects', special, special.checks),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return queue.sha(Path(path).read_bytes())


def checked(path, expected):
    raw = Path(path).read_bytes()
    require(queue.sha(raw) == expected, 'Changed replay dependency: '+str(path))
    return raw


def pick(data, name):
    rows = [c for c in data['cases'] if c['case'] == name]
    require(len(rows) == 1, 'Missing or duplicate reference case.')
    return rows[0]


def reconstruct(reader):
    catalog, cases, _ = special.reconstruct(reader)
    latest = reader.read(LATEST, LATEST_SHA)
    for case in cases:
        prior = pick(latest, case['case'])
        require(case['gds_sha256'] == prior['original_gds_sha256'], 'Changed original reference.')
        case['rows'] = queue.apply_decisions(case['rows'], prior['original_new_error_decisions'], catalog)
        case['counts'] = dict(Counter(r['disposition'] for r in case['rows']))
        require(case['counts'] == prior['original_error_counts'], 'Latest catalog does not reconstruct.')
    return catalog, cases, latest


def check_result(rows, catalog, original):
    """Only the eight newly clean boundary records may change disposition."""
    queue.validate_rows(rows, catalog)
    queue.validate_rows(original, catalog)
    for current, old in zip(rows, original):
        expected = 'executed-reviewed' if current['id'] in BOUNDARY_IDS else old['disposition']
        require(current['disposition'] == expected,
                'Fresh catalog differs from the reviewed coverage: '+current['id'])
    return dict(Counter(r['disposition'] for r in rows))


def apply_rows(rows, changes, catalog, stage, provenance):
    require(changes, 'Empty catalog replay stage: '+stage)
    result = queue.apply_decisions(rows, changes, catalog)
    for row in changes:
        require(row['id'] not in provenance, 'Duplicate replay provenance: '+row['id'])
        provenance[row['id']] = stage
    return result


def manual_from_fresh(fresh, reconciled, inventory):
    manual = deepcopy(fresh)
    for row in manual['rows']:
        if row['id'] in reconciled['periphery_bindings']:
            row['disposition'] = 'executed-reviewed'
            row['execution_reconciliation'] = reconciled['periphery_bindings'][row['id']]
            row['reason'] = row['execution_reconciliation']['reason']
    manual['rows'] = density_scope.apply(manual['rows'], density_scope.bindings(inventory))
    manual['counts'] = dict(Counter(r['disposition'] for r in manual['rows']))
    return correct(manual)


def source_proofs(source, catalog, inventory, reader):
    proofs = {}
    for name, module in (('nsm', nsm), ('marker', marker), ('waffle', waffle), ('esd', esd)):
        proofs[name] = module.source_proof(source, inventory, catalog)
    proofs['device'] = device.source_proof(source)
    proofs['subjects'] = subjects.source_proof(source, catalog, inventory)
    proofs['local'] = local.source_proof(source, catalog, inventory)
    proofs['voltage'] = voltage.source_proof(source, inventory)
    proofs['wl'] = wl.source_proof(source, catalog, inventory)
    proofs['grid'] = grid.source_proof(source, catalog, inventory,
                                     reader.read(grid.GEOMETRY, grid.GEOMETRY_SHA))
    for name, review, _ in CURRENT:
        proofs[name] = review.source_proof(source, catalog)
    return proofs


def native_dependencies(workspace, reader, name, original_sha, layout):
    """Explicit retained native input; fresh physical census and voltage selectors."""
    prior = pick(reader.read(wl.NATIVE, wl.NATIVE_SHA), name)['execution']
    require(prior['gds_sha256'] == original_sha, 'Native census belongs to another original layout.')
    native = workspace/'outputs'/('sky130-filled-capacitance-v'+('2' if name == 'counter' else '3'))/name/'filled'
    ext = native/(layout.top_cell().name+'.ext')
    checked(ext, prior['native_ext_sha256'])
    models = dict(sorted(Counter(d[2] for d in device.circuit.headers(ext)['devices']).items()))
    require(models == prior['native_models'], 'Retained native model census changed.')
    measured = device.measure(layout)
    choices = device.decisions(measured, models)
    require(measured == prior['measurement'], 'Corrected physical device census differs from retained extraction.')
    volts = pick(reader.read(local.VOLTAGE), name)
    require(volts['gds_sha256'] == original_sha and
            volts['execution']['native_ext_sha256'] == prior['native_ext_sha256'],
            'Voltage contract belongs to another layout or extraction.')
    for path, identity in volts['execution']['authenticated_files'].items():
        resolved = (workspace/path).resolve()
        require(resolved.is_relative_to(workspace.resolve()), 'Voltage dependency leaves workspace.')
        require(len(checked(resolved, identity['sha256'])) == identity['bytes'], 'Changed voltage dependency size.')
    checked(native/'inventory.json', volts['execution']['inventory_sha256'])
    voltage_measurement = voltage.measure(layout)
    require(voltage_measurement == volts['measurement'], 'Changed voltage source/exception selectors.')
    nominal = volts['execution']['contract_check']
    require(voltage.decisions(voltage_measurement, nominal) == volts['decisions'], 'Changed voltage interpretation.')
    checked(ext, prior['native_ext_sha256'])
    return dict(native_ext_sha256=prior['native_ext_sha256'], native_models=models,
                measurement=measured, decisions=choices, voltage_measurement=voltage_measurement,
                nominal_contract=nominal, retained_voltage_files=volts['execution']['authenticated_files']), prior


def replay_case(workspace, entry, folder, catalog, inventory, original, latest, proofs, controls, reader, progress=None):
    name = entry['case']
    base = workspace/'outputs/sky130-application-boundary-v1/linux'/name
    path = base/'sky130-pin-export/final.gds'
    gds_sha = latest['corrected_gds_sha256']
    checked(path, gds_sha)
    # Reproduce through the real export code, checking the independent OpenDB
    # inventory. The complete resulting GDS bytes must match the delivered file.
    result = json.loads((base/'result.json').read_bytes())['digital_result']
    artifact = result['artifacts']['sky130_pin_inventory']
    require(artifact['sha256'] == INVENTORIES[name], 'Changed independent pin/die inventory identity.')
    intent = json.loads(checked(base/artifact['path'], INVENTORIES[name]))
    export_path = folder/(name+'-reproduced.gds')
    export = pins.write(folder/entry['gds'], export_path, intent)
    require(sha(export_path) == gds_sha, 'Fresh export does not reproduce delivered GDS.')
    if progress: progress(dict(case=name, stage='export-reproduced'))
    fresh = execution.audit(path, folder/'sources'); fresh['case'] = name
    baseline = geometry.reconcile(catalog, inventory, fresh,
        geometry.geometry_bindings() | geometry.mask_bindings(catalog), controls)
    manual = manual_from_fresh(fresh, baseline, inventory)
    provenance = {r['id']: 'geometry' for r in baseline['rows'] if r['disposition'] != 'unreviewed'}
    measurements = {'geometry': fresh}
    for stage, module in (('nsm', nsm), ('marker', marker), ('waffle', waffle), ('esd', esd)):
        measured = module.audit(path)
        before = deepcopy(baseline['rows'])
        if stage == 'nsm':
            baseline = nsm.reconcile(catalog, baseline, manual, measured)
        elif stage == 'esd':
            manual, baseline = esd.reconcile(manual, baseline, measured, proofs[stage])
        else:
            baseline = module.reconcile(catalog, inventory, baseline, manual, measured)
        changes = [a for a, b in zip(baseline['rows'], before) if a != b]
        apply_rows(before, changes, catalog, stage, provenance)
        measurements[stage] = measured
    rows = baseline['rows']
    layout = k.Layout(); layout.read(str(path))
    native, prior = native_dependencies(workspace, reader, name, entry['gds_sha256'], layout)
    measurements['native_dependency'] = native
    changes = [dict(id=key, **native['decisions'][rule])
               for key, rule in (('r426', 'hvtr_3'), ('r759', 'licon_19'))]
    rows = apply_rows(rows, changes, catalog, 'device', provenance)
    measured = subjects.measure(layout)
    reconciled = subjects.reconcile(rows, catalog, proofs['subjects']['bindings'], measured, manual)
    changes = [a for a, b in zip(reconciled, rows) if a != b]
    require({r['id'] for r in changes} == set(proofs['subjects']['bindings']), 'Selected subject review is incomplete.')
    rows = apply_rows(rows, changes, catalog, 'subjects', provenance)
    measurements['subjects'] = measured
    measured = local.measure(layout)
    choices = local.decisions(measured, proofs['local']['bindings'], native['nominal_contract'])
    parents = {r['id']: r for r in manual['rows']}
    for relation in proofs['local']['bindings'].values():
        parent = relation['parent']
        if parent:
            require(all(parents[parent['id']][key] == value for key, value in parent.items()) and
                    parents[parent['id']]['disposition'] == 'absent-operand',
                    'Fresh local/HV parent does not establish the required absence.')
    rows = apply_rows(rows, [dict(id=key, **value) for key, value in choices.items()], catalog, 'local', provenance)
    measurements['local'] = measured
    library, library_provenance = wl.load_library(workspace/'outputs/sky130-filled-electrical-v1'/name/'finish', name)
    measured = wl.measure(layout, library)
    choices = wl.decisions(measured, prior, proofs['wl']['bindings'])
    rows = wl.apply_decisions(rows, choices, catalog)
    for choice in choices:
        require(choice['id'] not in provenance, 'Overlapping W/L decision.')
        provenance[choice['id']] = 'wl'
    measurements['wl'] = dict(measurement=measured, library_provenance=library_provenance)
    measured = grid.measure(layout)
    rows = apply_rows(rows, grid.decisions(measured, proofs['grid']['bindings']), catalog, 'grid', provenance)
    measurements['grid'] = measured
    if progress: progress(dict(case=name, stage='historical-checks-reexecuted'))
    for stage, _, module in CURRENT:
        measured = module.audit(path)
        module.evaluate(measured, gds_sha, entry['top'])
        rows = apply_rows(rows, measured['rows'], catalog, stage, provenance)
        measurements[stage] = measured
        if stage == 'selected_devices':
            choices = proofs[stage]['advisory_decisions']
            rows = selected.apply_advisories(rows, choices, catalog)
            for choice in choices:
                require(choice['id'] not in provenance, 'Overlapping advisory decision.')
                provenance[choice['id']] = 'source-advisory'
    counts = check_result(rows, catalog, original['rows'])
    reviewed = {r['id'] for r in rows if r['disposition'] != 'unreviewed'}
    require(set(provenance) == reviewed, 'Missing or unrelated fresh decision provenance.')
    checked(path, gds_sha)
    if progress: progress(dict(case=name, stage='catalog-replayed', counts=counts))
    return dict(case=name, top=entry['top'], gds_sha256=gds_sha, original_gds_sha256=entry['gds_sha256'],
                inventory_sha256=INVENTORIES[name], export=export, measurements=measurements,
                counts=counts, rows=rows, provenance=provenance,
                remaining_batches=queue.partition([r for r in rows if r['disposition'] == 'unreviewed']))


def build(workspace=None, case=None, progress=None):
    workspace = Path(workspace or ROOT.parents[1]).resolve()
    require(case is None or case in queue.CASES, 'Unknown replay case.')
    reader = queue.RetainedReader()
    catalog, originals, latest = reconstruct(reader)
    inventory = reader.read(local.INVENTORY)
    cases = []
    with TemporaryDirectory() as td:
        folder = Path(td)/'inputs'
        manifest = fixture.unpack(fixture.BUNDLE, folder)
        proofs = source_proofs(folder/'sources', catalog, inventory, reader)
        controls = geometry.notch_controls()
        for entry in manifest['cases']:
            if case is not None and entry['case'] != case: continue
            cases.append(replay_case(workspace, entry, folder, catalog, inventory,
                pick(dict(cases=originals), entry['case']), pick(latest, entry['case']), proofs, controls, reader, progress))
    modules = [fixture, queue, execution, geometry, density_scope, nsm, marker, waffle, esd,
               device, subjects, local, voltage, wl, grid, pins]
    modules += [module for _, review, checks in CURRENT for module in (review, checks)]
    files = {Path(m.__file__) for m in modules} | {Path(__file__)}
    # Include transitive repository helpers actually imported by this replay,
    # not only the orchestration modules. Never record interpreter/site-packages
    # paths, which differ between supported operating systems.
    for name, module in tuple(sys.modules.items()):
        if name.startswith(('scripts.', 'icstudio.')) and getattr(module, '__file__', None):
            path = Path(module.__file__).resolve()
            if path.is_relative_to(ROOT): files.add(path)
    files.add(ROOT/'tests/test_sky130_delivery_catalog.py')
    return dict(schema=1, chunk=6, status='corrected-reference-catalog-replayed', qualified=False, chunk_complete=False,
                scope='Fresh geometry and source-bound catalog decisions on exact corrected reference exports. '
                      'Native extraction and nominal voltage contracts are explicitly retained, authenticated dependencies; '
                      'no new extraction or electrical signoff is claimed. All 1556 records remain present; unresolved '
                      'catalog, periphery, density, grid, pin-spacing and complete-chip requirements remain open. '
                      'This reference replay is not a general application signoff policy.',
                reference_cases=list(queue.CASES), selected_cases=[c['case'] for c in cases],
                inputs=dict(sorted(reader.digests.items())),
                source_files={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)},
                proofs=proofs, notch_controls=controls, cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--case', choices=queue.CASES)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build(args.workspace, args.case, lambda row: print(json.dumps(row), flush=True))
    raw = (json.dumps(report, indent=2, ensure_ascii=False)+'\n').encode()
    if args.check:
        require(args.output.read_bytes() == raw, 'Saved delivery catalog differs from fresh execution.')
    else:
        args.output.write_bytes(raw)
    print(json.dumps(dict(status=report['status'], qualified=False, chunk_complete=False)))


if __name__ == '__main__':
    main()
