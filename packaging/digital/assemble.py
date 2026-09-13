"""Run inside the build image; create relocatable tools and a content lock."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from icstudio.digital_platform import from_orfs, pin_flow
from icstudio.model import file_digest

ROOT = Path('/opt/icstudio')
platform = from_orfs(ROOT/'orfs')
flow = pin_flow(ROOT/'orfs')
# Retain the selected technology, shared scripts and upstream license files.
for p in (ROOT/'orfs/flow/platforms').iterdir():
    if p.name != 'sky130hd' and p.is_dir():
        # Dereference platform links before removing sibling technologies.
        for link in (ROOT/'orfs/flow/platforms/sky130hd').rglob('*'):
            if link.is_symlink() and link.is_file():
                data = link.read_bytes(); link.unlink(); link.write_bytes(data)
        shutil.rmtree(p)
shutil.rmtree(ROOT/'orfs/.git')
for name in ('docs', 'tools', 'flow/designs', 'flow/tutorials', 'flow/test', 'flow/reports'):
    shutil.rmtree(ROOT/'orfs'/name, ignore_errors=True)
platform['root'] = 'opt/icstudio/orfs/flow/platforms'
flow['root'] = 'opt/icstudio/orfs/flow'
(ROOT/'platform.json').write_text(json.dumps(platform, indent=2))
(ROOT/'flow.json').write_text(json.dumps(flow, indent=2))

# Native Linux uses the host glibc (Ubuntu 24.04 or newer), private non-glibc
# libraries, and a compiler sysroot. WSL uses the same image at /.
libraries = ROOT/'lib'; libraries.mkdir()
excluded = ('libc.so', 'libm.so', 'libmvec.so', 'libpthread.so', 'libdl.so',
            'librt.so', 'libresolv.so', 'libutil.so', 'libnss_', 'ld-linux')
for folder in (Path('/usr/lib/x86_64-linux-gnu'), Path('/usr/lib/klayout'), Path('/opt/or-tools/lib')):
    for p in sorted(folder.glob('*.so*')):
        if p.is_file() and not p.name.startswith(excluded) and not (libraries/p.name).exists():
            (libraries/p.name).symlink_to(os.path.relpath(p, libraries))

bindir = ROOT/'bin'; bindir.mkdir()
suite = ('iverilog','vvp','verilator','verilator_coverage','yosys','yosys-abc','eqy','sby','bitwuzla')
system = ('openroad','sta','klayout','make','perl','python3','gcc','g++','cc','c++','as','ld','ar','ranlib')
header = '''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
[ "$root" != / ] || root=
runtime="$root/opt/icstudio"
unset PYTHONHOME PYTHONPATH QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH
export PATH="$runtime/bin:/usr/bin:/bin"
export LD_LIBRARY_PATH="$runtime/lib"
export TCL_LIBRARY="$root/usr/share/tcltk/tcl8.6"
export QT_QPA_PLATFORM=offscreen
export QT_PLUGIN_PATH="$root/usr/lib/x86_64-linux-gnu/qt5/plugins"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export PERL5LIB="$root/usr/share/perl5:$root/usr/share/perl/5.38:$root/usr/lib/x86_64-linux-gnu/perl/5.38:$root/usr/lib/x86_64-linux-gnu/perl-base"
'''
for name in suite + system:
    text = header
    if name in suite:
        text += 'exec "$runtime/oss-cad-suite/bin/'+name+'" "$@"\n'
    elif name in ('gcc','g++','cc','c++'):
        actual = 'g++' if name in ('g++','c++') else 'gcc'
        text += 'exec "$root/usr/bin/'+actual+'" --sysroot="${root:-/}" -B"$root/usr/bin/" "$@"\n'
    else:
        if name in ('python3','klayout','openroad'): text += 'export PYTHONHOME="$root/usr"\n'
        executable = 'usr/lib/klayout/klayout' if name=='klayout' else 'usr/bin/'+name
        text += 'exec "$root/'+executable+'" "$@"\n'
    (bindir/name).write_text(text); (bindir/name).chmod(0o755)

# Replace absolute links with equivalent relative links so safe extraction to a
# per-user directory never resolves outside that directory.
for base in ('usr','bin','sbin','lib','lib64','etc','opt','var'):
    paths = [Path('/')/base] + list((Path('/')/base).rglob('*'))
    for p in paths:
        if p.is_symlink() and os.readlink(p).startswith('/'):
            target = os.readlink(p); p.unlink(); p.symlink_to(os.path.relpath(target, p.parent))
packages = subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n'], text=True)
(ROOT/'packages.tsv').write_text(packages)
records = {}
for base in ('usr','opt'):
    for p in sorted((Path('/')/base).rglob('*')):
        if p.is_file() and not p.is_symlink():
            records[str(p)[1:]] = file_digest(p)
(ROOT/'files.json').write_text(json.dumps(records, sort_keys=True))
(ROOT/'runtime.json').write_text(json.dumps({
    'schema':1, 'system':'ubuntu-24.04-x86_64', 'tools':list(suite+system),
    'oss_cad_suite':'2026-09-13', 'openroad':'26Q2-1164-g08f67ee5ec',
    'orfs':'eaba6576441bf7c1743ea56ecdb1904210ec02c2',
    'files_sha256':file_digest(ROOT/'files.json'),
    'licenses':['usr/share/doc/*/copyright','opt/icstudio/oss-cad-suite/license','opt/icstudio/orfs/LICENSE'],
    'sources':['https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-13',
               'https://github.com/The-OpenROAD-Project/OpenROAD/tree/08f67ee5ec',
               'https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/eaba6576441bf7c1743ea56ecdb1904210ec02c2',
               'https://archive.ubuntu.com/ubuntu/']}, indent=2))
