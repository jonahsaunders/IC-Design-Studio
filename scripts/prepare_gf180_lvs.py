"""Stage the source-locked GF180 physical-substrate/diode LVS recipe.

This preserves the upstream checkout and records every changed byte. Use this
deck with an independent metal-continuity check: LVS alone can miss an isolated
power port. Preparing a deck is not a connectivity or foundry acceptance result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import atomic_write, file_digest
from scripts.gf180_cdl_diodes import RUBY_GEOMETRY_GUARD

LOCK = ROOT / 'examples/gf180-lvs-source-lock.json'
RECIPE = 'gf180-physical-substrate-diode-v1'
CONNECTIONS = 'klayout/lvs/rule_decks/general_connections.lvs'
ENTRY = 'klayout/lvs/gf180mcu.lvs'


def patch_connections(text):
    implicit = "connect_implicit('*')"
    substrate = 'connect_global(sub, substrate_name)'
    if text.count(implicit) != 1 or text.count(substrate) != 1:
        raise ValueError('The upstream GF180 connection declarations changed.')
    if 'soft_connect_global' in text or 'top_level(' in text:
        raise ValueError('GF180 connection policy has already been modified.')
    return text.replace(implicit, '# Require physical connections.\ntop_level(true)').replace(
        substrate, substrate + '\nsoft_connect_global(ptap, substrate_name)')


def patch_comparison(text):
    if text.count('\ncompare\n') != 1 or 'icstudio_gf180_diode_geometry' in text:
        raise ValueError('The upstream GF180 comparison section changed.')
    guard = RUBY_GEOMETRY_GUARD + '\n[netlist, schematic].each { |nl| logger.info("ICSTUDIO_DIODE_GEOMETRY=" + icstudio_gf180_diode_geometry(nl).join(",")) }\n'
    return text.replace('\ncompare\n', '\n' + guard + '\ncompare\n')


def prepare(pv, output):
    """Validate every input before creating a new, attributed rule directory."""
    pv = Path(pv).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new output directory; existing results are preserved.')
    output = output.resolve()
    if output.is_relative_to(pv) or pv.is_relative_to(output):
        raise ValueError('Stage GF180 rules separately from their source checkout.')
    lock_bytes = LOCK.read_bytes()
    lock = json.loads(lock_bytes)
    inputs = {}
    for name, expected in lock['files'].items():
        relative = PurePosixPath(name)
        if (relative.is_absolute() or relative.as_posix() != name or '\\' in name
                or ':' in name or any(part in ('.', '..') for part in relative.parts)):
            raise ValueError('Invalid GF180 source-lock path.')
        path = pv / name
        if path.is_symlink() or not path.resolve().is_relative_to(pv):
            raise ValueError('GF180 source dependencies must remain inside the checkout.')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('GF180 source does not match its pinned revision: ' + name)
        inputs[name] = data
    required = {'LICENSE', 'AUTHORS', ENTRY, CONNECTIONS}
    if not required <= inputs.keys():
        raise ValueError('GF180 source lock is missing required rules or attribution.')
    changed = dict(inputs)
    for name, transform in ((CONNECTIONS, patch_connections), (ENTRY, patch_comparison)):
        changed[name] = transform(inputs[name].decode('utf-8')).encode('utf-8')
    if {name for name in inputs if inputs[name] != changed[name]} != {ENTRY, CONNECTIONS}:
        raise ValueError('Unexpected GF180 rule changes.')
    output.mkdir(parents=True, exist_ok=False)
    for name, data in changed.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / 'source-lock.json').write_bytes(lock_bytes)
    record = dict(schema=1, recipe=RECIPE, status='prepared_not_qualified', qualified=False,
        repository=lock['repository'], revision=lock['revision'], source_lock_sha256=hashlib.sha256(lock_bytes).hexdigest(),
        implementation_sha256=file_digest(Path(__file__)),
        diode_guard_sha256=hashlib.sha256(RUBY_GEOMETRY_GUARD.encode()).hexdigest(),
        files={name: dict(source_sha256=hashlib.sha256(inputs[name]).hexdigest(),
                          staged_sha256=file_digest(output / name), changed=inputs[name] != data)
               for name, data in changed.items()},
        entry=ENTRY, supported_reference_scope='GF180 C/D 5LM 9-track standard-cell reference layouts; broader devices and workflows require their own acceptance.',
        requirements=['Use a KLayout engine with soft-connection support, qualified by native controls.',
                      'Normalize supported positional diode CDL with the strict GF180 diode adapter.',
                      'Require both strict native LVS and independent written-metal continuity; neither is sufficient alone.',
                      'Retain source, engine, layout, reference and comparison identities and all extraction diagnostics.',
                      'Complete geometry, fill, extracted function/timing and installed-runtime acceptance separately.'],
        scope='Reproducible staging of the experimentally audited substrate and diode comparison corrections. No warning waiver, foundry signoff or production qualification is issued.')
    atomic_write(output / 'recipe.json', json.dumps(record, indent=2, allow_nan=False) + '\n')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pv', required=True, type=Path, help='Pinned upstream GF180 physical-verification checkout.')
    parser.add_argument('--output', required=True, type=Path, help='New staging directory, outside the source checkout.')
    args = parser.parse_args(argv)
    record = prepare(args.pv, args.output)
    print(json.dumps(record, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
