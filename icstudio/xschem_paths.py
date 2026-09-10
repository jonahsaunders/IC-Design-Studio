"""Declarative library discovery. Does not source configuration or launch tools."""
from pathlib import Path, PurePosixPath
import os, shutil, sys


def library_folders(paths):
    """Keep explicit search order; append familiar installation subdirectories."""
    explicit=[];extra=[]
    for raw in paths:
        if not str(raw).strip():continue
        p=Path(str(raw).strip().strip('"')).expanduser().resolve()
        if p not in explicit:explicit.append(p)
        for suffix in ('devices','xschem_library','xschem_library/devices',
                       'share/xschem/xschem_library','share/xschem/xschem_library/devices',
                       'libs.tech/xschem'):
            q=p/suffix
            if q.is_dir():extra.append(q.resolve())
        # Selecting the devices/symbols directory itself also supports qualified
        # references such as devices/code_shown.sym or symbols/nfet.sym.
        if p.name in ('devices','symbols'):extra.append(p.parent)
    return [str(p) for p in dict.fromkeys(explicit+extra)]


def default_libraries():
    candidates=[p for p in os.environ.get('XSCHEM_LIBRARY_PATH','').split(os.pathsep) if p]
    shared=os.environ.get('XSCHEM_SHAREDIR')
    if shared:candidates.append(shared)
    executable=shutil.which('xschem')
    if executable:
        p=Path(executable).resolve();candidates.extend([p.parent,p.parent.parent])
    candidates.extend(['/usr/share/xschem','/usr/local/share/xschem'])
    if sys.platform=='win32':
        for key in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
            if os.environ.get(key):candidates.append(str(Path(os.environ[key])/'xschem'))
    root=os.environ.get('PDK_ROOT');pdk=os.environ.get('PDK')
    if root and pdk:candidates.append(str(Path(root)/pdk))
    return library_folders(p for p in candidates if Path(p).expanduser().is_dir())


def reference_folder(reference,selected):
    """Infer a library root from a user-selected file with a matching suffix."""
    p=Path(selected).resolve();ref=PurePosixPath(reference.replace('\\','/'))
    if ref.is_absolute() or ':' in reference or '..' in ref.parts:return str(p.parent)
    parts=ref.parts
    if parts and tuple(v.casefold() for v in p.parts[-len(parts):])==tuple(v.casefold() for v in parts):
        return str(p.parents[len(parts)-1])
    return str(p.parent)


def dependency_hint(reference):
    ref=reference.replace('\\','/')
    if ref.startswith('/') or (len(ref)>1 and ref[1]==':'):
        return 'Path from another installation? Select this row and use Locate selected file… to map its local copy.'
    if '/' in ref:
        parent=ref.rsplit('/',1)[0]
        return 'Add the folder containing '+parent+'/ or locate this file directly.'
    return 'Add the folder containing this file. For standard symbols, choose Xschem’s devices folder or installation folder.'
