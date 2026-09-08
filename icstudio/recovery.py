"""Session-isolated recovery, with a validated previous snapshot fallback."""
import json
from pathlib import Path
from .model import load_project,save_project,atomic_write,now


def write(project,directory,source=None):
    path=Path(directory)/(project['id']+'.icproj');previous=path.with_suffix('.previous.icproj')
    if path.exists():
        try:load_project(path)
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):pass
        else:atomic_write(previous,path.read_bytes())
    save_project(project,path)
    atomic_write(path.with_suffix('.origin.json'),json.dumps({'name':project['name'],'source':str(source) if source else None,'updated':now()}))
    return path


def read(path):
    path=Path(path)
    try:return load_project(path),False
    except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):return load_project(path.with_suffix('.previous.icproj')),True


def clear(path):
    path=Path(path)
    for p in (path,path.with_suffix('.previous.icproj'),path.with_suffix('.origin.json')):p.unlink(missing_ok=True)


def candidates(root):
    out=[]
    for path in Path(root).rglob('*.icproj'):
        if path.name.endswith('.previous.icproj'):continue
        try:
            p,fallback=read(path);out.append((path,p,fallback))
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):continue
    return sorted(out,key=lambda entry:entry[0].stat().st_mtime,reverse=True)
