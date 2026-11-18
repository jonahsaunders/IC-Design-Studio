"""Discover maintained Python modules and compute their release identity."""
import hashlib
import os
from pathlib import Path, PurePosixPath


def python_files(folder, excluded=()):
    for directory, children, files in os.walk(folder):
        children[:] = [name for name in children if name != '__pycache__'
                       and (Path(directory) != folder or name not in excluded)]
        for name in files:
            if name.endswith('.py'):
                yield Path(directory) / name


def is_workflow_module(name):
    """Accept a maintained module by its path relative to icstudio."""
    parts = PurePosixPath(name).parts
    return (name.endswith('.py') and name != 'build_info.py'
            and parts[0] != 'assets' and '__pycache__' not in parts)


def workflow_hash(names, read_bytes):
    """Accept module names relative to icstudio, from disk or a source archive."""
    modules = sorted(name for name in names if is_workflow_module(name))
    digest = hashlib.sha256()
    nested = any('/' in name for name in modules)
    if nested:
        digest.update(b'icstudio/modules/v2\0')
    for name in modules:
        path = name.encode('utf-8')
        content = read_bytes(name)
        if nested:
            digest.update(len(path).to_bytes(4, 'big') + path)
            digest.update(len(content).to_bytes(8, 'big'))
        else:
            # Preserve published identities for older, flat source checkouts.
            digest.update(path)
        digest.update(content)
    return digest.hexdigest()


def checkout_workflow_hash(root):
    package = Path(root) / 'icstudio'
    names = (path.relative_to(package).as_posix() for path in python_files(package, {'assets'}))
    return workflow_hash(names, lambda name: (package / name).read_bytes())
