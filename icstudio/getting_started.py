"""Portable examples and bounded discovery of local PDK installations."""
from pathlib import Path
import json
import os
import sys
from .model import load_project, uid


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def examples():
    return json.loads((resource_root() / 'examples/gallery.json').read_text(encoding='utf-8'))


def example_copy(entry):
    root = (resource_root() / 'examples').resolve()
    path = (root / entry['file']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Example path must be inside the examples folder.')
    project = load_project(path)
    # Independent documents must not pick up another copy's run history.
    project['id'] = uid()
    project['revision'] = 0
    return project


def default_pdk_roots(environ=None, home=None):
    env = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    paths = [Path(env[k]).expanduser() for k in ('PDK_ROOT', 'PDK_HOME') if env.get(k)]
    if env.get('PDK_ROOT') and env.get('PDK'):
        paths.append(Path(env['PDK_ROOT']).expanduser() / env['PDK'])
    paths += [home / '.ciel', home / '.volare', home / '.local/share/pdk',
              Path('/usr/local/share/pdk'), Path('/usr/share/pdk')]
    return list(dict.fromkeys(paths))


def discover_pdks(roots):
    """Inspect roots and two child levels, never crawl a whole disk.

    Recognizes Ciel's enabled variant symlinks, a single stock variant, and
    extracted package collections with an optional outer archive directory.
    Full checksums and model dependencies are validated at registration time.
    """
    from .pdk_import import detect_root
    found = {}
    visited = set()
    pending = [(Path(p).expanduser(), 0) for p in roots]
    notes = []
    while pending:
        path, depth = pending.pop(0)
        try:
            path = path.resolve()
            if path in visited or not path.is_dir():
                continue
            visited.add(path)
            if (path / 'package.json').is_file():
                manifest = json.loads((path / 'package.json').read_text(encoding='utf-8'))
                if manifest.get('schema') == 1 and 'technology' in manifest and 'files' in manifest:
                    found[str(path)] = {'path': str(path), 'kind': 'package',
                        'name': str(manifest.get('id', path.name)), 'family': manifest.get('family', 'custom'),
                        'revision': str(manifest.get('revision', ''))}
                    continue
            if (path / 'libs.tech').is_dir():
                root, family = detect_root(path)
                found[str(root)] = {'path': str(root), 'kind': 'folder',
                    'name': root.name, 'family': family, 'revision': 'Index local files'}
                continue
            if depth < 2:
                children = sorted(p for p in path.iterdir() if p.is_dir())
                if len(children) > 200:
                    notes.append(str(path) + ': too many folders; choose the PDK installation folder directly.')
                else:
                    pending.extend((p, depth + 1) for p in children)
        except (OSError, ValueError, RuntimeError) as exc:
            notes.append(str(path) + ': ' + str(exc))
    return sorted(found.values(), key=lambda item: (item['name'], item['path'])), notes


def readiness(technology, ngspice=None, osdi=()):
    """Describe prerequisites without claiming an engine or rule deck ran."""
    simulation = technology.get('simulation', {})
    catalog = simulation.get('catalog', {})
    placeable = sum(not item.get('unavailable') for item in catalog.values())
    includes = simulation.get('includes', [])
    corner_sets = [set(item['sections']) for item in includes if item.get('sections')]
    corners = sorted(set.intersection(*corner_sets)) if corner_sets else ['nominal']
    needs_osdi = simulation.get('requires_osdi', False)
    runtime = 'ngspice found; run a small device test to validate this revision.' if ngspice else 'Select ngspice in Engine setup before simulation.'
    if needs_osdi:
        runtime += ' IHP OSDI libraries need a matching simulator build; ' + ('configured files still require a runtime test.' if osdi else 'compile and select them in Simulation runtime.')
    return {'placeable': placeable, 'indexed': len(catalog), 'corners': corners,
            'requires_osdi': needs_osdi, 'runtime': runtime}
