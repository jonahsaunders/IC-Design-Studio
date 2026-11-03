"""Recheck the finite installed CMIM gate and its exact distributed bytes."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile

MAX_FILES = 50000
MAX_BYTES = 512 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError('IHP CMIM release evidence: ' + message)


def safe(name):
    require(isinstance(name, str) and name and '\\' not in name, 'invalid relative path')
    parts = name.split('/')
    require(all(part not in ('', '.', '..', 'tmpuxoell2b') and
                not any(ord(c) < 32 or c in ':<>|"?*' for c in part) and
                not part.endswith((' ', '.')) for part in parts), 'unsafe path or alias')
    require(all(part.split('.')[0].upper() not in
                {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1, 10)),
                 *('LPT'+str(i) for i in range(1, 10))} for part in parts), 'reserved path')
    return PurePosixPath(name)


def digest(stream):
    return hashlib.file_digest(stream, 'sha256').hexdigest()


def same_receipt(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def link_destination(name, target):
    require(isinstance(target, str) and target and not target.startswith('/') and '\\' not in target and
            all(p != 'tmpuxoell2b' and not any(ord(c) < 32 or c in ':<>|"?*' for c in p)
                for p in target.split('/')), 'invalid resource link')
    result = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    safe(result)
    return result


def validate_receipt(value, commit):
    require(isinstance(value, dict) and isinstance(commit, str) and
            re.fullmatch('[0-9a-f]{40}', commit) is not None, 'invalid receipt or candidate')
    require(value.get('status') == 'PASS' and value.get('gate') == 'ihp-cmim-installed-reference'
            and value.get('expected_commit') == commit, 'wrong gate, outcome or candidate')
    require(value.get('installed_acceptance') is True and
            all(value.get(key) is False for key in ('qualified', 'full_family', 'release_ready')),
            'incomplete installed claim or expanded qualification claim')
    require(value.get('platform') in ('Windows', 'Linux') and isinstance(value.get('execution_id'), str) and
            re.fullmatch('[0-9a-f]{32}', value['execution_id']) is not None,
            'invalid platform or execution identity')
    counts = value.get('counts')
    require(isinstance(counts, dict) and counts == {'gui_layouts': 1, 'fresh_managed_jobs': 2} and
            all(type(n) is int for n in counts.values()), 'incomplete or mistyped finite selection')
    files = value.get('distribution_files')
    require(isinstance(files, dict) and bool(files), 'missing distributed resource closure')
    names = set()
    for name, sha in files.items():
        safe(name)
        require(name.casefold() not in names and isinstance(sha, str) and
                re.fullmatch('[0-9a-f]{64}', sha) is not None, 'duplicate resource or invalid digest')
        names.add(name.casefold())
    links = value.get('distribution_links')
    require(isinstance(links, dict), 'missing complete resource link inventory')
    for name, target in links.items():
        safe(name)
        require(name.casefold() not in names, 'colliding resource link')
        names.add(name.casefold())
        visited = {name}
        destination = link_destination(name, target)
        while destination in links:
            require(destination not in visited, 'cyclic resource link')
            visited.add(destination)
            destination = link_destination(destination, links[destination])
        require(destination in files, 'resource link leaves the ordinary-file closure')
    exe = 'ICDesignStudio.exe' if value['platform'] == 'Windows' else 'ICDesignStudio'
    require(files.get(exe) == value.get('executable_sha256') and exe in files, 'executable is not bound')
    require(any(name.startswith('_internal/icstudio/assets/') for name in files), 'missing shipped resources')
    return value


def safe_tree(directory):
    directory = Path(directory).absolute()
    require('tmpuxoell2b' not in directory.parts, 'forbidden evidence root')
    for path in (*reversed(directory.parents), directory):
        require(not path.is_symlink() and not path.is_junction(), 'linked evidence root or ancestor')
    require(directory.is_dir(), 'missing evidence root')
    count = size = 0
    names = set()
    for folder, dirs, files in os.walk(directory, topdown=True, followlinks=False):
        require('tmpuxoell2b' not in dirs and 'tmpuxoell2b' not in files, 'forbidden evidence member')
        for name in dirs + files:
            path = Path(folder) / name
            relative = path.relative_to(directory).as_posix()
            safe(relative)
            require(relative.casefold() not in names, 'case-aliased evidence member')
            names.add(relative.casefold())
            require(not path.is_symlink() and not path.is_junction(), 'linked evidence member')
            if name in files:
                require(path.is_file(), 'nonregular evidence member')
                count += 1
                size += path.stat().st_size
                require(count <= MAX_FILES and size <= MAX_BYTES, 'evidence exceeds bounded gate size')


def from_directory(directory, commit):
    safe_tree(directory)
    from scripts.verify_frozen_ihp_cmim import verify_evidence
    actual = validate_receipt(verify_evidence(Path(directory), commit), commit)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate verdict key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite verdict value: ' + value)
    stored = json.loads((Path(directory) / 'verification.json').read_bytes(),
                        object_pairs_hook=unique, parse_constant=invalid)
    require(same_receipt(stored, actual),
            'stored verdict differs from independent raw readback')
    return actual


def from_zip(archive, prefix, commit):
    safe(prefix)
    selected = []
    aliases = set()
    total = 0
    for item in archive.infolist():
        raw = item.orig_filename
        scoped = item.filename.casefold().startswith(prefix.casefold() + '/') or raw.replace('\\', '/').casefold().startswith(prefix.casefold() + '/')
        if not scoped:
            continue
        require(raw == item.filename and item.filename.startswith(prefix + '/'), 'raw ZIP path alias')
        if item.filename == prefix + '/':
            require(item.is_dir() and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFDIR), 'linked archive root')
            require('' not in aliases, 'duplicate archive root'); aliases.add('')
            continue
        relative = item.filename[len(prefix) + 1:]
        name = relative[:-1] if item.is_dir() else relative
        safe(name)
        require(name.casefold() not in aliases, 'duplicate or case-aliased archive member')
        aliases.add(name.casefold())
        mode = stat.S_IFMT(item.external_attr >> 16)
        require(mode in ((0, stat.S_IFDIR) if item.is_dir() else (0, stat.S_IFREG)), 'linked or nonregular ZIP member')
        total += item.file_size
        require(len(selected) < MAX_FILES and total <= MAX_BYTES, 'archive exceeds bounded gate size')
        selected.append((item, name))
    require(selected, 'missing installed CMIM evidence')
    with tempfile.TemporaryDirectory(prefix='cmim-') as folder:
        root = Path(folder)
        require(root.resolve().parent == Path(tempfile.gettempdir()).resolve() and
                root.name.startswith('cmim-'), 'temporary extraction escaped its selected parent')
        for item, name in selected:
            path = root.joinpath(*safe(name).parts)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, path.open('xb') as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
                require(path.stat().st_size == item.file_size, 'truncated archive member')
        return from_directory(root, commit)


def check_distribution(path, platform, receipt):
    validate_receipt(receipt, receipt.get('expected_commit', ''))
    require(platform == receipt['platform'], 'distribution platform differs')
    expected = {'ICDesignStudio/' + name: sha for name, sha in receipt['distribution_files'].items()}
    links = {'ICDesignStudio/' + name: target for name, target in receipt['distribution_links'].items()}
    if platform == 'Windows':
        with zipfile.ZipFile(path) as archive:
            members = {}
            aliases = set()
            for item in archive.infolist():
                require(item.orig_filename == item.filename, 'raw distribution ZIP path alias')
                name = item.filename[:-1] if item.is_dir() else item.filename
                safe(name)
                require(name.casefold() not in aliases, 'duplicate distribution member')
                aliases.add(name.casefold()); members[name] = item
            require({name for name, item in members.items() if not item.is_dir()} == set(expected) | set(links),
                    'distribution file or link inventory differs')
            for name, target in links.items():
                require(stat.S_IFMT(members[name].external_attr >> 16) == stat.S_IFLNK and
                        archive.read(members[name]) == target.encode('utf-8'), 'distributed link differs')
            for name, sha in expected.items():
                require(name in members and not members[name].is_dir(), 'missing distributed input: ' + name)
                for parent in PurePosixPath(name).parents:
                    if str(parent) in members:
                        item = members[str(parent)]
                        require(item.is_dir() and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFDIR), 'linked resource parent')
                item = members[name]
                require(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG), 'linked distributed input')
                with archive.open(item) as stream:
                    require(digest(stream) == sha, 'distributed input differs: ' + name)
    else:
        with tarfile.open(path, 'r:*') as archive:
            members = {}
            for item in archive.getmembers():
                safe(item.name)
                require(item.name not in members, 'duplicate distribution member')
                members[item.name] = item
            require({name for name, item in members.items() if not item.isdir()} == set(expected) | set(links),
                    'distribution file or link inventory differs')
            for name, target in links.items():
                require(members[name].issym() and members[name].linkname == target, 'distributed link differs')
            for name, sha in expected.items():
                item = members[name]
                visited = {name}
                while item.islnk():
                    target = item.linkname
                    safe(target)
                    require(target in expected and target not in visited, 'unsafe or cyclic archive hard link')
                    visited.add(target)
                    item = members[target]
                require(item.isfile(), 'nonregular distributed input: ' + name)
                for parent in PurePosixPath(name).parents:
                    if str(parent) in members:
                        require(members[str(parent)].isdir(), 'linked resource parent')
                with archive.extractfile(item) as stream:
                    require(digest(stream) == sha, 'distributed input differs: ' + name)
