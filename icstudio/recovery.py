"""Session-isolated recovery, with a validated previous snapshot fallback."""
import json
import hashlib
from threading import RLock
from pathlib import Path
from .model import load_project,save_project,atomic_write,now,validate


_verified_bytes={}
_cache_lock=RLock()


def write(project,directory,source=None,*,validated=False):
    """Publish a durable snapshot, preserving a known-valid previous snapshot.

    Only History's constrained operation passes validated=True. General callers
    still validate before writing. A content hash detects changes to the previous
    file before it is trusted; cache misses use the normal validating reader.
    """
    path=Path(directory)/(project['id']+'.icproj');previous=path.with_suffix('.previous.icproj')
    if not validated:validate(project)
    data=(json.dumps(project,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
    if path.exists():
        old=path.read_bytes();fingerprint=hashlib.sha256(old).hexdigest()
        with _cache_lock:valid=_verified_bytes.get(str(path))==fingerprint
        if not valid:
            try:load_project(path);valid=True
            except (ValueError,KeyError,TypeError,json.JSONDecodeError):pass
        if valid:atomic_write(previous,old)
    atomic_write(path,data)
    with _cache_lock:
        _verified_bytes[str(path)]=hashlib.sha256(data).hexdigest()
        while len(_verified_bytes)>8:_verified_bytes.pop(next(iter(_verified_bytes)))
    atomic_write(path.with_suffix('.origin.json'),json.dumps({'name':project['name'],'source':str(source) if source else None,'updated':now()}))
    return path


def read(path):
    path=Path(path)
    try:return load_project(path),False
    except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):return load_project(path.with_suffix('.previous.icproj')),True


def clear(path):
    path=Path(path)
    with _cache_lock:_verified_bytes.pop(str(path),None)
    for p in (path,path.with_suffix('.previous.icproj'),path.with_suffix('.origin.json')):p.unlink(missing_ok=True)


def candidates(root):
    out=[]
    for path in Path(root).rglob('*.icproj'):
        if path.name.endswith('.previous.icproj'):continue
        try:
            p,fallback=read(path);out.append((path,p,fallback))
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):continue
    return sorted(out,key=lambda entry:entry[0].stat().st_mtime,reverse=True)
