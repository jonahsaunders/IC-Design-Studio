"""Replay recovered pin-corrected SKY130 references, before remote fill.

The application pin exporter must reproduce each original output byte for byte.
All six supplemental profiles then execute on that output. This does not rerun
the later filled layouts, place/route, native decks, timing or Windows gates.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import klayout.db as k

from icstudio import digital_sky130_pins as pins
from scripts import check_sky130_grid_density as inputs
from scripts import sky130_error_reconciliation as retained

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/validation/sky130-reference-replay-2026-10-14.json'
CHECKPOINT = ROOT / 'docs/validation/sky130-pin-progress-2026-10-11.json'
CHECKPOINT_SHA256 = 'ab7042f040c03decb02384b3e9f222bb3c5fdb7633a8f0df654631199cd384fc'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_profiles(reports, gds_sha256, top):
    if set(reports) != set(retained.PROFILES):
        raise ValueError('Missing or extra reference profiles.')
    for name, module in retained.PROFILES.items():
        report = reports[name]
        expected = Counter(row['rule'] for row in module.check({})['checks'])
        checks = report['checks']
        if (report.get('status') != 'PASS' or report.get('qualified') is not False
                or type(report.get('violations')) is not int or report['violations'] != 0
                or report.get('gds_sha256') != gds_sha256 or report.get('top') != top
                or report.get('checker_sha256') != digest(Path(module.__file__).read_bytes())
                or Counter(row['rule'] for row in checks) != expected
                or any(type(row['violations']) is not int or row['violations'] != 0 for row in checks)):
            raise ValueError('Failed, incomplete or stale reference profile: ' + name)
    geometry = reports['global_geometry']
    if geometry.get('layer_map_sha256') != retained.sky130_global_geometry.LAYER_MAP_SHA256:
        raise ValueError('Changed layer-purpose map.')
    connection = reports['floating_connectivity']
    areas = connection['layer_area_nm2']
    expected_layers = set(retained.PROFILES['floating_connectivity'].check({})['layer_area_nm2'])
    if (set(areas) != expected_layers or connection['covered_area_nm2'] != areas
            or any(type(value) is not int or value < 0 for value in areas.values())
            or any(type(value) is not int or value < 0 for value in connection['covered_area_nm2'].values())
            or connection['floating'] != []
            or type(connection['nets']) is not int or type(connection['anchored_nets']) is not int
            or not 0 < connection['anchored_nets'] <= connection['nets']):
        raise ValueError('Incomplete conductor extraction.')


def member_bytes(archive, name):
    if archive.namelist().count(name) != 1:
        raise ValueError('Missing or duplicate archive member: ' + name)
    return archive.read(name)


def build(artifact):
    if inputs.digest(artifact) != inputs.ARTIFACT['sha256']:
        raise ValueError('CI archive differs from the locked artifact.')
    checkpoint_bytes = CHECKPOINT.read_bytes()
    if digest(checkpoint_bytes) != CHECKPOINT_SHA256:
        raise ValueError('Changed pin-reference checkpoint.')
    checkpoint = json.loads(checkpoint_bytes)
    for name, sha in checkpoint['source_files'].items():
        if inputs.digest(ROOT / name) != sha:
            raise ValueError('Changed original pin-export source: ' + name)
    references = {row['case']: row for row in checkpoint['references']}
    if set(references) != set(inputs.MEMBERS) or len(checkpoint['references']) != 3:
        raise ValueError('Changed reference inventory.')
    # Keep the newer filled identities explicit, without transferring any
    # fresh unfilled-layout results into their acceptance records.
    filled = {row['case']: row['gds_sha256'] for row in retained.build()['cases']}
    cases = []
    with ZipFile(artifact) as archive, TemporaryDirectory() as temporary:
        for name, member in inputs.MEMBERS.items():
            reference = references[name]
            inventory_bytes = member_bytes(archive, member + '/inventory.json')
            if digest(inventory_bytes) != reference['inventory']['sha256']:
                raise ValueError('Changed independent OpenDB pin inventory: ' + name)
            inventory = json.loads(inventory_bytes)
            exported = member_bytes(archive, member + '/final.gds')
            if digest(exported) != reference['gds_sha256'] or digest(exported) == filled[name]:
                raise ValueError('Changed pin-corrected reference identity: ' + name)
            report = json.loads(member_bytes(archive, member + '/report.json'))
            relative = PurePosixPath(report['source']['path'])
            if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):
                raise ValueError('Invalid source GDS archive path.')
            source_member = str(PurePosixPath(member).parent / relative)
            source_bytes = member_bytes(archive, source_member)
            if (digest(source_bytes) != report['source']['sha256']
                    or digest(source_bytes) != report['source_gds_sha256']
                    or len(source_bytes) != report['source']['bytes']):
                raise ValueError('Changed original CI source GDS: ' + name)
            source = Path(temporary) / (name + '-source.gds')
            target = Path(temporary) / (name + '-export.gds')
            source.write_bytes(source_bytes)
            # Actual application exporter and its independent mask/text readback.
            export_report = pins.write(source, target, inventory)
            if (export_report != {key: value for key, value in report.items() if key != 'source'}
                    or target.read_bytes() != exported):
                raise ValueError('Application export did not reproduce the exact reference: ' + name)
            profiles = {key: module.audit(target) for key, module in retained.PROFILES.items()}
            validate_profiles(profiles, reference['gds_sha256'], inventory['top'])
            cases.append(dict(case=name, top=inventory['top'], gds_sha256=reference['gds_sha256'],
                              filled_reference_sha256=filled[name], matches_filled_reference=False,
                              artifact_member=member + '/final.gds', source_member=source_member,
                              inventory_sha256=digest(inventory_bytes), application_export=export_report,
                              byte_exact_export=True, profiles=profiles))
    paths = [Path(__file__), Path(inputs.__file__), Path(pins.__file__),
             ROOT / 'tests/test_sky130_reference_replay.py',
             *(Path(module.__file__) for module in retained.PROFILES.values())]
    return dict(schema=1, chunk=6, status='pin-corrected-reference-replay-pass', qualified=False,
                chunk_complete=False, execution_mode='fresh-unfilled-reference-execution',
                runtime=dict(system=platform.system(), klayout=k.__version__), artifact=inputs.ARTIFACT,
                pin_checkpoint=dict(path=str(CHECKPOINT.relative_to(ROOT)), sha256=CHECKPOINT_SHA256),
                source_files={str(path.relative_to(ROOT)): inputs.digest(path) for path in paths},
                cases=cases,
                scope='The three original pin-corrected outputs and OpenDB inventories match the retained checkpoint. '
                      'Fresh application pin export reproduces those GDS bytes exactly and all six supplemental profiles pass. '
                      'CI source-GDS hashes are recorded separately; they differ from the earlier capture. '
                      'No fresh filled-layout, place/route, native DRC/LVS, timing, Windows or complete application gate is asserted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = build(args.artifact)
    content = (json.dumps(result, indent=2, ensure_ascii=False) + '\n').encode()
    if args.check:
        if args.output.read_bytes() != content:
            raise ValueError('Saved reference replay does not reproduce.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    print(json.dumps(dict(status=result['status'], chunk_complete=False,
                         cases={row['case']: dict(byte_exact_export=row['byte_exact_export'],
                                                 profiles={name: report['status'] for name, report in row['profiles'].items()})
                                for row in result['cases']})))


if __name__ == '__main__':
    main()
