"""Retain the public four-terminal IHP varactor in physical comparison.

The public KLayout writer emits C records with G1/W/G2/SUB, rather than
ordinary two-terminal SPICE capacitors. Convert only that reviewed interface.
"""
import math
import re
from pathlib import Path

from .model import scalar, file_digest

MODEL = 'sg13_hv_svaricap'


def recognition_label(layer, datatype, text):
    return (layer, datatype) == (63, 0) and text.casefold() == 'svaricap'


def recognition_inventory(source, top):
    import klayout.db as k
    ly = k.Layout(); ly.read(str(source)); cell = ly.cell(top)
    if cell is None or any(cell.each_inst()):
        raise ValueError('IHP varactor checking needs the flattened physical stream.')
    index = ly.find_layer(63, 0)
    return [dict(text=s.text.string, x=s.text.x, y=s.text.y)
            for s in cell.shapes(index).each() if s.is_text() and recognition_label(63, 0, s.text.string)] if index is not None else []


def extractor_connections(destination):
    """Recognition text must not short distinct devices after flattening."""
    relative = 'rule_decks/cap_connections.lvs'
    path = Path(destination)/relative
    expected = 'adba1f9e036ec47b6f431615c1538073aafbab51087ba57dee6b0080699face6'
    original = b'connect(varicap_ports, text_drw)'
    content = path.read_bytes()
    if file_digest(path) != expected or content.count(original) != 1:
        raise ValueError('Unexpected public IHP varactor connection source.')
    path.write_bytes(content.replace(original, b'# IC Design Studio: SVaricap is device recognition, not an electrical net.\n# Actual conductor labels and contact/metal connectivity establish the ports.'))
    return dict(path=relative, source_sha256=expected, sha256=file_digest(path),
                change='Keep SVaricap recognition without making equal annotation strings global electrical nets. Contact and conductor connectivity unchanged.')


def geometry(text):
    lines = re.sub(r'\n[ \t]*\+[ \t]*', ' ', text).splitlines()
    changes = []
    for i, line in enumerate(lines):
        row = line.split()
        if not row or row[0].startswith(('*', '.')):
            continue
        j = next((n for n, token in enumerate(row) if '=' in token), len(row)) - 1
        if row[j].casefold() != MODEL:
            continue
        if row[0][0].upper() not in ('C', 'X') or j != 5:
            raise ValueError('IHP varactor LVS must retain G1, W, G2 and substrate terminals.')
        values = {}
        for token in row[j+1:]:
            parts = token.split('=', 1)
            if len(parts) != 2 or parts[0].lower() in values:
                raise ValueError('Duplicate or unresolved IHP varactor LVS parameter.')
            key, raw = parts[0].lower(), parts[1]
            value = scalar(raw)
            if not math.isfinite(value) or value <= 0:
                raise ValueError('IHP varactor dimensions and counts must be positive and finite.')
            values[key] = (value, raw)
        if not {'w', 'l'} <= values.keys() or values.keys() - {'w', 'l', 'nx', 'm'}:
            raise ValueError('IHP varactor LVS requires W/L and supports Nx/M; unreviewed parameters cannot be discarded.')
        for key in ('nx', 'm'):
            values.setdefault(key, (1., '1'))
            if not values[key][0].is_integer():
                raise ValueError('IHP varactor Nx and multiplicity must be integers.')
        name = row[0] if row[0][0].upper() == 'X' else 'XICSTUDIO_VAR_' + row[0]
        lines[i] = ' '.join([name, *row[1:j], MODEL,
                             *(key+'='+values[key][1] for key in ('w', 'l', 'nx', 'm'))])
        changes.append(dict(instance=row[0], replacement=name, model=MODEL, terminal_count=4,
                            original=line, comparison=lines[i],
                            reason='Retain the public G1/W/G2/SUB and W/L/Nx/M interface; no two-terminal capacitor reduction.'))
    if not changes:
        return text, []
    from .ihp_tap_lvs import _names
    _names(lines)
    return '\n'.join(lines)+'\n', changes
