"""Bind the release payload to the selected frozen pw2dn acceptance receipts.

This checks receipt continuity; the independent native auditor remains the
authority for numerical and model validation, and its complete output is kept.
"""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import tarfile
import zipfile

FILES = ('verification.json', 'gui-verification.json', 'native-verification.json',
         'native-references/verification.json', 'expected.json', 'readback-input.json',
         'native-inputs.json', 'gui/report.json', 'gui/prelaunch.json',
         'gui/new/project.icproj', 'gui/new/schematic.spice', 'native/report.json',
         'invocation.json', 'reference-invocation.json',
         'native-references/reference-report.json', 'native-references/expected-inputs.json')

def digest(data):
    return hashlib.sha256(data).hexdigest()


def bundled_runtime(native_input, native_report):
    """Map the actually accepted runtime closure into portable archive members."""
    def require(ok, message):
        if not ok: raise ValueError('pw2dn runtime: ' + message)
    runtime = native_input['runtime']
    platform = {'win32': 'Windows', 'linux': 'Linux'}.get(runtime['platform'])
    require(platform is not None, 'unsupported platform')
    path_type = PureWindowsPath if platform == 'Windows' else PurePosixPath
    def absolute(value):
        require(isinstance(value, str) and value, 'missing path')
        text = value.replace('\\', '/') if platform == 'Windows' else value
        if platform == 'Windows':
            require(bool(re.match(r'^[A-Za-z]:/', text)), 'absolute drive path required')
            parts = text[3:].split('/')
        else:
            require(text.startswith('/') and '\\' not in text, 'absolute POSIX path required')
            parts = text[1:].split('/')
        require(all(part not in ('', '.', '..') for part in parts), 'path alias')
        require(all(not any(ord(c) < 32 for c in part) for part in parts), 'control character in path')
        if platform == 'Windows':
            require(all(not any(c in part for c in ':<>|"?*') and not part.endswith((' ', '.'))
                        for part in parts), 'Windows path alias')
        return path_type(text)
    def digest(value):
        require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'invalid digest')
        return value
    root = absolute(native_input['resource_root'])
    require(root.name == '_internal', 'resource layout differs')
    engine = absolute(native_input['engine'])
    expected_engine = root / 'icstudio/assets/runtime/ngspice' / ('ngspice.exe' if platform == 'Windows' else 'ngspice')
    require(engine == expected_engine and absolute(runtime['engine']) == engine, 'engine resource mapping differs')
    require(runtime['sha256'] == native_input['engine_sha256'], 'engine digest differs')
    require(native_report['runtime_before'] == native_report['runtime_after'] == runtime,
            'accepted runtime captures differ')
    require(absolute(native_report['resource_root']) == root, 'producer resource mapping differs')
    require(isinstance(runtime['files'], dict) and runtime['files'], 'missing runtime files')
    files = {}; spellings = {}
    def add(path, sha):
        relative = path.relative_to(root).as_posix(); key = relative.casefold() if platform == 'Windows' else relative
        require(key not in spellings or spellings[key] == relative, 'case alias')
        require(relative not in files or files[relative] == sha, 'conflicting runtime digest')
        spellings[key] = relative; files[relative] = digest(sha)
    for name, sha in runtime['files'].items():
        path = absolute(name); digest(sha)
        if path.is_relative_to(root): add(path, sha)
        else:
            require(platform == 'Linux' and str(path) in ('/usr/bin/ldd', '/etc/ld.so.cache'),
                    'unreviewed external runtime file')
    require(files.get(engine.relative_to(root).as_posix()) == native_input['engine_sha256'], 'engine missing from runtime files')
    require('icstudio/assets/runtime/ngspice/spinit' in files, 'initializer missing')
    dependencies = runtime['elf_dependencies']
    require(isinstance(dependencies, dict), 'missing ELF dependency map')
    if platform == 'Windows':
        require(not dependencies and 'icstudio/assets/runtime/ngspice/libomp140.x86_64.dll' in files,
                'Windows runtime closure differs')
    else:
        core = {'libc.so.6', 'libm.so.6', 'ld-linux-x86-64.so.2'}
        bundled = {'libgcc_s.so.1', 'libgomp.so.1', 'libstdc++.so.6', 'libreadline.so.8', 'libtinfo.so.6'}
        names = set()
        for name, row in dependencies.items():
            path = absolute(name); resolved = absolute(row['resolved']); sha = digest(row['sha256'])
            require(path.name not in names, 'duplicate ELF soname'); names.add(path.name)
            if path.is_relative_to(root):
                require(path == resolved and path.parent == root and path.name in bundled,
                        'unreviewed bundled ELF alias or layout')
                add(path, sha)
            else:
                require(path.name in core and not resolved.is_relative_to(root) and resolved.name == path.name,
                        'external non-system ELF dependency')
        require(names == core | bundled, 'incomplete exact ELF dependency closure')
    return platform, dict(sorted(files.items()))

