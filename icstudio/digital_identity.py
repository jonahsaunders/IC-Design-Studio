"""Stage-specific input identities, independent of paths and execution policy."""
from .model import digest


PHYSICAL = ('floorplan', 'place', 'cts', 'route', 'finish')


def fingerprints(config):
    platform = config.get('platform', {})
    technology = {k: platform.get(k) for k in ('fingerprint', 'corner')}
    rtl = {'top': config['top'], 'files': [f for f in config['files'] if f['role'] in ('rtl', 'include', 'data')],
           'defines': config.get('defines', {}), 'include_dirs': config.get('include_dirs', ['.']),
           'bindings': config.get('bindings', {})}
    constraints = [f for f in config['files'] if f['role'] == 'constraint']
    # Hash raw intent here; validation/translation happens at the engine boundary.
    synthesis = {'synthesis': config.get('synthesis', {}), 'intent': config.get('constraints')}
    if config.get('constraints'):
        synthesis['sdc'] = constraints
    physical = {k: v for k, v in config.get('physical', {}).items() if k != 'threads'}
    return {'rtl': digest(rtl), 'technology': digest(technology), 'synthesis': digest(synthesis),
            'constraints': digest(constraints), 'physical': digest(physical),
            'simulation': digest({'rtl': rtl, 'testbench': config.get('testbench'),
                                  'files': [f for f in config['files'] if f['role'] == 'testbench'],
                                  'waveform': config.get('waveform', 'wave.vcd'), 'coverage': config.get('coverage', False)}),
            'tests': digest(config.get('tests', [])), 'corners': digest(config.get('timing_corners', []))}


def stage_key(config, stage, simulator='icarus'):
    f = fingerprints(config)
    keys = {'simulate': ('simulation',), 'regression': ('simulation', 'tests'),
            'lint': ('rtl',), 'elaborate': ('rtl', 'synthesis'), 'synth': ('rtl', 'synthesis'),
            'mapped': ('rtl', 'technology', 'synthesis'),
            'equivalence': ('rtl', 'technology', 'synthesis'),
            'timing': ('rtl', 'technology', 'synthesis', 'constraints', 'corners')}
    if stage in PHYSICAL:
        selected = {k: f[k] for k in ('rtl', 'technology', 'synthesis', 'constraints')}
        # Route-layer edits don't invalidate placement. Pin/macro/PDN edits do.
        physical = {k: v for k, v in config.get('physical', {}).items() if k != 'threads'}
        if stage in ('floorplan', 'place', 'cts'):
            physical = {k: v for k, v in physical.items() if k not in ('min_routing_layer', 'max_routing_layer')}
        selected['physical'] = physical
    else:
        selected = {k: f[k] for k in keys.get(stage, tuple(f))}
    if stage in ('simulate', 'lint'):
        selected['simulator'] = 'verilator' if stage == 'lint' else simulator
    return digest({'version': 1, 'stage': stage, 'inputs': selected})


def physical_key(config):
    return stage_key(config, 'finish')


def logic_key(config):
    f = fingerprints(config)
    return digest({k: f[k] for k in ('rtl', 'technology')})


def current(data, config, simulator='icarus'):
    if data.get('input_key'):
        return data['input_key'] == stage_key(config, data['stage'], simulator)
    from .digital import source_hash
    return data.get('source_hash') == source_hash(config)


def comparison_context(result):
    """Keep performance deltas tied to comparable operating conditions."""
    data = result.get('digital_result', {})
    f = data.get('fingerprints', {})
    timing = data.get('timing', {})
    return {'stage': data.get('stage'), 'platform': data.get('platform'),
            'constraints': f.get('constraints', data.get('source_hash')),
            'synthesis': f.get('synthesis'), 'corners': f.get('corners'),
            'parasitics': timing.get('parasitics'),
            'physical': f.get('physical') if 'physical' in data else None,
            'tools': data.get('environment', {}).get('executables'),
            'workflow': data.get('environment', {}).get('sources')}
