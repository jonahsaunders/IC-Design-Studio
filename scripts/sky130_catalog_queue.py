"""Reconstruct retained SKY130 decisions once and group the remaining work.

This is a planning index, not a physical check or an applicability decision.
It imports no geometry engines and does not rerun historical extractions. Each
prior result is authenticated and its decisions/counts are replayed in order.
Grouping never changes a record's coverage or moves it to a later chunk.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from scripts.sky130_rule_errors import validate as validate_catalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'docs/qualification/sky130-error-rule-inventory.json'
PREFIX = 'docs/validation/sky130-'
CHECKPOINT = PREFIX + 'selected-subjects-2026-10-14.json'
CHECKPOINT_SHA256 = '9757823897dcc17028442528caf1e32ba6a37292e33fe168e8bcebed88187719'
OUTPUT = ROOT / 'docs/validation/sky130-catalog-work-queue-2026-10-15.json'
STAGES = ('geometry-reconciliation', 'nsm-reconciliation', 'marker-reconciliation',
          'waffle-density', 'esd-fuse', 'device-intent', 'selected-subjects')
CASES = ('counter', 'uart', 'apb')

# These ranges partition the already authenticated open records for scheduling
# only. A matching range, name or description cannot establish rule coverage.
BATCHES = (
    ('local_geometry', 'Local geometry and resistor/pad selectors',
     ((436,439),(522,522),(528,530),(534,534),(774,774),(899,900),(1039,1039),(1046,1046)), (),
     'Bind exact catalog operands to existing geometry or absence evidence; resolve URPM construction separately.'),
    ('voltage', 'Marked high-voltage geometry', ((496,496),(1164,1178)), (),
     'Bind catalog operands to the reviewed nominal contract, raw HV selectors and label census; preserve electrical tagging obligations.'),
    ('grid', 'Coordinate grids and layer aliases', ((0,112),(150,157)), (),
     'Separate drawn vertices, text anchors and generated-mask purposes; resolve unit and metop alias meanings before accepting the existing diagnostics.'),
    ('device_selection', 'Device identification and RF geometry',
     ((391,391),(396,396),(453,453),(537,705),(908,908),(922,926),(928,946),(1047,1047),(1059,1061)), (),
     'Resolve each device selector and standard-cell exemption. RF map/Table H5 remain explicit dependencies; cell-name absence alone cannot resolve device recognition.'),
    ('core_generated', 'Core context and generated implant masks',
     ((258,258),(411,411),(416,416),(429,435),(444,450),(461,461),(471,474),(477,477),
      (487,490),(513,513),(520,521),(535,536),(753,754),(760,762),(765,765),(775,776),
      (785,786),(799,799),(827,828),(1024,1038),(1132,1132),(1473,1497)), (),
     'Establish COREID and generated-mask construction/enclosure. Empty drawn masks are not evidence that their enclosed targets are absent.'),
    ('module', 'Module cut and selected boundary rules', ((261,330),(378,378),(380,380),(927,927)), (),
     'Define moduleCutAREA and q0/q1 subjects, then prove applicability or execute spacing/enclosure; an absent enclosing region is not sufficient.'),
    ('frame_scribe', 'Frame, seal, scribe and alignment marks',
     ((379,379),(381,390),(392,392),(988,1023),(1076,1131),(1376,1472)), (),
     'Establish explicit frame/die-cut, seal and alignment context, including exemptions. Do not substitute a block bounding box for chip boundaries.'),
    ('pad_via', 'Pads, package geometry and ViaTop', ((836,845),(1208,1209),(1312,1375)), (),
     'Resolve ViaTop and pad construction, then bind each required geometry/connectivity check or prove its selected subject absent.'),
    ('density_fill', 'VPP, dummy diffusion and density', ((1133,1154),(1256,1272)), ((8,8),),
     'Resolve VPP cell selection, dummy diffusion and density window/operand semantics; retain the separate wider density obligations beyond these catalog records.'),
    ('connectivity', 'Connectivity, redundancy and chip labels', ((1207,1207),), ((0,7),(9,43),(72,73)),
     'Review chip-context records separately from block checks; bind physical graphs, labels, redundant contacts and interface regions to their exact scope.'),
    ('routing_boundary', 'Routing blockages and boundary purposes', ((1234,1255),), ((68,71),),
     'Resolve Block/Routing operands and forbidden boundary purposes, including the distinct r/s records; do not inherit coverage from a shared name.'),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RetainedReader:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.digests = {}
        self.records = {}

    def read(self, name, expected=None):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Retained input escapes the repository.')
        if name not in self.records:
            data = path.read_bytes()
            self.digests[name] = sha(data)
            self.records[name] = json.loads(data)
        if expected is not None and self.digests[name] != expected:
            raise ValueError('Changed retained input: ' + name)
        return self.records[name]


def validate_rows(rows, catalog):
    if len(rows) != len(catalog['rows']) or any(
        any(row.get(key) != original[key] for key in ('id', 'rule', 'record'))
        for row, original in zip(rows, catalog['rows'])
    ):
        raise ValueError('Missing, reordered, duplicate or changed catalog record.')


def apply_decisions(rows, decisions, catalog):
    result = deepcopy(rows)
    indexed = {row['id']: row for row in result}
    for decision in decisions:
        row = indexed.get(decision['id'])
        if row is None or row['disposition'] != 'unreviewed':
            raise ValueError('Unknown or overlapping retained decision.')
        if decision['disposition'] not in ('executed-reviewed', 'absent-operand'):
            raise ValueError('Unexpected retained disposition.')
        row.update(decision)
    validate_rows(result, catalog)
    return result


def reconstruct(reader):
    checkpoint = reader.read(CHECKPOINT, CHECKPOINT_SHA256)
    # The pinned checkpoint authenticates every stage below. Validate their
    # direct dependencies as well without importing their expensive build().
    for name, digest in checkpoint['inputs'].items():
        reader.read(name, digest)
    catalog = reader.read(CATALOG)
    validate_catalog(catalog)
    stages = []
    for stage in STAGES:
        data = reader.read(PREFIX + stage + '-2026-10-14.json')
        if data['qualified'] is not False or data['chunk_complete'] is not False:
            raise ValueError('Retained checkpoint unexpectedly claims qualification.')
        for name, digest in data.get('inputs', {}).items():
            reader.read(name, digest)
        if 'predecessor' in data:
            reader.read(data['predecessor']['path'], data['predecessor']['sha256'])
        if tuple(c['case'] for c in data['cases']) != CASES:
            raise ValueError('Changed retained reference case set/order.')
        stages.append(data)
    cases = []
    for index, name in enumerate(CASES):
        expected_gds = checkpoint['cases'][index]['gds_sha256']
        rows = deepcopy(stages[0]['cases'][index]['rows'])
        validate_rows(rows, catalog)
        for stage, data in zip(STAGES, stages):
            case = data['cases'][index]
            identity = case.get('gds_sha256', case.get('execution', {}).get(
                'gds_sha256', case.get('measurement', {}).get('gds_sha256')))
            if identity != expected_gds:
                raise ValueError('Retained decisions refer to a different layout.')
            if stage == 'device-intent':
                decisions = [dict(id=r['error_id'], disposition=r['decision']['disposition'])
                             for r in case['new_decisions']]
            else:
                decisions = case.get('new_error_decisions', [])
            rows = apply_decisions(rows, decisions, catalog)
            counts = dict(Counter(r['disposition'] for r in rows))
            if counts != case.get('error_counts', case.get('counts')):
                raise ValueError('Retained stage counts do not reconstruct: ' + stage)
        cases.append(dict(case=name, gds_sha256=expected_gds, counts=counts, rows=rows))
    return catalog, cases


def partition(open_rows, batches=BATCHES):
    result = [dict(id=b[0], title=b[1], next_action=b[4], records=[]) for b in batches]
    if len({b[0] for b in batches}) != len(batches):
        raise ValueError('Duplicate work batch.')
    seen = set()
    for row in open_rows:
        if row['disposition'] != 'unreviewed' or row['id'] in seen:
            raise ValueError('Queue accepts each unreviewed record exactly once.')
        seen.add(row['id'])
        kind, number = row['id'][0], int(row['id'][1:])
        matches = [i for i, batch in enumerate(batches)
                   if any(lo <= number <= hi for lo, hi in batch[2 if kind == 'r' else 3])]
        if kind not in ('r', 's') or len(matches) != 1:
            raise ValueError('Unassigned or multiply assigned open record: ' + row['id'])
        result[matches[0]]['records'].append({key: row[key] for key in ('id', 'rule', 'record', 'disposition')})
    for batch in result:
        batch['count'] = len(batch['records'])
    return result


def build(root=ROOT):
    reader = RetainedReader(root)
    catalog, cases = reconstruct(reader)
    batches = None
    for case in cases:
        current = partition([r for r in case['rows'] if r['disposition'] == 'unreviewed'])
        if batches is not None and current != batches:
            raise ValueError('Reference work queues differ; retain separate case queues.')
        batches = current
    return dict(schema=1, chunk=6, status='planning-only', qualified=False, chunk_complete=False,
                new_coverage_decisions=0,
                scope='Authenticated retained results, not reexecuted checks. Every queued record remains unreviewed. '
                      'Batches are scheduling groups, not applicability decisions, completion percentages or later-chunk exemptions. '
                      'The separate periphery, density and application obligations still apply.',
                checkpoint=dict(path=CHECKPOINT, sha256=CHECKPOINT_SHA256),
                inputs=dict(sorted(reader.digests.items())), generator_sha256=sha(Path(__file__).read_bytes()),
                cases=[{key: c[key] for key in ('case', 'gds_sha256', 'counts')} for c in cases],
                catalog_records=len(catalog['rows']), queued_records=sum(b['count'] for b in batches),
                batches=batches)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = build()
    content = (json.dumps(result, indent=2, ensure_ascii=False) + '\n').encode()
    if args.check:
        if args.output.read_bytes() != content:
            raise ValueError('Saved work queue differs from the retained decisions.')
    else:
        args.output.write_bytes(content)
    print(json.dumps(dict(status=result['status'], new_coverage_decisions=0,
                          queued_records=result['queued_records'],
                          batches={b['id']: b['count'] for b in result['batches']})))


if __name__ == '__main__':
    main()