def validate(files, commit):
    def require(ok, message):
        if not ok: raise ValueError('pw2dn evidence: ' + message)
    require(set(files) == set(FILES), 'missing or extra receipt input')
    require(bool(re.fullmatch('[0-9a-f]{40}', commit)), 'invalid commit')
    try:
        read = lambda name: json.loads(files[name])
        combined, gui, native = (read(n) for n in FILES[:3])
        reference, expected, gui_input, native_input = (read(n) for n in FILES[3:7])
        gui_report, prelaunch, native_report = read(FILES[7]), read(FILES[8]), read(FILES[11])
        invocation, ref_invocation = read(FILES[12]), read(FILES[13])
        eid = combined['execution_id']
        require(bool(re.fullmatch('[0-9a-f]{32}', eid)), 'invalid execution identity')
        require(combined['status'] == 'PASS_FROZEN_GUI_AND_NATIVE' and combined['commit'] == commit, 'combined status or commit differs')
        require(gui['status'] == 'PASS_FROZEN_GUI_LIFECYCLE_ONLY' and native['status'] == 'PASS_FROZEN_NATIVE_ELECTRICAL' and native == reference, 'component verdict differs')
        require(all(native.get('expected', {}).get(key) == value for key, value in native_input.items()), 'native audit inputs differ')
        require(read(FILES[15]) == native['expected'], 'reference audit inputs differ')
        require(native['reader_sha256'] == native_input['source_files']['scripts/audit_installed_sky130_pw2dn_native.py'], 'native reader identity differs')
        require(native['reference_report_sha256'] == native['expected']['reference_report_sha256'] == digest(files[FILES[14]]), 'reference report differs')
        require((native['conditions'], native['geometries'], native['application_runs'], native['literal_runs'], native['detected_faulted_instances']) == (9, 3, 45, 18, 81), 'native selection differs')
        for key, name in (('gui_verification_sha256', FILES[1]), ('native_verification_sha256', FILES[2])):
            require(combined[key] == digest(files[name]), 'combined component hash differs')
        for obj in (expected, gui_input, native_input, gui_report, prelaunch, native_report, invocation, ref_invocation):
            require(obj['execution_id'] == eid, 'execution identity differs')
        require(expected['commit'] == gui_input['commit'] == native_input['commit'] == commit, 'input commit differs')
        for key in ('executable_sha256', 'engine_sha256'):
            require(bool(re.fullmatch('[0-9a-f]{64}', expected[key])) and expected[key] == gui_input[key] == native_input[key], 'binary input identity differs')
        require(gui_report['executable_sha256'] == prelaunch['executable_sha256'] == expected['executable_sha256'], 'GUI executable identity differs')
        require(native_report['engine_sha256'] == expected['engine_sha256'], 'native engine identity differs')
        for obj in (gui_report, native_report):
            require(obj['frozen'] is True and obj['build']['frozen'] is True and obj['build']['dirty'] is False and obj['build']['commit'] == commit, 'frozen build differs')
        require(gui_report['status'] == 'PASS_GUI_LIFECYCLE' and native_report['status'] == 'PASS_NATIVE_PRODUCTION_ONLY', 'producer status differs')
        require(native_input['mode'] == 'installed' and native_input['pilot'] is False, 'installed full selection required')
        for obj in (invocation, ref_invocation):
            require(obj['status'] == 'PASS' and type(obj['returncode']) is int and obj['returncode'] == 0, 'child invocation failed')
        for obj, key, name in ((gui, 'report_sha256', FILES[7]), (gui, 'project_sha256', FILES[9]),
                (gui, 'spice_sha256', FILES[10]), (gui, 'readback_input_sha256', FILES[5]),
                (gui_input, 'prelaunch_sha256', FILES[8]), (native_input, 'native_report_sha256', FILES[11]),
                (native_input, 'gui_verification_sha256', FILES[1]), (native_input, 'gui_report_sha256', FILES[7]),
                (native_input, 'selected_project_sha256', FILES[9]), (native_input, 'selected_export_sha256', FILES[10])):
            require(obj[key] == digest(files[name]), 'referenced receipt hash differs: ' + name)
        require(native_report['selected_project_sha256'] == gui['project_sha256'], 'native project differs')
        require(expected['runtime'] == gui_input['runtime'] == native_input['runtime'], 'prelaunch runtime differs')
        runtime_platform, runtime_files = bundled_runtime(native_input, native_report)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('pw2dn evidence invalid: ' + str(exc)) from exc
    return {'status': combined['status'], 'commit': commit, 'execution_id': eid,
            'combined_sha256': digest(files[FILES[0]]),
            'runtime_platform': runtime_platform, 'bundled_runtime_files': runtime_files,
            'executable_sha256': expected['executable_sha256'], 'engine_sha256': expected['engine_sha256'],
            'gui_verification_sha256': combined['gui_verification_sha256'],
            'native_verification_sha256': combined['native_verification_sha256']}

