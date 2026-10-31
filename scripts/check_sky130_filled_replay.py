"""Replay the exact filled references; preserve every unresolved acceptance gate.

The small source-controlled fixture replaces no native archive. It contains
the three final GDS files, their independent original die/pin inventories and
the pinned published manual. No network or native EDA executable is needed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from scripts import sky130_error_reconciliation as retained
from scripts import sky130_geometry_reconciliation as geometry
from scripts import sky130_rule_execution as execution
from scripts import sky130_grid_geometry as grid
from scripts import sky130_density_windows as density
from scripts.check_sky130_reference_replay import validate_profiles

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'tests/fixtures/sky130-filled-references-v1.zip'
BUNDLE_SHA256 = '8db9401bc73e117db9d72dcccb03ac7700016b5a5c61e518c14cb5a0ec3542fa'
MANIFEST_SHA256 = 'd3811b984d55cf3cb9f0dc6cb10c7d6dd627e5c7d4eb3439d5a05e9df2ad63bc'
OUTPUT = ROOT / 'docs/validation/sky130-filled-replay-2026-10-14.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def member_name(name):
    if not isinstance(name, str):
        raise ValueError('Unsafe or noncanonical bundle member.')
    path = PurePosixPath(name)
    if (not name or path.is_absolute()
            or '..' in path.parts or '\\' in name or ':' in name or str(path) != name):
        raise ValueError('Unsafe or noncanonical bundle member.')
    return path


def unpack(bundle, destination):
    """Authenticate all members before writing into a new, private directory."""
    bundle = Path(bundle)
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Bundle destination must be new.')
    if digest(bundle.read_bytes()) != BUNDLE_SHA256:
        raise ValueError('Changed filled-reference bundle.')
    checkpoint = json.loads((ROOT / retained.CHECKPOINT).read_bytes())
    final = {row['case']: row for row in checkpoint['cases']}
    pin_checkpoint = json.loads((ROOT / 'docs/validation/sky130-pin-progress-2026-10-11.json').read_bytes())
    pins = {row['case']: row for row in pin_checkpoint['references']}
    manual = json.loads((ROOT / retained.PERIPHERY).read_bytes())
    retained.validate_unreviewed(manual)
    with ZipFile(bundle) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or names.count('manifest.json') != 1:
            raise ValueError('Duplicate or missing bundle member.')
        raw = archive.read('manifest.json')
        if digest(raw) != MANIFEST_SHA256:
            raise ValueError('Changed filled-reference manifest.')
        manifest = json.loads(raw)
        if (manifest.get('schema') != 1 or manifest.get('qualified') is not False
                or manifest.get('chunk_complete') is not False
                or Counter(row['case'] for row in manifest['cases']) != Counter(final.keys())):
            raise ValueError('Changed bundle scope or cases.')
        expected = {'sources/source-lock.json'} | {'sources/' + key for key in manual['source_files']}
        expected |= {case + '/' + filename for case in final for filename in ('filled.gds', 'inventory.json')}
        if set(manifest['files']) != expected or set(names) != expected | {'manifest.json'}:
            raise ValueError('Missing or unexpected bundle member.')
        contents = {}
        for name, identity in manifest['files'].items():
            member_name(name)
            info = archive.getinfo(name)
            if (info.is_dir() or type(identity['bytes']) is not int or not 0 < identity['bytes'] < 100_000_000
                    or info.file_size != identity['bytes']):
                raise ValueError('Invalid bundle member size: ' + name)
            data = archive.read(name)
            if len(data) != identity['bytes'] or digest(data) != identity['sha256']:
                raise ValueError('Changed bundle member bytes: ' + name)
            contents[name] = data
        if digest(contents['sources/source-lock.json']) != retained.SOURCE_LOCK_SHA256:
            raise ValueError('Changed manual source lock.')
        for name, identity in manual['source_files'].items():
            if digest(contents['sources/' + name]) != identity['sha256']:
                raise ValueError('Changed published source: ' + name)
        for case in manifest['cases']:
            name = case['case']
            if case['gds'] != name + '/filled.gds' or case['inventory'] != name + '/inventory.json':
                raise ValueError('Changed reference member mapping.')
            if (case['gds_sha256'] != final[name]['gds_sha256']
                    or digest(contents[case['gds']]) != final[name]['gds_sha256']
                    or case['inventory_sha256'] != pins[name]['inventory']['sha256']
                    or digest(contents[case['inventory']]) != pins[name]['inventory']['sha256']):
                raise ValueError('Reference differs from its independent checkpoint: ' + name)
            inventory = json.loads(contents[case['inventory']])
            if case['die_nm'] != inventory['die_nm'] or case['top'] != inventory['top']:
                raise ValueError('Changed independent die/top identity.')
    destination.mkdir(parents=True)
    for name, data in contents.items():
        path = destination.joinpath(*member_name(name).parts)
        if not path.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Bundle member leaves destination.')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return manifest


def summarize(cases):
    """Even a clean geometry run cannot satisfy missing rule definitions."""
    if Counter(row['case'] for row in cases) != Counter(('counter', 'uart', 'apb')):
        raise ValueError('Missing or duplicate final cases.')
    return dict(status='BLOCKED', qualified=False, chunk_complete=False,
                blockers=[
                    '22 periphery execution reviews and the x.20 numeric pin-spacing definition remain open per design.',
                    '1161 published error records remain unreviewed per design, including chip-specific records.',
                    'Grid units and mask aliases need source reconciliation; all text-anchor findings remain visible.',
                    'Oxide-density construction, edge policy and parent-chip windows remain unresolved; raw metal occupancy is not acceptance.',
                    'Final filled-layout timing/equivalence, combined application and delivered-runtime acceptance remain unexecuted.',
                ])


def build(bundle=BUNDLE, progress=None):
    baseline = geometry.build()
    checkpoint = json.loads((ROOT / retained.CHECKPOINT).read_bytes())
    old = {row['case']: row for row in json.loads((ROOT / checkpoint['data']['path']).read_bytes())}
    catalog = json.loads((ROOT / retained.CATALOG).read_bytes())
    periphery = json.loads((ROOT / retained.PERIPHERY).read_bytes())
    bindings = geometry.geometry_bindings() | geometry.mask_bindings(catalog)
    controls = geometry.notch_controls()
    cases = []
    with TemporaryDirectory() as temporary:
        folder = Path(temporary) / 'authenticated'
        manifest = unpack(bundle, folder)
        for reference in manifest['cases']:
            name = reference['case']
            gds = folder / reference['gds']
            fresh = execution.audit(gds, folder / 'sources')
            fresh['case'] = name
            # A changed result must be explicitly reviewed, not silently
            # accepted as the historical final candidate's equivalent.
            if fresh != old[name]:
                raise ValueError('Fresh final-layout execution differs from retained evidence: ' + name)
            profiles = {key: fresh[key] for key in retained.PROFILES}
            validate_profiles(profiles, reference['gds_sha256'], reference['top'])
            reconciled = geometry.reconcile(catalog, periphery, fresh, bindings, controls)
            prior = next(row for row in baseline['cases'] if row['case'] == name)
            if reconciled != prior:
                raise ValueError('Fresh rule reconciliation differs from retained coverage.')
            grid_report = grid.audit(gds)
            density_report = density.audit(gds, reference['die_nm'])
            cases.append(dict(case=name, top=reference['top'], gds_sha256=reference['gds_sha256'],
                              inventory_sha256=reference['inventory_sha256'],
                              execution=fresh, reconciliation=reconciled,
                              grid=grid_report, density=density_report))
            if progress:
                progress(dict(case=name, geometry='PASS', grid=grid_report['status'], density=density_report['status']))
    files = [Path(__file__), Path(execution.__file__), Path(geometry.__file__),
             Path(grid.__file__), Path(density.__file__),
             ROOT / 'tests/test_sky130_filled_replay.py']
    return dict(schema=1, chunk=6, **summarize(cases),
                execution_mode='fresh-final-filled-layout-polygon-execution',
                bundle=dict(path=BUNDLE.relative_to(ROOT).as_posix(), sha256=BUNDLE_SHA256,
                            manifest_sha256=MANIFEST_SHA256, files=len(manifest['files'])),
                source_files={path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in files},
                retained_checkpoint=dict(path=retained.CHECKPOINT, sha256=digest((ROOT / retained.CHECKPOINT).read_bytes())),
                geometry_checkpoint=dict(path=geometry.OUTPUT.relative_to(ROOT).as_posix(), sha256=digest(geometry.OUTPUT.read_bytes())),
                cases=cases, notch_controls=controls,
                scope='Fresh complete periphery applicability and six supplemental profiles on the three exact filled GDS files. '
                      'The current reconciliation runs on the fresh reports. Grid and density diagnostics remain failures/blockers. '
                      'No fresh native DRC/LVS, place/route, timing, installer or full process qualification is asserted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=BUNDLE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build(args.bundle, progress=lambda row: print(json.dumps(row), flush=True))
    raw = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode()
    if args.check:
        if args.output.read_bytes() != raw:
            raise ValueError('Saved filled-layout replay differs from fresh execution.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    print(json.dumps(dict(status=report['status'], chunk_complete=False, blockers=report['blockers'])))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
