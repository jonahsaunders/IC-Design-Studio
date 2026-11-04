"""Run a captured physical job in Studio's verified Linux/WSL runtime."""
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
import time
import uuid
from .model import atomic_write, clone, design_digest, digest, file_digest

TOOLS=('magic','netgen','ngspice','klayout')


def available():
    from . import digital_runtime
    runtime=digital_runtime.installed(); data=digital_runtime.manifest()
    if runtime and data and set(TOOLS)<=set(data.get('tools',[])):return runtime
    return None


def prepare(job):
    """Resolve an included or unconfigured physical job on Linux and Windows."""
    if job['settings'].get('type')!='silicon':return job
    mode=job['settings'].get('physical_toolchain','auto')
    config=job['settings'].get('tools',{})
    job['settings'].pop('physical_runtime',None)
    job['settings'].pop('physical_blocked_reason',None)
    if mode=='custom' or (mode=='auto' and (config.get('magic') or config.get('netgen'))):return job
    try:
        if mode not in ('auto','included'):raise ValueError('Unknown physical toolchain selection.')
        if not job['project']['pdk'].get('package_lock',{}).get('files'):
            raise ValueError('Managed physical verification requires a checksummed PDK package.')
        runtime=available()
        if not runtime:raise ValueError('Set up the included physical tools from Tools → Physical tools setup before verification.')
    except (OSError,ValueError) as exc:
        # Preserve the normal queued preflight report for incomplete setup.
        # A synchronous exception would discard its stages and bench identity.
        job['settings']['physical_blocked_reason']=str(exc)
        return job
    job['settings']['physical_runtime']=runtime
    return job


def prepare_simulation(job):
    """Use included IHP OSDI on its native platform, including from Windows."""
    from . import digital_runtime
    from .osdi import managed_models
    managed_models(job['project']['pdk'],digital_runtime.manifest())
    runtime=available()
    if not runtime:raise ValueError('Open Tools → Physical tools setup to prepare the included IHP simulator and verification tools.')
    job['settings']['physical_runtime']=runtime
    job['settings']['managed_osdi']='ihp-sg13g2'
    return job


def stage(job, work, native_work, native_root):
    native=clone(job); pdk=native['project']['pdk']
    source=Path(pdk.get('package_root','')).resolve()
    files=pdk.get('package_lock',{}).get('files',{})
    if not files:raise ValueError('Managed physical verification requires a checksummed PDK package.')
    for relative,sha in files.items():
        if (not isinstance(relative,str) or '\\' in relative or PureWindowsPath(relative).drive
                or PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts):
            raise ValueError('Unsafe PDK asset path: '+str(relative))
        path=(source/relative).resolve()
        if not path.is_relative_to(source) or not path.is_file() or file_digest(path)!=sha:
            raise ValueError('Missing, changed or unsafe PDK asset: '+relative)
        target=work/'pdk'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
        if file_digest(target)!=sha:raise ValueError('PDK asset changed during transfer: '+relative)
    pdk['package_root']=str(PurePosixPath(native_work)/'pdk')
    settings=native['settings'];settings.pop('physical_runtime',None)
    settings['tools']={name:str(PurePosixPath(native_root)/'opt/icstudio/bin'/name) for name in TOOLS}
    if settings.get('managed_osdi'):
        from . import digital_runtime
        from .osdi import managed_models
        models=managed_models(pdk,digital_runtime.manifest())
        folder=PurePosixPath(native_root)/'opt/icstudio/osdi/ihp-sg13g2'
        native['project']['simulation_runtime']={'osdi':[
            dict(path=str(folder/m['output']),sha256=m['sha256'],system='Linux',machine='x86_64') for m in models]}
        native['executable']=settings['tools']['ngspice']
    native.pop('environment',None)
    return native


def receive(source, destination):
    """Require the finished backend's complete artifact inventory and bytes."""
    records=json.loads((source/'physical-artifacts.json').read_text())
    actual={p.relative_to(source).as_posix():file_digest(p) for p in source.rglob('*')
            if p.is_file() and p.name!='physical-artifacts.json'}
    if records!=actual or any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Physical artifacts changed before transfer.')
    shutil.copytree(source,destination,dirs_exist_ok=True)
    for name,sha in records.items():
        if file_digest(destination/name)!=sha:raise ValueError('Physical artifact changed during transfer: '+name)
    return records


