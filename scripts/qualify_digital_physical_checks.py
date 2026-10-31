"""Qualify final antenna/power checks and actual geometry faults on three processes."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import digital_flow, digital_macro, digital_physical_checks
from icstudio.digital_platform import BUNDLED_PLATFORMS
from icstudio.model import atomic_write, file_digest


FAULT_WORKER = '''import json
from pathlib import Path
import odb
from openroad import Tech, Design
request = json.loads(Path(REQUEST).read_text())
tech = Tech(); design = Design(tech); design.readDb(request['checkpoint'])
block = design.getBlock()
if request['fault'] == 'removed-grid':
    nets = [n for n in block.getNets() if n.getSigType() == 'POWER' and n.getSWires()]
    if not nets: raise ValueError('No actual power grid is available for the negative control.')
    net = nets[0]; count = len(net.getSWires())
    for wire in list(net.getSWires()): odb.dbSWire.destroy(wire)
    mutation = {'net': net.getName(), 'removed_special_wires': count}
else:
    candidates = [t for i in block.getInsts() for t in i.getITerms()
        if t.getMTerm().getIoType() == 'INPUT' and t.getMTerm().hasDefaultAntennaModel()
        and t.getNet() and t.getNet().getWire() and t.getNet().getSigType() not in ('POWER', 'GROUND')]
    if not candidates: raise ValueError('No routed modeled gate is available for the antenna control.')
    term = candidates[0]; net = term.getNet(); valid, x, y = term.getAvgXY()
    if not valid: raise ValueError('The selected gate has no pin geometry.')
    layer = next(l for l in tech.getDB().getTech().getLayers() if l.getRoutingLevel() > 0)
    encoder = odb.dbWireEncoder(); encoder.begin(net.getWire()); encoder.newPath(layer, 'ROUTED')
    encoder.addPoint(x, y); encoder.addITerm(term)
    extent = 20000 * block.getDbUnitsPerMicron()
    encoder.addPoint(x + extent, y); encoder.addPoint(x + extent, y + extent)
    encoder.addPoint(x, y + extent); encoder.end()
    mutation = {'net': net.getName(), 'instance': term.getInst().getName(),
        'pin': term.getMTerm().getName(), 'layer': layer.getName(), 'routing_length_um': 60000}
design.writeDb(request['output'])
Path(request['mutation']).write_text(json.dumps(mutation, indent=2))
'''


def command(argv, log, timeout):
    with Path(log).open('w', encoding='utf-8') as stream:
        subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)


def qualify(evidence, output, openroad, timeout=180):
    evidence = Path(evidence).resolve()
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose an empty physical-check qualification output directory.')
    output.mkdir(parents=True, exist_ok=True)
    engine = Path(shutil.which(str(openroad)) or openroad).resolve()
    report = {'schema': 1, 'status': 'running', 'scope': digital_physical_checks.SCOPE,
              'negative_control_scope': 'Isolated damaged OpenDB copies with unchanged source rules; not valid designs.',
              'source_files': {p.name: file_digest(p) for p in (
                  Path(__file__), ROOT/'icstudio/digital_physical_checks.py', ROOT/'icstudio/digital_physical_engine.py')},
              'cases': []}

    def retain():
        atomic_write(output/'report.json', json.dumps(report, indent=2) + '\n')

    retain()
    try:
        report['engine'] = {'path': str(engine), 'sha256': file_digest(engine)}
        command([str(engine), '-version'], output/'version.log', timeout)
        report['engine']['version'] = (output/'version.log').read_text().strip()
        for platform in BUNDLED_PLATFORMS:
            candidates = [evidence/platform/name for name in ('gds', 'finished')
                          if (evidence/platform/name/'result.json').is_file()]
            if len(candidates) != 1:
                raise ValueError('Expected one retained final job for ' + platform)
            jobdir = candidates[0]
            result = json.loads((jobdir/'result.json').read_text())
            job = json.loads((jobdir/'input.json').read_text())
            digital_flow.validate_result(result, jobdir)
            config = digital_macro.verify_inputs(result, job)
            data = result['digital_result']
            if (data['stage'] != 'finish' or data.get('platform', {}).get('name') != platform
                    or config.get('platform', {}).get('name') != platform):
                raise ValueError('Wrong stage or platform in physical qualification input.')
            checkpoint = jobdir/data['artifacts']['checkpoint']['path']
            source = {'input_sha256': file_digest(jobdir/'input.json'),
                      'result_sha256': file_digest(jobdir/'result.json'),
                      'checkpoint_sha256': file_digest(checkpoint),
                      'platform_fingerprint': config['platform']['fingerprint']}
            for case in ('baseline', 'removed-grid', 'antenna-route'):
                directory = output/platform/case
                directory.mkdir(parents=True)
                target = checkpoint
                mutation = None
                if case != 'baseline':
                    target = directory/'fault.odb'
                    request = directory/'fault-request.json'
                    atomic_write(request, json.dumps({'checkpoint': str(checkpoint), 'fault': case,
                        'output': str(target), 'mutation': str(directory/'mutation.json')}))
                    script = directory/'fault.py'
                    atomic_write(script, 'REQUEST = ' + repr(str(request)) + '\n' + FAULT_WORKER)
                    command([str(engine), '-no_init', '-exit', '-python', str(script)], directory/'fault.log', timeout)
                    mutation = json.loads((directory/'mutation.json').read_text())
                    if file_digest(target) == source['checkpoint_sha256']:
                        raise ValueError('The negative control did not change the checkpoint.')
                driver, rawpath = digital_physical_checks.prepare(target, directory/'checks')
                argv = [str(engine), '-no_init', '-exit', '-python', str(driver)]
                command(argv, directory/'engine.log', timeout)
                raw = json.loads(rawpath.read_text())
                verdict = digital_physical_checks.evaluate(raw, file_digest(target), config['top'])
                expected = 'PASS' if case == 'baseline' else 'FAIL'
                if verdict['status'] != expected:
                    raise ValueError(platform + '/' + case + ' did not produce ' + expected)
                if case == 'removed-grid' and not any('PSM-0069' in row['error'] for row in raw['power']):
                    raise ValueError('The grid control was not detected by the native connectivity checker.')
                if case == 'antenna-route' and not (type(raw['antenna']['violating_nets']) is int
                                                    and raw['antenna']['violating_nets'] > 0):
                    raise ValueError('The routed antenna fault was not detected by the native antenna checker.')
                atomic_write(directory/'result.json', json.dumps(verdict, indent=2) + '\n')
                report['cases'].append({'platform': platform, 'case': case, 'status': 'passed',
                    'expected_check_status': expected, 'source': source, 'mutation': mutation, 'command': argv,
                    'checkpoint_sha256': file_digest(target), 'result_sha256': file_digest(directory/'result.json'),
                    'log_sha256': file_digest(directory/'engine.log')})
                retain()
                print(platform, case, verdict['status'], flush=True)
            if (source['input_sha256'] != file_digest(jobdir/'input.json')
                    or source['result_sha256'] != file_digest(jobdir/'result.json')
                    or source['checkpoint_sha256'] != file_digest(checkpoint)):
                raise ValueError('Original source evidence changed during qualification.')
            digital_flow.validate_result(result, jobdir)
        if len(report['cases']) != 3 * len(BUNDLED_PLATFORMS):
            raise ValueError('Physical check qualification coverage is incomplete.')
        if file_digest(engine) != report['engine']['sha256']:
            raise ValueError('The OpenROAD executable changed during qualification.')
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        retain()
        raise
    retain()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--openroad', default='openroad')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    qualify(args.evidence, args.output, args.openroad, args.timeout)


if __name__ == '__main__':
    main()
