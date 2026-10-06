"""Per-user installation and verification of the included digital runtime.

The archive is produced and qualified by release CI. No package manager, PATH
edit, compiler download or network access is needed on the user's machine.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tarfile
import uuid
from contextlib import contextmanager

from .model import atomic_write, clone, digest, file_digest, now

TOOLS = ('iverilog','vvp','verilator','verilator_coverage','yosys','eqy','sby','bitwuzla','sta','openroad','make','klayout')


def payload_root():
    override = os.environ.get('ICSTUDIO_DIGITAL_PAYLOAD')
    if override: return Path(override).resolve()
    bundled = Path(__file__).parent/'assets/runtime/digital'
    return bundled if bundled.is_dir() else Path(__file__).resolve().parents[1]/'build/digital-payload'


def state_root():
    override = os.environ.get('ICSTUDIO_DIGITAL_STATE')
    if override: return Path(override).resolve()
    if os.name == 'nt': return Path(os.environ['LOCALAPPDATA'])/'ICDesignStudio/digital'
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'ICDesignStudio/digital'


def manifest():
    path = payload_root()/'manifest.json'
    if not path.is_file(): return None
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or data.get('schema') != 1 or data.get('system') != 'ubuntu-24.04-x86_64'
            or data.get('archive') != 'runtime.tar.gz' or not isinstance(data.get('sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}',data['sha256'])):
        raise ValueError('The included digital runtime manifest is invalid. Repair the application installation.')
    if 'platforms' in data:
        from .digital_platform import BUNDLED_PLATFORMS
        if (not isinstance(data['platforms'],list) or not data['platforms']
                or any(not isinstance(name,str) or name not in BUNDLED_PLATFORMS for name in data['platforms'])
                or len(data['platforms'])!=len(set(data['platforms']))
                or data.get('default_platform') not in data['platforms']):
            raise ValueError('The included digital platform catalog is invalid. Repair the application installation.')
    return data


def wsl(args, timeout=60, empty_list_ok=False):
    executable = shutil.which('wsl.exe')
    if not executable: raise ValueError('Windows Linux support is not enabled. Use Enable Windows Linux support, then restart Windows and retry setup.')
    result = subprocess.run([executable]+list(args), capture_output=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    def decode(data):
        return data.decode('utf-16-le' if b'\x00' in data else 'utf-8',errors='replace').strip().lstrip('\ufeff')
    # WSL returns a nonzero code when no distributions are installed. Import is
    # still the next operation, and reports a real feature/kernel error itself.
    if result.returncode and empty_list_ok and list(args)==['--list','--quiet']: return ''
    if result.returncode: raise ValueError('Windows Linux support: '+decode(result.stdout+result.stderr)[-4000:])
    return decode(result.stdout)


def location(data):
    key = data['sha256']
    if os.name == 'nt':
        distro = 'ICStudio-Digital-'+key[:16]+'-'+digest(str(state_root()))[:8]
        return {'kind':'wsl','distro':distro,'root':'\\\\wsl.localhost\\'+distro,'sha256':key}
    if sys.platform != 'linux' or host_platform.machine().lower() not in ('x86_64','amd64'):
        raise ValueError('The included digital runtime supports Linux x64 and Windows x64 with WSL 2.')
    return {'kind':'linux','root':str(state_root()/'runtimes'/key),'sha256':key}


def status():
    try:
        data = manifest()
        if not data:
            if getattr(sys, 'frozen', False):
                return {'state':'error', 'reason':'package_missing',
                        'message':'The digital tools are missing from this application. Reinstall the complete desktop package, or extract the entire portable archive.'}
            return {'state':'unavailable', 'reason':'source_checkout',
                    'message':'This source checkout does not include the digital tools. Get the desktop package for automatic setup, or select Custom tools to use an existing installation.'}
        if not (payload_root()/data['archive']).is_file():
            return {'state':'error', 'reason':'package_missing',
                    'message':'The included digital archive is missing. Reinstall the complete desktop package, or extract the entire portable archive.'}
        record = state_root()/('ready-'+data['sha256']+'.json')
        if not record.is_file(): return {'state':'setup','message':'The included digital tools need their first-run verification.'}
        ready = json.loads(record.read_text()); runtime = location(data)
        if not isinstance(ready,dict):
            return {'state':'setup','message':'The digital setup record is invalid. Run setup again to restore it.'}
        if ready.get('runtime') != runtime or ready.get('manifest') != digest(data) or ready.get('backend') != backend_identity():
            return {'state':'setup','message':'The digital runtime changed. Run setup again.'}
        if 'platforms' in data and ready.get('platforms')!=data['platforms']:
            return {'state':'setup','message':'Not every included platform has passed setup. Run setup again.'}
        if not (Path(runtime['root'])/'opt/icstudio/runtime.json').is_file():
            return {'state':'setup','message':'The digital runtime is missing. Run setup to restore it.'}
        from .digital_platform import PLATFORM_LABELS
        labels=', '.join(PLATFORM_LABELS[name] for name in data.get('platforms',['sky130hd']))
        return {'state':'ready','message':'Ready · '+labels+' · installation checks passed',
                'runtime':runtime,'evidence':ready['evidence']}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return {'state':'error', 'reason':'runtime_error', 'message':str(exc)}


def installed():
    if os.environ.get('ICSTUDIO_DIGITAL_NATIVE') == '1': return None
    value = status()
    return value.get('runtime') if value['state']=='ready' else None


def backend_identity():
    source=payload_root()/'backend/icstudio'
    if not source.is_dir(): source=Path(__file__).parent
    return digest({p.name:file_digest(p) for p in sorted(source.glob('*.py'))})


def identity(runtime, full=False):
    data = manifest()
    if not data or runtime != location(data): raise ValueError('This job uses another digital runtime. Prepare a new run.')
    base = Path(runtime['root']); folder = base/'opt/icstudio'
    internal = json.loads((folder/'runtime.json').read_text())
    if internal.get('files_sha256') != data.get('files_sha256') or file_digest(folder/'files.json') != data['files_sha256']:
        raise ValueError('The digital runtime file lock changed. Repair the installation.')
    records = json.loads((folder/'files.json').read_text())
    if full and runtime['kind']=='wsl':
        code = ('import hashlib,json,pathlib; root=pathlib.Path("/"); '
                'records=json.loads((root/"opt/icstudio/files.json").read_text()); '
                'bad=[name for name,sha in records.items() if not (root/name).is_file() or hashlib.file_digest((root/name).open("rb"),"sha256").hexdigest()!=sha]; '
                'assert not bad, "Changed digital runtime files: "+repr(bad[:10])')
        wsl(['--distribution',runtime['distro'],'--exec','/opt/icstudio/bin/python3','-c',code],timeout=600)
        full=False
    selected = records if full else {name:sha for name,sha in records.items() if name.startswith('opt/icstudio/bin/')}
    for name, sha in selected.items():
        path = base/name
        if not path.is_file() or file_digest(path) != sha:
            raise ValueError('A digital runtime file is missing or changed: '+name)
    return {'sha256':data['sha256'],'files_sha256':data['files_sha256'],'manifest':digest(data)}


def platforms(runtime):
    """Read the locked catalog, with compatibility for SKY130-only payloads."""
    from .digital_platform import validate
    identity(runtime)
    base=Path(runtime['root']).resolve();folder=base/'opt/icstudio';meta=manifest()
    name='platforms.json' if 'platforms' in meta else 'platform.json'
    records=json.loads((folder/'files.json').read_text());path=folder/name
    if not path.is_file() or records.get('opt/icstudio/'+name)!=file_digest(path):
        raise ValueError('The included digital platform catalog changed or is missing. Repair the installation.')
    data=json.loads(path.read_text())
    if name=='platform.json':data={'schema':1,'default':'sky130hd','platforms':{'sky130hd':data}}
    expected=meta.get('platforms',['sky130hd'])
    if (not isinstance(data,dict) or data.get('schema')!=1 or not isinstance(data.get('platforms'),dict)
            or set(data['platforms'])!=set(expected) or data.get('default')!=meta.get('default_platform','sky130hd')):
        raise ValueError('The included digital platform catalog does not match the package.')
    result={}
    for name in expected:
        platform=clone(data['platforms'][name])
        if not isinstance(platform,dict) or platform.get('name')!=name or platform.get('root')!='opt/icstudio/orfs/flow/platforms':
            raise ValueError('Invalid included platform location or identity: '+name)
        platform['root']=str(base/platform['root']);result[name]=validate(platform)
    return result


def platform(runtime, name=None):
    name=name or manifest().get('default_platform','sky130hd')
    values=platforms(runtime)
    if name not in values:raise ValueError('This package does not include '+name+'. Install a package containing that platform.')
    return values[name]


def flow(runtime):
    base = Path(runtime['root'])
    data = json.loads((base/'opt/icstudio/flow.json').read_text())
    data['root'] = str(base/data['root'])
    return data


def defaults(project, cid=None, runtime=None):
    from .digital_design import config, set_config
    runtime = runtime or installed()
    cid = cid or project.get('digital_cell',project['top'])
    value = config(project,cid)
    if runtime and value and 'platform' not in value:
        value = clone(value); value['platform'] = platform(runtime); set_config(project,cid,value)
        return True
    return False


def extract(archive, destination):
    """Only regular files, directories and confined links; no device nodes."""
    with tarfile.open(archive,'r:gz') as source:
        for member in source:
            if member.name.lstrip('./').split('/')[0] in ('dev','proc','sys','run'): continue
            if member.isdev() or member.isfifo(): continue
            source.extract(member, destination, filter='data')


@contextmanager
def setup_lock(state):
    """Serialize setup and post-crash cleanup across Studio processes."""
    state = Path(state); state.mkdir(parents=True,exist_ok=True)
    lock = state/'setup.lock'
    # OS lock is released after a crash, unlike an exclusive sentinel file.
    with lock.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            # Do not write into a byte another process already locked.
            if handle.seek(0,os.SEEK_END)==0:
                handle.write(b'0');handle.flush()
            handle.seek(0)
            try: msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc: raise ValueError('Digital setup is already running in another Studio window.') from exc
        else:
            import fcntl
            try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc: raise ValueError('Digital setup is already running in another Studio window.') from exc
        yield


def _cleanup_partial_install(state):
    """Remove only a journaled, owned unpack directory while holding the lock."""
    journal=state/'partial-install.json'
    if not journal.exists():return True
    if journal.is_symlink():return False
    try:
        record=json.loads(journal.read_text())
        sha=record['sha256']; relative=record['directory']
        if (record.get('schema')!=1 or record.get('kind')!='linux'
                or not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{64}',sha)
                or not isinstance(relative,str)
                or not re.fullmatch('runtimes/'+sha+r'\.install-[0-9a-f]{32}',relative)):
            return False
        directory=state/relative
        if (any(path.is_symlink() or path.is_junction() for path in (directory,directory.parent))
                or not directory.resolve().is_relative_to(state.resolve())):
            return False
        if directory.exists():
            if not directory.is_dir():return False
            shutil.rmtree(directory)
        journal.unlink(missing_ok=True)
        return True
    except (ValueError,KeyError,TypeError):
        return False


def cleanup_partial_install():
    """Reclaim cancelled unpacking after its worker has exited.

    Reacquiring the same OS lock prevents a finished dialog from deleting a
    newer window's active installation. Unknown directories are retained.
    """
    state=state_root()
    with setup_lock(state):return _cleanup_partial_install(state)


def _cleanup_legacy_installs(state, sha):
    """Recover pre-journal unpacking for this verified package only.

    The checksum/UUID directory convention is Studio's reserved namespace in
    its private runtime root. Different packages and other names are retained.
    This helper is called only under setup_lock after archive verification.
    """
    root=state/'runtimes'
    if (not re.fullmatch('[0-9a-f]{64}',sha) or not root.is_dir() or root.is_symlink() or root.is_junction()
            or not root.resolve().is_relative_to(state.resolve())):
        return 0
    count=0
    for directory in root.iterdir():
        if (re.fullmatch(re.escape(sha)+r'\.install-[0-9a-f]{32}',directory.name)
                and directory.is_dir() and not directory.is_symlink() and not directory.is_junction()):
            shutil.rmtree(directory);count+=1
    return count


def setup(progress=lambda message: None):
    data = manifest()
    if not data: raise ValueError('The digital runtime payload is missing. Install a complete Studio release or build the payload with scripts/build_digital_runtime.py.')
    runtime = location(data); state = state_root().resolve()
    with setup_lock(state):
        if not _cleanup_partial_install(state):
            progress('An unrecognized partial setup directory was retained for safety.')
        ready = state/('ready-'+data['sha256']+'.json')
        ready.unlink(missing_ok=True)
        progress('Verifying the included digital package…')
        archive = payload_root()/data['archive']
        if not archive.is_file() or file_digest(archive) != data['sha256']:
            raise ValueError('The included digital archive is missing or damaged. Repair the application installation.')
        if runtime['kind']=='wsl':
            progress('Preparing Studio’s private Windows Linux environment…')
            distributions = wsl(['--list','--quiet'],empty_list_ok=True).splitlines()
            target = state/'wsl'/runtime['distro']; owner = target.with_suffix('.owner.json')
            if runtime['distro'] in [line.strip() for line in distributions]:
                if not owner.is_file() or json.loads(owner.read_text()).get('sha256') != data['sha256']:
                    raise ValueError('A WSL distribution already uses Studio’s runtime name. It has not been modified. Choose a distinct ICSTUDIO_DIGITAL_STATE folder or rename that distribution.')
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():
                    raise ValueError('A WSL installation folder already exists but its distribution was not listed. Restore Windows Linux support and retry. The folder was retained: '+str(target))
                atomic_write(owner,json.dumps({'sha256':data['sha256']}))
                wsl(['--import',runtime['distro'],str(target),str(archive),'--version','2'],timeout=900)
            wsl(['--distribution',runtime['distro'],'--exec','/bin/true'])
        else:
            libc, version = host_platform.libc_ver()
            if libc != 'glibc' or tuple(int(v) for v in version.split('.')[:2]) < (2,39):
                raise ValueError('The included native Linux runtime requires glibc 2.39 or newer (Ubuntu 24.04 baseline).')
            if _cleanup_legacy_installs(state,data['sha256']):
                progress('Removed interrupted unpacking from this package. Restarting setup…')
            target = Path(runtime['root'])
            if any(path.is_symlink() or path.is_junction() for path in (target,target.parent)):
                raise ValueError('The included digital installation folder is a symbolic link or junction. Choose a distinct ICSTUDIO_DIGITAL_STATE folder and retry setup.')
            # Windows short directory names and other state-folder aliases must
            # use the same spelling as the journal's root. Check confinement
            # before integrity repair can rename an existing installation.
            target = target.resolve()
            if not target.is_relative_to(state):
                raise ValueError('The included digital installation folder is outside Studio’s state folder. Choose a distinct ICSTUDIO_DIGITAL_STATE folder and retry setup.')
            if target.is_dir():
                try: identity(runtime,full=True)
                except (OSError,ValueError,KeyError):
                    progress('Retaining the damaged installation for diagnosis and restoring the included package…')
                    target.rename(target.with_name(target.name+'.damaged-'+uuid.uuid4().hex))
            if not target.is_dir():
                progress('Unpacking the included tools and digital platforms…')
                target.parent.mkdir(parents=True,exist_ok=True)
                temporary = target.with_name(target.name+'.install-'+uuid.uuid4().hex)
                journal=state/'partial-install.json'
                atomic_write(journal,json.dumps({'schema':1,'kind':'linux','sha256':data['sha256'],
                                                'directory':temporary.relative_to(state).as_posix()}))
                temporary.mkdir()
                try: extract(archive,temporary); temporary.rename(target)
                finally:
                    shutil.rmtree(temporary,ignore_errors=True)
                    if not temporary.exists():journal.unlink(missing_ok=True)
        progress('Checking installed files…'); identity(runtime,full=True)
        progress('Running the installation acceptance design…')
        from .digital_setup_probe import qualify
        evidence = state/'checks'/uuid.uuid4().hex
        qualification=qualify(runtime,evidence,progress)
        if 'platforms' in data and (not isinstance(qualification,dict) or qualification.get('status')!='PASS'
                                   or qualification.get('platforms')!=data['platforms']):
            raise ValueError('Installation checks did not qualify every included platform.')
        if {'magic','netgen','ngspice'} <= set(data.get('tools',[])):
            from .physical_runtime_probe import qualify as qualify_physical
            progress('Checking DRC, strict LVS and deliberate physical failures…')
            qualify_physical(runtime,evidence/'physical-tools',progress)
        record = {'runtime':runtime,'manifest':digest(data),'backend':backend_identity(),'checked':now(),'evidence':str(evidence)}
        if 'platforms' in data:record['platforms']=qualification['platforms']
        atomic_write(ready,json.dumps(record,indent=2))
        progress('Ready. The included digital engines and platforms passed the installation checks.')
        return record


def main():
    try:
        setup(lambda message: print(json.dumps({'message':message}),flush=True)); return 0
    except Exception as exc:
        print(json.dumps({'error':str(exc)}),flush=True); return 1
