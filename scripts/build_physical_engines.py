"""Build exact upstream Magic/Netgen commits into an isolated local prefix."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(output, jobs=2, lock_path=None, only=None):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new engine build directory.')
    output.mkdir(parents=True)
    prefix = output / 'installed'
    # Netgen's configure can omit the include flag when Tcl and Tk share a
    # directory. Use the installed development packages' include directories.
    flags = subprocess.check_output(['pkg-config', '--cflags-only-I', 'tcl', 'tk'], text=True)
    includes = [flag[2:] for flag in shlex.split(flags) if flag.startswith('-I')]
    env = os.environ.copy()
    env['CPATH'] = os.pathsep.join(includes + ([env['CPATH']] if env.get('CPATH') else []))
    lock_path=Path(lock_path or ROOT/'examples/physical-engine-lock.json').resolve()
    lock = json.loads(lock_path.read_text())
    if only:
        if only not in lock:raise ValueError('Engine is absent from this source lock: '+only)
        lock={only:lock[only]}
    for name, entry in lock.items():
        source = output / name
        source.mkdir()
        with (output / (name + '-build.log')).open('w') as log:
            def run(arguments):
                subprocess.run(arguments, cwd=source, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
            run(['git', 'init'])
            run(['git', 'remote', 'add', 'origin', entry['repository']])
            run(['git', 'fetch', '--depth', '1', 'origin', entry['commit']])
            run(['git', 'checkout', '--detach', 'FETCH_HEAD'])
            actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
            if actual != entry['commit']:
                raise ValueError('Unexpected source commit for ' + name)
            if entry.get('patch'):
                patch=(ROOT/entry['patch']).resolve()
                if not patch.is_relative_to(ROOT) or hashlib.sha256(patch.read_bytes()).hexdigest()!=entry['patch_sha256']:
                    raise ValueError('Pinned engine patch changed: '+name)
                run(['git','apply','--check',str(patch)])
                run(['git','apply',str(patch)])
            if entry.get('autogen'):run(['./autogen.sh'])
            run(['./configure', '--prefix=' + str(prefix),*entry.get('configure',[])])
            run(['make', '-j' + str(jobs)])
            run(['make', 'install'])
        executable = prefix / 'bin' / name
        if not executable.is_file():
            raise ValueError('Build did not install ' + name)
        command = [str(executable),*entry.get('version_args',['-batch'] if name=='netgen' else ['--version'])]
        version = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=30)
        if entry['version'] not in version:
            raise ValueError('Installed ' + name + ' does not report its pinned version')
        if entry.get('require_klu') and 'KLU' not in version:raise ValueError('ngspice must include KLU.')
        licenses=output/'licenses'/name;licenses.mkdir(parents=True)
        for filename in ('COPYING','Copying','COPYRIGHT','LICENSE','LICENSE.txt'):
            if (source/filename).is_file():shutil.copy2(source/filename,licenses/filename)
        if not any(licenses.iterdir()):raise ValueError('No upstream license captured for '+name)
        (output / (name + '-version.log')).write_text(version, encoding='utf-8')
        print(name + ' ' + entry['version'] + ' installed', flush=True)
    (output / 'source-lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
    return prefix


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--lock',type=Path,help='Explicit additional qualification lock; the default supported engines stay unchanged.')
    parser.add_argument('--only',help='Build one explicitly named entry of the selected lock.')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error('--jobs must be between 1 and 16')
    print(build(args.output, args.jobs,args.lock,args.only))
