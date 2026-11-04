"""Review only the eight window parameters of explicitly recommended rules.

An A flag alone is not an exemption. Each selected child names its exact RR
parent. Required RC metal/waffle-drop algorithms retain their original status.
Neither this source review nor raw metal occupancy establishes oxide density.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from scripts import sky130_geometry_reconciliation as geometry
from scripts import sky130_grid_geometry as grid
from scripts import check_sky130_filled_replay as replay
from scripts.sky130_rule_inventory import manual_rows

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/validation/sky130-density-scope-2026-10-14.json'
SECTIONS = (
    ('m1', 'p038-m1_dotdash', 11, 12, 13),
    ('m2', 'p040-m2_dotdash', 11, 12, 13),
    ('m3', 'p042-m3_dotdash', 13, 14, 15),
    ('m4', 'p044-m4_dotdash', 10, 11, 12),
)


def bindings(inventory):
    grid.source_metadata()
    capture = json.loads(grid.SOURCES.read_bytes())
    indexed = {row['id']: row for row in inventory['rule_rows']}
    result = {}
    # Bind the flag meaning to the complete captured upstream source, rather
    # than a local explanatory sentence that could change independently.
    with ZipFile(replay.BUNDLE) as archive:
        flags_raw = archive.read('sources/docs/rules/periphery-rules.rst')
    flags_sha = hashlib.sha256(flags_raw).hexdigest()
    expected = inventory['source_files']['docs/rules/periphery-rules.rst']['sha256']
    if flags_sha != expected:
        raise ValueError('Changed source flag definitions.')
    rr_section = flags_raw.decode().split('.. _RR:', 1)[1].split('.. _AL:', 1)[0]
    if 'Recommended rule at any IP level' not in rr_section:
        raise ValueError('RR no longer has its reviewed meaning.')
    for metal, section, parent_index, window_index, step_index in SECTIONS:
        source = 'docs/rules/periphery/' + section + '.csv'
        rows = {row['record']: row for row in manual_rows(capture['files'][source]['content'].encode(), source)}
        parent = rows[parent_index]
        if (parent['rule'] != metal + '.pd.1' or 'RR' not in parent['flags']
                or 'RC' in parent['flags'] or parent['value'] != '0.7'):
            raise ValueError('Changed advisory parent.')
        for index, suffix, description, value, unit in (
            (window_index, '2a', 'square regions of width and length equal to …', '700', 'µm'),
            (step_index, '2b', 'steps of …', '70', ''),
        ):
            child = rows[index]
            if (child['rule'] != metal + '.pd.' + suffix
                    or child['description'] != 'Rule ' + parent['rule'] + ' has to be checked by dividing the chip into ' + description
                    or child['flags'] != (['A', 'AL'] if metal == 'm1' else ['A'])
                    or child['value'] != value or child['unit'] != unit):
                raise ValueError('Changed explicit parent/parameter dependency.')
            for row in (parent, child):
                supplied = indexed[row['id']]
                if any(supplied.get(key) != row[key] for key in
                       ('rule', 'description', 'flags', 'value', 'unit', 'source', 'source_sha256', 'record')):
                    raise ValueError('Inventory differs from captured source bytes.')
            result[child['id']] = dict(parent=parent['id'], parent_rule=parent['rule'],
                rule=child['rule'], source_sha256=child['source_sha256'],
                parameter=dict(value=value, unit=unit), flags_definition_sha256=flags_sha,
                disposition='advisory',
                reason='This exact row specifies the measurement window of the named RR recommendation; it is not an independent required density threshold. The recommendation is not claimed executed.')
    return result


def apply(manual_rows, relations):
    rows = deepcopy(manual_rows)
    indexed = {row['id']: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError('Duplicate periphery rows.')
    for source_id, relation in relations.items():
        child = indexed[source_id]
        parent = indexed[relation['parent']]
        if (parent['disposition'] != 'advisory' or child['disposition'] != 'execution-review-required'
                or parent['rule'] != relation['parent_rule'] or child['rule'] != relation['rule']
                or child['source_sha256'] != relation['source_sha256']):
            raise ValueError('Source dependency would replace unrelated coverage.')
        child.update(disposition='advisory', reason=relation['reason'], source_dependency=deepcopy(relation))
    return rows


def build():
    base = geometry.build()
    inventory = json.loads((ROOT / geometry.previous.PERIPHERY).read_bytes())
    relations = bindings(inventory)
    checkpoint = json.loads((ROOT / geometry.previous.CHECKPOINT).read_bytes())
    historical = json.loads((ROOT / checkpoint['data']['path']).read_bytes())
    cases = []
    for old in historical:
        geometry.previous.validate_review(old, inventory)
        reviewed = next(row for row in base['cases'] if row['case'] == old['case'])
        rows = deepcopy(old['rows'])
        for row in rows:
            if row['id'] in reviewed['periphery_bindings']:
                row['disposition'] = 'executed-reviewed'
                row['execution_reconciliation'] = reviewed['periphery_bindings'][row['id']]
                row['reason'] = row['execution_reconciliation']['reason']
        if dict(Counter(row['disposition'] for row in rows)) != reviewed['periphery_counts']:
            raise ValueError('Earlier periphery reconciliation did not reproduce.')
        after = apply(rows, relations)
        cases.append(dict(case=old['case'], gds_sha256=old['gds_sha256'],
                          counts=dict(Counter(row['disposition'] for row in after)), rows=after,
                          error_counts=reviewed['counts']))
    source_paths = [Path(__file__), ROOT / 'tests/test_sky130_density_rule_scope.py', grid.SOURCES]
    return dict(schema=1, chunk=6, status='partial-source-scope-review', qualified=False, chunk_complete=False,
                execution_mode='source-dependency-reconciliation', bindings=relations, cases=cases,
                source_files={path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in source_paths},
                input_geometry=dict(path=geometry.OUTPUT.relative_to(ROOT).as_posix(),
                                    sha256=hashlib.sha256(geometry.OUTPUT.read_bytes()).hexdigest()),
                scope='Eight window/step parameters retain their exact RR parent recommendation scope. '
                      'All required RC metal-fill rows and all measured results are unchanged. '
                      'Fourteen periphery execution reviews, the x.20 definition, error reconciliation and final acceptance remain open. '
                      'No oxide-density metric, unknown step unit or edge policy is invented; density diagnostics remain BLOCKED.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    raw = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode()
    if args.check:
        if args.output.read_bytes() != raw:
            raise ValueError('Saved density scope differs from reviewed source.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    print(json.dumps(dict(status=report['status'], cases={row['case']: row['counts'] for row in report['cases']}, chunk_complete=False)))


if __name__ == '__main__':
    main()
