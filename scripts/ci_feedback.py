"""Bounded source feedback with timings; never a substitute for release acceptance."""
import argparse
import hashlib
import json
import re
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

UNIT_MODULES = (
    'test_ci_candidate', 'test_recover_pw2dn_diagnostics', 'test_frozen_physical', 'test_ci_feedback', 'test_reference_toolchain', 'test_checkout_integrity',
    'test_core', 'test_lifecycle', 'test_project_data_safety', 'test_workflows', 'test_project_pdk',
    'test_pdk_templates', 'test_student_physical',
    'test_document.RecoveryQueueTests', 'test_layout_verification',
    'test_digital.DigitalChildEnvironmentTests', 'test_digital.YosysIntegrationTests',
    'test_analog.AnalogTests.test_capabilities_do_not_trust_catalog_or_metadata',
    'test_digital_bundle', 'test_digital_runtime', 'test_digital_rc',
    'test_sky130_retained_catalog', 'test_digital_platforms',
    'test_release_acceptance', 'test_release_evidence', 'test_release_intent',
    'test_pdk_qualification_matrix', 'test_ihp_hv_mos_layouts', 'test_mos_grouping', 'test_sky130_li_linked', 'test_sky130_li_array_dynamic',
    'test_ihp_resistor_via_class', 'test_ihp_resistor_via_auditor', 'test_ihp_resistor_editor', 'test_ihp_guard_vias',
    'test_ihp_pmos_measured_reference', 'test_ihp_pmos_measured_reference_v2', 'test_ihp_pmos_measured_v3_readback', 'test_ihp_tap_linked', 'test_ihp_guard_corner_safe',
    'test_ihp_guard_app', 'test_ihp_guard_backend_assets', 'test_frozen_ihp_guard_corner',
    'test_ihp_resistor_backend_assets', 'test_ihp_resistor_lvs_reference', 'test_frozen_ihp_resistor_gate',
    'test_ihp_capacitor_corners', 'test_ihp_cmim_boundary', 'test_ihp_cmim_lvs_reference', 'test_hierarchical_lvs_reference',
    'test_ihp_metal_spacing', 'test_ihp_klayout_drc', 'test_ihp_cmim_process_control', 'test_ihp_cmim_enclosures',
    'test_ihp_cmim_multiplicity', 'test_ihp_cmim_multiplicity_electrical',
    'test_ihp_cmim_desktop_probe', 'test_frozen_ihp_cmim', 'test_release_ihp_cmim_evidence', 'test_ci_windows_native_identity',
    'test_ihp_cmim_capacitance', 'test_ihp_cmim_parallel', 'test_ihp_managed_saved_bench', 'test_physical_backend', 'test_frozen_device_classes', 'test_managed_mos_manifest', 'test_wsl_platform_capture', 'test_ihp_backend_packaging',
    'test_resistor_layout_qualification', 'test_sky130_metal_resistor_layouts',
    'test_sky130_li_resume', 'test_sky130_mim_passive_corners', 'test_sky130_mim_passive_audit',
    'test_sky130_mim_bias_boundaries', 'test_sky130_mim_bias_audit',
    'test_sky130_mim1_extract', 'test_sky130_mim2_extract', 'test_sky130_mim_shared', 'test_sky130_mim_contact_topology',
    'test_mim_desktop_probe', 'test_frozen_mim', 'test_sky130_pw2dn_native_probe', 'test_pw2dn_elapsed_clock',
    'test_frozen_esd', 'test_frozen_esd_default', 'test_sky130_esd_default_candidate', 'test_sky130_mos_voltage_contract', 'test_sky130_mos_voltage_source', 'test_sky130_contract_versions',
    'test_metal_hierarchy_electrical', 'test_sky130_mim_conditioning',
    'test_source_mim_fixture_archive', 'test_linux_ngspice_manifest',
    'test_installed_mim_contract_versions', 'test_installed_mim_electrical', 'test_installed_mim_public_drc', 'test_installed_mim_aggregate',
    'test_sky130_mim_mismatch_aliases', 'test_sky130_mim_mismatch_alias_audit',
    'test_sky130_metal_editor', 'test_sky130_metal_resistors_linked',
    'test_sky130_metal_resistors_linked_audit', 'test_pdks_publication',
    # Full thirty-layout Qt lifecycle remains in exhaustive core discovery.
    'test_metal_resistor_desktop_probe.ProbeBoundaries', 'test_frozen_metal_resistors',
    'test_installed_metal_resistor_inputs', 'test_installed_metal_resistors',
    'test_installed_metal_resistors_audit', 'test_installed_metal_resistors_aggregate',
    'test_sky130_metal_resistor_hierarchy', 'test_sky130_metal_resistor_hierarchy_audit',
    'test_sky130_mim_hierarchy', 'test_sky130_mim_hierarchy_audit',
    'test_sky130_metal_resistor_parallel', 'test_sky130_metal_resistor_parallel_audit',
    'test_metal_resistor_parallel_desktop_probe.ProbeBoundaries', 'test_frozen_metal_parallel',
    'test_installed_metal_parallel_inputs', 'test_installed_metal_parallel',
    'test_installed_metal_parallel_audit', 'test_installed_metal_parallel_aggregate',
    'test_catalog_numeric_choices',
    'test_sky130_esd_nvt', 'test_sky130_esd_nvt_audit', 'test_esd_installed_header_regression',
    'test_sky130_rf_default_acceptance', 'test_project_hub_completion',
    'test_sky130_rf_default', 'test_sky130_rf_corner_sources',
    'test_sky130_mim_hierarchy_electrical', 'test_sky130_mim_hierarchy_electrical_audit',
    'test_desktop_acceptance_handoff', 'test_release_source_handoff',
    'test_ihp_bondpad', 'test_ihp_rf_mos_exchange', 'test_ihp_lvs_selector_review', 'test_digital_recipe_corner_contract', 'test_source_spice_archives', 'test_sky130_mim_hierarchy_selection',
    'test_ihp_l2n0_reference', 'test_sky130_release_inventory', 'test_upstream_semantics',
    'test_source_dispositions', 'test_source_disposition_cache', 'test_source_disposition_reconstruction', 'test_source_disposition_reconstruction_v2', 'test_source_disposition_reconstruction_v3', 'test_source_configs', 'test_xcircuit_inventory', 'test_xcircuit_rc',
    'test_cvc_models', 'test_physical_layers',
    'test_legacy_symbols',
    'test_schematic_views',
    'test_verilog_fragments',
    'test_source_references',
    'test_klayout_wrappers', 'test_xschem_configs', 'test_source_manifests',
    'test_ihp_ct_reference', 'test_sky130_vpp_applicability',
)


