"""Reject fill widths absent from any applicable nominal OpenRCX table.

Width presence is a necessary coverage check, not model accuracy acceptance.
Native response and independent reference comparisons remain separate gates.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

LAYERS = ('Metal1', 'Metal2', 'Metal3', 'Metal4', 'Metal5', 'TopMetal1', 'TopMetal2')
KINDS = ('RESOVER', 'OVER', 'UNDER', 'DIAGUNDER', 'OVERUNDER')


def tables(text):
    result = {}
    lines = text.splitlines()
    if len(re.findall(r'^DensityModel \d+\s*$', text, re.M)) != 1:
        raise ValueError('Use one explicitly captured nominal density model.')
    for index, line in enumerate(lines):
        match = re.fullmatch(r'Metal ([1-7]) ('+'|'.join(KINDS)+')', line.strip())
        if not match:
            continue
        key = (LAYERS[int(match[1])-1], match[2])
        if key in result or index+1 >= len(lines):
            raise ValueError('Repeated or incomplete width table.')
        header = re.fullmatch(r'WIDTH Table (\d+) entries:\s*(.*)', lines[index+1].strip())
        if not header:
            raise ValueError('Missing width-table header.')
        try:
            values = [Decimal(v)*1000 for v in header[2].split()]
        except InvalidOperation as exc:
            raise ValueError('Invalid tabulated width.') from exc
        if len(values) != int(header[1]) or any(not v.is_finite() or v <= 0 for v in values):
            raise ValueError('Width count or value is invalid.')
        if values != sorted(set(values)):
            raise ValueError('Widths must be unique and ordered.')
        result[key] = values
    expected = {(layer, kind) for layer in LAYERS for kind in KINDS
                if not (layer in ('Metal1', 'TopMetal2') and kind == 'OVERUNDER')}
    if set(result) != expected:
        raise ValueError('Missing or unsupported nominal metal tables.')
    for (layer, kind), values in result.items():
        empty = layer == 'TopMetal2' and kind in ('UNDER', 'DIAGUNDER')
        if bool(values) == empty:
            raise ValueError('Unexpected empty or populated metal table.')
    return result


def coverage(text, rectangles):
    available = tables(text)
    widths = {layer: set() for layer in LAYERS}
    for item in rectangles:
        if item['layer'] not in widths:
            raise ValueError('Unknown fill metal.')
        box = item['box_nm']
        if len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError('Fill rectangles must use integer nanometres.')
        width = min(box[2]-box[0], box[3]-box[1])
        if width <= 0:
            raise ValueError('Fill rectangle is empty or reversed.')
        widths[item['layer']].add(width)
    if any(not v for v in widths.values()):
        raise ValueError('Expected the complete seven-metal fill inventory.')
    missing = []
    for (layer, kind), values in available.items():
        if not values:
            continue
        for width in sorted(widths[layer]):
            # Exact model point: do not silently rely on width clamping or an
            # unvalidated interpolation. Decimal preserves the stated grid.
            if Decimal(width) not in values:
                missing.append(dict(layer=layer, table=kind, width_nm=width))
    return dict(schema=1, status='width-coverage-failed' if missing else 'width-coverage-passed',
                passed=not missing, qualified=False,
                fill_widths_nm={k: sorted(v) for k, v in widths.items()}, missing=missing,
                scope='Exact nominal table points for every represented fill width. Does not establish native response, field accuracy, active-fill coverage or timing.')


def audit(rules, represented):
    rules, represented = Path(rules), Path(represented)
    value = json.loads(represented.read_text())
    result = coverage(rules.read_text(), value['added'])
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result.update(rules_sha256=sha(rules), represented_sha256=sha(represented))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rules', type=Path)
    p.add_argument('represented', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = audit(args.rules, args.represented)
    args.output.write_text(json.dumps(result, indent=2)+'\n', newline='\n')
    print(json.dumps({k: result[k] for k in ('status', 'passed', 'qualified')}))
    raise SystemExit(0 if result['passed'] else 1)
