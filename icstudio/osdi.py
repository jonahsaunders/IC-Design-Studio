"""Explicit, checksummed native model runtimes for ngspice."""
from pathlib import Path
import platform, re
from .model import file_digest


def managed_models(technology, manifest):
    """Accept bundled native models only for their exact locked source closure."""
    key=technology.get('package_lock',{}).get('id')
    report=(manifest or {}).get('osdi',{}).get(key,{})
    models=report.get('models',[])
    if (key!='ihp-sg13g2' or report.get('system')!='Linux' or report.get('machine')!='x86_64'
            or report.get('cpu_target')!='generic' or len(models)!=6):
        raise ValueError('Install the current included physical tools with the IHP simulation models.')
    files=technology['package_lock']['files']
    expected={'psp103.osdi','psp103_nqs.osdi','r3_cmc.osdi','mosvar.osdi','cap_cmomi.osdi','cap_cmomf.osdi'}
    if {m.get('output') for m in models}!=expected:raise ValueError('Incomplete IHP model runtime.')
    for model in models:
        dependencies=model.get('dependencies',{})
        if (not dependencies or not re.fullmatch('[0-9a-f]{64}',model.get('sha256',''))
                or any(files.get('libs.tech/verilog-a/'+path)!=sha for path,sha in dependencies.items())):
            raise ValueError('The included IHP models do not match this PDK revision. Use matching compiled models or the bundled IHP package.')
    return models


def configure(paths):
    entries=[]
    for raw in paths:
        path=Path(raw).resolve()
        if not path.is_file() or path.suffix.lower()!='.osdi':raise ValueError('Select compiled .osdi model libraries.')
        if any(c in path.as_posix() for c in ('"','\n','\r','$','`')):raise ValueError('Unsupported OSDI filename.')
        entry={'path':str(path),'sha256':file_digest(path),'system':platform.system(),'machine':platform.machine()}
        if any(Path(e['path']).name==path.name for e in entries):raise ValueError('Duplicate OSDI library name.')
        entries.append(entry)
    return entries


def verified(project, required=True):
    entries=project.get('simulation_runtime',{}).get('osdi',[])
    if not isinstance(entries,list) or len(entries)>64:raise ValueError('Invalid OSDI runtime list.')
    if required and project['pdk'].get('simulation',{}).get('requires_osdi') and not entries:
        raise ValueError('This PDK requires OSDI models. Open Tools → Simulation runtime and select the compiled libraries for this computer.')
    for entry in entries:
        path=Path(entry['path'])
        if not path.is_absolute() or path.suffix.lower()!='.osdi' or any(c in path.as_posix() for c in ('"','\n','\r','$','`')):raise ValueError('Invalid OSDI runtime path.')
        if entry.get('system')!=platform.system() or entry.get('machine')!=platform.machine():
            raise ValueError('OSDI models target a different platform. Configure libraries built for this computer.')
        if not path.is_file() or file_digest(path)!=entry['sha256']:
            raise ValueError('OSDI model is missing or changed: '+path.name+'. Select the intended library again in Simulation runtime.')
    return entries


def preload(project, text, directory, required=True):
    entries=verified(project,required)
    if not entries:return text
    import shutil
    # ngspice 42's pre_osdi loader retains quote characters in filenames.
    # Stage libraries beside the job under simple relative names, which also
    # works when the project/profile directory contains spaces or Unicode.
    root=Path(directory)/'runtime-osdi';root.mkdir(parents=True,exist_ok=True)
    commands=['.control']
    for i,entry in enumerate(entries):
        target=root/('model-'+str(i)+'.osdi');shutil.copyfile(entry['path'],target)
        if file_digest(target)!=entry['sha256']:raise ValueError('OSDI model changed during staging.')
        commands.append('pre_osdi runtime-osdi/'+target.name)
    commands.append('.endc')
    # pre_osdi is processed before netlist parsing, including in batch mode.
    lines=text.splitlines();lines[1:1]=commands
    return '\n'.join(lines)+'\n'
