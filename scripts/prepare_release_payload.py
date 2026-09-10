"""Package exact desktop assets, execute the extracted archive, and hash evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import __version__
from scripts.release_archives import source_archive


def checksum(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_distribution(archive, output):
    """Run from the archive, with isolated app settings and no engine overrides."""
    archive, output = Path(archive).resolve(), Path(output).resolve()
    require(not output.exists(), 'Use a new distribution evidence directory')
    extracted = output / 'Extracted app with spaces'
    extracted.mkdir(parents=True)
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                require((extracted / entry.filename).resolve().is_relative_to(extracted), 'Unsafe ZIP member')
            bundle.extractall(extracted)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(extracted, filter='data')
    executable = extracted / 'ICDesignStudio' / ('ICDesignStudio.exe' if os.name == 'nt' else 'ICDesignStudio')
    require(executable.is_file(), 'Archive has no expected desktop executable')
    env = {k: v for k, v in os.environ.items() if not k.startswith('ICSTUDIO_') and k != 'PDK_ROOT'}
    profile = output / 'Clean application profile'
    for key in (('APPDATA', 'LOCALAPPDATA') if os.name == 'nt' else ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME')):
        directory = profile / key
        directory.mkdir(parents=True)
        env[key] = str(directory)
    if os.name == 'nt':
        env.pop('QT_QPA_PLATFORM', None)
    else:
        env['QT_QPA_PLATFORM'] = 'offscreen'
    evidence = output / 'probe'
    result = subprocess.run([str(executable), '--release-test', str(evidence)],
                            cwd=executable.parent, env=env, capture_output=True, timeout=240)
    (output / 'execution.log').write_bytes(result.stdout + result.stderr)
    require(result.returncode == 0, 'Extracted desktop probe failed; inspect distribution-evidence')
    report = json.loads((evidence / 'release-test.json').read_text())
    require(report['status'] == 'passed' and report['frozen'] and report['version'] == __version__,
            'Extracted application report does not qualify this release')
    return {'status': 'passed', 'archive': archive.name, 'archive_sha256': checksum(archive),
            'clean_application_profile': True, 'paths_with_spaces': True,
            'report': report, 'display': 'native' if os.name == 'nt' else 'offscreen'}


def prepare(output):
    output = Path(output).resolve()
    require(not output.exists(), 'Use a new release payload directory')
    output.mkdir(parents=True)
    target = 'Windows' if os.name == 'nt' else 'Linux'
    require(target == 'Windows' or sys.platform.startswith('linux'), 'Unqualified build platform')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if target == 'Windows':
        packages = []
        for suffix in ('Windows-x64-Setup.exe', 'Windows-x64-Portable.zip'):
            original = ROOT / 'dist/installers' / f'IC-Design-Studio-{__version__}-{suffix}'
            require(original.is_file(), 'Missing release package: ' + original.name)
            packages.append(Path(shutil.copy2(original, output / original.name)))
        installer = json.loads((ROOT / 'build/windows-evidence/windows-release.json').read_text())
        require(installer['status'] == 'passed', 'Installed Windows package has not passed')
        archive = packages[1]
    else:
        bundle = ROOT / 'dist/ICDesignStudio'
        require((bundle / 'ICDesignStudio').is_file(), 'Build and verify the Linux desktop first')
        archive = output / f'IC-Design-Studio-{__version__}-Linux-x86_64.tar.gz'
        with tarfile.open(archive, 'w:gz') as package:
            package.add(bundle, arcname='ICDesignStudio')
        packages = [archive]
        installer = None
    source = source_archive(output)
    source = source.rename(output / f'IC-Design-Studio-{__version__}-Source-{target}.zip')
    packages.append(source)
    probe = verify_distribution(archive, ROOT / 'build/distribution-evidence')
    evidence_zip = output / f'IC-Design-Studio-{__version__}-Evidence-{target}.zip'
    with zipfile.ZipFile(evidence_zip, 'w', zipfile.ZIP_DEFLATED) as evidence:
        for directory in sorted((ROOT / 'build').glob('*evidence')):
            for file in sorted(directory.rglob('*')):
                if file.is_file() and 'Extracted app with spaces' not in file.parts:
                    evidence.write(file, file.relative_to(ROOT / 'build'))
    packages.append(evidence_zip)
    validation = {'schema': 1, 'status': 'passed', 'version': __version__, 'commit': commit,
                  'platform': target, 'host': platform.platform(),
                  'workflow_run': os.environ.get('GITHUB_RUN_ID'),
                  'workflow_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                  'distribution': probe, 'installer': installer,
                  'assets': {f.name: checksum(f) for f in packages},
                  'limitations': ['Engineering preview; no foundry signoff.',
                                  'Windows signing is not configured.',
                                  'Clean Windows 10/11 consumer-machine and upgrade acceptance remain manual gates.',
                                  'Linux archive execution uses offscreen Qt on Ubuntu 24.04.']}
    record = output / f'IC-Design-Studio-{__version__}-Validation-{target}.json'
    record.write_text(json.dumps(validation, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'passed', 'platform': target, 'commit': commit, 'assets': len(packages)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output)
