"""OpenROAD Python worker for checks on an unchanged final database.

Executed by the captured OpenROAD build, not the application's Python runtime.
"""
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tcl_word(value):
    return '"' + ''.join('\\' + c if c in '\\"$[]' else c for c in value) + '"'


def run(request):
    from openroad import Tech, Design
    source = Path(request['checkpoint'])
    if sha(source) != request['checkpoint_sha256']:
        raise ValueError('The final checkpoint changed before physical checks.')
    tech = Tech()
    design = Design(tech)
    design.readDb(str(source))
    block = design.getBlock()
    if block is None:
        raise ValueError('The checkpoint has no design block.')

    inputs = 0
    missing_models = []
    unrouted_inputs = []
    unconnected_power = []
    for inst in block.getInsts():
        for term in inst.getITerms():
            pin = term.getMTerm()
            net = term.getNet()
            label = inst.getName() + '/' + pin.getName()
            if pin.getSigType() in ('POWER', 'GROUND'):
                if not net or net.getSigType() != pin.getSigType():
                    unconnected_power.append(label)
                continue
            if pin.getIoType() not in ('INPUT', 'INOUT'):
                continue
            inputs += 1
            areas = pin.getDefaultAntennaModel().getGateArea() if pin.hasDefaultAntennaModel() else []
            if not areas or not any(math.isfinite(area) and area > 0 for area, layer in areas):
                missing_models.append(label)
            if not net or not net.getWire():
                unrouted_inputs.append(label)

    layers = [{'name': layer.getName(), 'has_antenna_rule': layer.hasDefaultAntennaRule()}
              for layer in tech.getDB().getTech().getLayers() if layer.getRoutingLevel() > 0]

    def checked(command):
        status = design.evalTclString('if {[catch {' + command +
            '} studio_check_value]} {set studio_check_status 1} else {set studio_check_status 0}; set studio_check_status')
        if status not in ('0', '1'):
            raise ValueError('OpenROAD did not return a physical-check status.')
        value = design.evalTclString('set studio_check_value')
        return {'error': value if status == '1' else '', 'value': value if status == '0' else None}

    antenna = checked('check_antennas -verbose')
    if not antenna['error']:
        try:
            antenna['violating_nets'] = int(antenna.pop('value'))
        except (TypeError, ValueError):
            raise ValueError('OpenROAD did not return an antenna violation count.') from None
    else:
        antenna.pop('value')
        antenna['violating_nets'] = None
    power = []
    for net in block.getNets():
        if net.getSigType() not in ('POWER', 'GROUND'):
            continue
        result = checked('check_power_grid -net ' + tcl_word(net.getName()))
        power.append({'net': net.getName(), 'kind': net.getSigType(),
                      'terminals': len(net.getITerms()), 'special_wires': len(net.getSWires()),
                      'error': result['error']})
    if sha(source) != request['checkpoint_sha256']:
        raise ValueError('The final checkpoint changed during physical checks.')
    return {'schema': 1, 'checkpoint_sha256': request['checkpoint_sha256'],
            'top': block.getName(), 'signal_inputs': inputs,
            'missing_gate_models': missing_models, 'unrouted_inputs': unrouted_inputs,
            'unconnected_power_pins': unconnected_power, 'routing_layers': layers,
            'antenna': antenna, 'power': power}


if 'REQUEST_PATH' in globals():
    request = json.loads(Path(REQUEST_PATH).read_text())
    result = run(request)
    Path(request['output']).write_text(json.dumps(result, indent=2) + '\n')
