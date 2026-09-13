"""Execute a captured job in the private Linux runtime, retaining host identity."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from .model import atomic_write, clone, design_digest, file_digest


def translate(job, native_root, work):
    """Only translate infrastructure paths. Never rewrite user RTL/SDC strings."""
    from .digital_design import config
    native = clone(job); settings = native['settings']; settings.pop('runtime')
    settings['tools'] = {name:str(Path(native_root)/path) for name,path in settings['tools'].items()}
    value = config(native['project'],native['cell'])
    if 'platform' in value: value['platform']['root'] = str(Path(work)/'platform-input')
    if 'flow' in settings: settings['flow']['root'] = str(Path(work)/'flow-input')
    if 'upstream' in settings: settings['upstream']['root'] = str(Path(work)/'upstream-input')
    native.pop('environment',None)
    return native


def stage_inputs(job, target):
    from .digital_design import config
    from .digital_platform import stage, verify_flow
    value = config(job['project'],job['cell'])
    if 'platform' in value: stage(value['platform'],target/'platform-input')
    flow = job['settings'].get('flow')
    if flow:
        verify_flow(flow)
        for record in flow['files']:
            p = target/'flow-input'/record['path']; p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(Path(flow['root'])/record['path'],p)
    upstream = job['settings'].get('upstream')
    if upstream:
        from .digital_implementation import verify_upstream
        verify_upstream(upstream)
        destination = target/'upstream-input'; destination.mkdir()
        shutil.copy2(Path(upstream['root'])/'result.json',destination/'result.json')
        for record in upstream['artifacts'].values():
            p = destination/record['path']; p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(Path(upstream['root'])/record['path'],p)
        copy = {**upstream,'root':str(destination)}; verify_upstream(copy)


def cancel(directory):
    """Cooperative cancellation also works after taskkill stops the host worker.

    The native supervisor watches this marker and stops only its child process
    tree. It never terminates a WSL distribution or another Studio job.
    """
    atomic_write(Path(directory)/'digital-cancel','cancel\n')


def dispatch(job, directory, progress):
    from . import digital_flow, digital_runtime
    from .engines import execute
    runtime = job['settings']['runtime']; root = Path(directory).resolve(); root.mkdir(parents=True,exist_ok=True)
    if digital_flow.environment(job) != job['environment']: raise ValueError('The captured digital runtime changed. Prepare a new run.')
    digital_runtime.identity(runtime,full=True)
    token = uuid.uuid4().hex
    if runtime['kind']=='wsl':
        native_work = '/var/tmp/icstudio-jobs/'+token
        work = Path(runtime['root'])/native_work.lstrip('/')
        work.mkdir(parents=True)
        command = [shutil.which('wsl.exe') or 'wsl.exe','--distribution',runtime['distro'],'--exec',
                   '/opt/icstudio/bin/python3',native_work+'/backend/entry.py']
        native_root = '/'
    else:
        # ORFS and Verilator's generated makefiles need a space-free job path.
        work = Path(tempfile.mkdtemp(prefix='icstudio-digital-'))
        native_work = str(work); native_root = runtime['root']
        command = [str(Path(native_root)/'opt/icstudio/bin/python3'),str(work/'backend/entry.py')]
    try:
        stage_inputs(job,work)
        backend = work/'backend'; backend.mkdir()
        source = digital_runtime.payload_root()/'backend/icstudio'
        if not source.is_dir(): source = Path(__file__).parent
        shutil.copytree(source,backend/'icstudio',ignore=shutil.ignore_patterns('assets','__pycache__','*.pyc','*.so','*.dll'))
        atomic_write(backend/'entry.py','from icstudio.digital_backend import supervise\nraise SystemExit(supervise())\n')
        native = translate(job,native_root,native_work)
        atomic_write(work/'native-input.json',json.dumps(native))
        # A token file on the host is visible via /mnt on Windows. The native
        # supervisor gets it through wslpath, which handles spaces and drives.
        marker = root/'digital-cancel'; marker.unlink(missing_ok=True)
        if runtime['kind']=='wsl':
            marker_path = digital_runtime.wsl(['--distribution',runtime['distro'],'--exec','wslpath','-a','-u',str(marker)])
        else: marker_path = str(marker)
        command += [native_work,marker_path]
        atomic_write(root/'backend.json',json.dumps({'runtime':runtime,'native_input_sha256':file_digest(work/'native-input.json'),
                                                    'native_directory':native_work},indent=2))
        env = dict(os.environ)
        for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'): env.pop(key,None)
        def line(text):
            try:
                data = json.loads(text); progress(data.get('progress',.1),data.get('message',data.get('error',text)))
            except ValueError: progress(.1,text)
        timeout = max(1800,job['project'].get('digital',{}).get('timeout',300)*20)
        try: execute(command,root,timeout=timeout,on_line=line,env=env)
        finally:
            output = work/'output'
            if output.is_dir(): shutil.copytree(output,root,dirs_exist_ok=True)
            shutil.copy2(work/'native-input.json',root/'backend-input.json')
        result = json.loads((root/'backend-result.json').read_text())
        metadata = json.loads((root/'backend.json').read_text())
        metadata['native_input_sha256'] = file_digest(root/'backend-input.json')
        atomic_write(root/'backend.json',json.dumps(metadata,indent=2))
        from .digital import source_hash
        from .digital_design import config
        result['settings'] = clone(job['settings']); result['design_hash'] = design_digest(job['project'])
        result['digital_result'].update(source_hash=source_hash(config(job['project'],job['cell'])),
                                        environment=clone(job['environment']),execution={'runtime':runtime,'native_environment':result['digital_result']['environment']})
        result['digital_result']['artifacts']['backend_input'] = digital_flow.artifact(root,root/'backend-input.json')
        result['digital_result']['artifacts']['backend_result'] = digital_flow.artifact(root,root/'backend-result.json')
        digital_flow.validate_result(result,root)
        return result
    finally:
        # On cancellation signal the supervisor before deleting its directory.
        # Keep failed/cancelled native jobs for diagnosis; successful output is
        # already copied and hash-verified on the host.
        cancel(root)
        if 'result' in locals(): shutil.rmtree(work,ignore_errors=True)


def native_run(work):
    from . import digital_flow
    work = Path(work); job = json.loads((work/'native-input.json').read_text())
    os.environ['ICSTUDIO_DIGITAL_NATIVE']='1'
    job['environment'] = digital_flow.environment(job)
    atomic_write(work/'native-input.json',json.dumps(job,indent=2))
    output = work/'output'; output.mkdir()
    result = digital_flow.run(job,output,lambda fraction,message:print(json.dumps({'progress':fraction,'message':message}),flush=True))
    atomic_write(output/'backend-result.json',json.dumps(result))


def supervise():
    """Linux-only supervisor: detect cancellation without a running host worker."""
    import signal
    import subprocess
    import time
    work, marker = sys.argv[1:3]
    if '--native' in sys.argv:
        native_run(work); return 0
    def interrupted(*_): raise InterruptedError('Digital supervisor cancelled.')
    signal.signal(signal.SIGTERM,interrupted)
    proc = subprocess.Popen([sys.executable,sys.argv[0],work,marker,'--native'],start_new_session=True)
    try:
        while proc.poll() is None:
            if Path(marker).exists(): raise InterruptedError('Digital job cancelled.')
            time.sleep(.2)
        return proc.returncode
    finally:
        if proc.poll() is None:
            # Engine commands create their own sessions. Find descendants before
            # stopping the worker so that synthesis/proof children cannot escape.
            rows = subprocess.check_output(['/bin/ps','-e','-o','pid=,ppid='],text=True)
            descendants={proc.pid}; pairs=[tuple(map(int,line.split())) for line in rows.splitlines()]
            for _ in range(len(pairs)):
                more={pid for pid,parent in pairs if parent in descendants}
                if more.issubset(descendants): break
                descendants.update(more)
            for sig in (signal.SIGTERM,signal.SIGKILL):
                for pid in sorted(descendants,reverse=True):
                    try: os.kill(pid,sig)
                    except ProcessLookupError: pass
                if sig==signal.SIGTERM: time.sleep(.5)
            proc.wait()
