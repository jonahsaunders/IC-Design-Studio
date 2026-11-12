"""Stage complete pinned GF180 9-track views and strict connectivity rules.

Preparation captures reproducible inputs; it does not qualify a design or PDK.
The caller explicitly attaches this collateral to a compatible C or D profile.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import digital_gf180_checks, digital_lvs_reference, digital_platform
from icstudio.model import atomic_write, clone, digest, file_digest

LIBRARY_LOCK = ROOT / 'examples/gf180-connectivity-library-lock.json'
RULE_LOCK = digital_gf180_checks.LOCK
RECIPE = 'gf180-complete-connectivity-collateral-v1'


def inputs(library, rules):
    """Authenticate every view and rule before writing a preparation result."""
    library, rules = Path(library).resolve(strict=True), Path(rules).resolve(strict=True)
    lock = json.loads(LIBRARY_LOCK.read_text(encoding='utf-8'))
    views, files = lock['views'], lock['files']
    if (not views or not {'LICENSE', 'README.rst'} <= files.keys() or
            any(set(v) != {'.cdl', '.gds'} for v in views.values()) or
            set(files) != {'LICENSE', 'README.rst'} | {p for v in views.values() for p in v.values()}):
        raise ValueError('The complete GF180 library lock needs paired views and attribution.')
    for master, view in views.items():
        family = master.removeprefix('gf180mcu_fd_sc_mcu9t5v0__').split('_')[0]
        if (not master.startswith('gf180mcu_fd_sc_mcu9t5v0__') or
                any(p != 'cells/' + family + '/' + master + ext for ext, p in view.items())):
            raise ValueError('Use the canonical captured standard-cell view paths.')
    captured = {}
    for prefix, source, hashes in [('library', library, {p: v['sha256'] for p, v in files.items()}),
                                   ('rules', rules, RULE_LOCK['files'])]:
        for name, sha in hashes.items():
            relative = digital_platform.relative_path(name)
            path = source / relative
            if path.is_symlink() or not path.resolve().is_relative_to(source) or file_digest(path) != sha:
                raise ValueError('GF180 connectivity source differs from its lock: ' + prefix + '/' + name)
            captured[prefix + '/' + name] = dict(path=path, sha256=sha)
    for master, view in views.items():
        digital_lvs_reference.cell_definition((library / view['.cdl']).read_text(encoding='utf-8'), master)
    return lock, captured


def prepare(library, rules, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new collateral directory; preserve existing results.')
    output = output.resolve()
    for source in (Path(library).resolve(strict=True), Path(rules).resolve(strict=True)):
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('Stage connectivity collateral separately from its sources.')
    lock, captured = inputs(library, rules)
    output.mkdir(parents=True, exist_ok=False)
    for name, item in captured.items():
        source = item['path']; target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        if file_digest(target) != item['sha256'] or file_digest(source) != item['sha256']:
            raise ValueError('Connectivity source changed during staging: ' + name)
    (output / 'library-source-lock.json').write_bytes(LIBRARY_LOCK.read_bytes())
    atomic_write(output / 'rule-source-lock.json', json.dumps(RULE_LOCK, indent=2) + '\n')
    paths = [*captured, 'library-source-lock.json', 'rule-source-lock.json']
    record = dict(schema=1, recipe=RECIPE, status='prepared_not_qualified', qualified=False,
        library_revision=lock['revision'], masters=len(lock['views']),
        library_lock_sha256=file_digest(LIBRARY_LOCK), rules_revision=RULE_LOCK['revision'],
        files=digital_platform.inventory(output, paths),
        scope='Complete pinned 9-track independent CDL/GDS views and strict GF180 C/D 5LM connectivity rules. Design verification, operating conditions, runtime installation and tapeout acceptance remain separate.')
    atomic_write(output / 'preparation.json', json.dumps(record, indent=2) + '\n')
    return record


def attach(platform, collateral):
    """Return a new profile bound to complete, authenticated staged collateral."""
    digital_platform.verify(platform)
    if platform['name'] not in ('gf180', 'gf180d') or any(
            key in platform for key in ('lvs_reference', 'gf180_connectivity')):
        raise ValueError('Attach once to an unconfigured GF180 C or D profile.')
    expected = dict(TRACK_OPTION='9t', METAL_OPTION='5LM_1TM', POWER_OPTION='5v0',
                    KVALUE='9' if platform['name'] == 'gf180' else '11')
    for corner in platform['corners']:
        options = digital_platform.implementation_options({**platform, 'corner': corner})
        if any(options.get(key) != value for key, value in expected.items()):
            raise ValueError('Connectivity collateral requires the matching 9-track 5LM C/D stack in every corner.')
    base = Path(platform['root']).resolve(strict=True)
    collateral = Path(collateral).resolve(strict=True)
    if not collateral.is_relative_to(base) or collateral == base:
        raise ValueError('Stage collateral inside the captured platform root.')
    lock, captured = inputs(collateral / 'library', collateral / 'rules')
    record = json.loads((collateral / 'preparation.json').read_text(encoding='utf-8'))
    names = [*captured, 'library-source-lock.json', 'rule-source-lock.json']
    if (record.get('recipe') != RECIPE or record.get('status') != 'prepared_not_qualified' or
            record.get('qualified') is not False or record.get('masters') != len(lock['views']) or
            record.get('library_lock_sha256') != file_digest(LIBRARY_LOCK) or
            record.get('library_revision') != lock['revision'] or record.get('rules_revision') != RULE_LOCK['revision'] or
            record.get('files') != digital_platform.inventory(collateral, names) or
            (collateral / 'library-source-lock.json').read_bytes() != LIBRARY_LOCK.read_bytes() or
            json.loads((collateral / 'rule-source-lock.json').read_text(encoding='utf-8')) != RULE_LOCK):
        raise ValueError('Prepared connectivity metadata differs from the complete source locks.')
    relative = collateral.relative_to(base).as_posix()
    old = [f['path'] for f in platform['files']]
    added = [relative + '/' + name for name in [*names, 'preparation.json']]
    if set(old) & set(added):
        raise ValueError('Connectivity collateral overlaps an existing platform capture.')
    result = clone(platform)
    result['files'] = digital_platform.inventory(base, old + added)
    result['fingerprint'] = digest(result['files'])
    result['lvs_reference'] = dict(recipe=digital_lvs_reference.RECIPE, library_revision=lock['revision'],
        masters={m: relative + '/library/' + v['.cdl'] for m, v in lock['views'].items()})
    result['gf180_connectivity'] = dict(recipe=digital_gf180_checks.RECIPE, rules_root=relative + '/rules',
        masters={m: relative + '/library/' + v['.gds'] for m, v in lock['views'].items()})
    digital_platform.verify(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--rules', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.library, args.rules, args.output), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
