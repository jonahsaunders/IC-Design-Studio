"""Check GF180 C/D written-metal continuity using authenticated job inputs.

Exit 0 means this metal check passed, not complete LVS or tapeout acceptance.
Use an independently pinned library source-lock.json with files and views maps.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import gf180_connectivity
from icstudio.model import atomic_write, file_digest


def run(*, gds, reference_gds, database, preview, result, library_root,
        library_lock, top, variant, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new report path; existing evidence is preserved.')
    paths = {name: Path(path).resolve(strict=True) for name, path in
             dict(database=database, preview=preview, result=result, library_lock=library_lock).items()}
    bindings = {name: dict(path=str(path), sha256=file_digest(path)) for name,path in paths.items()}
    raw = json.loads(paths['result'].read_text(encoding='utf-8-sig'))['digital_result']
    if raw['stage'] != 'finish':
        raise ValueError('Use captured inputs from a finished physical implementation.')
    for role, artifact in (('database', 'database'), ('preview', 'layout_preview')):
        if bindings[role]['sha256'] != raw['artifacts'][artifact]['sha256']:
            raise ValueError('Input differs from the saved job result: ' + role)
    db = json.loads(paths['database'].read_text(encoding='utf-8-sig'))
    lock = json.loads(paths['library_lock'].read_text(encoding='utf-8-sig'))
    if not isinstance(lock.get('revision'), str) or not lock['revision']:
        raise ValueError('The independent cell library must identify its source revision.')
    base = Path(library_root).resolve(strict=True)
    library = {}
    for master in {i['master'] for i in db['instances']}:
        name = lock['views'][master]['.gds']
        rel = PurePosixPath(name)
        if (rel.is_absolute() or rel.as_posix() != name or '\\' in name or ':' in name or
                any(p in ('.', '..') for p in rel.parts)):
            raise ValueError('Invalid library GDS path in the source lock.')
        path = (base/name).resolve(strict=True)
        if not path.is_relative_to(base):
            raise ValueError('Library GDS must remain inside its source directory.')
        library[master] = dict(path=path, sha256=lock['files'][name]['sha256'])
    terminals = gf180_connectivity.capture(reference_gds, paths['database'], paths['preview'],
        library, top_name=top, variant=variant)
    report = gf180_connectivity.inspect(gds, terminals)
    for role,path in paths.items():
        if file_digest(path) != bindings[role]['sha256']:
            raise ValueError('Input changed during connectivity checking: ' + role)
    report.update(input_bindings=bindings, library_revision=lock['revision'],
                  implementation_sha256=file_digest(Path(gf180_connectivity.__file__)))
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output, json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag, help_text in [
        ('gds', 'Written candidate layout to check.'),
        ('reference-gds', 'Hierarchical layout whose cell placements and masks match the captured job.'),
        ('database', 'Captured OpenDB database.json.'),
        ('preview', 'Captured layout_preview.json with the complete port set.'),
        ('result', 'Saved finished job result.json binding database and preview hashes.'),
        ('library-root', 'Independent standard-cell GDS source directory.'),
        ('library-lock', 'Pinned source-lock.json containing revision, files and views.'),
        ('output', 'New report path.')]:
        parser.add_argument('--' + flag, type=Path, required=True, help=help_text)
    parser.add_argument('--top', required=True)
    parser.add_argument('--variant', choices=('C', 'D'), required=True)
    report = run(**vars(parser.parse_args(argv)))
    print(json.dumps({key: report[key] for key in
          ('status', 'qualified', 'placed_cells', 'power_terminals', 'failure_counts')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
