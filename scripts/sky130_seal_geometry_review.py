"""Replay the complete reference catalog with explicit seal origin and width checks."""
import argparse, csv, io, json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from icstudio import digital_sky130_seal_geometry as checks
from scripts import sky130_scribe_bound_review as previous_review

delivery = previous_review.delivery
ROOT = delivery.ROOT
PREVIOUS = 'docs/validation/sky130-scribe-bounds-2026-10-15.json'
PREVIOUS_SHA = '6441b56f326d523327eb6669c0ca3e5a20715a1900552d7e6a71fd13ae488f06'
OUTPUT = ROOT/'docs/validation/sky130-seal-geometry-2026-10-15.json'


def source_proof(folder, catalog):
    raw = {key: delivery.checked(Path(folder)/key, digest) for key, digest in checks.SOURCE['files'].items()}
    def rows(key): return list(csv.DictReader(io.StringIO(raw[key].decode())))
    layers = rows('docs/rules/gds_layers.csv')
    found = [r for r in layers if r['Layer name'] == 'areaid.sl' and r['Description'] == 'Seal ring identifier']
    delivery.require(len(found) == 1 and found[0]['GDS layer:datatype'] == '81:1' and found[0]['Purpose'] == 'identifier',
                     'Changed SKY130 seal drawing purpose.')
    delivery.require('areaid.sl{81:1},areaid sealring,areaid.sea,The area of the Seal ring,Tech,' in
                     raw['docs/rules/layers/table-c4b-layer-description.csv'].decode(), 'Changed SKY130 seal alias.')
    manual = rows('docs/rules/periphery/p018-x_dotdash.csv')
    origin = [r for r in manual if r['Name'] == '(x.19)']
    width = [r for r in manual if r['Name'] == '(x.28)']
    delivery.require(len(origin) == len(width) == 1 and origin[0]['Description'] ==
        'Lower left corner of the seal ring should be at origin i.e (0,0)' and width[0]['Value'] == 'N/A',
        'Changed SKY130 seal manual definition.')
    errors = {r['ID']: r for r in rows('docs/rules/errors.csv')}
    indexed = {r['id']: r for r in catalog['rows']}
    literals = {'r379': ('x.19', 'SEAL ring is not at origin (0,0)'), 'r392': ('x.28', '6 min. width of SEALID')}
    for key, literal in literals.items():
        delivery.require((indexed[key]['rule'], indexed[key]['description']) == literal and
                         (errors[key]['Name'], errors[key]['Description']) == literal, 'Changed literal SKY130 seal rule.')
    return dict(source=checks.SOURCE, layer=found[0], manual=origin+width,
                bindings={key: dict(catalog=indexed[key], check=check) for key, check in checks.CHECKS.items()},
                interpretation=checks.SCOPE,
                unresolved='No seal presence/completeness requirement is discharged. Multiple components need origin context; advanced-seal diffusion overlap r390 remains unreviewed.')


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
                         'Fresh corrected replay differs from the scribe baseline.')
        path = workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        report = checks.audit(path); checks.evaluate(report, row['gds_sha256'], row['top'])
        delivery.require(all(r['disposition'] == 'absent-operand' for r in report['rows']), 'Reference seal geometry changed.')
        row['rows'] = delivery.apply_rows(row['rows'], report['rows'], catalog, 'seal_geometry', row['provenance'])
        row['counts'] = dict(Counter(r['disposition'] for r in row['rows']))
        row['measurements']['seal_geometry'] = report
        row['remaining_batches'] = delivery.queue.partition([r for r in row['rows'] if r['disposition'] == 'unreviewed'])
        if progress: progress(dict(case=row['case'], stage='seal-geometry-replayed', counts=row['counts']))
    fresh.update(status='corrected-catalog-seal-geometry-reviewed', predecessor=dict(path=PREVIOUS, sha256=PREVIOUS_SHA))
    fresh['proofs']['seal_geometry'] = proof
    for path in (Path(__file__), Path(checks.__file__), ROOT/'tests/test_sky130_seal_geometry.py'):
        fresh['source_files'][path.relative_to(ROOT).as_posix()] = delivery.sha(path)
    fresh['source_files'] = dict(sorted(fresh['source_files'].items()))
    fresh['scope'] += ' Seal origin and 6 um width are now checked on the explicit drawing purpose. Reference seal targets are absent; this does not qualify complete-chip boundaries.'
    return fresh


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--workspace', type=Path)
    p.add_argument('--case', choices=delivery.queue.CASES); p.add_argument('--output', type=Path, default=OUTPUT)
    p.add_argument('--check', action='store_true'); a = p.parse_args()
    raw = (json.dumps(build(a.workspace, a.case, lambda r: print(json.dumps(r), flush=True)), indent=2, ensure_ascii=False)+'\n').encode()
    if a.check: delivery.require(a.output.read_bytes() == raw, 'Saved seal review differs from fresh execution.')
    else: a.output.write_bytes(raw)
