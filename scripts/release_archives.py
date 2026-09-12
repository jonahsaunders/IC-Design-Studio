"""Create a platform-neutral source release, optionally with the built Linux app."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio import __version__

EXCLUDED_DIRS={'build','dist','release','__pycache__','.git','.venv','private-live-data','live-sessions'}
SOURCE_DIRS={'icstudio','tests','native','scripts','docs','examples','packaging','plugins','licenses','.github'}
EXCLUDED_SUFFIXES={'.pyc','.spec','.so','.dll','.dylib','.pyd','.o','.obj','.lib','.exp','.exe','.sqlite3','.sqlite3-wal','.sqlite3-shm'}


def source_archive(destination,windows_runtime=None,repository=False):
    bundled=ROOT/'icstudio/assets/runtime/ngspice'
    if windows_runtime is None and not repository and (bundled/'ngspice.exe').is_file():windows_runtime=bundled
    if repository:windows_runtime=None
    path=destination/f'IC-Design-Studio-{__version__}-{"GitHub" if repository else "Source"}.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for file in sorted(ROOT.rglob('*')):
            rel=file.relative_to(ROOT)
            if rel.name == 'creation-key.txt':continue
            if rel.parts[:4]==('icstudio','assets','runtime','ngspice'):continue
            if (len(rel.parts)>1 and rel.parts[0] not in SOURCE_DIRS) or (len(rel.parts)==1 and (rel.name.startswith(('tmp','pip-')) or rel.name in ('core',) or rel.suffix.lower() in ('.s','.log'))):continue
            if file.is_file() and not any(part in EXCLUDED_DIRS for part in rel.parts) and file.suffix.lower() not in EXCLUDED_SUFFIXES:
                z.write(file,Path('IC-Design-Studio')/rel)
        if windows_runtime:
            runtime=Path(windows_runtime)
            for name in ('ngspice.exe','libomp140.x86_64.dll','spinit','COPYING.txt','runtime-manifest.json'):
                z.write(runtime/name,Path('IC-Design-Studio/icstudio/assets/runtime/ngspice')/name)
    return path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--with-linux-bundle',action='store_true');parser.add_argument('--repository',action='store_true',help='Also create a clean GitHub repository archive without native binaries');parser.add_argument('--windows-runtime',type=Path,help='Include the four packaged Windows ngspice runtime files in the source archive');args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    source=source_archive(out,args.windows_runtime);files=[source]
    if args.repository:files.append(source_archive(out,repository=True))
    if args.with_linux_bundle:
        if not sys.platform.startswith('linux'):raise ValueError('Build the Linux bundle on Linux.')
        bundle=ROOT/'dist'/'ICDesignStudio'
        if not (bundle/'ICDesignStudio').is_file():raise ValueError('Run scripts/package.py first.')
        for old in bundle.glob('IC-Design-Studio-*-Source.zip'):old.unlink()
        shutil.copy2(source,bundle/source.name)
        for name in ('README.md','THIRD_PARTY_NOTICES.md','LICENSE'):
            if (ROOT/name).exists():shutil.copy2(ROOT/name,bundle/name)
        shutil.copytree(ROOT/'docs',bundle/'_internal'/'docs',dirs_exist_ok=True)
        (bundle/'START-HERE.txt').write_text(f'IC Design Studio {__version__} — standalone desktop\n\nExtract this entire folder and run ./ICDesignStudio. Keep _internal beside the executable.\nThis Linux x86_64 build targets Ubuntu 24.04 / glibc 2.39 or newer.\nPython, Qt, ngspice, standard Xschem symbols and GF180 simulation models are included.\nThe complete source is included in {source.name}.\nUse File > Open project to open your .sch file. F5 runs its simulation program.\nOpen Analysis > Xschem analyses for individual cases and waveforms.\nRead _internal/docs/UPDATE_0.18.md for features and validation limits.\n')
        archive=out/f'IC-Design-Studio-{__version__}-Linux-x86_64.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(bundle,arcname='ICDesignStudio')
        files.append(archive)
    checks=[]
    for file in files:
        sha=hashlib.sha256(file.read_bytes()).hexdigest();checks.append(sha+'  '+file.name);print(file.name,file.stat().st_size,sha)
    (out/f'SHA256SUMS-{__version__}.txt').write_text('\n'.join(checks)+'\n')

if __name__=='__main__':main()
