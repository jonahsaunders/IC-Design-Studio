"""Require native transistor comparison AND complete, correctly named ports.

The native graph matcher may accept unpaired or permuted pins. A successful
process exit or 'Netlists match' message is not this reference's acceptance.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def port_match(pairs, expected):
    wanted = {p.casefold() for p in expected}
    return (bool(wanted) and len(wanted) == len(expected) == len(pairs) and
            all(p['status'] == 'Match' and p['layout'] and p['reference'] and
                p['layout'].casefold() == p['reference'].casefold() for p in pairs) and
            {p['layout'].casefold() for p in pairs if p['layout']} == wanted)


def audit(path, top, expected_ports):
    import klayout.db as k
    path = Path(path); db = k.LayoutVsSchematic(); db.read(str(path))
    xref = db.xref()
    if xref is None:
        raise ValueError('Missing native schematic comparison.')
    circuits = [dict(layout=p.first().name if p.first() else None,
                     reference=p.second().name if p.second() else None, status=str(p.status()))
                for p in xref.each_circuit_pair()]
    ctop = db.netlist().circuit_by_name(top)
    if ctop is None:
        raise ValueError('Expected top circuit was not extracted.')
    pins = [dict(layout=p.first().name() if p.first() else None,
                 reference=p.second().name() if p.second() else None, status=str(p.status()))
            for p in xref.each_pin_pair(ctop)]
    logs = [dict(severity=str(e.severity), category=e.category_name, message=e.message,
                 cell=e.cell_name, blocks_match=e.severity != k.LogEntryData.Info) for e in db.each_log_entry()]
    matched = (bool(circuits) and all(c['status'] == 'Match' for c in circuits) and
               port_match(pins, expected_ports) and not any(e['blocks_match'] for e in logs))
    inventory = {}
    for label, netlist in [('layout', db.netlist()), ('reference', db.reference)]:
        flat = netlist.dup(); flat.flatten(); cell = flat.top_circuit()
        if cell is None:
            raise ValueError('Incomplete flattened transistor inventory.')
        inventory[label] = dict(devices=dict(Counter(d.device_class().name.casefold() for d in cell.each_device())),
                                pins=sorted(p.name().casefold() for p in cell.each_pin()))
    return dict(schema=1, status='native-device-and-port-match' if matched else 'native-lvs-audit-failed',
                matched=matched, qualified=False, report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                top=top, circuits=circuits, extraction_log=logs, port_pairs=pins,
                port_labels_match=port_match(pins, expected_ports), expected_ports=sorted(expected_ports),
                port_case_policy='Native SPICE reader uppercases names; require unique case-insensitive graph-paired port names.',
                inventory=inventory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--aliases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); aliases = json.loads(args.aliases.read_text(encoding='utf-8'))
    result = audit(args.report, aliases['top'], list(aliases['ports'].values()))
    result['aliases_sha256'] = hashlib.sha256(args.aliases.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({key: result[key] for key in ('status', 'matched', 'qualified')}))
    return 0 if result['matched'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
