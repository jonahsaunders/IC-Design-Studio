"""Retain error-catalog rules that a periphery-only inventory can miss.

Error IDs are independent source records. An exact name match with a periphery
row is a navigation aid, never proof that a rule ran or applies to a design.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re

from scripts.sky130_rule_inventory import REVISION, SOURCE_LOCK_SHA256

ERRORS_SHA256 = 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed'


def parse(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8'), newline=''))
    if reader.fieldnames != ['ID', 'Name', 'Description']:
        raise ValueError('Unexpected SKY130 error catalog columns.')
    rows = []
    seen = set()
    for index, row in enumerate(reader, 1):
        if (None in row or any(not isinstance(v, str) or not v.strip() for v in row.values()) or
                not re.fullmatch(r'[rs]\d+', row['ID']) or row['ID'] in seen):
            raise ValueError('Missing, duplicate or malformed error catalog record.')
        seen.add(row['ID'])
        rows.append(dict(id=row['ID'], record=index, rule=row['Name'], description=row['Description']))
    if not rows:
        raise ValueError('Empty error catalog.')
    return rows


def build(data, periphery):
    if hashlib.sha256(data).hexdigest() != ERRORS_SHA256:
        raise ValueError('Unreviewed SKY130 error catalog source.')
    from scripts.sky130_rule_inventory import validate_unreviewed
    validate_unreviewed(periphery)
    rows = parse(data)
    assert len(rows) == 1556
    names = {}
    for row in periphery['rule_rows']:
        names.setdefault(row['rule'].removesuffix('.-'), []).append(row['id'])
    for row in rows:
        row.update(periphery_candidates=names.get(row['rule'], []),
                   disposition='unreviewed', coverage='unestablished')
    unmatched = sorted({r['rule'] for r in rows if not r['periphery_candidates']})
    return dict(schema=1, status='coverage-review-required', qualified=False,
                source_revision=REVISION, source_lock_sha256=SOURCE_LOCK_SHA256,
                source='docs/rules/errors.csv', source_sha256=ERRORS_SHA256,
                scope='Complete published error catalog, including dummy-fill, core and chip rules. '
                      'Applicability and execution must be reviewed separately; this is not acceptance.',
                rows=rows, counts=dict(error_records=len(rows), unreviewed=len(rows),
                                       unmatched_rule_names=len(unmatched)),
                unmatched_rule_names=unmatched)


def validate(record):
    if (record.get('schema') != 1 or record.get('status') != 'coverage-review-required' or
            record.get('qualified') is not False or record.get('source_revision') != REVISION or
            record.get('source_lock_sha256') != SOURCE_LOCK_SHA256 or
            record.get('source_sha256') != ERRORS_SHA256 or record.get('source') != 'docs/rules/errors.csv'):
        raise ValueError('Invalid SKY130 error inventory scope or identity.')
    rows = record['rows']
    if len(rows) != 1556 or len({r['id'] for r in rows}) != 1556:
        raise ValueError('Missing or duplicate error catalog records.')
    # Reconstruct the captured CSV semantic content in source order, then bind
    # its exact fields to the retained source hash via a canonical content hash.
    canonical = [[r['id'], r['rule'], r['description']] for r in rows]
    expected = '449db8e574b18f4f5eb00e2ad04bf2f24dc053196aa8bd32ac3cb5a86a4cccb7'
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if digest != expected:
        raise ValueError('Error catalog content or order changed.')
    for index, row in enumerate(rows, 1):
        if (row['record'] != index or row['coverage'] != 'unestablished' or
                row['disposition'] != 'unreviewed'):
            raise ValueError('Catalog text cannot establish executed coverage.')
    unmatched = sorted({r['rule'] for r in rows if not r['periphery_candidates']})
    if (record.get('unmatched_rule_names') != unmatched or
            record.get('counts') != dict(error_records=1556, unreviewed=1556,
                                         unmatched_rule_names=len(unmatched))):
        raise ValueError('Error catalog summary differs from its source rows.')
    return dict(status='inventory-consistent', error_records=len(rows), qualified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--periphery', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = build(args.source.read_bytes(), json.loads(args.periphery.read_text(encoding='utf-8')))
    print(json.dumps(validate(record)))
    args.output.write_bytes((json.dumps(record, indent=2, ensure_ascii=False)+'\n').encode())