# Keep the complete selection above auditable while bounding each subprocess.
# Physical coverage outgrew the original unit stage on ordinary Windows.
# Preserve the complete ordered selection and the existing per-child deadline.
_IHP_STAGE_START = UNIT_MODULES.index('test_ihp_hv_mos_layouts')
_PHYSICAL_STAGE_START = UNIT_MODULES.index('test_resistor_layout_qualification')
_DEVICE_STAGE_START = UNIT_MODULES.index('test_sky130_metal_editor')
UNIT_STAGE_MODULES = UNIT_MODULES[:_IHP_STAGE_START]
IHP_STAGE_MODULES = UNIT_MODULES[_IHP_STAGE_START:_PHYSICAL_STAGE_START]
PHYSICAL_STAGE_MODULES = UNIT_MODULES[_PHYSICAL_STAGE_START:_DEVICE_STAGE_START]
DEVICE_STAGE_MODULES = UNIT_MODULES[_DEVICE_STAGE_START:]


# Package reconstruction performs many verified file copies on Windows. Keep
# these additional checks required without crowding the existing unit budget.
PACKAGE_MODULES = (
    'test_sky130_pw2dn_default', 'test_catalog_multiplicity',
    'test_default_device_packages.DefaultDevicePackageTests.test_rebuild_matches_the_bundled_package_and_original_assets_remain_recoverable',
    'test_default_device_packages.DefaultDevicePackageTests.test_exact_rf_predecessor_still_reconstructs_and_rebuilds_the_current_default',
    'test_default_device_packages.DefaultDevicePackageTests.test_changed_current_asset_cannot_be_hidden_by_predecessor_reconstruction',
)

