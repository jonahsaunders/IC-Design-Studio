"""Require measured AREA/PJ stability before explicit SKY130 RF diode calls.

This protects emitted catalog calls, including captured native circuits and
preserved control programs. It does not identify arbitrary renamed third-party
subcircuits hidden in external libraries. No circuit or model text is rewritten.
"""
import json
import re
from pathlib import Path
from uuid import uuid4
from .model import atomic_write

MODELS = frozenset('sky130_fd_pr__model__parasitic__rf_diode_' + name
                   for name in ('ps2nw', 'pw2dn'))


def calls(text):
    """Match explicit two-terminal calls, respecting SPICE continuation lines."""
    logical = re.sub(r'\r?\n[ \t]*\+[ \t]*', ' ', text)
    found = []
    for line in logical.splitlines():
        words = line.split()
        if len(words) < 4 or words[0][0].casefold() not in ('x', 'd'):
            continue
        if words[3].casefold() in MODELS:
            if words[0][0].casefold() != 'x':
                raise ValueError('The SKY130 RF diode is a two-terminal X subcircuit, not a primitive D model.')
            found.append(dict(instance=words[0], model=words[3].casefold()))
    return found


def enforce(text, executable, directory):
    selected = calls(text)
    if not selected:
        return
    # Run a fresh, small independent circuit every time. A cached version string
    # cannot prove behavior for a changed executable, wrapper, DLL or initializer.
    from .diode_runtime import verify
    root = Path(directory) / ('rf-runtime-' + uuid4().hex)
    report = verify(executable, root)
    passed = (report['status'] == 'PASS' and
              report.get('behavior', {}).get('mode') == 'unscaled-explicit-area')
    acceptance = dict(status='PASS' if passed else 'FAIL', calls=selected,
                      probe=str(root / 'report.json'),
                      requirement='Stable unscaled level-3 AREA/PJ/M through OP, DC, repeated AC and alterations.',
                      circuit_rewritten=False, qualified=False)
    atomic_write(root / 'rf-acceptance.json', json.dumps(acceptance, indent=2))
    if not passed:
        raise ValueError('This simulator does not pass the SKY130 RF diode geometry check. '
                         'Select the verified bundled runtime or a compatible engine. Details: ' +
                         str(root / 'report.json'))
    return acceptance