def from_directory(directory, commit):
    directory = Path(directory)
    return validate({name: (directory / name).read_bytes() for name in FILES}, commit)

def from_zip(archive, prefix, commit):
    # ZipFile.read rejects missing members; require each selected member once.
    names = archive.namelist()
    for name in FILES:
        if names.count(prefix + '/' + name) != 1:
            raise ValueError('pw2dn evidence missing or duplicated in archive: ' + name)
    return validate({name: archive.read(prefix + '/' + name) for name in FILES}, commit)

def check_distribution(archive_path, platform, receipt):
    """Bind selected executable and engine to unique regular archive members."""
    root = 'ICDesignStudio/'
    executable = root + ('ICDesignStudio.exe' if platform == 'Windows' else 'ICDesignStudio')
    engine = root + '_internal/icstudio/assets/runtime/ngspice/' + ('ngspice.exe' if platform == 'Windows' else 'ngspice')
    if receipt['runtime_platform'] != platform: raise ValueError('pw2dn runtime platform differs')
    wanted = {root + '_internal/' + name: sha for name, sha in receipt['bundled_runtime_files'].items()}
    if wanted.get(engine) != receipt['engine_sha256']: raise ValueError('pw2dn archived engine closure differs')
    wanted[executable] = receipt['executable_sha256']
    def safe(name):
        # Permit the conventional final slash for directories only; do not let
        # path normalization hide aliases which can overwrite selected files.
        parts = name.rstrip('/').split('/')
        return bool(name) and not name.startswith('/') and not name.endswith('//') and '\\' not in name and all(
            part not in ('', '.', '..') and (platform != 'Windows' or (
                not any(ch in part for ch in ':<>|"?*') and not part.endswith((' ', '.')) and
                part.split('.', 1)[0].upper() not in
                {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}))
            for part in parts)
    ancestors = {str(parent) for name in wanted for parent in PurePosixPath(name).parents if str(parent) != '.'}
    def compare(stream, expected):
        return hashlib.file_digest(stream, 'sha256').hexdigest() == expected
    if platform == 'Windows':
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if not all(safe(m.filename) for m in members): raise ValueError('Unsafe distribution member')
            normalized = [str(PurePosixPath(m.filename)).casefold() for m in members]
            if len(normalized) != len(set(normalized)): raise ValueError('Ambiguous Windows distribution member')
            wanted_ancestors = {name.casefold() for name in ancestors}
            for member in members:
                if str(PurePosixPath(member.filename)).casefold() in wanted_ancestors:
                    if not member.is_dir() or stat.S_ISLNK(member.external_attr >> 16):
                        raise ValueError('Linked or non-directory pw2dn distribution ancestor: ' + member.filename)
            for name, expected in wanted.items():
                found = [m for m in members if m.filename == name]
                if len(found) != 1 or found[0].is_dir() or stat.S_ISLNK(found[0].external_attr >> 16):
                    raise ValueError('Missing, linked or duplicate pw2dn distribution member: ' + name)
                with archive.open(found[0]) as stream:
                    if not compare(stream, expected): raise ValueError('pw2dn distribution binary differs: ' + name)
    elif platform == 'Linux':
        seen = set(); paths = set()
        with tarfile.open(archive_path, 'r|*') as archive:
            for member in archive:
                if not safe(member.name): raise ValueError('Unsafe distribution member')
                normalized = str(PurePosixPath(member.name))
                if normalized in paths: raise ValueError('Ambiguous Linux distribution member: ' + member.name)
                paths.add(normalized)
                if normalized in ancestors and not member.isdir():
                    raise ValueError('Linked or non-directory pw2dn distribution ancestor: ' + member.name)
                if member.name in wanted:
                    if member.name in seen or not member.isfile(): raise ValueError('Linked or duplicate pw2dn distribution member: ' + member.name)
                    seen.add(member.name)
                    with archive.extractfile(member) as stream:
                        if not compare(stream, wanted[member.name]): raise ValueError('pw2dn distribution binary differs: ' + member.name)
        if seen != set(wanted): raise ValueError('Missing pw2dn distribution binary')
    else:
        raise ValueError('Unsupported pw2dn distribution platform')
