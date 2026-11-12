"""Audit native device matching and every encoded SKY130 boundary port.

KLayout combines names when independently declared ports share a physical net.
The complete group must match the independently flattened CDL, with each
expected alias present exactly once. Unknown names and unmatched pins fail.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from scripts.check_ihp_lvs import audit as native_audit


def port_groups_match(pairs, expected):
    wanted = [p.casefold() for p in expected]
    if not wanted or len(set(wanted)) != len(wanted):
        return False
    if any(re.fullmatch(r'n[0-9]{7}', p) is None for p in wanted):
        return False
    seen = []
    for pair in pairs:
        if pair['status'] != 'Match' or not pair['layout'] or not pair['reference']:
            return False
        left = pair['layout'].casefold().split(',')
        right = pair['reference'].casefold().split(',')
        if Counter(left) != Counter(right) or len(set(left)) != len(left):
            return False
        seen.extend(left)
    return Counter(seen) == Counter(wanted)


def audit(path, top, expected_ports):
    result = native_audit(path, top, expected_ports)
    ports = port_groups_match(result['port_pairs'], expected_ports)
    circuits = result['circuits']
    result['port_labels_match'] = ports
    result['matched'] = (
        len(circuits) == 1 and circuits[0]['status'] == 'Match' and
        circuits[0]['layout'].casefold() == top.casefold() and
        circuits[0]['reference'].casefold() == top.casefold() and ports and
        result['inventory']['layout']['devices'] == result['inventory']['reference']['devices'] and
        not any(e['blocks_match'] for e in result['extraction_log']))
    result['status'] = 'native-device-and-port-match' if result['matched'] else 'native-lvs-audit-failed'
    result['port_case_policy'] = (
        'Unique N plus seven-digit aliases; case-insensitive native graph-paired '
        'port groups must agree exactly and cover every declared port once.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--aliases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    aliases = json.loads(args.aliases.read_text(encoding='utf-8'))
    result = audit(args.report, aliases['top'], list(aliases['ports'].values()))
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({key: result[key] for key in ('status', 'matched', 'qualified')}))
    return 0 if result['matched'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
