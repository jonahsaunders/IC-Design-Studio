"""Run an explicitly selected simulator on captured, user-authored inputs."""

import base64
import csv
import hashlib
import math
import re
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath

from .engines import execute
from .model import atomic_write, clone, design_digest, digest, file_digest, now


def relative_file(text):
    path = PurePosixPath(text.replace('\\', '/'))
    if not path.parts or path.is_absolute() or any(
            part in ('.', '..') or not re.fullmatch(r'[\w. +@-]+', part) or part.endswith((' ', '.'))
            or PureWindowsPath(part).is_reserved()
            for part in path.parts):
        raise ValueError('Use a portable relative file path inside the selected deck folder: ' + text)
    return path.as_posix()


def prepare(project, cell_id, executable, arguments, entry, dependencies, outputs, table='', timeout=180):
    exe = shutil.which(executable.strip().strip('"'))
    if not exe or not Path(exe).is_file():
        raise ValueError('Choose the installed simulator executable or enter its full path.')
    entry = Path(entry.strip().strip('"')).resolve()
    root = entry.parent
    if not 1 <= timeout <= 86400 or not 1 <= len(arguments) <= 64 or '{input}' not in arguments:
        raise ValueError('Include {input} as an argument and use a timeout between 1 and 86,400 seconds.')
    names = [relative_file(entry.name), *(relative_file(name) for name in dependencies)]
    expected = [relative_file(name) for name in outputs]
    table = relative_file(table) if table else ''
    if table and table.casefold() not in {name.casefold() for name in expected}:
        expected.append(table)
    if (not expected or len(names) > 128 or len(expected) > 128 or
            len({name.casefold() for name in names + expected}) != len(names) + len(expected)):
        raise ValueError('List one or more distinct output paths and keep them separate from captured inputs.')
    files, hashes, total = {}, {}, 0
    for name in names:
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Find this input within the deck folder: ' + name)
        total += path.stat().st_size
        if total > 16 * 1024 * 1024:
            raise ValueError('Capture at most 16 MiB of explicitly listed input files.')
        data = path.read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        files[name] = base64.b64encode(data).decode('ascii')
    settings = dict(type='external_simulator', entry=names[0], input_hashes=hashes,
                    arguments=list(arguments), outputs=expected, table=table, timeout=timeout)
    job = dict(project=clone(project), cell=cell_id, settings=settings, engine='external_simulator',
               executable=str(Path(exe).resolve()), external_inputs=files)
    from .run_environment import stamp
    job['environment'] = stamp(job)
    return job


def read_table(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('The result CSV exceeds 64 MiB. Review the full file in the run folder.')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream)
        try:
            names = [name.strip() for name in next(reader)]
        except StopIteration as exc:
            raise ValueError('The result CSV has no header.') from exc
        active = [index for index, name in enumerate(names) if name.casefold() not in ('index', 'step')]
        if not 2 <= len(active) <= 128 or len(set(names)) != len(names) or not all(names):
            raise ValueError('The result CSV needs one sweep column and uniquely named numeric traces.')
        columns = [[] for _ in active]
        for row in reader:
            if not row or len(row) == 1 and row[0].startswith('End of '):
                continue
            if len(row) != len(names) or len(columns[0])*len(active) >= 1_000_000:
                raise ValueError('The result CSV has inconsistent rows or too many values.')
            for index, column in zip(active, columns):
                value = float(row[index])
                if not math.isfinite(value):
                    raise ValueError('The result CSV contains a non-finite value.')
                column.append(value)
    x = columns[0]
    if not x or any(a >= b for a, b in zip(x, x[1:])):
        raise ValueError('The result CSV must contain one strictly increasing sweep.')
    return x, names[active[0]], dict(zip((names[i] for i in active[1:]), columns[1:]))


def output_manifest(root, names):
    records = {}
    for name in names:
        path = root/relative_file(name)
        if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.exists():
            raise ValueError('The simulator did not produce the required output inside its run folder: ' + name)
        produced = (p for p in path.rglob('*') if p.is_file()) if path.is_dir() else (path,)
        found = False
        for file in produced:
            if not file.resolve().is_relative_to(root) or file.is_symlink():
                raise ValueError('Simulator output links must resolve within the run folder.')
            if len(records) >= 2048:
                raise ValueError('The simulator produced more than 2,048 requested output files.')
            records[file.relative_to(root).as_posix()] = file_digest(file)
            found |= file.stat().st_size > 0
        if not found:
            raise ValueError('The simulator output has no data: ' + name)
    return records


def run(job, directory, progress):
    settings, project, executable = (job[k] for k in ('settings', 'project', 'executable'))
    root = (Path(directory)/'external').resolve()
    root.mkdir()
    if set(settings['input_hashes']) != set(job['external_inputs']):
        raise ValueError('The captured simulator inputs do not match their manifest.')
    for name, encoded in job['external_inputs'].items():
        data = base64.b64decode(encoded, validate=True)
        if hashlib.sha256(data).hexdigest() != settings['input_hashes'][name]:
            raise ValueError('A captured simulator input changed: ' + name)
        path = root/relative_file(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, data)
    if any((root/relative_file(name)).exists() for name in settings['outputs']):
        raise ValueError('Required outputs cannot already exist in the captured inputs.')
    args = [relative_file(settings['entry']) if arg == '{input}' else arg for arg in settings['arguments']]
    progress(.1, 'Running the selected external simulator')
    log_path = Path(directory)/'engine.log'
    # Stream lines to disk so a long simulator log does not inflate result.json.
    try:
        with log_path.open('w', encoding='utf-8') as stream:
            execute([executable, *args], root, timeout=settings['timeout'],
                    on_line=lambda line: stream.write(line+'\n'))
    except Exception as exc:
        with log_path.open('a', encoding='utf-8') as stream:
            stream.write(str(exc)+'\n')
        raise
    outputs = output_manifest(root, settings['outputs'])
    x, axis, traces = read_table(root/settings['table']) if settings['table'] else ([], '', {})
    with log_path.open('rb') as stream:
        stream.seek(max(0, log_path.stat().st_size - 12000))
        log = stream.read().decode('utf-8', errors='replace')
    progress(1, 'External simulation completed and produced the requested files')
    return dict(schema=1, created=now(), engine=Path(executable).name, engine_hash=file_digest(executable),
                project_id=project['id'], revision=project['revision'], design_hash=design_digest(project),
                pdk_hash=digest(project['pdk']), rule_hash=digest(project['pdk']['layers']), cell_id=job['cell'],
                settings=settings, x=x, x_label=axis, traces=traces, plot_unit='', log=log,
                external_outputs=outputs,
                warnings=['Outputs come from the captured external inputs. The active schematic was used to file the run in project history.'])
