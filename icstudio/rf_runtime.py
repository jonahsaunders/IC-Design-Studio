"""Require measured AREA/PJ stability before explicit SKY130 RF diode calls.

This protects emitted catalog calls and calls behind included wrappers. Include
inspection is conservative: unresolved inputs require the same measured runtime
proof. It is not an electrical certification of renamed third-party models.
No circuit or model text is rewritten.
"""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from .model import atomic_write, io_path

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


def inspect_inputs(text, directory):
    """Inspect static includes without changing their bytes or SPICE execution.

    ngspice tries its working directory before the including file's directory.
    An initializer's sourcepath can intervene before that second location, so a
    parent-relative fallback requires the probe even if no known call is found.
    Unsupported/dynamic directives and bounded inspection exhaustion likewise
    cannot be evidence that the circuit is free of RF diode dependencies.
    """
    root = Path(directory).resolve()
    seen = set(); dependencies = []; selected = []; uncertain = []
    total = 0

    def visit(contents, parent, section=None, depth=0, source='<circuit>'):
        nonlocal total
        if depth > 64:
            uncertain.append(dict(source=source, reason='Include nesting exceeds 64.'))
            return
        # Comments may contain legacy encodings. Inspection never repairs the
        # original file, and all hashes describe its exact original bytes.
        logical = re.sub(r'\r?\n[ \t]*\+[ \t]*', ' ', contents)
        active = section is None; matched = False; control = False
        for line in logical.splitlines():
            line = line.strip()
            if not line or line.startswith('*'):
                continue
            # Retain quoted paths containing spaces or semicolons.
            words = re.findall(r'''"[^"]*"|'[^']*'|[^\s]+''', line)
            words = words[:next((i for i, word in enumerate(words)
                                if word.startswith(('$', ';', '//'))), len(words))]
            if not words:
                continue
            command = words[0].casefold()
            if command == '.lib' and len(words) == 2:
                if section is not None:
                    active = words[1].strip('"\'').casefold() == section.casefold()
                    matched |= active
                continue
            if command == '.endl':
                if section is not None:
                    active = False
                continue
            if not active:
                continue
            if command == '.control':
                control = True
                continue
            if command == '.endc':
                control = False
                continue
            if control:
                if command in ('source', 'sourcepath', 'cd', 'chdir') or (command == 'set' and any('sourcepath' in w.casefold() for w in words[1:])):
                    uncertain.append(dict(source=source, reason='Dynamic circuit input or source path.'))
                continue
            for item in calls(' '.join(words)):
                selected.append({**item, 'source': source})
            if command not in ('.inc', '.include', '.lib'):
                continue
            expected = 3 if command == '.lib' else 2
            if len(words) != expected:
                uncertain.append(dict(source=source, reason='Unsupported include syntax.'))
                continue
            name = words[1].strip('"\'')
            requested = words[2].strip('"\'') if command == '.lib' else None
            if not name or any(c in name for c in ('$', '{', '}', '`', '~')):
                uncertain.append(dict(source=source, reason='Dynamic include path.'))
                continue
            path = (root / name).resolve()
            if not io_path(path).is_file():
                path = (parent / name).resolve()
                uncertain.append(dict(source=source, reason='Include needs a parent directory or external sourcepath: ' + name))
            key = (path, requested.casefold() if requested is not None else None)
            if key in seen:
                continue
            seen.add(key)
            try:
                size = io_path(path).stat().st_size
                if len(seen) > 4096 or total + size > 64 * 1024 * 1024:
                    uncertain.append(dict(source=source, reason='Include inspection size limit.'))
                    return
                data = io_path(path).read_bytes(); total += len(data)
            except OSError:
                uncertain.append(dict(source=source, reason='Unreadable include: ' + name))
                continue
            dependencies.append(dict(path=str(path), section=requested,
                                     sha256=hashlib.sha256(data).hexdigest()))
            visit(data.decode('utf-8', 'replace'), path.parent, requested, depth + 1, str(path))
        if section is not None and not matched:
            uncertain.append(dict(source=source, reason='Requested library section was not found: ' + section))

    visit(text, root)
    return dict(calls=selected, dependencies=dependencies, uncertainty=uncertain)


def enforce(text, executable, directory, *, input_directory=None):
    inspection = inspect_inputs(text, input_directory or directory)
    selected = inspection['calls']
    if not selected and not inspection['uncertainty']:
        return
    # Run a fresh, small independent circuit every time. A cached version string
    # cannot prove behavior for a changed executable, wrapper, DLL or initializer.
    from .diode_runtime import verify
    root = Path(directory) / ('rf-runtime-' + uuid4().hex)
    report = verify(executable, root)
    passed = (report['status'] == 'PASS' and
              report.get('behavior', {}).get('mode') == 'unscaled-explicit-area')
    acceptance = dict(status='PASS' if passed else 'FAIL', calls=selected,
                      input_inspection=inspection,
                      probe=str(root / 'report.json'),
                      requirement='Stable unscaled level-3 AREA/PJ/M through OP, DC, repeated AC and alterations.',
                      circuit_rewritten=False, qualified=False)
    atomic_write(root / 'rf-acceptance.json', json.dumps(acceptance, indent=2))
    if not passed:
        raise ValueError('This simulator does not pass the SKY130 RF diode geometry check. '
                         'Select the verified bundled runtime or a compatible engine. Details: ' +
                         str(root / 'report.json'))
    return acceptance
