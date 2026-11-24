"""Verify the installed VGA-enabled Windows shell with production asset placement.

The focused installer contains the real desktop executable and dependencies.
It isolates the VGA path from the separate simulation and physical runtimes.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_vga_playground import verify_dist
from scripts.desktop_resources import stage_documents
from scripts.source_files import checkout_workflow_hash
from scripts.verify_packaged_vga import verify


def freeze(temporary: Path, assets: Path, commit: str) -> Path:
    metadata = ROOT / 'icstudio/build_info.py'
    previous = metadata.read_bytes()
    versions = dict(
        ENGINE_SOURCE_HASH=hashlib.sha256((ROOT/'icstudio/simulation.py').read_bytes()).hexdigest(),
        WORKFLOW_SOURCE_HASH=checkout_workflow_hash(ROOT),
        BUILD_COMMIT=commit, BUILD_BRANCH='vga-install-probe', BUILD_DIRTY=False,
    )
    dist = temporary / 'dist'
    sources = {ROOT/'icstudio/assets': 'icstudio/assets',
               ROOT/'examples': 'examples',
               ROOT/'licenses': 'licenses',
               assets: 'icstudio/assets/vga-playground'}
    sources.update({ROOT/name: '.' for name in
                    ('README.md', 'CONTRIBUTING.md', 'SIMULATION_SETUP.md',
                     'THIRD_PARTY_NOTICES.md', 'LICENSE')})
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
            '--name', 'ICDesignStudio', '--windowed', '--onedir', '--collect-all', 'klayout',
            '--recursive-copy-metadata', 'cryptography', '--distpath', str(dist),
            '--workpath', str(temporary/'freeze'), '--specpath', str(temporary)]
    for module in ('PySide6.QtSvg', 'PySide6.QtWebEngineWidgets', 'icstudio.cli', 'icstudio.sdk'):
        args.extend(('--hidden-import', module))
    for source, destination in sources.items():
        args.extend(('--add-data', f'{source}{os.pathsep}{destination}'))
    try:
        metadata.write_text(''.join(f'{key} = {value!r}\n' for key,value in versions.items()), encoding='utf-8')
        subprocess.run([*args, str(ROOT/'main.py')], cwd=ROOT, check=True, timeout=480)
    finally:
        metadata.write_bytes(previous)
    stage_documents(ROOT, dist/'ICDesignStudio/_internal')
    return dist/'ICDesignStudio'


def install(temporary: Path, packaged: Path, evidence: Path) -> Path:
    target = temporary/'Fresh Studio Installation'
    recipe = temporary/'vga-install.iss'
    recipe.write_text(f'''[Setup]
AppId=ICDesignStudio.VGA.InstallProbe
AppName=IC Design Studio VGA Install Probe
AppVersion=1.0
DefaultDirName={target}
PrivilegesRequired=lowest
UsePreviousAppDir=no
Uninstallable=no
CreateUninstallRegKey=no
OutputDir={temporary}
OutputBaseFilename=studio-vga-setup
Compression=fast
[Files]
Source: "{packaged}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs
''', encoding='utf-8')
    iscc = Path(os.environ['ProgramFiles(x86)'])/'Inno Setup 6/ISCC.exe'
    subprocess.run([str(iscc), str(recipe)], check=True, timeout=180)
    subprocess.run([str(temporary/'studio-vga-setup.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                    '/NORESTART', f'/DIR={target}', f'/LOG={evidence/"installer.log"}'],
                   check=True, timeout=180)
    return target


def main() -> None:
    if os.name != 'nt' or not os.environ.get('RUNNER_TEMP'):
        raise SystemExit('Run this installer verification on a disposable Windows CI runner.')
    commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'], cwd=ROOT, text=True):
        raise SystemExit('Verify a clean source checkout.')
    assets = ROOT/'build/vga-playground/dist'
    verify_dist(assets)
    evidence = ROOT/'build/windows-vga-install-evidence'
    evidence.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='studio-vga-', dir=os.environ['RUNNER_TEMP']) as work:
        temporary = Path(work)
        installed = install(temporary, freeze(temporary, assets, commit), evidence)
        verify_dist(installed/'_internal/icstudio/assets/vga-playground')
        if not (installed/'_internal/licenses/ECL-2.0.txt').is_file():
            raise ValueError('The installed Educational Community License text is missing.')
        # Leave Windows system directories available while making build tools
        # such as Node, Git and emcc undiscoverable by the installed application.
        windows = Path(os.environ['SystemRoot'])
        os.environ['PATH'] = os.pathsep.join(map(str, (windows/'System32', windows)))
        verify(installed/'ICDesignStudio.exe', evidence/'offline', commit)


if __name__=='__main__':
    main()