# Independent bounded stage avoids adding new portable release and runtime
# checks to the already substantial unit/package stages.
RUNTIME_RELEASE_MODULES = (
    'test_openems_runtime', 'test_stage_linux_ngspice', 'test_linux_ngspice_dependencies',
    'test_fetch_linux_ngspice_sources', 'test_release_pw2dn_evidence',
    'test_release_qualification', 'test_publish_prerelease', 'test_windows_failure_summary',
    'test_ihp_wsl_host_provenance',
    'test_ihp_wsl_research_payload',
    'test_ihp_wsl_research_projects',
    'test_ihp_wsl_builder_cleanup',
    'test_ihp_wsl_preparation_request',
    'test_ihp_wsl_research_delivery',
    'test_ihp_wsl_prepared',
    'test_ihp_wsl_payload_transport',
    'test_ihp_wsl_app_dispatch',
    'test_ihp_wsl_app_reconstruction',
    'test_ihp_wsl_elf_symbols',
)


PYTHON_SOURCE_FOLDERS = (
    'icstudio', 'scripts', 'tests',
    'scripts/qualification/sky130_mim_conditioning',
)


def python_sources(root):
    return sorted(path for folder in PYTHON_SOURCE_FOLDERS
                  for path in (root / folder).glob('*.py'))


def check_syntax(root=ROOT):
    files = python_sources(root)
    for path in files:
        compile(path.read_bytes(), str(path), 'exec')
    return len(files)


