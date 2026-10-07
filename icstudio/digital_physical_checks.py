"""Evidence-bound antenna and power-grid checks; not foundry signoff."""
import json
from pathlib import Path
import shutil

from .model import atomic_write, file_digest

SCOPE = ('Final OpenDB default-oxide LEF antenna rules and all declared POWER/GROUND net connectivity. '
         'Model/rule presence is checked; deck adequacy, streamed-GDS DRC/LVS, density, ERC, '
         'ESD/latch-up, IR drop and electromigration are not qualified by these checks.')


def evaluate(raw, checkpoint_sha256, top):
    if (not isinstance(raw, dict) or raw.get('schema') != 1
            or raw.get('checkpoint_sha256') != checkpoint_sha256 or raw.get('top') != top):
        raise ValueError('Physical-check evidence belongs to another checkpoint or design.')
    issues = []
    if type(raw.get('signal_inputs')) is not int or raw['signal_inputs'] <= 0:
        issues.append('No signal inputs were covered.')
    for key in ('missing_gate_models', 'unrouted_inputs', 'unconnected_power_pins'):
        if not isinstance(raw.get(key), list) or raw[key]:
            issues.append(key.replace('_', ' ').capitalize() + ' coverage is incomplete.')
    layers = raw.get('routing_layers')
    if (not isinstance(layers, list) or not layers
            or any(not isinstance(x, dict) or not isinstance(x.get('name'), str) or not x['name']
                   or x.get('has_antenna_rule') is not True for x in layers)
            or len({x['name'] for x in layers}) != len(layers)):
        issues.append('Routing-layer antenna rules are missing or incomplete.')
    antenna = raw.get('antenna', {})
    if (not isinstance(antenna, dict) or antenna.get('error') != ''
            or type(antenna.get('violating_nets')) is not int or antenna['violating_nets'] != 0):
        issues.append('Antenna check failed or has no complete violation count.')
    power = raw.get('power')
    if (not isinstance(power, list) or not power
            or any(not isinstance(x, dict) or not isinstance(x.get('net'), str) or not x['net']
                   or x.get('kind') not in ('POWER', 'GROUND')
                   or type(x.get('terminals')) is not int or x['terminals'] <= 0
                   or type(x.get('special_wires')) is not int or x['special_wires'] <= 0
                   or x.get('error') != '' for x in power)
            or {x['kind'] for x in power} != {'POWER', 'GROUND'}
            or len({x['net'] for x in power}) != len(power)):
        issues.append('Power/ground connectivity failed or coverage is incomplete.')
    return {'schema': 1, 'status': 'FAIL' if issues else 'PASS', 'issues': issues,
            'scope': SCOPE, 'checkpoint_sha256': checkpoint_sha256, 'top': top, 'checks': raw}


def prepare(checkpoint, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / 'engine-checks.json'
    output.unlink(missing_ok=True)
    worker = directory / 'physical_engine.py'
    shutil.copy2(Path(__file__).with_name('digital_physical_engine.py'), worker)
    request = directory / 'request.json'
    atomic_write(request, json.dumps({'checkpoint': str(Path(checkpoint).resolve()),
        'checkpoint_sha256': file_digest(checkpoint), 'output': str(output.resolve())}, indent=2))
    driver = directory / 'check.py'
    atomic_write(driver, 'import runpy\nrunpy.run_path(' + repr(str(worker.resolve())) +
                 ', init_globals={"REQUEST_PATH": ' + repr(str(request.resolve())) + '})\n')
    return driver, output


def validate_saved(data, root):
    artifacts = data['artifacts']
    declared = data.get('physical', {}).get('checks')
    if declared is None and 'physical_checks' not in artifacts:
        return None  # Historical jobs remain readable, without a check claim.
    if not isinstance(declared, dict) or 'physical_checks' not in artifacts:
        raise ValueError('Physical-check evidence is missing from the saved result.')
    report = json.loads((Path(root)/artifacts['physical_checks']['path']).read_text())
    if (report != declared or report.get('platform_fingerprint') != data.get('platform', {}).get('fingerprint')
            or report.get('checkpoint_sha256') != artifacts.get('checkpoint', {}).get('sha256')):
        raise ValueError('Physical-check evidence does not match the saved implementation.')
    expected = evaluate(report.get('checks'), artifacts['checkpoint']['sha256'], report.get('top'))
    if expected['status'] != 'PASS' or any(report.get(key) != value for key, value in expected.items()):
        raise ValueError('Saved physical-check evidence is incomplete or failed.')
    return report


def execute(r):
    checkpoint = r.root / r.artifacts['checkpoint']['path']
    expected = r.artifacts['checkpoint']['sha256']
    if file_digest(checkpoint) != expected:
        raise ValueError('The captured checkpoint changed before physical checks.')
    driver, output = prepare(checkpoint, r.root / 'physical-checks')
    r.command([r.tools['openroad'], '-no_init', '-exit', '-python', str(driver)],
              'Checking final antenna rules and power connectivity', fraction=.97)
    if file_digest(checkpoint) != expected:
        raise ValueError('The captured checkpoint changed during physical checks.')
    report = evaluate(json.loads(output.read_text()), expected, r.config['top'])
    report['platform_fingerprint'] = r.platform['fingerprint']
    for path in sorted(output.parent.iterdir()):
        r.add_artifact('physical_check_' + path.stem, path)
    r.save_json('physical_checks', report, 'physical_checks.json')
    if report['status'] != 'PASS':
        raise ValueError('Final physical checks failed: ' + ' '.join(report['issues']))
    return report
