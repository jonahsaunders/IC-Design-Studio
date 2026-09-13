"""Build a private, relocatable openEMS runtime for the desktop package.

No system Python or solver installation is modified. Linux build hosts need
cmake, a C++ compiler, libhdf5-dev, libvtk9-dev, libboost-all-dev, libcgal-dev
and libtinyxml-dev. End users need none of these build dependencies.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import openems_runtime

REVISION = 1
PROJECT_COMMIT = 'd0d2e8dad8a02388f1919bbcdd29a67e9199dd2c'
PYTHON_RELEASE = '20260901'
PYTHON_VERSION = '3.11.16'
PYTHON_HASHES = {
    'Windows': '6be524fa6752af802146a4adc7d098565425b0b1c166e19a5a7a4c8cccb86bf6',
    'Linux': 'faa0758583a63f14c5eee516af82738403b59c13edda6fc0a21d953febd89eed',
}
WINDOWS_URL = 'https://github.com/thliebig/openEMS-Project/releases/download/v0.0.36/openEMS_v0.0.36.zip'
WINDOWS_SHA256 = 'e0d62b1176c0897ad18876b45667de877d7d3b58b37c0be95545f9b988896059'
# NumPy 2 is incompatible with these upstream Windows extension wheels.
PACKAGES = ['numpy==1.23.5', 'matplotlib==3.7.5', 'h5py==3.10.0',
            'contourpy==1.2.1', 'cycler==0.12.1', 'fonttools==4.60.1',
            'kiwisolver==1.4.9', 'packaging==25.0', 'pillow==11.3.0',
            'pyparsing==3.2.5', 'python-dateutil==2.9.0.post0', 'six==1.17.0']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(command, **kwargs):
    print(' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, timeout=1800, **kwargs)


def download(url, digest, cache):
    path = cache/url.rsplit('/', 1)[-1]
    if path.is_file() and sha(path) == digest: return path
    partial = path.with_suffix('.part')
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'IC-Design-Studio-runtime-builder'})
        with urllib.request.urlopen(request, timeout=120) as source, partial.open('wb') as target:
            shutil.copyfileobj(source, target)
        if sha(partial) != digest: raise ValueError('Download checksum mismatch: '+url)
        partial.replace(path)
    finally: partial.unlink(missing_ok=True)
    return path


def extract(archive, destination):
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as package:
            for name in package.namelist():
                if not (destination/name).resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Unsafe archive member: '+name)
            package.extractall(destination)
    else:
        with tarfile.open(archive) as package:
            package.extractall(destination, filter='data')


def source_tree(cache):
    source = cache/'source'
    if not (source/'.git').is_dir():
        run(['git', 'clone', '--no-checkout', 'https://github.com/thliebig/openEMS-Project.git', source])
    run(['git', 'checkout', '--detach', PROJECT_COMMIT], cwd=source)
    run(['git', 'submodule', 'update', '--init', 'CSXCAD', 'openEMS', 'fparser'], cwd=source)
    return source


def source_archive(source, target):
    """Include the exact solver, bindings and fparser source with their licenses."""
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for component in (source, source/'CSXCAD', source/'openEMS', source/'fparser'):
            names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=component).decode().split('\0')
            for name in filter(None, names):
                file = component/name
                if file.is_file(): archive.write(file, file.relative_to(source))


def collect_linux_libraries(native):
    """Copy the native dependency closure, retaining the host's glibc boundary."""
    excluded = re.compile(r'^(?:ld-linux.*|lib(?:c|m|pthread|dl|rt|resolv|util|anl)\.so\..*)$')
    lib = native/'lib'; lib.mkdir(exist_ok=True)
    queue = [p for p in lib.iterdir() if p.is_file() and '.so' in p.name]
    seen = set(); packages = set()
    while queue:
        file = queue.pop()
        if str(file) in seen: continue
        seen.add(str(file))
        output = subprocess.check_output(['ldd', str(file)], text=True,
                                         env={**os.environ, 'LD_LIBRARY_PATH': str(lib)})
        if 'not found' in output: raise RuntimeError('Unresolved solver library:\n'+output)
        for name, filename in re.findall(r'^\s*(\S+)\s+=>\s+(/\S+)', output, re.M):
            if excluded.match(name): continue
            dest = lib/name
            if not dest.exists():
                shutil.copy2(filename, dest); queue.append(dest)
                lookup = subprocess.run(['dpkg-query', '-S', filename], capture_output=True, text=True)
                if lookup.returncode:
                    lookup = subprocess.run(['dpkg-query', '-S', str(Path(filename).resolve())], capture_output=True, text=True)
                for line in lookup.stdout.splitlines():
                    packages.add(line.split(': ')[0].split(':')[0])
    notices = native.parent/'licenses/system'; notices.mkdir(parents=True)
    for package in sorted(packages):
        file = Path('/usr/share/doc')/package/'copyright'
        if file.is_file(): shutil.copy2(file, notices/(package+'.copyright'))
    versions = subprocess.check_output(['dpkg-query', '-W', '-f=${Package} ${Version}\n', *sorted(packages)], text=True) if packages else ''
    (notices/'PACKAGES.txt').write_text(versions+'\nCorresponding Ubuntu sources: https://archive.ubuntu.com/ubuntu/pool/\n', encoding='utf-8')
    return versions.splitlines()


