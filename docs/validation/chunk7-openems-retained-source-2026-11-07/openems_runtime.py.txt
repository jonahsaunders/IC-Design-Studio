"""Locate the separate, relocatable open-source solver shipped with Studio."""
import json
import os
from pathlib import Path
import sys


def bundled_root():
    packaged = Path(__file__).parent/'assets'/'runtime'/'openems'
    if packaged.is_dir() or getattr(sys, 'frozen', False):
        return packaged
    return Path(__file__).resolve().parents[1]/'build'/'openems-runtime'


def python_path(root):
    return Path(root)/'python'/('python.exe' if os.name == 'nt' else 'bin/python3')


def discover(saved=''):
    """An explicit override wins; a stale saved path cannot hide a ready bundle."""
    override = os.environ.get('ICSTUDIO_OPENEMS_PYTHON', '').strip()
    if override:
        return override, 'Custom solver'
    if saved and Path(saved).is_file():
        return str(saved), 'Custom solver'
    root = bundled_root()
    if python_path(root).is_file() and (root/'runtime.json').is_file():
        return str(python_path(root)), 'Included openEMS'
    # Source installations can reuse upstream's standard isolated environment.
    for base in (Path.home()/'opt/openEMS', Path.home()/'openEMS'):
        for path in (base/'venv/bin/python3', base/'venv/Scripts/python.exe'):
            if path.is_file():
                return str(path), 'Detected openEMS'
    return '', 'Solver setup needed'


def runtime_for(executable):
    path = Path(executable).absolute()
    root = path.parent.parent if os.name == 'nt' else path.parent.parent.parent
    if (root/'runtime.json').is_file() and path == python_path(root).absolute():
        return root
    return None


def environment(executable, base=None):
    """Never let the frozen app's Python/Qt libraries replace solver libraries."""
    env = dict(os.environ if base is None else base)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(key, None)
    if getattr(sys, 'frozen', False):
        original = env.pop('LD_LIBRARY_PATH_ORIG', '')
        if original: env['LD_LIBRARY_PATH'] = original
        else: env.pop('LD_LIBRARY_PATH', None)
    root = runtime_for(executable)
    if root:
        native = root/'native'
        env['OPENEMS_INSTALL_PATH'] = str(native)
        env['CSXCAD_INSTALL_PATH'] = str(native)
        env['PATH'] = str(native)+os.pathsep+env.get('PATH', '')
        if os.name != 'nt':
            env['LD_LIBRARY_PATH'] = str(native/'lib')+os.pathsep+str(root/'python/lib')
        env['PYTHONNOUSERSITE'] = '1'
    env.update(PYTHONUNBUFFERED='1', MPLBACKEND='Agg')
    return env


def describe(executable):
    root = runtime_for(executable) if executable else None
    if root:
        try:
            record = json.loads((root/'runtime.json').read_text(encoding='utf-8'))
            return 'Included openEMS '+record['openems_version']+' · ready to check automatically when you run'
        except (OSError, ValueError, KeyError):
            return 'Included solver needs repair. Re-extract the complete desktop download.'
    return 'A custom solver will be checked automatically when you run.' if executable else (
        'Use the ready-to-run desktop download to get openEMS and Python together. '
        'An existing installation can also be selected under Advanced settings.')
