"""Session-isolated recovery, with a validated previous snapshot fallback."""
import json
import hashlib
import os
from threading import RLock
from pathlib import Path
from .model import atomic_write,now,validate,digest,uid


_verified_bytes={}
_cache_lock=RLock()


def verified_receipt(path, required=True, data=None):
    """Check the published bytes, not the writer's in-memory project.

    Legacy snapshots have no receipt. A new receipt binds an acknowledged write
    to its session file, revision and exact bytes, including valid-but-old file
    replacement. This is an integrity check, not authentication of local files.
    """
    path=Path(path);metadata=path.with_suffix('.origin.json')
    record=json.loads(metadata.read_text(encoding='utf-8')) if metadata.exists() else {}
    if not isinstance(record,dict):raise ValueError('Invalid recovery receipt: '+str(metadata))
    if 'receipt_schema' not in record:
        if required:raise ValueError('Recovery write has no verification receipt: '+str(path))
        return None
    if record['receipt_schema']!=1:raise ValueError('Unsupported recovery receipt: '+str(metadata))
    actual=hashlib.sha256(path.read_bytes() if data is None else data).hexdigest()
    if actual!=record.get('file_sha256'):
        raise ValueError('Recovery file differs from acknowledged write '+str(record.get('write_id'))+
                         ' at revision '+str(record.get('revision'))+'. Expected '+
                         str(record.get('file_sha256'))+', found '+actual+'. File: '+str(path))
    return record


def _project_from_bytes(data,path):
    if len(data)>512*1024*1024:raise ValueError('Project exceeds the 512 MiB native project limit.')
    project=json.loads(data.decode('utf-8'))
    if not isinstance(project,dict):raise ValueError('Recovery project must be an object.')
    package_root=project.get('pdk',{}).get('package_root')
    if package_root and not Path(package_root).is_absolute():
        project['pdk']['package_root']=str((path.parent/package_root).resolve())
    return validate(project)


def _read_verified(path):
    data=path.read_bytes()
    verified_receipt(path,required=False,data=data)
    return _project_from_bytes(data,path)


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
        try:
            verified_receipt(path,required=False,data=old)
            if not valid:_project_from_bytes(old,path)
            valid=True
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):valid=False
        if valid:
            atomic_write(previous,old)
            origin=path.with_suffix('.origin.json')
            if origin.exists():atomic_write(previous.with_suffix('.origin.json'),origin.read_bytes())
            else:previous.with_suffix('.origin.json').unlink(missing_ok=True)
    atomic_write(path,data)
    # Read after replacement before acknowledging it. A valid older JSON file
    # must fail just as decisively as a truncated file.
    expected=hashlib.sha256(data).hexdigest()
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError('Recovery file was replaced before its write could be verified: '+str(path))
    record={'receipt_schema':1,'write_id':uid(),'writer_pid':os.getpid(),
            'project_id':project['id'],'revision':project['revision'],
            'project_hash':digest(project),'file_sha256':expected,
            'name':project['name'],'source':str(source) if source else None,'updated':now()}
    atomic_write(path.with_suffix('.origin.json'),json.dumps(record))
    verified_receipt(path)
    with _cache_lock:
        _verified_bytes[str(path)]=expected
        while len(_verified_bytes)>8:_verified_bytes.pop(next(iter(_verified_bytes)))
    return path


def read(path):
    path=Path(path)
    try:
        return _read_verified(path),False
    except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):
        previous=path.with_suffix('.previous.icproj')
        return _read_verified(previous),True


def clear(path):
    path=Path(path)
    with _cache_lock:_verified_bytes.pop(str(path),None)
    for p in (path,path.with_suffix('.previous.icproj'),path.with_suffix('.origin.json'),
              path.with_suffix('.previous.origin.json')):p.unlink(missing_ok=True)


def candidates(root):
    out=[]
    for path in Path(root).rglob('*.icproj'):
        if path.name.endswith('.previous.icproj'):continue
        try:
            p,fallback=read(path);out.append((path,p,fallback))
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):continue
    return sorted(out,key=lambda entry:entry[0].stat().st_mtime,reverse=True)
