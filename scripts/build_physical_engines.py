"""Build exact upstream Magic/Netgen commits into an isolated local prefix."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(output, jobs=2):
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
    lock = json.loads((ROOT / 'examples/physical-engine-lock.json').read_text())
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
            run(['./configure', '--prefix=' + str(prefix)])
            run(['make', '-j' + str(jobs)])
            run(['make', 'install'])
        executable = prefix / 'bin' / name
        if not executable.is_file():
            raise ValueError('Build did not install ' + name)
        command = [str(executable), '--version' if name == 'magic' else '-batch']
        version = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=30)
        if entry['version'] not in version:
            raise ValueError('Installed ' + name + ' does not report its pinned version')
        (output / (name + '-version.log')).write_text(version, encoding='utf-8')
        print(name + ' ' + entry['version'] + ' installed', flush=True)
    (output / 'source-lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
    return prefix


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error('--jobs must be between 1 and 16')
    print(build(args.output, args.jobs))
