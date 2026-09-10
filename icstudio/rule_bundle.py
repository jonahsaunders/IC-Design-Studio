"""Snapshot an explicitly selected local rule folder for reproducible batch jobs."""
from pathlib import Path, PurePosixPath
from .model import digest, atomic_write


def check(bundle):
    files=bundle.get('files',{})
    if bundle.get('version')!=1 or not 1<=len(files)<=256 or bundle.get('entry') not in files:raise ValueError('Invalid rule bundle entry or file count.')
    size=0
    for name,text in files.items():
        path=PurePosixPath(name)
        if not name or '\\' in name or ':' in name or path.is_absolute() or any(v in ('.','..') for v in path.parts) or path.as_posix()!=name:
            raise ValueError('Rule bundle paths must stay within the selected folder.')
        if not isinstance(text,str) or len(text.encode('utf-8'))>2_000_000:raise ValueError('Each bundled text file must be at most 2 MB.')
        size+=len(text.encode('utf-8'))
    if size>16_000_000:raise ValueError('The rule bundle exceeds 16 MB.')
    return bundle


def capture(entry,root=None):
    entry=Path(entry).resolve();root=Path(root).resolve() if root else entry.parent
    if not entry.is_relative_to(root) or not entry.is_file():raise ValueError('Select a rule entry inside the chosen folder.')
    allowed={'.drc','.rb','.lydrc','.lvs','.lylvs','.json','.yaml','.yml','.csv','.txt','.lyp'};files={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Rule bundles cannot contain symbolic links; copy the dependency into the rule folder.')
        if not path.is_file() or path.suffix.lower() not in allowed:continue
        if path.stat().st_size>2_000_000:raise ValueError('A rule dependency exceeds 2 MB: '+path.name)
        files[path.relative_to(root).as_posix()]=path.read_text(encoding='utf-8')
        if len(files)>256 or sum(len(v.encode('utf-8')) for v in files.values())>16_000_000:raise ValueError('The rule folder exceeds the 256-file / 16 MB bundle budget.')
    return check({'version':1,'entry':entry.relative_to(root).as_posix(),'files':files})


def materialize(bundle,expected,root):
    check(bundle)
    if digest(bundle)!=expected:raise ValueError('The planned rule bundle changed. Capture it again.')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()):raise ValueError('Materialize rules in a new empty directory.')
    for name,text in bundle['files'].items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);atomic_write(path,text)
    return root/bundle['entry']
