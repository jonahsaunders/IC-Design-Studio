"""Explicit runtime identity for bounded native acceptance probes.

The engine, initializer, bundle files and resolved ELF dependencies are recorded;
this is not a hermetic identity for the complete operating system.
"""
import hashlib
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(path):
    original = Path(path).absolute()
    for component in (original, *original.parents):
        require(not component.is_symlink() and not component.is_junction(), 'Linked acceptance input.')
    require(original.is_file(), 'Missing acceptance input.')
    return original.resolve()


def inventory(root):
    root = Path(root).resolve()
    files = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink() and not path.is_junction(), 'Linked runtime input.')
        if path.is_file(): files[path.relative_to(root).as_posix()] = sha(path)
    return files


def native_environment(binding, engine, output):
    """Allowlisted child environment, matching packaged scalar initializer/loader."""
    engine, output = Path(engine), Path(output)
    env = dict(LANG='C', LC_ALL='C', TZ='UTC', HOME=str(output/'empty-home'), USERPROFILE=str(output/'empty-home'),
               TMP=str(output/'temporary'), TEMP=str(output/'temporary'))
    for folder in ('empty-home', 'temporary'):
        (output/folder).mkdir(exist_ok=True)
    if os.name == 'nt':
        system = os.environ.get('SystemRoot', r'C:\Windows')
        env.update(SystemRoot=system, WINDIR=system, PATH=str(engine.parent)+os.pathsep+str(Path(system)/'System32'))
    else:
        env['PATH'] = str(engine.parent)+':/usr/bin:/bin'
        if binding['mode'] == 'installed':
            env['LD_LIBRARY_PATH'] = binding['resource_root']
    if (engine.parent/'spinit').is_file():
        env['SPICE_SCRIPTS'] = str(engine.parent)
    elif binding['mode'] == 'source-pilot' and Path('/usr/share/ngspice/scripts/spinit').is_file():
        env['SPICE_SCRIPTS'] = '/usr/share/ngspice/scripts'
    else:
        raise ValueError('No explicit simulator initializer is available.')
    require(not any(k.upper().startswith('GIT_') or k.upper() in ('ICSTUDIO_NGSPICE', 'ICSTUDIO_BUNDLED_NGSPICE',
            'PYTHONPATH', 'PYTHONHOME', 'LD_PRELOAD') for k in env), 'Forbidden native environment override.')
    return env

def runtime(binding, engine, env):
    """Capture actual engine/config/bundle and ELF libraries; not a hermetic OS claim."""
    engine = checked_path(engine)
    files = {str(engine): sha(engine)}
    roots = [engine.parent] if binding['mode'] == 'installed' or os.name == 'nt' else []
    if binding['mode'] == 'source-pilot' and os.name != 'nt':
        roots += [p for p in (Path('/usr/share/ngspice'), Path('/usr/lib/x86_64-linux-gnu/ngspice')) if p.is_dir()]
    for root in roots:
        for name, digest in inventory(root).items():
            files[str(root/name)] = digest
    initializer = Path(env['SPICE_SCRIPTS'])/'spinit'
    files[str(initializer)] = sha(initializer)
    if os.name == 'nt':
        from icstudio.runtime_setup import verify_runtime_files
        verify_runtime_files(engine.parent)
    libraries = {}; ldd_output = None
    if sys.platform == 'linux':
        require(engine.read_bytes()[:4] == b'\x7fELF', 'Linux acceptance requires the actual ELF engine, not a wrapper.')
        preload = Path('/etc/ld.so.preload')
        require(not preload.exists() or not preload.read_text().strip(), 'Unreviewed system preload is present.')
        result = subprocess.run(['/usr/bin/ldd', str(engine)], env=env, capture_output=True, text=True, timeout=30)
        require(result.returncode == 0 and 'not found' not in result.stdout+result.stderr, 'Native library resolution failed.')
        ldd_output = re.sub(r'\(0x[0-9a-fA-F]+\)', '(address)', result.stdout+result.stderr)
        for value in sorted(set(re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', ldd_output, re.M))):
            path = Path(value)
            libraries[value] = dict(resolved=str(path.resolve()), sha256=sha(path))
        require(bool(libraries), 'Native ELF dependency closure is missing.')
        for path in (Path('/usr/bin/ldd'), Path('/etc/ld.so.cache')):
            files[str(path)] = sha(path)
    version = subprocess.run([str(engine), '--version'], env=env, capture_output=True, text=True, timeout=30)
    require(version.returncode == 0 and 'ngspice' in (version.stdout+version.stderr).lower(), 'Simulator version probe failed.')
    return dict(engine=str(engine), sha256=sha(engine), platform=sys.platform, machine=platform.machine(),
        environment=env, files=files, elf_dependencies=libraries, ngspice_version=version.stdout+version.stderr,
        dependency_listing=ldd_output, scope='Engine, adjacent packaged runtime/configuration and resolved ELF dependencies when Linux; not a hermetic full-OS closure.')
