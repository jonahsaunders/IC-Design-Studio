"""Saved diagnostic definitions shared by schematic and extracted testbenches."""
from .model import clone, scalar

MEASUREMENTS = {'input_noise': 'V', 'output_noise': 'V', 'phase_margin': 'deg',
                'unity_frequency': 'Hz', 'startup_settling': 's'}


def settings(project, testbench):
    analysis = clone(testbench['analysis'])
    config = analysis.get('diagnostic')
    if config is not None and not isinstance(config, dict):
        raise ValueError('Saved diagnostic configuration must be an object.')
    if config and config.get('kind') == 'startup' and config.get('supply_from_source', True):
        fixture = next(c for c in project['cells'] if c['id'] == testbench['bench_cell'])
        source = next((d for d in fixture['devices'] if d['name'] == config.get('source') and d['kind'] == 'V'), None)
        if not source or source['source']['type'] != 'dc':
            raise ValueError('Saved startup diagnostics require a DC supply source to ramp.')
        config['supply'] = scalar(source['value'])
    return analysis


def validate(project, testbench):
    from .analog_diagnostics import validate_config
    analysis = settings(project, testbench)
    config = analysis.get('diagnostic')
    if config is None:
        return
    if not isinstance(config, dict):
        raise ValueError('Saved diagnostic configuration must be an object.')
    expected = {'noise': 'noise', 'loop': 'ac', 'startup': 'tran', 'bias': 'op'}
    if config.get('kind') not in expected or expected[config['kind']] != analysis['type']:
        raise ValueError('Saved diagnostics require noise/noise, loop/AC, startup/transient or bias/OP.')
    validate_config(project, testbench['bench_cell'], config)
    probes = set(testbench['probes'])
    if config['kind'] == 'loop' and not {config['numerator'], config['denominator']} <= probes:
        raise ValueError('Save both loop injection and return voltages as probes.')
    if config['kind'] in ('startup', 'noise') and config['output'] not in probes:
        raise ValueError('Save the diagnostic output as a probe.')
    if config['kind'] == 'noise' and (config['source'] != analysis.get('noise_source', analysis.get('source')) or config['output'] != analysis.get('output')):
        raise ValueError('The noise diagnostic source/output must match the saved noise analysis.')
    if config['kind'] == 'startup':
        if scalar(config['stop']) != scalar(analysis['stop']):
            raise ValueError('Startup diagnostic duration must match the saved transient duration.')
        if type(config.get('supply_from_source', True)) is not bool:
            raise ValueError('Startup supply selection must be true or false.')


def validate_measurement(testbench, measurement):
    kind = measurement['kind']
    expected = {'input_noise': 'noise', 'output_noise': 'noise', 'phase_margin': 'loop',
                'unity_frequency': 'loop', 'startup_settling': 'startup'}[kind]
    if testbench['analysis'].get('diagnostic', {}).get('kind') != expected:
        raise ValueError(kind + ' requires a saved ' + expected + ' diagnostic.')


def measurement(result, kind):
    evidence = result.get('diagnostics', {})
    if kind in ('input_noise', 'output_noise'):
        key = 'input_rms_V' if kind == 'input_noise' else 'output_rms_V'
        return evidence[key], {'unit': 'V', 'band_Hz': evidence['band_Hz']}
    if kind in ('phase_margin', 'unity_frequency'):
        crossings = evidence.get('unity_crossings', [])
        if not crossings:
            raise ValueError('No measured unity-gain crossing; extend the AC sweep. A missing crossing is not a passing margin.')
        if kind == 'phase_margin':
            return min(c['phase_margin_deg'] for c in crossings), {'unit': 'deg', 'crossings': len(crossings),
                'convention': 'Minimum phase margin over sampled unity crossings of T; characteristic 1 + T.'}
        return min(c['frequency_Hz'] for c in crossings), {'unit': 'Hz', 'crossings': len(crossings)}
    if kind == 'startup_settling':
        if not evidence.get('passed') or evidence.get('settled_by_s') is None:
            raise ValueError('Startup output did not remain inside the saved voltage band through the final observation window.')
        return evidence['settled_by_s'], {'unit': 's', 'limits_V': evidence['limits_V'], 'window_s': evidence['window_s']}
    raise ValueError('Unsupported saved diagnostic measurement.')
