"""Bind experimental wire resistance to the pinned nominal Magic material.

OpenRCX's minimum-width table resistance is not a width-aware wire model. Its
LEF-resistance mode is, but a routed database can contain layer-R overrides.
Explicitly bind all seven sheet values before using that mode. This does not
qualify capacitance, vias, other extraction corners or the production flow.
"""
import hashlib
import math
from pathlib import Path
import re

SOURCE_SHA256 = '1b57f6763dfd4d1ad3c6a897883bf1f62ffe91031a97765a0666bfaf2012be68'
LAYERS = ('Metal1', 'Metal2', 'Metal3', 'Metal4', 'Metal5', 'TopMetal1', 'TopMetal2')


def nominal_sheets(text):
    """Read only the explicitly selected nominal/lvs variant, in ohms/square."""
    active = False
    found = {}
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if line.startswith('variants '):
            active = line == 'variants (),(lvs)'
            continue
        if not active:
            continue
        match = re.fullmatch(r'resist\s+\(allm([1-7])\)/metal([1-7])\s+([0-9.]+)', line)
        if match:
            a, b, value = match.groups()
            if a != b or a in found:
                raise ValueError('Ambiguous nominal metal resistance.')
            value = float(value)/1000
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid nominal sheet resistance.')
            found[a] = value
        elif line.startswith('resist (allm'):
            raise ValueError('Unsupported nominal metal resistance statement.')
    if set(found) != set('1234567'):
        raise ValueError('Incomplete nominal seven-metal material.')
    return {layer: found[str(i)] for i, layer in enumerate(LAYERS, 1)}


def read(path):
    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError('The nominal IHP material source differs from the pinned revision.')
    return dict(schema=1, source_sha256=digest, extraction_style='ngspice()',
                sheet_ohms=nominal_sheets(data.decode('utf-8')))


def apply(dbtech, material):
    """Replace routing overrides; return their original values for the evidence."""
    expected = dict(zip(LAYERS, (.110, .088, .088, .088, .088, .018, .011)))
    if (material.get('schema') != 1 or material.get('source_sha256') != SOURCE_SHA256
            or material.get('extraction_style') != 'ngspice()'
            or material.get('sheet_ohms') != expected):
        raise ValueError('An exact pinned nominal material profile is required.')
    # Validate the entire stack before modifying any layer.
    layers = {name: dbtech.findLayer(name) for name in LAYERS}
    if any(layer is None for layer in layers.values()):
        raise ValueError('Missing IHP routing layer.')
    previous = {name: layer.getResistance() for name, layer in layers.items()}
    for name, layer in layers.items():
        layer.setResistance(expected[name])
        if not math.isclose(layer.getResistance(), expected[name], rel_tol=1e-12, abs_tol=0):
            raise ValueError('Native sheet-resistance assignment did not persist.')
    return dict(schema=1, qualified=False, material=material, previous_sheet_ohms=previous,
                required_extraction_option='-lef_res',
                scope='Nominal metal-wire sheet resistance only; no capacitance, via or corner acceptance.')