def dispatch(job, directory, progress):
    from . import digital_runtime
    from .digital_backend import cancel
    from .engines import execute
    runtime=job['settings']['physical_runtime'];digital_runtime.identity(runtime,full=True)
    if not set(TOOLS)<=set(digital_runtime.manifest().get('tools',[])):
        raise ValueError('This runtime has no physical engines. Install the complete current package.')
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    if runtime['kind']=='wsl':
        native_work='/var/tmp/icstudio-physical/'+token;native_root='/'
        work=Path(runtime['root'])/native_work.lstrip('/');work.mkdir(parents=True)
        command=[shutil.which('wsl.exe') or 'wsl.exe','--distribution',runtime['distro'],'--exec',
                 '/opt/icstudio/bin/python3',native_work+'/backend/entry.py']
    else:
        work=Path(tempfile.mkdtemp(prefix='icstudio-physical-'));native_work=str(work);native_root=runtime['root']
        command=[str(Path(native_root)/'opt/icstudio/bin/python3'),str(work/'backend/entry.py')]
    result=None
    marker=root/'digital-cancel';marker.unlink(missing_ok=True)
    try:
        native=stage(job,work,native_work,native_root)
        backend=work/'backend';backend.mkdir()
        source=digital_runtime.payload_root()/'backend/icstudio'
        if not source.is_dir():source=Path(__file__).parent
        shutil.copytree(source,backend/'icstudio',ignore=shutil.ignore_patterns('assets','__pycache__','*.pyc','*.so','*.dll'))
        atomic_write(backend/'entry.py','from icstudio.digital_backend import supervise\nfrom icstudio.physical_backend import native_run\nraise SystemExit(supervise(native_run))\n')
        atomic_write(work/'native-input.json',json.dumps(native))
        marker_path=digital_runtime.wsl(['--distribution',runtime['distro'],'--exec','wslpath','-a','-u',str(marker)]) if runtime['kind']=='wsl' else str(marker)
        command += [native_work,marker_path]
        metadata={'runtime':runtime,'native_directory':native_work,'native_input_sha256':file_digest(work/'native-input.json')}
        atomic_write(root/'physical-backend.json',json.dumps(metadata,indent=2))
        environment=dict(os.environ)
        for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):environment.pop(key,None)
        def line(text):
            try:
                data=json.loads(text);progress(data.get('progress',.1),data.get('message',data.get('error',text)))
            except ValueError:progress(.1,text)
        try:execute(command,root,timeout=3600,on_line=line,env=environment)
        except BaseException:
            cancel(root)
            deadline=time.monotonic()+5
            while not (work/'supervisor-exit.json').exists() and time.monotonic()<deadline:time.sleep(.1)
            if (work/'supervisor-exit.json').exists() and (work/'output').is_dir():
                shutil.copytree(work/'output',root,dirs_exist_ok=True)
            raise
        metadata['received_files']=receive(work/'output',root)
        shutil.copy2(work/'native-input.json',root/'physical-backend-input.json')
        if file_digest(root/'physical-backend-input.json')!=metadata['native_input_sha256']:
            raise ValueError('Physical job inputs changed in the backend.')
        result=json.loads((root/'physical-backend-result.json').read_text())
        result['settings']=clone(job['settings']);result['design_hash']=design_digest(job['project'])
        result['pdk_hash']=digest(job['project']['pdk'])
        if job['settings'].get('managed_osdi'):
            if 'case_directory' in result:result['case_directory']=str(root)
            result['managed_execution']=metadata
            atomic_write(root/'physical-host-result.json',json.dumps(result,indent=2))
            return result
        result['evidence_directory']=str(root/'physical-flow')
        report=result['silicon_report'];report['native_design_hash']=report['design_hash'];report['design_hash']=result['design_hash']
        for finding in result.get('physical_result',{}).get('issues',[])+report.get('findings',[]):
            if finding.get('source_design_hash')==report['native_design_hash']:
                finding['native_source_design_hash']=finding['source_design_hash']
                finding['source_design_hash']=result['design_hash']
                finding['fingerprint']=digest({k:v for k,v in finding.items() if k!='fingerprint'})
        report['execution']=metadata
        # Preserve the original backend report and artifact inventory verbatim.
        atomic_write(root/'physical-host-result.json',json.dumps(result,indent=2))
        return result
    finally:
        cancel(root)
        if result is not None:shutil.rmtree(work,ignore_errors=True)


def native_run(work):
    from .silicon_flow import job as physical_job
    work=Path(work);job=json.loads((work/'native-input.json').read_text());output=work/'output';output.mkdir()
    progress=lambda fraction,message:print(json.dumps({'progress':fraction,'message':message}),flush=True)
    if job['settings']['type']=='physical_probe':
        from .physical_runtime_probe import run
        result=run(job,output,progress)
    elif job['settings'].get('managed_osdi'):
        kind=job['settings'].get('type')
        if kind=='program':
            from .native_spice import run as simulate
        elif kind=='xschem':
            from .xschem_runtime import run as simulate
        else:
            from .engines import run_ngspice as simulate
        result=simulate(job['project'],job['cell'],job['settings'],job['executable'],output,progress)
    else:result=physical_job(job['project'],job['cell'],job['settings'],output,progress)
    atomic_write(output/'physical-backend-result.json',json.dumps(result,allow_nan=False))
    records={p.relative_to(output).as_posix():file_digest(p) for p in output.rglob('*') if p.is_file()}
    atomic_write(output/'physical-artifacts.json',json.dumps(records,indent=2))