def verify(target, files=True):
    record = json.loads((target/'runtime.json').read_text(encoding='utf-8'))
    if record['recipe_revision'] != REVISION or record['platform'] != platform.system():
        raise ValueError('Runtime recipe or platform changed')
    if files:
        for name, digest in record['files'].items():
            file = (target/name).resolve()
            if not file.is_relative_to(target.resolve()) or not file.is_file() or sha(file) != digest:
                raise ValueError('Missing or changed solver runtime file: '+name)
    python = openems_runtime.python_path(target)
    result = subprocess.run([str(python), '-u', str(ROOT/'icstudio/assets/openems/driver.py'), '--probe'],
                            env=openems_runtime.environment(python), cwd=target,
                            capture_output=True, text=True, timeout=60)
    if result.returncode or 'ICSTUDIO_EM:' not in result.stdout or '"ready"' not in result.stdout:
        raise RuntimeError('Bundled openEMS installation check failed:\n'+result.stdout+result.stderr)
    return record


def stage(target, cache):
    system = platform.system()
    if system not in PYTHON_HASHES or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Bundled openEMS currently supports Windows x64 and Ubuntu 24.04+ x86_64 builds.')
    cache.mkdir(parents=True, exist_ok=True)
    try:
        verify(target); print('Included openEMS runtime is ready.', flush=True); return target
    except (OSError, ValueError, KeyError, RuntimeError): pass
    triple = 'x86_64-pc-windows-msvc' if system == 'Windows' else 'x86_64-unknown-linux-gnu'
    python_url = f'https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_RELEASE}/cpython-{PYTHON_VERSION}%2B{PYTHON_RELEASE}-{triple}-install_only.tar.gz'
    python_archive = download(python_url, PYTHON_HASHES[system], cache)
    source = source_tree(cache)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='openems-stage-', dir=target.parent) as temporary:
        stage = Path(temporary)/'runtime'; stage.mkdir()
        extract(python_archive, stage); python = openems_runtime.python_path(stage)
        # Python isolation and native loader setup are shared with the desktop.
        record = dict(recipe_revision=REVISION, platform=system, openems_version='0.0.36',
                      python_version=PYTHON_VERSION, python_url=python_url, python_sha256=PYTHON_HASHES[system],
                      project_commit=PROJECT_COMMIT, python_packages=PACKAGES)
        (stage/'runtime.json').write_text(json.dumps(record), encoding='utf-8')
        env = openems_runtime.environment(python)
        wheelhouse = cache/('wheels-'+system); wheelhouse.mkdir(exist_ok=True)
        run([python, '-m', 'pip', 'download', '--only-binary=:all:', '--no-deps', '--dest', wheelhouse, *PACKAGES], env=env)
        run([python, '-m', 'pip', 'install', '--no-index', '--no-deps', '--find-links', wheelhouse, *PACKAGES], env=env)
        native = stage/'native'
        if system == 'Windows':
            archive = download(WINDOWS_URL, WINDOWS_SHA256, cache)
            extract(archive, stage); (stage/'openEMS').rename(native)
            record.update(openems_url=WINDOWS_URL, openems_sha256=WINDOWS_SHA256)
            for name in ('CSXCAD', 'openEMS'):
                wheels = list((native/'python').glob(name+'-*-cp311-cp311-win_amd64.whl'))
                if len(wheels) != 1: raise ValueError('Missing pinned Windows Python wheel: '+name)
                run([python, '-m', 'pip', 'install', '--no-deps', wheels[0]], env=env)
        else:
            # v0.0.36 uses pre-VTK-9 CMake component names. Change build metadata
            # only; retain the patched files in the corresponding source archive.
            for component in ('CSXCAD', 'openEMS'):
                path = source/component/'CMakeLists.txt'; text = path.read_text()
                text = re.sub(r'\bvtk(IO\w+)\b', r'\1', text)
                text = text.replace('include(${VTK_USE_FILE})', '')
                path.write_text(text)
            build = Path(temporary)/'native-build'
            run(['cmake', '-S', source, '-B', build, '-DBUILD_APPCSXCAD=OFF', '-DWITH_MPI=OFF', '-DCMAKE_INSTALL_PREFIX='+str(native)])
            run(['cmake', '--build', build, '--parallel', '2'])
            run([python, '-m', 'pip', 'install', 'Cython==0.29.37', 'setuptools==75.8.2', 'wheel==0.45.1'], env=env)
            for component in ('CSXCAD', 'openEMS'):
                directory = source/component/'python'
                run([python, 'setup.py', 'build_ext', '-I'+str(native/'include'), '-L'+str(native/'lib'), 'bdist_wheel'], cwd=directory, env=env)
                wheels = list((directory/'dist').glob('*.whl'))
                if len(wheels) != 1: raise ValueError('Expected one compiled wheel for '+component)
                run([python, '-m', 'pip', 'install', '--no-deps', wheels[0]], env=env)
            record['linux_packages'] = collect_linux_libraries(native)
        licenses = stage/'licenses'; licenses.mkdir(exist_ok=True)
        source_archive(source, licenses/'openEMS-corresponding-source.zip')
        shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md', licenses/'THIRD_PARTY_NOTICES.md')
        (licenses/'SOURCES.txt').write_text(
            'openEMS (GPL-3.0) / CSXCAD (LGPL-3.0): '+
            'https://github.com/thliebig/openEMS-Project/tree/'+PROJECT_COMMIT+'\n'+
            'Exact source, bindings, fparser and Linux CMake compatibility changes: openEMS-corresponding-source.zip\n'+
            'CPython and dependencies: '+python_url+'\n'+
            'https://github.com/astral-sh/python-build-standalone/tree/'+PYTHON_RELEASE+'\n'+
            'Python distribution and wheel metadata retain their original licenses.\n', encoding='utf-8')
        record['wheels'] = {p.name: sha(p) for p in wheelhouse.glob('*.whl')}
        # Cache files would change on every launch; they are never integrity inputs.
        for directory in list(stage.rglob('__pycache__')): shutil.rmtree(directory)
        record['files'] = {p.relative_to(stage).as_posix(): sha(p) for p in sorted(stage.rglob('*')) if p.is_file() and p.name != 'runtime.json'}
        (stage/'runtime.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        relocated = Path(temporary)/'Relocated solver with spaces'; stage.rename(relocated)
        verify(relocated)
        if target.exists(): shutil.rmtree(target)
        relocated.rename(target)
    verify(target, files=False)
    print('Included openEMS runtime is ready: '+str(target), flush=True)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=ROOT/'build/openems-runtime')
    parser.add_argument('--cache', type=Path, default=ROOT/'build/openems-downloads')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify: verify(args.target.resolve())
    else: stage(args.target.resolve(), args.cache.resolve())
