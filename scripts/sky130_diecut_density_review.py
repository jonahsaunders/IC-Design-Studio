"""Reconcile die-cut spacing absences and retain new density observations separately."""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_diecut_absence as checks
from icstudio import digital_sky130_waffle_windows as density
from scripts import sky130_module_operand_review as previous_review

delivery = previous_review.delivery
ROOT = delivery.ROOT
PREVIOUS = 'docs/validation/sky130-module-operand-2026-10-15.json'
PREVIOUS_SHA = 'a29d5621672513fe7b014778eb3bd13d6c1a5f5b7ff476f13226ddbba05737b5'
OUTPUT = ROOT/'docs/validation/sky130-diecut-density-2026-10-15.json'


def source_proof(folder, catalog):
    raw = {key: delivery.checked(Path(folder)/key, digest) for key, digest in checks.SOURCE['files'].items()}
    def rows(key): return list(csv.DictReader(io.StringIO(raw[key].decode())))
    markers = [r for r in rows('docs/rules/gds_layers.csv') if r['Layer name'] == 'areaid.dt']
    delivery.require(checks.DIECUT == (81, 11) and len(markers) == 1 and markers[0] == dict(zip(
        ('Layer name', 'Purpose', 'GDS layer:datatype', 'Description'),
        ('areaid.dt', 'identifier', '81:11', 'Location of dice within the frame'))), 'Changed die-cut marker.')
    descriptions = list(csv.reader(io.StringIO(raw['docs/rules/layers/table-c4b-layer-description.csv'].decode())))
    c4 = [r for r in descriptions if r and r[0] == 'areaid.dt{81:11}']
    delivery.require(len(c4) == 1 and c4[0][1:3] == ['areaid die cut', 'areaid.die'] and
        'rules in frame to die edge' in c4[0][3], 'Changed die-cut definition.')
    manual = next(r for r in rows('docs/rules/periphery/p043-nsm_dotdash.csv') if r['Name'] == '(nsm.3b)')
    delivery.require(manual['Description'].startswith('Min spacing between :drc_tag:`areaid.dt` to diff.dg, tap.dg, fom.dy,') and
        (manual['Flags'], manual['Value'], manual['Unit']) == ('', '3.000', 'µm'), 'Changed nsm.3b operation.')
    indexed = {r['id']: r for r in catalog['rows']}; errors = {r['ID']: r for r in rows('docs/rules/errors.csv')}
    bindings = {}
    for key, check in checks.CHECKS.items():
        literal = '3 min. spacing of '+check['other_operand']+' & dieCut'
        delivery.require((indexed[key]['rule'], indexed[key]['description']) == ('nsm.3b', literal) and
            (errors[key]['Name'], errors[key]['Description']) == ('nsm.3b', literal), 'Changed die-cut spacing record: '+key)
        bindings[key] = dict(catalog=indexed[key], check=check)
    from scripts import sky130_waffle_density_review as waffle
    inventory = json.loads((ROOT/'docs/qualification/sky130-rule-inventory.json').read_bytes())
    waffle_proof = waffle.source_proof(folder, inventory, catalog)
    for name, digest in density.SOURCE['files'].items(): delivery.checked(Path(folder)/name, digest)
    return dict(source=checks.SOURCE, diecut_marker=markers[0], diecut_description=c4[0], manual=manual,
        bindings=bindings, interpretation=checks.SCOPE, density_source=waffle_proof,
        density_scope=density.SCOPE,
        unresolved='Present die-cut geometry and all enclosure remain separate. Numerical density predicates do not resolve window/cell policy or generated final-mask construction.')


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
                         'Module replay differs from preceding reference catalog.')
        path = workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        report = checks.audit(path); checks.evaluate(report, row['gds_sha256'], row['top'])
        delivery.require(all(r['disposition'] == 'absent-operand' for r in report['rows']), 'Reference die-cut is present.')
        row['rows'] = delivery.apply_rows(row['rows'], report['rows'], catalog, 'diecut_absence', row['provenance'])
        observation = density.audit(path); density.evaluate(observation, row['gds_sha256'], row['top'])
        delivery.require(observation['unreviewed'] == 0, 'Reference waffle-drop operands are present.')
        # Those 48 absences were already established. Never add them again or
        # relabel them as numerical execution on references without targets.
        current = {r['id']: r for r in row['rows']}
        delivery.require(all(current[r['id']]['disposition'] == 'absent-operand' for r in observation['rows']),
                         'New density census differs from retained reference decisions.')
        row['measurements'].update(diecut_absence=report, waffle_windows=observation)
        row['counts'] = dict(Counter(r['disposition'] for r in row['rows']))
        row['remaining_batches'] = delivery.queue.partition([r for r in row['rows'] if r['disposition'] == 'unreviewed'])
        if progress: progress(dict(case=row['case'], stage='diecut-and-density-census-reviewed', counts=row['counts']))
    fresh.update(status='corrected-catalog-diecut-density-reviewed', predecessor=dict(path=PREVIOUS, sha256=PREVIOUS_SHA),
                 verification_mode='authenticated-baseline-plus-fresh-width-module-diecut-density')
    fresh['inputs'][PREVIOUS] = PREVIOUS_SHA; fresh['proofs']['diecut_density'] = proof
    for path in (Path(__file__), Path(checks.__file__), Path(density.__file__),
                 ROOT/'tests/test_sky130_diecut_absence.py', ROOT/'tests/test_sky130_waffle_windows.py'):
        fresh['source_files'][path.relative_to(ROOT).as_posix()] = delivery.sha(path)
    fresh['source_files'] = dict(sorted(fresh['source_files'].items()))
    fresh['scope'] += (' The die-cut census resolves 18 spacing records through an empty known operand. '
        'A fresh raw waffle-drop census confirms 48 previously retained absences without increasing executed coverage. '
        'Nonempty numerical density controls are separate from these reference decisions; full density acceptance remains unresolved.')
    fresh['retained_baseline']['execution'] += ' Die-cut and waffle-drop censuses also execute freshly.'
    return fresh


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--workspace', type=Path)
    parser.add_argument('--case', choices=delivery.queue.CASES); parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.write_bytes((json.dumps(build(args.workspace, args.case, lambda r: print(json.dumps(r), flush=True)),
                                      indent=2, ensure_ascii=False)+'\n').encode())
