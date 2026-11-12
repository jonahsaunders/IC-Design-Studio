"""Reconcile four executed VPP geometry checks on exact retained references."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_vpp as vpp
from scripts import sky130_label_subject_review as labels
from scripts import sky130_catalog_queue as queue
from scripts import check_sky130_filled_replay as fixture

ROOT = queue.ROOT
PREVIOUS = 'docs/validation/sky130-label-subjects-2026-10-15.json'
PREVIOUS_SHA = '346291eb600c055674d5ed305de2109249b590ebcddb58aa388761591f66e495'
OUTPUT = ROOT/'docs/validation/sky130-vpp-geometry-2026-10-15.json'
DESCRIPTIONS = {'r1145': '1.43 min. width of capacitor',
                'r1151': 'capacitor must not straddle nwell',
                'r1152': 'capacitor must not straddle dnwell',
                'r1153': '1.5 min. enclosure of capacitor by nwell'}


def source_proof(source, catalog):
    raw = {name: (Path(source)/name).read_bytes() for name in vpp.SOURCE['files']}
    for name, digest in vpp.SOURCE['files'].items():
        if queue.sha(raw[name]) != digest:
            raise ValueError('Changed VPP primary source: '+name)
    indexed = {r['id']: r for r in catalog['rows']}
    for key, text in DESCRIPTIONS.items():
        if indexed[key]['rule'] != vpp.CHECKS[key] or indexed[key]['description'] != text:
            raise ValueError('Changed VPP catalog binding: '+key)
    rows = {r['Name']: r for r in csv.DictReader(io.StringIO(raw['docs/rules/periphery/p037-vpp_dotdash.csv'].decode()))}
    for rule, text, value, unit in (
        ('vpp.1', 'Min width of capacitor:dg', '1.430', 'µm'),
        ('vpp.4', 'capacitor:dg must not straddle (nwell or dnwell)', '', ''),
        ('vpp.8', 'Min enclosure of capacitor:dg by nwell', '1.500', 'µm')):
        if [rows['('+rule+')'][key] for key in ('Description', 'Value', 'Unit')] != [text, value, unit]:
            raise ValueError('Changed selected VPP rule.')
    layers = list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    for name, pair in vpp.LAYERS.items():
        matches = [r['GDS layer:datatype'] for r in layers if r['Layer name'] == name and 'drawing' in r['Purpose'].split(', ')]
        if matches != ['%s:%s' % pair]:
            raise ValueError('Changed VPP operand purpose.')
    return dict(source=vpp.SOURCE, bindings={key: indexed[key] for key in vpp.CHECKS},
                selected_parents={rule: rows['('+rule+')'] for rule in sorted(set(vpp.CHECKS.values()))},
                density_parents={rule: rows['('+rule+')'] for rule in ('vpp.5a', 'vpp.5b', 'vpp.5c', 'vpp.11')},
                interpretation='Execute minimum width and well-straddling checks; measure enclosure where capacitor overlaps nwell. Outside-nwell capacitor context stays unreviewed, never exempt by missing enclosure. Density ratios remain observations; unfinished special-cell selectors are not inferred.')


def build(workspace=None):
    workspace = Path(workspace or ROOT.parents[1]); reader = queue.RetainedReader()
    catalog, baselines, _ = labels.reconstruct(reader)
    previous = reader.read(PREVIOUS, PREVIOUS_SHA)
    for name, digest in previous['inputs'].items(): reader.read(name, digest)
    cases, batches = [], None
    with TemporaryDirectory() as td:
        folder = Path(td)/'inputs'; manifest = fixture.unpack(fixture.BUNDLE, folder)
        proof = source_proof(folder/'sources', catalog)
        for entry in manifest['cases']:
            name = entry['case']; before = next(c for c in baselines if c['case'] == name)
            prior = next(c for c in previous['cases'] if c['case'] == name)
            if not before['gds_sha256'] == prior['original_gds_sha256'] == entry['gds_sha256']:
                raise ValueError('Changed original VPP reference identity.')
            rows = queue.apply_decisions(before['rows'], prior['original_new_error_decisions'], catalog)
            if dict(Counter(r['disposition'] for r in rows)) != prior['original_error_counts']:
                raise ValueError('Label-subject baseline does not reconstruct.')
            original = vpp.audit(folder/entry['gds'])
            corrected = vpp.audit(workspace/'outputs/sky130-application-boundary-v1/linux'/name/'sky130-pin-export/final.gds')
            if corrected['gds_sha256'] != prior['corrected_gds_sha256']:
                raise ValueError('Changed corrected VPP reference identity.')
            for report in (original, corrected):
                vpp.evaluate(report, report['gds_sha256'], report['top'])
                if any(r['disposition'] != 'absent-operand' for r in report['rows']):
                    raise ValueError('Reference unexpectedly has VPP targets.')
            if original['measurements'] != corrected['measurements']:
                raise ValueError('VPP operands changed during boundary correction.')
            rows = queue.apply_decisions(rows, original['rows'], catalog)
            current = queue.partition([r for r in rows if r['disposition'] == 'unreviewed'])
            if batches is not None and batches != current: raise ValueError('VPP reference queues differ.')
            batches = current
            cases.append(dict(case=name, original_gds_sha256=entry['gds_sha256'], original_measurement=original,
                original_new_error_decisions=original['rows'], original_error_counts=dict(Counter(r['disposition'] for r in rows)),
                corrected_gds_sha256=corrected['gds_sha256'], corrected_vpp_geometry=corrected))
    paths = [Path(__file__), Path(vpp.__file__), ROOT/'tests/test_sky130_vpp.py',
             ROOT/'icstudio/digital_sky130_rules.py', ROOT/'icstudio/digital_sky130_rule_worker.py',
             ROOT/'tests/test_sky130_application_rules.py']
    return dict(schema=1, chunk=6, status='selected-vpp-geometry-verified', qualified=False, chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())), source_files={p.relative_to(ROOT).as_posix(): queue.sha(p.read_bytes()) for p in paths},
        proof=proof, cases=cases, remaining_original_batches=[dict(id=b['id'], count=b['count'], ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Four selected VPP geometry checks execute; capacitor targets are absent in these references. Nonempty numerical fault controls are separate. Outside-nwell enclosure context and density acceptance remain unreviewed. The original catalog retains 573 unreviewed records; full historical decisions remain source-specific.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--workspace', type=Path)
    p.add_argument('--output', type=Path, default=OUTPUT); p.add_argument('--check', action='store_true'); a = p.parse_args()
    raw = (json.dumps(build(a.workspace), indent=2, ensure_ascii=False)+'\n').encode()
    if a.check:
        if a.output.read_bytes() != raw: raise ValueError('Saved VPP review differs.')
    else: a.output.write_bytes(raw)
    print(json.dumps({c['case']: c['original_error_counts'] for c in json.loads(raw)['cases']}))
