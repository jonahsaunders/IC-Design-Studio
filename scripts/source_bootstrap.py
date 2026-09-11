"""Windows source launcher: short, isolated environments and verified setup state."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

SCHEMA = 1
CHECK_IMPORTS = 'from PySide6 import QtWidgets; import klayout.db; from cryptography import x509; from cryptography.hazmat.primitives.asymmetric import ec; ec.generate_private_key(ec.SECP256R1())'


def fingerprint(project, interpreter=None):
    return {'schema':SCHEMA, 'requirements_sha256':hashlib.sha256((Path(project)/'requirements.txt').read_bytes()).hexdigest(),
            'interpreter':os.path.normcase(str(Path(interpreter or sys.executable).resolve())),
            'python':list(sys.version_info[:3]), 'bits':struct.calcsize('P')*8}


def environment_path(project, local_app_data, interpreter=None):
    if not local_app_data or not Path(local_app_data).is_absolute():
        raise ValueError('LOCALAPPDATA is unavailable. Run from a normal Windows user profile.')
    identity=[os.path.normcase(str(Path(project).resolve())),fingerprint(project,interpreter)['interpreter'],list(sys.version_info[:2])]
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:12]
    return Path(local_app_data)/'ICStudio'/'venvs'/key


def run_checked(command, project, runner):
    result=runner([str(v) for v in command],cwd=str(project),check=False)
    if result.returncode:raise RuntimeError('Dependency setup failed. The application was not started. Review the error above and launch again after fixing it.')


def prepare(project, environment, runner=subprocess.run, interpreter=None):
    """Only publish readiness after pip, dependency consistency and Qt imports pass."""
    project=Path(project).resolve();environment=Path(environment);python=environment/'Scripts/python.exe'
    marker=environment/'icstudio-ready.json';expected=fingerprint(project,interpreter)
    try:ready=json.loads(marker.read_text(encoding='utf-8'))==expected
    except (OSError,ValueError):ready=False
    if ready and python.is_file():
        # A successful previous install still needs its native imports to load.
        check=runner([str(python),'-c',CHECK_IMPORTS],cwd=str(project),check=False)
        if check.returncode==0:return python
    # The environment is owned by this launcher. Keep all user project files and
    # the former project-local .venv untouched, including after a failed repair.
    if marker.exists():marker.unlink()
    environment.parent.mkdir(parents=True,exist_ok=True)
    if not python.is_file():
        run_checked([interpreter or sys.executable,'-m','venv',environment],project,runner)
    print('Preparing IC Design Studio dependencies in '+str(environment),flush=True)
    # An interrupted wheel install can leave both importable modules and metadata.
    # Force replacement when readiness is absent so pip cannot accept that state.
    run_checked([python,'-m','pip','install','--disable-pip-version-check','--force-reinstall','-r',project/'requirements.txt'],project,runner)
    run_checked([python,'-m','pip','check'],project,runner)
    run_checked([python,'-c',CHECK_IMPORTS],project,runner)
    temp=marker.with_suffix('.tmp');temp.write_text(json.dumps(expected,sort_keys=True),encoding='utf-8');temp.replace(marker)
    return python


def launch(project, environment, arguments, runner=subprocess.run, interpreter=None):
    python=prepare(project,environment,runner,interpreter)
    print('Checking bundled NGSpice and simulation libraries…',flush=True)
    run_checked([python,Path(project)/'scripts/stage_windows_ngspice.py','--ensure'],project,runner)
    run_checked([python,Path(project)/'scripts/check_simulation_assets.py'],project,runner)
    return runner([str(python),str(Path(project)/'main.py'),*arguments],cwd=str(project),check=False).returncode


def main(arguments=None):
    if os.name!='nt':
        print('This launcher is for Windows. Follow the README source instructions on Linux/macOS.',file=sys.stderr);return 1
    if struct.calcsize('P')!=8 or sys.version_info<(3,12):
        print('Use 64-bit Python 3.12 or newer. Python 3.12 is the reference test version.',file=sys.stderr);return 1
    project=Path(__file__).resolve().parents[1]
    try:
        environment=environment_path(project,os.environ.get('LOCALAPPDATA'))
        return launch(project,environment,list(sys.argv[1:] if arguments is None else arguments))
    except (OSError,ValueError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr)
        print('The next launch will retry unfinished dependency setup. See README.md for Windows source setup.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
