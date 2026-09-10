"""Small, real execution check shared by launchers and release packaging."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def check_ngspice(executable):
    from .spice_program import runtime_environment
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise ValueError('NGSpice executable is missing: ' + str(executable))
    with tempfile.TemporaryDirectory(prefix='icstudio-engine-') as directory:
        root = Path(directory)
        (root / 'check.cir').write_text(
            '* IC Design Studio installation check\nV1 in 0 2\n'
            'R1 in out 1k\nR2 out 0 1k\n.control\n'
            'op\nprint v(out)\nquit\n.endc\n.end\n', encoding='utf-8')
        result = subprocess.run([str(executable), '-n', '-b', 'check.cir'],
            cwd=root, env=runtime_environment(executable), capture_output=True,
            text=True, errors='replace', timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        log = result.stdout + '\n' + result.stderr
        voltage = re.search(r'(?im)^v\(out\)\s*=\s*([\d.eE+-]+)', log)
        if result.returncode or not voltage or abs(float(voltage[1]) - 1) > 1e-6:
            raise RuntimeError('NGSpice installation check failed. Repair the bundled runtime.\n' + log[-4000:])
        return {'executable': str(executable), 'divider_voltage': float(voltage[1]), 'status': 'passed'}


def verify_runtime_files(directory):
    """A present .exe alone cannot establish that its DLLs survived extraction."""
    from .model import file_digest
    root = Path(directory)
    record = json.loads((root / 'runtime-manifest.json').read_text(encoding='utf-8'))
    required = {'ngspice.exe', 'libomp140.x86_64.dll', 'spinit', 'COPYING.txt'}
    if not isinstance(record, dict) or not isinstance(record.get('files'), dict) or not required <= record['files'].keys():
        raise ValueError('Incomplete NGSpice runtime manifest.')
    for name, expected in record['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or file_digest(path) != expected:
            raise ValueError('Missing or changed NGSpice runtime file: ' + name)
    return record
