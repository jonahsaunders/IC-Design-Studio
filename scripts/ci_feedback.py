"""Bounded source feedback with timings; never a substitute for release acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
UNIT_MODULES = (
    'test_ci_candidate', 'test_ci_feedback', 'test_reference_toolchain', 'test_checkout_integrity',
    'test_core', 'test_lifecycle', 'test_workflows', 'test_project_pdk',
    'test_pdk_templates', 'test_student_physical', 'test_layout_verification',
    'test_analog.AnalogTests.test_capabilities_do_not_trust_catalog_or_metadata',
    'test_digital_bundle', 'test_digital_runtime', 'test_digital_rc',
    'test_release_acceptance', 'test_release_evidence', 'test_release_intent',
    'test_pdk_qualification_matrix', 'test_ihp_hv_mos_layouts', 'test_sky130_li_linked',
    'test_ihp_resistor_via_class', 'test_ihp_resistor_via_auditor', 'test_ihp_resistor_editor',
    'test_ihp_resistor_backend_assets', 'test_ihp_resistor_lvs_reference', 'test_frozen_ihp_resistor_gate',
    'test_ihp_capacitor_corners',
    'test_resistor_layout_qualification', 'test_sky130_metal_resistor_layouts',
    'test_sky130_li_resume', 'test_sky130_mim_passive_corners', 'test_sky130_mim_passive_audit',
    'test_sky130_mim_bias_boundaries', 'test_sky130_mim_bias_audit',
    'test_sky130_mim1_extract', 'test_sky130_mim2_extract', 'test_sky130_mim_contact_topology',
    'test_mim_desktop_probe', 'test_frozen_mim', 'test_sky130_pw2dn_native_probe',
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
    'test_sky130_esd_nvt', 'test_sky130_esd_nvt_audit',
    'test_sky130_rf_default_acceptance', 'test_project_hub_completion',
    'test_sky130_rf_default', 'test_sky130_rf_corner_sources',
    'test_sky130_mim_hierarchy_electrical', 'test_sky130_mim_hierarchy_electrical_audit',
    'test_desktop_acceptance_handoff', 'test_release_source_handoff',
    'test_ihp_bondpad', 'test_ihp_rf_mos_exchange', 'test_ihp_lvs_selector_review', 'test_digital_recipe_corner_contract', 'test_source_spice_archives', 'test_sky130_mim_hierarchy_selection',
)


# Keep the complete selection above auditable while bounding each subprocess.
# The former single unit stage exceeded 300 seconds on ordinary Windows.
_DEVICE_STAGE_START = UNIT_MODULES.index('test_sky130_metal_editor')
UNIT_STAGE_MODULES = UNIT_MODULES[:_DEVICE_STAGE_START]
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
    'test_stage_linux_ngspice', 'test_linux_ngspice_dependencies',
    'test_fetch_linux_ngspice_sources', 'test_release_pw2dn_evidence',
    'test_release_qualification', 'test_publish_prerelease',
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
    fixture = root / 'docs/qualification/sky130-mim-conditioning-v1/fixture-bundle.zip'
    if fixture.is_file():
        files.append(fixture)
    for folder in ('ihp-resistor-templates', 'ihp-resistor-legacy',
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
    for prefix in ('sky130-li-contract', 'sky130-metal-installed',
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


def stages(output=ROOT / 'build/ci-feedback'):
    return [
        ('unit-contracts', [sys.executable, '-m', 'unittest',
                            *('tests.' + name for name in UNIT_STAGE_MODULES), '-v']),
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
        ('ihp-capacitor-corner-smoke', [sys.executable, 'tests/gui_ihp_capacitor_corners.py',
                                      str(Path(output)/'ihp-capacitor-corners')]),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/ci-feedback')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(QT_QPA_PLATFORM='offscreen', PYTHONPATH=str(ROOT / 'tests'), PYTHONUTF8='1')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=env, text=True).strip()
    if env.get('GITHUB_SHA') and commit != env['GITHUB_SHA']:
        raise ValueError('The feedback checkout must match the GitHub event SHA, including PR/merge-queue merge commits.')
    report = {'schema': 1, 'commit': commit, 'event': env.get('GITHUB_EVENT_NAME', 'local'),
              'scope': __doc__, 'release_acceptance': False, 'stages': [], 'status': 'running',
              'source_files_sha256': source_identity()}
    started = time.monotonic()
    def save():
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    try:
        report['syntax_files'] = check_syntax()
        save()
        for name, command in stages(args.output):
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
