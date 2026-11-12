"""Reproduce supplemental diagnostics on a checksum-locked CI archive.

Exit 0 with --check means the diagnostic record reproduced, not that chunk 6
passed. These CI exports do not have the locked filled-reference identities.
"""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from scripts import sky130_grid_geometry as grid
from scripts import sky130_density_windows as density
from scripts import sky130_error_reconciliation as reconciliation

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/validation/sky130-grid-density-2026-10-14.json'
ARTIFACT = dict(
    repository='jonahsaunders/IC-Design-Studio',
    run_id=38190866879, artifact_id=11722609690,
    name='digital-implementation-evidence',
    commit='fb1a741c145595b1b0931157f1fb7ec3f236058b',
    sha256='4ec0edefcd132a2373c52a3030a58462788a0deabf386a4bece5238026186492',
)
MEMBERS = {
    'counter': 'digital-platforms/sky130hd/finished/sky130-pin-export',
    'uart': 'digital-workloads/sky130hd/uart/finished/sky130-pin-export',
    'apb': 'digital-workloads/sky130hd/apb/finished/sky130-pin-export',
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(artifact):
    if digest(artifact) != ARTIFACT['sha256']:
        raise ValueError('CI archive differs from the locked artifact.')
    # Revalidate the exact historical reports, their checker sources, both OS
    # audits and all three original case identities before quoting open work.
    retained = reconciliation.build()
    checkpoint_path = ROOT / reconciliation.CHECKPOINT
    checkpoint = json.loads(checkpoint_path.read_text())
    data = json.loads((ROOT / checkpoint['data']['path']).read_text())
    originals = {row['case']: row for row in data}
    manual = {row['id']: row for row in json.loads((ROOT / reconciliation.PERIPHERY).read_text())['rule_rows']}
    errors = {row['case']: row for row in retained['cases']}
    cases = []
    with ZipFile(artifact) as archive, TemporaryDirectory() as temp:
        for name, member in MEMBERS.items():
            gds_bytes = archive.read(member + '/final.gds')
            inventory_bytes = archive.read(member + '/inventory.json')
            inventory = json.loads(inventory_bytes)
            if inventory.get('schema') != 1:
                raise ValueError('Unknown pin inventory schema.')
            gds = Path(temp) / (name + '.gds')
            gds.write_bytes(gds_bytes)
            grid_result = grid.audit(gds)
            density_result = density.audit(gds, inventory['die_nm'])
            if grid_result['top'] != inventory['top']:
                raise ValueError('Independent inventory and GDS top differ.')
            original = originals[name]
            if grid_result['gds_sha256'] == original['gds_sha256']:
                raise ValueError('Diagnostic archive unexpectedly matches a filled reference; review scope explicitly.')
            open_rows = [row for row in original['rows'] if row['disposition'] in {
                'execution-review-required', 'definition-required'}]
            cases.append(dict(
                case=name, artifact_member=member + '/final.gds',
                inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
                filled_reference_sha256=original['gds_sha256'],
                matches_filled_reference=False, grid=grid_result, density=density_result,
                retained_periphery_counts=original['counts'],
                retained_error_counts=errors[name]['counts'],
                open_periphery_rows=[dict(id=row['id'], rule=row['rule'],
                                          description=manual[row['id']]['description'], disposition=row['disposition'])
                                     for row in open_rows]))
    files = [Path(__file__), Path(grid.__file__), Path(density.__file__), grid.SOURCES,
             ROOT / 'tests/test_sky130_grid_density.py']
    return dict(
        schema=1, chunk=6, status='blocked', qualified=False, chunk_complete=False,
        execution_mode='new-ci-export-diagnostics', artifact=ARTIFACT,
        source_files={str(path.relative_to(ROOT)): digest(path) for path in files},
        retained_checkpoint=dict(path=reconciliation.CHECKPOINT, sha256=digest(checkpoint_path)),
        required_filled_archive=checkpoint['archive']['dependency'],
        cases=cases,
        blockers=[
            'The available CI GDS files are different from all three locked filled references; final-layout checks cannot inherit these runs.',
            '24 periphery execution rows and the missing x.20 pin-spacing definition remain open per reference.',
            '1474 published error records remain unreviewed per reference; shared rule names do not transfer coverage.',
            'Oxide-density operand construction and source unit/edge interpretation remain unresolved; the current runs measure metal occupancy only.',
            'The declared 200/400 um dies have no full 700 um windows; full-window coverage needs a reviewed parent-context method.',
            'Final filled-layout timing/equivalence and the combined application/Windows/Linux acceptance gate remain unexecuted.',
        ])


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
            raise ValueError('Saved grid/density diagnostics do not reproduce.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    print(json.dumps(dict(status=result['status'], chunk_complete=False,
                         cases={row['case']: dict(grid=row['grid']['status'],
                                                 grid_checks=row['grid']['checks'],
                                                 full_windows=row['density']['full_windows'])
                                for row in result['cases']})))


if __name__ == '__main__':
    main()
