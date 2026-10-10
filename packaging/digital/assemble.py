"""Run inside the build image; create relocatable tools and a content lock."""
import json
import os
import re
import shlex
from pathlib import Path
import shutil
import subprocess

from bundle_platforms import bundle
from icstudio.model import file_digest
from icstudio.digital_platform import corner_coverage

ROOT = Path('/opt/icstudio')
catalog = bundle(ROOT)
shutil.rmtree(ROOT/'orfs/.git')
for name in ('docs', 'tools', 'flow/designs', 'flow/tutorials', 'flow/test', 'flow/reports'):
    shutil.rmtree(ROOT/'orfs'/name, ignore_errors=True)

# Native Linux uses the host glibc (Ubuntu 24.04 or newer), private non-glibc
# libraries, and a compiler sysroot. WSL uses the same image at /.
libraries = ROOT/'lib'; libraries.mkdir()
excluded = ('libc.so', 'libm.so', 'libmvec.so', 'libpthread.so', 'libdl.so',
            'librt.so', 'libresolv.so', 'libutil.so', 'libnss_', 'ld-linux')
for folder in (Path('/usr/lib/x86_64-linux-gnu'), Path('/usr/lib/klayout'), Path('/opt/or-tools/lib')):
    for p in sorted(folder.glob('*.so*')):
        if p.is_file() and not p.name.startswith(excluded) and not (libraries/p.name).exists():
            (libraries/p.name).symlink_to(os.path.relpath(p, libraries))

# Some dependencies live outside the default library directory (for example
# PulseAudio's private library used by KLayout's Qt multimedia dependency).
# Follow the actual loader closure, including Qt plugins, before relocation.
queue=[Path('/usr/bin/openroad'),Path('/usr/bin/sta'),Path('/usr/bin/klayout'),
       Path('/usr/bin/python3'),Path('/usr/bin/perl'),Path('/usr/bin/make')]
queue+=list((ROOT/'physical/installed/lib').rglob('*.so'))
queue+=list((ROOT/'python/lib').rglob('*.so'))
queue+=list(Path('/usr/lib/x86_64-linux-gnu/qt5/plugins').rglob('*.so'))
seen=set()
while queue:
    binary=queue.pop().resolve()
    if binary in seen: continue
    seen.add(binary)
    dependencies=subprocess.check_output(['ldd',str(binary)],text=True,
                                         env={**os.environ,'LD_LIBRARY_PATH':str(libraries)})
    if 'not found' in dependencies: raise ValueError('Unresolved digital library dependency:\n'+dependencies)
    for name, filename in re.findall(r'^\s*(\S+)\s+=>\s+(/\S+)',dependencies,re.M):
        if name.startswith(excluded): continue
        target=libraries/name
        if not target.exists(): target.symlink_to(os.path.relpath(filename,libraries))
        queue.append(Path(filename))

bindir = ROOT/'bin'; bindir.mkdir()
# The upstream Netgen launcher/initializer embeds its build prefix. Source
# the same initializer with the bundled Tcl interpreter after binding its
# library location to CAD_ROOT, so native per-user Linux extraction relocates.
netgen_init=ROOT/'physical/installed/lib/netgen/tcl/netgen.tcl'
netgen_text=netgen_init.read_text()
needle='load /opt/icstudio/physical/installed/lib/netgen/tcl/tclnetgen.so'
if netgen_text.count('\n'+needle+'\n')!=1:raise ValueError('Pinned Netgen initializer changed.')
netgen_init.write_text(netgen_text.replace('\n'+needle+'\n','\nload [file join $env(CAD_ROOT) netgen tcl tclnetgen.so]\n'))
# Magic 8.3.684 resolves its Tcl runtime through CAD_ROOT upstream, including
# the batch interpreter. Keep the pinned implementation intact.
magic_header=(ROOT/'physical/magic/tcltk/tcldir.h').read_text()
if 'getenv("CAD_ROOT")' not in magic_header:raise ValueError('Magic runtime relocation support changed.')
suite = ('iverilog','vvp','verilator','verilator_coverage','yosys','yosys-abc','eqy','sby','bitwuzla')
system = ('openroad','sta','klayout','make','perl','python3','gcc','g++','cc','c++','as','ld','ar','ranlib','magic','netgen','ngspice')
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
    elif name in ('magic','netgen'):
        text += 'export CAD_ROOT="$runtime/physical/installed/lib"\n'
        if name=='netgen':text += 'exec "$root/usr/bin/tclsh8.6" "$CAD_ROOT/netgen/tcl/netgen.tcl" "$@"\n'
        else:text += 'exec "$runtime/physical/installed/bin/'+name+'" "$@"\n'
    else:
        if name in ('python3','klayout','openroad'): text += 'export PYTHONHOME="$root/usr"\n'
        if name=='python3':text += 'export PYTHONPATH="$runtime/python/lib/python3.12/site-packages"\n'
        executable = 'usr/bin/'+name
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
    'klayout':'0.30.5',
    'klayout_package_sha256':'9f88fe45d1992fc9bd0ce986bbbe150ad198c6a59a86fc13343db822a5790e49',
    'orfs':'eaba6576441bf7c1743ea56ecdb1904210ec02c2',
    'files_sha256':file_digest(ROOT/'files.json'),
    'platforms':list(catalog['platforms']), 'default_platform':catalog['default'],
    'platform_corners':{name:corner_coverage(value) for name,value in catalog['platforms'].items()},
    'licenses':['usr/share/doc/*/copyright','opt/icstudio/oss-cad-suite/license',
                'opt/icstudio/orfs/LICENSE_BUILD_RUN_SCRIPTS','opt/icstudio/licenses','opt/icstudio/physical/licenses'],
    'physical_source_lock':json.loads((ROOT/'physical/source-lock.json').read_text()),
    'osdi':{'ihp-sg13g2':json.loads((ROOT/'osdi/ihp-sg13g2/build.json').read_text())},
    'sources':['https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-13',
               'https://www.klayout.org/downloads/Ubuntu-24/klayout_0.30.5-1_amd64.deb',
               'https://github.com/The-OpenROAD-Project/OpenROAD/tree/08f67ee5ec',
               'https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/eaba6576441bf7c1743ea56ecdb1904210ec02c2',
               'https://github.com/chipfoundry/volare/releases/tag/sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392',
               'https://github.com/RTimothyEdwards/magic','https://github.com/RTimothyEdwards/netgen',
               'https://archive.ubuntu.com/ubuntu/']}, indent=2))
