"""Build the release's Linux / private WSL runtime. Docker is a build dependency."""
import argparse
import hashlib
import json
import posixpath
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest

PLATFORM_SCRIPTS = ('prepare_sky130_digital.py', 'fetch_sky130_reference.py',
                    'fetch_gf180_connectivity.py', 'prepare_gf180_connectivity.py',
                    'prepare_gf180_lvs.py', 'gf180_cdl_diodes.py', 'prepare_ihp_fill.py',
                    'prepare_ihp_block_fill.py', 'check_ihp_fill_rules.py',
                    'check_ihp_flat_capacitance.py', 'ihp_cell_capacitance.py',
                    'ihp_magic_export.py', 'ihp_native_capacitance.py')
PLATFORM_LOCKS = ('physical-engine-lock.json', 'sky130-reference-assets.json',
                  'gf180-connectivity-library-lock.json', 'gf180-lvs-source-lock.json',
                  'ihp-fill-source-lock.json', 'ihp-active-fill-source-lock.json')


def sky130_rule_context(context):
    """Include the exact helper/source inputs used by the platform preparer."""
    from icstudio.digital_sky130_rules_lock import FILES
    from icstudio.digital_sky130_isolation_lock import FILES as ISOLATION_FILES
    context = Path(context)
    for name in FILES | ISOLATION_FILES:
        if not name.startswith('helpers/') or name.endswith('/__init__.py'):
            continue
        relative = name.removeprefix('helpers/')
        target = context/relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
    for relative in ('scripts/prepare_sky130_rule_checks.py', 'scripts/prepare_sky130_antenna.py', 'scripts/prepare_sky130_isolation.py',
                     'scripts/sky130_staged_antenna.drc', 'tests/fixtures/sky130-filled-references-v1.zip'):
        target = context/relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)


def pack_filesystem(source, destination):
    # Docker recreates system links such as /etc/mtab when a container is
    # created. Normalize the exported filesystem as well as the image itself.
    with tarfile.open(source,'r:') as src, tarfile.open(destination,'w:gz',compresslevel=1) as out:
        for member in src:
            if member.issym() and member.linkname.startswith('/'):
                member.linkname=posixpath.relpath(member.linkname,posixpath.dirname('/'+member.name))
            if member.islnk(): member.linkname=member.linkname.lstrip('/')
            stream=src.extractfile(member) if member.isfile() else None
            try: out.addfile(member,stream)
            finally:
                if stream: stream.close()


def stage_context(context):
    """Stage the same complete inputs for a build and its cache identity."""
    context = Path(context)
    shutil.copytree(ROOT/'packaging/digital', context, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    (context/'licenses').mkdir()
    shutil.copy2(ROOT/'licenses/Apache-2.0.txt',context/'licenses/Apache-2.0.txt')
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',context/'licenses/THIRD_PARTY_NOTICES.md')
    from icstudio.digital_backend import stage_backend
    stage_backend(ROOT/'icstudio', context/'icstudio')
    ihp_license=context/'icstudio/assets/pdks/ihp-sg13g2/LICENSE'
    ihp_license.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/'icstudio/assets/pdks/ihp-sg13g2/LICENSE',ihp_license)
    shutil.copy2(ROOT/'scripts/build_physical_engines.py',context/'build_physical_engines.py')
    shutil.copy2(ROOT/'scripts/build_ngspice_runtime.py',context/'build_ngspice_runtime.py')
    shutil.copy2(ROOT/'scripts/compile_ihp_osdi.py',context/'compile_ihp_osdi.py')
    (context/'scripts').mkdir()
    for name in PLATFORM_SCRIPTS:
        shutil.copy2(ROOT/'scripts'/name,context/'scripts'/name)
    sky130_rule_context(context)
    shutil.copytree(ROOT/'icstudio/assets/pdks/ihp-sg13g2/libs.tech/verilog-a',context/'ihp-pdk/libs.tech/verilog-a')
    (context/'examples').mkdir()
    for name in PLATFORM_LOCKS:
        shutil.copy2(ROOT/'examples'/name,context/'examples'/name)


def context_identity(context):
    """Hash every staged path and byte, including inputs omitted by old CI globs.

    Keep the builder itself in the identity: archive/export behavior is also an
    input. Timestamps and temporary directory names do not identify a recipe.
    This identifies source inputs, not mutable external package repositories.
    """
    context = Path(context)
    files = {}
    for path in sorted(context.rglob('*')):
        if path.is_symlink(): raise ValueError('Runtime build context must contain materialized files, not links.')
        if path.is_dir(): continue
        if not path.is_file(): raise ValueError('Unexpected runtime build context object.')
        files[path.relative_to(context).as_posix()] = dict(sha256=file_digest(path), mode=stat.S_IMODE(path.stat().st_mode))
    if not files or 'Dockerfile' not in files: raise ValueError('Incomplete runtime build context.')
    record = dict(schema=2, builder_sha256=file_digest(__file__), files=files)
    record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return record


def cache_identity():
    with tempfile.TemporaryDirectory() as td:
        stage_context(td)
        return context_identity(td)


def build(output, expected_cache_key=None):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        context = Path(td); stage_context(context); identity = context_identity(context)
        if expected_cache_key is not None and identity['sha256'] != expected_cache_key:
            raise ValueError('Runtime build inputs changed after computing the cache identity.')
        (output/'build-inputs.json').write_text(json.dumps(identity, indent=2)+'\n', encoding='utf-8')
        subprocess.run(['docker','build','--platform','linux/amd64','-t','icstudio-digital-runtime',str(context)],check=True)
    container = subprocess.check_output(['docker','create','icstudio-digital-runtime'],text=True).strip()
    try:
        subprocess.run(['docker','cp',container+':/opt/icstudio/runtime.json',str(output/'manifest.json')],check=True)
        subprocess.run(['docker','export','--output',str(output/'runtime.tar'),container],check=True)
        pack_filesystem(output/'runtime.tar',output/'runtime.tar.gz')
        (output/'runtime.tar').unlink()
    finally: subprocess.run(['docker','rm',container],check=True)
    metadata = json.loads((output/'manifest.json').read_text())
    metadata.update(archive='runtime.tar.gz',sha256=file_digest(output/'runtime.tar.gz'),
                    build_context_sha256=identity['sha256'],
                    bytes=(output/'runtime.tar.gz').stat().st_size,
                    image_id=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','icstudio-digital-runtime'],text=True).strip())
    (output/'manifest.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='build/digital-payload')
    parser.add_argument('--expected-cache-key', help='Require the previously computed complete source-input identity.')
    args=parser.parse_args();build(args.output,args.expected_cache_key)
