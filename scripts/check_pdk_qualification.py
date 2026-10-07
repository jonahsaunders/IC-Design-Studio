"""Validate coverage bookkeeping, never infer process qualification from it."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / 'docs/qualification/pdk-matrix.json'
TARGETS = ('sky130A', 'gf180mcuC', 'gf180mcuD', 'ihp-sg13g2')
STATUSES = {'not_run', 'partial', 'failed', 'needs_definition', 'unsupported'}
COMMON_TESTS = {
    'inventory', 'operating-envelope', 'tool-install', 'rule-controls',
    'device-interface', 'device-simulation', 'device-physical', 'source-completeness',
    'rc-reference', 'rc-corners', 'coupling', 'analog-mirror', 'analog-differential',
    'analog-amplifier', 'analog-reference', 'analog-oscillator', 'analog-noise',
    'analog-statistics', 'digital-controller', 'mixed-signal', 'clock-reset',
    'chip-assembly', 'chip-erc', 'chip-esd-latchup', 'chip-em-ir', 'chip-io-package',
    'desktop', 'independent-export', 'foundry-acceptance',
}
EXTRA_TESTS = {
    'sky130A': {'sky130-full-rules'},
    'gf180mcuC': {'gf180-geometry', 'gf180-density'},
    'gf180mcuD': {'gf180-geometry', 'gf180-density', 'digital-profile'},
    'ihp-sg13g2': {'ihp-fill', 'ihp-bipolar', 'ihp-rf'},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def family(name, device):
    """Qualification batches; keep the original catalog category separately."""
    name = name.lower()
    if 'annotate' in name or name.endswith(('/corner.sym', '/gallery.sym')):
        return 'utility'
    if any(s in name for s in ('npn', 'pnp')):
        return 'bipolar'
    if any(s in name for s in ('nfet', 'pfet', 'nmoscl', 'sg13_lv_', 'sg13_hv_')):
        return 'mos'
    if any(s in name for s in ('cap', 'varicap')):
        return 'capacitor'
    if 'inductor' in name:
        return 'inductor'
    if device['category'] == 'Resistors' or Path(name).stem in {
        'nplus_u', 'pplus_u', 'nwell', 'npolyf_s', 'npolyf_u', 'ppolyf_s',
        'ppolyf_u', 'ppolyf_u_1k', 'ppolyf_u_1k_6p0', 'ppolyf_u_2k',
        'ppolyf_u_2k_6p0', 'ppolyf_u_3k', 'rm1', 'rm2', 'rm3',
        'rhigh', 'rppd', 'rsil', 'res_generic_li',
    }:
        return 'resistor'
    if device['category'] == 'Diodes':
        return 'diode'
    return 'other'


def inventory(root=ROOT):
    base = Path(root) / 'icstudio/assets/pdks'
    collection = read(base / 'collection.json')
    entries = {e['variant']: e for e in collection['packages']}
    if set(entries) != set(TARGETS):
        raise ValueError('Bundled target inventory changed; review qualification scope.')
    result = {}
    for target in TARGETS:
        folder = base / target
        p = read(folder / 'package.json')
        if sha(folder / 'package.json') != entries[target]['manifest_sha256']:
            raise ValueError('Bundled manifest hash differs: ' + target)
        for name, digest in p['files'].items():
            asset = (folder / name).resolve()
            if not asset.is_relative_to(folder.resolve()) or sha(asset) != digest:
                raise ValueError('Bundled asset changed: ' + target + '/' + name)
        sim = p['technology']['simulation']
        devices = {}
        for name, device in sorted(sim['catalog'].items()):
            devices[name] = {k: device.get(k) for k in (
                'category', 'model', 'model_source', 'source', 'pin_order',
                'parameters', 'emit_parameters', 'parameter_scale', 'unavailable')}
            devices[name]['family'] = family(name, device)
            devices[name]['rf_batch'] = ('rf' in name.lower() or 'inductor' in name.lower()
                                        or 'varicap' in name.lower())
        locks = {name: {'sha256': sha(folder / name), 'content': read(folder / name)}
                 for name in ('UPSTREAM-LOCK.json', 'PHYSICAL-SOURCE-LOCK.json')
                 if (folder / name).is_file()}
        # Individual file identities already live in the hash-locked package.
        for lock in locks.values():
            lock['content'].pop('files', None)
            if isinstance(lock['content'].get('models'), dict):
                lock['content']['models'].pop('files', None)
        result[target] = {
            'revision': p['revision'], 'manifest_sha256': sha(folder / 'package.json'),
            'asset_count': len(p['files']), 'indexed_count': len(devices),
            'placeable_count': sum(not d['unavailable'] for d in devices.values()),
            'source_locks': locks, 'model_includes': sim['includes'],
            'requires_osdi': sim.get('requires_osdi', False),
            'physical': p['technology']['physical'], 'devices': devices,
        }
    return result


def validate(matrix, root=ROOT):
    root = Path(root)
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(matrix['schema'] == 1, 'Unsupported matrix schema.')
    require(matrix['inventory'] == inventory(root), 'Matrix inventory is stale or incomplete.')
    require(set(matrix['targets']) == set(TARGETS), 'Missing or extra qualification target.')
    tests = matrix['tests']
    needed = COMMON_TESTS | set.union(*EXTRA_TESTS.values())
    require(set(tests) == needed, 'Test definitions are incomplete or unexpected.')
    for name, test in tests.items():
        require(1 <= test['chunk'] <= 12, 'Invalid chunk: ' + name)
        for field in ('fixture', 'procedure', 'expected_result', 'conditions', 'automation_gap'):
            require(bool(test.get(field)), 'Missing test contract ' + name + ':' + field)
        for path in test['existing_runners']:
            require((root / path).is_file(), 'Missing runner: ' + path)
    requirements = matrix['requirements']
    expected = {target + ':' + test for target in TARGETS
                for test in COMMON_TESTS | EXTRA_TESTS[target]}
    require(set(requirements) == expected, 'Requirement coverage differs from required targets/tests.')
    for identity, req in requirements.items():
        target, test = identity.split(':')
        require(req['target'] == target and req['test'] == test, 'Misbound requirement: ' + identity)
        require(req['status'] in STATUSES, 'Unsupported qualification claim: ' + identity)
        require(bool(req['remaining']), 'Missing coverage gap: ' + identity)
        for evidence in req['historical_evidence']:
            require(evidence in matrix['evidence'], 'Unknown evidence: ' + evidence)
    for target in TARGETS:
        info = matrix['targets'][target]
        for field in ('metal_stack', 'digital_profile', 'operating_conditions', 'uncovered_scope'):
            require(bool(info.get(field)), 'Missing target definition: ' + target + ':' + field)
        devices = matrix['device_requirements'][target]
        require(set(devices) == set(matrix['inventory'][target]['devices']),
                'Device omitted or added: ' + target)
        for name, device in devices.items():
            require(set(device['tests']) == {'device-interface', 'device-simulation', 'device-physical'},
                    'Incomplete device coverage: ' + target + '/' + name)
            require(device['status'] in STATUSES and bool(device['remaining']),
                    'Unsupported device claim: ' + target + '/' + name)
            if matrix['inventory'][target]['devices'][name]['unavailable']:
                require(device['status'] == 'unsupported', 'Unavailable device promoted: ' + name)
    for name, evidence in matrix['evidence'].items():
        require(sha(root / evidence['path']) == evidence['sha256'], 'Evidence changed: ' + name)
        require(bool(evidence['scope_limit']), 'Missing evidence scope: ' + name)
    require(set(matrix['chunks']) == {str(n) for n in range(1, 13)}, 'Missing chunk.')
    require(matrix['chunks']['1']['status'] == 'matrix_defined', 'Chunk 1 definition missing.')
    require(all(matrix['chunks'][str(n)]['status'] in ('pending', 'in_progress') for n in range(2, 13)),
            'Completed execution requires a new, reviewed evidence schema.')
    return {'status': 'matrix_consistent', 'process_qualification': 'unqualified',
            'targets': len(TARGETS), 'requirements': len(requirements),
            'device_entries': sum(len(d) for d in matrix['device_requirements'].values()),
            'requirement_statuses': dict(Counter(r['status'] for r in requirements.values()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, default=MATRIX)
    args = parser.parse_args()
    print(json.dumps(validate(read(args.matrix)), indent=2))


if __name__ == '__main__':
    main()