def source_identity(root=ROOT):
    files = python_sources(root)
    for folder in ('ihp-wsl-experimental', 'ihp-wsl-reconstruction-v2'):
        files += [p for p in (root / 'docs/research' / folder).rglob('*') if p.is_file()]
    files += [p for p in (root / 'tests/fixtures/ihp-l2n0-reference-v1').glob('*') if p.is_file()]
    for folder in ('klayout-wrapper-sources-v1', 'xschem-config-facts-v1',
                   'source-manifest-wrappers-v1', 'ihp-pmos-measured-reference-v1',
                   'ihp-pmos-measured-reference-v2', 'ihp-pmos-measured-reference-v3'):
        files += [p for p in (root / 'docs/qualification' / folder).rglob('*') if p.is_file()]
    # Semantic inventories consume authenticated upstream graphs and the exact
    # release asset list; bind those inputs alongside their runners and tests.
    for name in ('upstream-view-inputs-2026-10-20.json.gz',
                 'upstream-views-2026-10-20.json.gz',
                 'sky130-release-inputs-2026-11-07.json',
                 'upstream-semantics-gf-inputs-2026-11-07.json.gz',
                 'source-dispositions-companion-inputs-2026-11-07.json.gz',
                 'upstream-semantics-inventory-2026-11-07-v2.json.gz',
                 'sky130-release-inventory-2026-11-07.json.gz',
                 'source-dispositions-2026-11-08-v1.json.gz',
                 'source-dispositions-2026-11-10-v1.delta.json.gz',
                 'source-dispositions-2026-11-10-v2.delta.json.gz',
                 'source-dispositions-2026-11-10-v3.delta.json.gz',
                 'ihp-resistor-guard-vias-v1.json', 'ihp-resistor-guard-corner-safe-v2.json'):
        source = root / 'docs/qualification' / name
        if source.is_file():
            files.append(source)
    files += [p for p in (root / 'tests/fixtures/pw2dn-recovery-2026-11-11').glob('*') if p.is_file()]
    matrix = root / 'docs/qualification/pdk-matrix.json'
    if matrix.is_file(): files.append(matrix)
    for folder in ('chunk7-openems-retained-source-2026-11-07',
                   'experimental-data-safety-retained-source-2026-11-11',
                   'experimental-copy-safety-retained-source-2026-11-11',
                   'experimental-export-safety-retained-source-2026-11-11',
                   'experimental-manifest-safety-retained-source-2026-11-11',
                   'experimental-findings-safety-retained-source-2026-11-12',
                   'experimental-layer-safety-retained-source-2026-11-12',
                   'solver-timing-text-retained-source-2026-11-12'):
        files += [p for p in (root / 'docs/validation' / folder).glob('*') if p.is_file()]
    # Retained qualification tests authenticate historical inputs separately
    # from live application code. Bind that complete selection to this run too.
    from scripts import sky130_retained_catalog as retained
    baseline = root / retained.BASELINE
    if baseline.is_file():
        prior = json.loads(baseline.read_bytes())
        names = {retained.BASELINE, retained.AUDIT, *prior['inputs'],
                 *(retained.SNAPSHOTS.get(name, name) for name in prior['source_files'])}
        files += [root / name for name in names]
    fixture = root / 'docs/qualification/sky130-mim-conditioning-v1/fixture-bundle.zip'
    if fixture.is_file():
        files.append(fixture)
    fixture = root / 'tests/fixtures/ihp-guard-raw-all100-v1.json'
    if fixture.is_file():
        files.append(fixture)
    fixture = root / 'tests/fixtures/esd-installed-headers-v1.json'
    if fixture.is_file():
        files.append(fixture)
    for folder in ('ihp-cmim-capacitance-v1', 'ihp-cmim-parallel-v1'):
        for name in ('SOURCE.json', 'LICENSE', 'coupon.ext', 'hierarchical.spice', 'flat.spice'):
            fixture = root / 'tests/fixtures' / folder / name
            if fixture.is_file():
                files.append(fixture)
    files += [p for p in (root / 'tests/fixtures/sky130-mim-shared-v1').rglob('*') if p.is_file()]
    for folder in ('ihp-resistor-templates', 'ihp-resistor-legacy', 'ihp-guard-corner-safe',
                   'sky130-esd-nvt-source-v1', 'sky130-esd-predecessor-v1', 'sky130-pw2dn-predecessor-v1'):
        files += [p for p in (root / 'icstudio/assets/qualification' / folder).glob('*') if p.is_file()]
    for name in ('collection.json','sky130A/package.json'):
        manifest = root / 'icstudio/assets/pdks' / name
        if manifest.is_file(): files.append(manifest)
    for name in ('sky130-mim-contract-v1.json', 'sky130-mim-contract-v2.json',
                 'sky130-mim-bias-source-map-v1.json', 'sky130-mim-bias-source-map-v2.json',
                 'sky130-mim-contract-v3.json', 'sky130-mim-bias-source-map-v3.json'):
        contract = root / 'docs/qualification' / name
        if contract.is_file(): files.append(contract)
    for prefix in ('sky130-li-contract', 'sky130-li-array-dynamic', 'sky130-metal-installed',
                   'sky130-metal-parallel-installed', 'sky130-metal-resistor-parallel',
                   'sky130-metal-resistors-linked'):
        for version in ('v1', 'v2', 'v3'):
            contract = root / 'docs/qualification' / (prefix + '-' + version + '.json')
            if contract.is_file(): files.append(contract)
    for version in ('v1', 'v2', 'v3'):
        folder = root / 'docs/qualification' / ('sky130-mos-voltage-' + version)
        files += [p for p in folder.glob('*') if p.is_file()]
        files += [p for p in (folder / 'sources').glob('*') if p.is_file()]
    archive = root / 'packaging/ngspice/ngspice-linux47-corrected-v1.zip'
    if archive.is_file(): files.append(archive)
    for package_name, label in (('sky130A', 'SKY130'), ('ihp-sg13g2', 'IHP')):
        package = root / 'icstudio/assets/pdks' / package_name / 'package.json'
        if not package.is_file():
            continue
        files.append(package)
        for current in (package, package.parent):
            if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
                raise ValueError('Linked selected '+label+' package path: ' + str(current))
        for name in json.loads(package.read_bytes())['files']:
            path = PurePosixPath(name)
            if (path.is_absolute() or any(part in ('', '.', '..') for part in name.split('/'))
                    or '\\' in name or ':' in name):
                raise ValueError('Unsafe selected '+label+' package member: ' + name)
            asset = package.parent.joinpath(*path.parts)
            current = package.parent
            for part in path.parts:
                current = current / part
                if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
                    raise ValueError('Linked selected '+label+' package member: ' + name)
            if not asset.resolve().is_relative_to(package.parent.resolve()):
                raise ValueError('Escaped selected '+label+' package member: ' + name)
            if not asset.is_file(): raise ValueError('Missing selected '+label+' package member: ' + name)
            files.append(asset)
    files += list((root / '.github/workflows').glob('*.yml'))
    files += list(root.glob('requirements*.txt'))
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def check_ihp_gui_output(folder):
    """Check the source child's complete file inventory after it has exited."""
    folder = Path(folder)
    report = json.loads((folder / 'report.json').read_bytes())
    inventory_file = folder / 'files.json'
    expected = json.loads(inventory_file.read_bytes())
    cases = {f'{model}-g{geometry}-v{via}-r{rotation}'
             for model in ('rsil', 'rppd', 'rhigh') for geometry in range(5)
             for via in (0, 1) for rotation in (0, 90)}
    if (report.get('status') != 'passed' or report.get('frozen') is not False
            or report.get('installed_acceptance') is not False
            or report.get('native_execution') is not False
            or any(report.get(key) is not False for key in ('qualified', 'release_ready', 'full_family'))
            or len(report.get('lifecycle', [])) != 60
            or {row.get('case') for row in report.get('lifecycle', [])} != cases
            or hashlib.sha256(inventory_file.read_bytes()).hexdigest() != report.get('files_sha256')):
        raise ValueError('Incomplete or overclaimed source IHP GUI result.')
    actual = {}
    for path in folder.rglob('*'):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked source IHP GUI evidence.')
        if path.is_file() and path not in (folder / 'report.json', folder / 'files.json'):
            actual[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError('Source IHP GUI evidence changed after the child inventory.')



def check_ihp_guard_gui_output(folder, execution_id, resources=ROOT):
    """Bind the launched source child, then independently read all its evidence."""
    from scripts.verify_frozen_ihp_guard_corner import source_audit, unlinked
    folder = unlinked(folder).resolve()
    report = json.loads((folder / 'report.json').read_bytes())
    if (not re.fullmatch('[0-9a-f]{32}', execution_id)
            or report.get('execution_id') != execution_id
            or Path(report.get('execution_root', '')).resolve() != folder):
        raise ValueError('Stale or relocated source guard GUI evidence.')
    return source_audit(folder, resources)


def stages(output=ROOT / 'build/ci-feedback'):
    return [
        ('unit-contracts', [sys.executable, '-m', 'unittest',
                            *('tests.' + name for name in UNIT_STAGE_MODULES), '-v']),
        ('ihp-contracts', [sys.executable, '-m', 'unittest',
                          *('tests.' + name for name in IHP_STAGE_MODULES), '-v']),
        ('physical-contracts', [sys.executable, '-m', 'unittest',
                               *('tests.' + name for name in PHYSICAL_STAGE_MODULES), '-v']),
        ('device-contracts', [sys.executable, '-m', 'unittest',
                              *('tests.' + name for name in DEVICE_STAGE_MODULES), '-v']),
        ('package-contracts', [sys.executable, '-m', 'unittest',
                               *('tests.' + name for name in PACKAGE_MODULES), '-v']),
        ('runtime-release-contracts', [sys.executable, '-m', 'unittest',
                                      *('tests.' + name for name in RUNTIME_RELEASE_MODULES), '-v']),
        ('release-contracts', [sys.executable, 'scripts/check_release.py']),
        ('menu-smoke', [sys.executable, 'tests/gui_menu_audit.py']),
        ('project-hub-smoke', [sys.executable, 'tests/gui_project_hub.py']),
        ('metal-resistor-editor-smoke', [sys.executable, 'tests/gui_sky130_metal_editor.py',
                                      '--out', str(Path(output)/'metal-resistor-editor')]),
        ('metal-resistor-parallel-smoke', [sys.executable, 'tests/gui_sky130_metal_resistor_parallel.py',
                                         '--out', str(Path(output)/'metal-resistor-parallel')]),
        ('ihp-resistor-editor-smoke', [sys.executable, 'tests/gui_ihp_resistor_editor.py',
                                       '--out', str(Path(output)/'ihp-resistor-editor'),
                                       '--execution-id', uuid.uuid4().hex]),
        ('ihp-guard-corner-smoke', [sys.executable, 'tests/gui_ihp_guard_corner.py',
                                   '--out', str(Path(output)/'ihp-guard-corner'),
                                   '--execution-id', uuid.uuid4().hex]),
        ('ihp-capacitor-corner-smoke', [sys.executable, 'tests/gui_ihp_capacitor_corners.py',
                                      str(Path(output)/'ihp-capacitor-corners')]),
    ]


STAGE_GROUPS = {
    'contracts': ('unit-contracts', 'ihp-contracts', 'physical-contracts',
                  'device-contracts', 'package-contracts', 'runtime-release-contracts',
                  'release-contracts'),
    'gui': ('menu-smoke', 'project-hub-smoke', 'metal-resistor-editor-smoke',
            'metal-resistor-parallel-smoke', 'ihp-resistor-editor-smoke',
            'ihp-guard-corner-smoke', 'ihp-capacitor-corner-smoke'),
}


def select_stages(commands, group='all'):
    """Partition hosted work without changing the default complete local lane."""
    if group == 'all':
        return commands
    if group not in STAGE_GROUPS:
        raise ValueError('Unknown source-feedback group: ' + group)
    ordered = STAGE_GROUPS['contracts'] + STAGE_GROUPS['gui']
    if len(set(ordered)) != len(ordered) or tuple(name for name, _ in commands) != ordered:
        raise ValueError('Source-feedback groups must partition every ordered stage exactly once.')
    selected = set(STAGE_GROUPS[group])
    return [(name, command) for name, command in commands if name in selected]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/ci-feedback')
    parser.add_argument('--group', choices=('all', 'contracts', 'gui'), default='all',
                        help='Run a named required hosted subset, or all 14 stages by default.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(QT_QPA_PLATFORM='offscreen', PYTHONPATH=str(ROOT / 'tests'), PYTHONUTF8='1')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=env, text=True).strip()
    if env.get('GITHUB_SHA') and commit != env['GITHUB_SHA']:
        raise ValueError('The feedback checkout must match the GitHub event SHA, including PR/merge-queue merge commits.')
    commands = stages(args.output)
    selected = select_stages(commands, args.group)
    report = {'schema': 1, 'commit': commit, 'event': env.get('GITHUB_EVENT_NAME', 'local'),
              'scope': __doc__, 'release_acceptance': False, 'stages': [], 'status': 'running',
              'stage_group': args.group, 'full_stage_selection': args.group == 'all',
              'expected_stages': [name for name, _ in selected],
              'all_expected_stages': [name for name, _ in commands],
              'source_files_sha256': source_identity()}
    started = time.monotonic()
    def save():
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    try:
        report['syntax_files'] = check_syntax()
        save()
        for name, command in selected:
            step_start = time.monotonic()
            print('Running ' + name, flush=True)
            with (args.output / (name + '.log')).open('w', encoding='utf-8') as log:
                try:
                    result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=300)
                    returncode = result.returncode
                except subprocess.TimeoutExpired:
                    returncode = 124
            report['stages'].append({'name': name, 'returncode': returncode,
                                    'elapsed_seconds': round(time.monotonic() - step_start, 3)})
            save()
            if returncode:
                print((args.output / (name + '.log')).read_text(encoding='utf-8'), flush=True)
                raise RuntimeError(f'{name} failed with exit code {returncode}; see the retained log.')
            if name == 'ihp-resistor-editor-smoke':
                check_ihp_gui_output(args.output / 'ihp-resistor-editor')
            if name == 'ihp-guard-corner-smoke':
                readback = check_ihp_guard_gui_output(
                    args.output / 'ihp-guard-corner',
                    command[command.index('--execution-id') + 1])
                (args.output / 'ihp-guard-corner-readback.json').write_text(
                    json.dumps(readback, indent=2) + '\n', encoding='utf-8')
        if source_identity() != report['source_files_sha256']:
            raise RuntimeError('Source files changed during feedback; keep this run as invalid and run the final sources again.')
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=str(exc), first_failure_seconds=round(time.monotonic() - started, 3))
        raise
    finally:
        save()
        print(json.dumps({k: v for k, v in report.items() if k != 'source_files_sha256'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
