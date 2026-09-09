"""Assemble a relocatable Windows x64 desktop using official Windows runtimes.

This packaging step can run on any host. Execute --release-test on Windows to
qualify the resulting binary; assembly and PE checks are not a runtime test.
"""
import argparse,hashlib,io,json,shutil,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio import __version__


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--python',type=Path,required=True);ap.add_argument('--wheels',type=Path,required=True);ap.add_argument('--ngspice',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    target=args.output.resolve()/('IC-Design-Studio-'+__version__+'-Windows-x64');target.mkdir(parents=True,exist_ok=True)
    if any(target.iterdir()):raise ValueError('Use an empty assembly directory.')
    app=target/'app';app.mkdir();ignored=shutil.ignore_patterns('__pycache__','*.pyc','*.so','*.dylib','runtime')
    for name in ('icstudio','docs','examples','licenses','native','scripts','tests','packaging','.github'):shutil.copytree(ROOT/name,app/name,ignore=ignored)
    for name in ('main.py','requirements.txt','requirements-build.txt','README.md','CONTRIBUTING.md','LICENSE','THIRD_PARTY_NOTICES.md'):shutil.copy2(ROOT/name,app/name)
    runtime=target/'python';runtime.mkdir()
    with zipfile.ZipFile(args.python) as z:z.extractall(runtime)
    pth=next(runtime.glob('python*._pth'));stdlib=next(runtime.glob('python*.zip'));pth.write_text(stdlib.name+'\n.\nLib/site-packages\n../app\nimport site\n',encoding='utf-8')
    site=runtime/'Lib/site-packages';site.mkdir(parents=True)
    wheels=list(args.wheels.glob('*.whl'))
    if not all(any(w.name.lower().startswith(prefix) for w in wheels) for prefix in ('pyside6_essentials','shiboken6','klayout')):raise ValueError('Download all pinned Windows wheels first.')
    for wheel in wheels:
        if 'win_amd64' not in wheel.name:raise ValueError('Expected Windows x64 wheel: '+wheel.name)
        with zipfile.ZipFile(wheel) as z:z.extractall(site)
    # The Essentials wheel contains optional plugins whose dependencies live in
    # Addons or external database clients. This QWidget application uses none
    # of those modules; omit their plugins instead of shipping broken loaders.
    qt=site/'PySide6'
    for name in ('qml','plugins/designer','plugins/qmltooling','plugins/sqldrivers'):
        shutil.rmtree(qt/name,ignore_errors=True)
    for name in ('plugins/imageformats/qpdf.dll','plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll'):
        (qt/name).unlink(missing_ok=True)
    engine=app/'icstudio/assets/runtime/ngspice';engine.mkdir(parents=True)
    shutil.copy2(args.ngspice/'bin/ngspice_con.exe',engine/'ngspice.exe');shutil.copy2(args.ngspice/'bin/libomp140.x86_64.dll',engine/'libomp140.x86_64.dll');shutil.copy2(args.ngspice/'docs/COPYING',engine/'COPYING.txt')
    shutil.copy2(ROOT/'icstudio/assets/ngspice/spinit',engine/'spinit')
    # Distlib's maintained native launcher supports <launcher_dir> shebangs.
    from pip._vendor import distlib
    lib=Path(distlib.__file__).parent
    script='''import sys,os,traceback
from pathlib import Path
root=Path(sys.argv[0]).resolve().parent
sys.path.insert(0,str(root/'app'))
if len(sys.argv)==2 and not sys.argv[1].startswith('--'):
    sys.argv.insert(1,'--project')
try:
    from icstudio.__main__ import main
    raise SystemExit(main())
except Exception:
    detail=traceback.format_exc()
    folder=Path(os.environ.get('LOCALAPPDATA',str(root)))/'ICDesignStudio'
    folder.mkdir(parents=True,exist_ok=True)
    log=folder/'startup-error.log';log.write_text(detail,encoding='utf-8')
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,'The application could not start. Details were saved to '+str(log),'IC Design Studio',16)
    raise
'''
    zipdata=io.BytesIO()
    with zipfile.ZipFile(zipdata,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('__main__.py',script)
    for name,stub,python in [('ICDesignStudio.exe','w64.exe','pythonw.exe'),('ICDesignStudio-Console.exe','t64.exe','python.exe')]:
        (target/name).write_bytes((lib/stub).read_bytes()+b'#!<launcher_dir>\\python\\'+python.encode()+b'\n'+zipdata.getvalue())
    (target/'START-HERE.txt').write_text(f'IC Design Studio {__version__}\n\nExtract the entire folder, then double-click ICDesignStudio.exe.\nKeep the app and python folders beside it. Python, Qt and ngspice are included.\n\nStart with Your first waveform in the example gallery, choose Open a copy, and press F5.\nThe gallery has six guided examples. Reopen it through File > Start here / example gallery.\nFor an open PDK, choose Tools > Set up an open PDK; add a folder or the optional adapter collection.\nFor Xschem migration, use File > Import and migrate Xschem project and review the result.\n\nRead app/docs/GETTING_STARTED.md and app/docs/RELEASE_0.21.md.\nThis unsigned portable build targets Windows 10/11 x64. Static packaging checks do not establish native Windows execution.\nUse ICDesignStudio-Console.exe for startup diagnostics.\n',encoding='utf-8')
    shutil.copy2(app/'LICENSE',target/'LICENSE');shutil.copy2(app/'THIRD_PARTY_NOTICES.md',target/'THIRD_PARTY_NOTICES.md')
    notices=target/'app/licenses/distlib';notices.mkdir(exist_ok=True)
    for path in lib.glob('LICENSE*'):shutil.copy2(path,notices/path.name)
    (notices/'SOURCE.txt').write_text('Distlib '+distlib.__version__+'\nhttps://github.com/pypa/distlib/tree/'+distlib.__version__+'\nNative launcher source: PC/launcher.c\n',encoding='utf-8')
    provenance={'application':__version__,'python_archive':{'name':args.python.name,'sha256':hashlib.sha256(args.python.read_bytes()).hexdigest()},'wheels':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in wheels},'launcher':'distlib '+distlib.__version__,'engine':'ngspice 42 console x64','files':{p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}}
    (target/'runtime-manifest.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8');print(target)


if __name__=='__main__':main()
