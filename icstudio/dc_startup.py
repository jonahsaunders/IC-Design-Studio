"""Optional DC convergence hints from the circuit's own first sweep point.

ngspice 42 HSA restarts CKTop at every DC point. A separately converged
first point supplies .nodeset guesses, released before convergence testing.
No voltages are clamped, tolerances changed or reference results reused.
"""
import json
import math
import re
from pathlib import Path
from .model import atomic_write, scalar


def seed_deck(text, command, directory, timeout=120, env=None):
    from .engines import execute, parse_raw
    directory = Path(directory).resolve()
    # Restrict this option to the single-source sweep emitted by the UI.
    sweeps = list(re.finditer(r'(?im)^\.dc\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$', text))
    if len(sweeps) != 1:
        raise ValueError('DC startup requires one single-source .dc sweep.')
    sweep = sweeps[0]
    start = scalar(sweep[2])
    for value in (sweep[3], sweep[4]): scalar(value)
    if scalar(sweep[4]) == 0: raise ValueError('DC sweep step must be nonzero.')
    first = text[:sweep.start()] + f'.dc {sweep[1]} {sweep[2]} {sweep[2]} {sweep[4]}\n' + text[sweep.end():]
    # Preserve temperature, model setup (including OSDI preload), and user
    # nodesets. Replace only the sweep range and saved-vector selection.
    end = list(re.finditer(r'(?im)^\.end\s*$', text))
    if len(end) != 1: raise ValueError('DC startup requires a single deck terminator.')
    first = re.sub(r'(?im)^\.save[^\n]*(?:\n\+[^\n]*)*\n?', '', first)
    first = re.sub(r'(?im)^\.end\s*$', '.save all\n.end\n', first)
    deck, raw = directory / 'dc-startup.cir', directory / 'dc-startup.raw'
    atomic_write(deck, first)
    if raw.exists(): raw.unlink()
    try:
        log = execute(command(raw, deck), directory, timeout=timeout, env=env)
        atomic_write(directory / 'dc-startup.log', log)
        if re.search(r'(?im)^\s*error|analysis aborted|simulation interrupted', log):
            raise ValueError('The DC startup solve failed; see dc-startup.log.')
        variables, rows, complex_data = parse_raw(raw)
        if complex_data or len(rows) != 1 or not all(math.isfinite(v) for v in rows[0]):
            raise ValueError('DC startup did not produce one finite operating point.')
        if not math.isclose(rows[0][0], start, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('DC startup solved the wrong sweep point.')
    except Exception as exc:
        atomic_write(directory / 'dc-startup-error.log', str(exc)); raise
    existing = set()
    for match in re.finditer(r'(?im)^\.nodeset\s+([^\n]*(?:\n\+[^\n]*)*)', text):
        existing.update(n.casefold() for n in re.findall(r'(?i)v\(([^)]+)\)\s*=', match[1]))
    hints = []; internal_nodes = 0
    for name, value in zip(variables, rows[0]):
        if not name.lower().startswith('v(') or not name.endswith(')'): continue
        node = name[2:-1]
        # BSIM creates #body/#dbody/#sbody nodes after nodeset resolution.
        # They are saved in raw output but cannot be addressed by .nodeset;
        # ngspice's own wrnodev command excludes these internal nodes too.
        if '#' in node:
            internal_nodes += 1; continue
        if node.casefold() in existing or node.casefold() in ('v-sweep', '0'): continue
        if not re.fullmatch(r'[A-Za-z0-9_.$:\[\]#!+-]+', node):
            raise ValueError('Unsupported DC startup node name: ' + node)
        hints.append(f'.nodeset v({node})={value:.17g}')
    if not hints: raise ValueError('DC startup produced no usable voltage hints.')
    hint_text = '* Initial guesses from this circuit at the DC sweep start\n' + '\n'.join(hints) + '\n'
    atomic_write(directory / 'dc-startup.nodeset', hint_text)
    atomic_write(directory / 'dc-startup.json', json.dumps(dict(source=sweep[1], start=start,
        nodes=len(hints), skipped_internal_nodes=internal_nodes, preserved_user_nodesets=sorted(existing), method='first-point nodeset',
        tolerance_changes=False, compatibility_changes=False), indent=2) + '\n')
    return text[:end[0].start()] + hint_text + text[end[0].start():]
