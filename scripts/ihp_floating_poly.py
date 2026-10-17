"""Identify native poly nodes that occur only in the extracted capacitor graph.

The benchmark circuit must contain every functional device and resistor.
Native ports, every device terminal and every resistor endpoint are protected.
Only zero-resistance singleton nodes on Magic's poly type are eligible.
"""
import math
from pathlib import Path
import shlex


def classify(ext_path, circuit_path, weights):
    nodes, connected = {}, set()
    for line in Path(ext_path).read_text().splitlines():
        t = shlex.split(line)
        if not t:
            continue
        if t[0] == 'port':
            connected.add(t[1])
        elif t[0] in ('node', 'substrate'):
            if len(t) < 7 or t[1] in nodes:
                raise ValueError('Native node inventory is incomplete or ambiguous.')
            nodes[t[1]] = t
    if nodes.keys() != weights.keys():
        raise ValueError('Native nodes and normalized resistance groups differ.')
    for line in Path(circuit_path).read_text().splitlines():
        t = line.split()
        if not t or t[0].startswith('*'):
            continue
        if t == ['.include', 'capacitance.spice']:
            continue
        if t[0].startswith('X'):
            if len(t) == 6 and t[3] == 'dantenna':
                connected.update(t[1:3])
            elif len(t) > 6 and t[5] in ('sg13_lv_nmos', 'sg13_lv_pmos'):
                connected.update(t[1:5])
            else:
                raise ValueError('Unknown physical device in the connection inventory.')
        elif t[0].startswith('R') and len(t) == 4 and math.isfinite(float(t[3])) and float(t[3]) > 0:
            connected.update(t[1:3])
        else:
            raise ValueError('Unsupported benchmark circuit record; do not omit a physical connection.')
    physical = {n for group in weights.values() for n in group}
    if not connected <= physical:
        raise ValueError('A physical connection is absent from the resistance graph.')
    selected = []
    for name, group in weights.items():
        if name.startswith('FILL') or set(group) & connected:
            continue
        t = nodes[name]
        if t[0] != 'node' or t[6] != 'p' or float(t[2]) != 0 or group != {name: 1.}:
            raise ValueError('Unconnected node is not a verified capacitor-only poly singleton.')
        selected.append(name)
    return dict(nodes=sorted(selected), connected_nodes=sorted(connected),
                scope='Native capacitor-only poly; no device terminal, resistor endpoint or port removed.')
