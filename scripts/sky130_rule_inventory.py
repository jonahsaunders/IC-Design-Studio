"""Inventory pinned published SKY130 rules without mistaking mentions for coverage.

The output is a review ledger, not an acceptance report. Commented-out deck
statements remain visible and every manual row starts unresolved. Native runs,
applicability proofs, exceptions and negative controls must establish coverage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

REVISION = '7198cf647113f56041e02abf3eb623692820c5e1'
SOURCE_LOCK_SHA256 = '8025621eeab07f39b23c80e74096ff56281a883b299b1141ab6431ec98b2fab7'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manual_rows(data, source):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8'), newline=''))
    if reader.fieldnames != ['Name', 'Description', 'Flags', 'Value', 'Unit']:
        raise ValueError('Unexpected manual columns: ' + source)
    rows = []
    for index, row in enumerate(reader, 1):
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Incomplete manual row: ' + source)
        name = row['Name']
        if not re.fullmatch(r'\([^()]+\)', name) or not row['Description'].strip():
            raise ValueError('Unrecognized manual row: ' + source)
        # A record index, not a line number: quoted CSV descriptions span lines.
        rows.append(dict(id=f'{source}#{index}', source=source,
                         source_sha256=digest(data), record=index,
                         rule=name[1:-1], description=row['Description'],
                         flags=row['Flags'].split(), value=row['Value'], unit=row['Unit'],
                         disposition='unreviewed', coverage='unestablished',
                         candidates=[]))
    if not rows:
        raise ValueError('Empty manual section: ' + source)
    return rows


def deck_lines(data):
    text = data.decode('utf-8')
    if text.lstrip().startswith('<?xml'):
        text = ET.fromstring(text).findtext('text')
        if text is None:
            raise ValueError('Missing deck text')
    # No Ruby parsing or execution is claimed. These are search candidates.
    return [dict(line=i, comment=line.lstrip().startswith('#'), text=line)
            for i, line in enumerate(text.splitlines(), 1)]


def references(rule, data):
    if '-' in rule or '/' in rule or ' ' in rule:
        return []
    aliases = {rule}
    if rule.startswith('m') and re.match(r'm[1-5]\.', rule):
        aliases.add('met' + rule[1:])
    pattern = re.compile(r'(?<![A-Za-z0-9_.])(?:' + '|'.join(re.escape(a) for a in sorted(aliases)) +
                         r')(?![A-Za-z0-9_.])', re.I)
    return [line for line in deck_lines(data) if pattern.search(line['text'])]


def build(source_root, decks):
    source_root = Path(source_root)
    lock_data = (source_root / 'source-lock.json').read_bytes()
    if digest(lock_data) != SOURCE_LOCK_SHA256:
        raise ValueError('Unrecognized source lock')
    lock = json.loads(lock_data)
    if lock['revision'] != REVISION or lock['repository'] != 'google/skywater-pdk':
        raise ValueError('Unexpected upstream revision')
    captured = {}
    for name, identity in lock['files'].items():
        path = (source_root / name).resolve()
        if not path.is_relative_to(source_root.resolve()):
            raise ValueError('Source outside captured root')
        data = path.read_bytes()
        if digest(data) != identity['sha256']:
            raise ValueError('Changed upstream source: ' + name)
        captured[name] = data
    rows = []
    for name, data in sorted(captured.items()):
        if re.fullmatch(r'docs/rules/periphery/p\d{3}-.+\.csv', name):
            rows.extend(manual_rows(data, name))
    if len(rows) != 601:
        raise ValueError('Incomplete published periphery inventory')
    deck_data = {name: Path(path).read_bytes() for name, path in decks.items()}
    for row in rows:
        for name, data in deck_data.items():
            row['candidates'].extend(dict(deck=name, **hit) for hit in references(row['rule'], data))
    return dict(schema=1, status='coverage-review-required', qualified=False,
                scope='Published periphery rows; additional antenna, assumptions, connectivity and device rules remain separate mandatory review groups.',
                source_revision=REVISION, source_lock_sha256=digest(lock_data),
                source_files=lock['files'],
                decks={name: dict(sha256=digest(data),
                                 flags=[row for row in deck_lines(data) if re.search(
                                     r'\b(FEOL|BEOL|OFFGRID|SEAL|FLOATING_MET)\b', row['text'])])
                       for name, data in deck_data.items()},
                rule_rows=rows, counts=dict(manual_rows=len(rows), unreviewed=len(rows)),
                pending_groups=['periphery-row-reconciliation', 'density-interpretation-and-execution',
                                'antenna-all-etch-stages', 'connectivity-final-gds-lvs',
                                'criteria-and-assumptions', 'device-specific-and-chip-applicability'])


def validate_unreviewed(record):
    """Validate this initial inventory; it deliberately cannot accept a PDK."""
    if (record.get('schema') != 1 or record.get('status') != 'coverage-review-required' or
            record.get('qualified') is not False or record.get('source_revision') != REVISION or
            record.get('source_lock_sha256') != SOURCE_LOCK_SHA256):
        raise ValueError('Invalid source inventory scope')
    rows = record['rule_rows']
    if len(rows) != 601 or len({r['id'] for r in rows}) != 601:
        raise ValueError('Missing or duplicated source rows')
    for row in rows:
        if row['coverage'] != 'unestablished' or row['disposition'] != 'unreviewed':
            raise ValueError('Text references cannot establish executed rule coverage')
        if row['source_sha256'] != record['source_files'][row['source']]['sha256']:
            raise ValueError('Manual row source identity differs')
    return dict(status='inventory-consistent', manual_rows=len(rows), qualified=False,
                required_rule_coverage='unestablished')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--deck', action='append', required=True, help='NAME=PATH')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    pairs = [value.split('=', 1) for value in args.deck]
    if any(len(pair) != 2 for pair in pairs) or len({pair[0] for pair in pairs}) != len(pairs):
        parser.error('Use unique NAME=PATH deck arguments')
    inventory = build(args.source, dict(pairs))
    print(json.dumps(validate_unreviewed(inventory)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(inventory, indent=2) + '\n').encode())
