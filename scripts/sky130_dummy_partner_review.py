"""Bind five empty-partner proofs without constructing generated dummy FOM."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_dummy_partners as checks
from scripts import sky130_diecut_density_review as previous_review

delivery = previous_review.delivery
ROOT = delivery.ROOT
PREVIOUS = 'docs/validation/sky130-diecut-density-2026-10-15.json'
PREVIOUS_SHA = '2e69be4e7708e1e81c39dc469e22be2ac5561f3e1944091397c396549c17c859'
OUTPUT = ROOT/'docs/validation/sky130-dummy-partners-2026-10-15.json'


def source_proof(folder, catalog):
    raw = {key: delivery.checked(Path(folder)/key, digest) for key, digest in checks.SOURCE['files'].items()}
    def rows(key): return list(csv.DictReader(io.StringIO(raw[key].decode())))
    errors = {r['ID']: r for r in rows('docs/rules/errors.csv')}
    indexed = {r['id']: r for r in catalog['rows']}
    manual = {r['Name']: r for r in rows('docs/rules/periphery/p018-x_dotdash.csv')}
    # Same rule and operation bind the error-catalog SEALID to areaid.sl.
    delivery.require(manual['(x.23b)']['Description'] == 'diff cannot straddle :drc_tag:`areaid.sl`' and
        errors['r381']['Description'] == 'diff must not straddle SEALID' and
        errors['r381']['Name'] == 'x.23b', 'Changed seal alias correspondence.')
    from scripts import sky130_seal_geometry_review as seal
    from scripts import sky130_esd_fuse_review as fuse
    seal_proof = seal.source_proof(folder, catalog)
    diecut_proof = previous_review.source_proof(folder, catalog)
    inventory = json.loads((ROOT/'docs/qualification/sky130-rule-inventory.json').read_bytes())
    fuse_proof = fuse.source_proof(folder, inventory, catalog)
    delivery.require(checks.LAYERS['seal'] == (81, 1) and checks.LAYERS['diecut'] == (81, 11) and
        tuple(checks.LAYERS[name] for name in checks.PARTNERS['fuse']) == fuse.FUSE_PAIRS,
        'Changed known partner purposes.')
    bindings = {}
    for key, check in checks.CHECKS.items():
        literal = (f"{check['limit_nm']/1000:g} min. spacing of fomDummyDRC & {check['partner']}"
                   if check['operation'] == 'spacing' else f"fomDummyDRC must not overlap {check['partner']}")
        delivery.require((errors[key]['Name'], errors[key]['Description']) == (check['rule'], literal) and
            (indexed[key]['rule'], indexed[key]['description']) == (check['rule'], literal),
            'Changed dummy-FOM binary relation: '+key)
        bindings[key] = dict(catalog=indexed[key], check=check)
    return dict(source=checks.SOURCE, bindings=bindings, seal=seal_proof, fuse=fuse_proof,
        diecut={key: diecut_proof[key] for key in ('diecut_marker', 'diecut_description', 'manual')},
        interpretation=checks.SCOPE,
        unresolved='No manual fomdmy construction is inferred. Twelve other dummy-FOM records and the separate required density obligations remain open.')


def build(workspace=None, case=None, progress=None):
    workspace = Path(workspace or ROOT.parents[1]).resolve()
    previous = json.loads(delivery.checked(ROOT/PREVIOUS, PREVIOUS_SHA))
    fresh = previous_review.build(workspace, case, progress)
    catalog = json.loads((ROOT/delivery.queue.CATALOG).read_bytes())
    with TemporaryDirectory() as td:
        folder = Path(td)/'inputs'; delivery.fixture.unpack(delivery.fixture.BUNDLE, folder)
        proof = source_proof(folder/'sources', catalog)
    for row in fresh['cases']:
        original = delivery.pick(previous, row['case'])
        delivery.require(row['gds_sha256'] == original['gds_sha256'] and row['counts'] == original['counts'],
                         'Die-cut/density replay differs from the previous checkpoint.')
        path = workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        report = checks.audit(path); checks.evaluate(report, row['gds_sha256'], row['top'])
        delivery.require(report['unreviewed'] == 0, 'Reference dummy-FOM partners are present.')
        row['rows'] = delivery.apply_rows(row['rows'], report['rows'], catalog, 'dummy_partners', row['provenance'])
        row['measurements']['dummy_partners'] = report
        row['counts'] = dict(Counter(r['disposition'] for r in row['rows']))
        row['remaining_batches'] = delivery.queue.partition([r for r in row['rows'] if r['disposition'] == 'unreviewed'])
        if progress: progress(dict(case=row['case'], stage='dummy-partners-reviewed', counts=row['counts']))
    fresh.update(status='corrected-catalog-dummy-partners-reviewed', predecessor=dict(path=PREVIOUS, sha256=PREVIOUS_SHA),
                 verification_mode='authenticated-baseline-plus-fresh-width-module-diecut-density-dummy-partners')
    fresh['inputs'][PREVIOUS] = PREVIOUS_SHA; fresh['proofs']['dummy_partners'] = proof
    for path in (Path(__file__), Path(checks.__file__), ROOT/'tests/test_sky130_dummy_partners.py'):
        fresh['source_files'][path.relative_to(ROOT).as_posix()] = delivery.sha(path)
    fresh['source_files'] = dict(sorted(fresh['source_files'].items()))
    fresh['scope'] += ' Five dummy-FOM binary records have freshly verified empty known partners. No generated dummy-FOM recipe or enclosure obligation is discharged.'
    fresh['retained_baseline']['execution'] += ' The dummy-FOM known-partner census executes freshly.'
    return fresh


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--workspace', type=Path)
    p.add_argument('--case', choices=delivery.queue.CASES); p.add_argument('--output', type=Path, default=OUTPUT)
    args = p.parse_args()
    args.output.write_bytes((json.dumps(build(args.workspace, args.case, lambda r: print(json.dumps(r), flush=True)),
        indent=2, ensure_ascii=False)+'\n').encode())
