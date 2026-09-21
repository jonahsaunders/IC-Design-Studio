"""Build the second-pass Banba schematic and its two reproducible searches."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.create_gf180_banba import build as first_pass
from icstudio.model import clone, uid, validate, erc, save_project
from icstudio.interchange import pin_positions
from icstudio.wiring import rebuild

OUT = ROOT / 'examples/gf180-banba/pass2'


def cell(p, name):
    return next(c for c in p['cells'] if c['name'] == name)


def device(p, name):
    return next(d for c in p['cells'] for d in c['devices'] if d['name'] == name)


def add_cap(p, c, name, x, y, a, b, side):
    cap = clone(device(p, 'CMILLER'))
    cap.update(id=uid(), name=name, x=x, y=y, nets=dict(g=a, b=b))
    cap['model_params'].update(w=side, l=side)
    cap['symbol']['primitives'] = [s for s in cap['symbol']['primitives'] if s['kind'] != 'text'] + [
        dict(kind='text', points=[[37,5],[230,15]], text='W=@w', font_size=9),
        dict(kind='text', points=[[37,23],[230,33]], text='L=@l', font_size=9)]
    c['devices'].append(cap)
    for pin, point in pin_positions(cap).items():
        end = [point[0], point[1] + (-60 if pin == 'g' else 60)]
        net = cap['nets'][pin]
        c['wires'].append(dict(id=uid(), net=net, points=[list(point), end]))
        c['labels'].append(dict(id=uid(), kind='net_label', name=net,
            anchor=dict(kind='point', point=end), offset=[7, -16], rotation=0))
    intended = {d['id']: clone(d['nets']) for d in c['devices']}
    rebuild(c, p)
    assert all(d['nets'] == intended[d['id']] for d in c['devices'])


def build():
    p, _, _ = first_pass()
    p['name'] = 'GF180MCU Banba bandgap — second pass'
    device(p, 'RBIAS')['model_params']['l'] = '1000u'
    device(p, 'MSENSE')['params'].update(w='1u', l='8u')
    device(p, 'RDET')['model_params']['l'] = '1600u'
    device(p, 'RPULL')['model_params']['l'] = '2000u'
    device(p, 'MNKICK')['params'].update(w='.5u', l='4u')
    device(p, 'CMILLER')['model_params'].update(w='44.72136u', l='44.72136u')
    device(p, 'RPTAT')['model_params']['l'] = '10.85u'
    device(p, 'ROUT')['model_params']['l'] = '50.15u'
    start = cell(p, 'startup')
    # Selected 193 1/3 µm square; retain the optimizer's numeric precision.
    add_cap(p, start, 'CTRACK', 1030, 270, 'VDD', 'CTRL', '0.0001933333333333333')
    add_cap(p, cell(p, 'banba_core'), 'COUT', 1210, 470, 'VREF', 'VSS', '450u')
    start['annotations'][1]['text'] = 'Core current releases the startup kick.\nMSENSE: 1/8 µm; RDET: 1/1600 µm.\nLow-current detector; RPULL: 1/2000 µm.'
    start['annotations'].append(dict(id=uid(), x=825, y=0, text=
        'CTRACK couples supply rise to CTRL.\nPMOS branches stay off during the edge.\nLarger capacitor trades area for overshoot.'))
    ota = cell(p, 'error_amplifier')
    ota['annotations'][1]['text'] = 'Lower OTA bias: RBIAS W/L = 1/1000 µm.\nPBIAS: 4/4 µm; tail: 8/4 µm.\nInput pair: 24/2 µm, matched.'
    ota['annotations'][2]['text'] = 'MIM Miller capacitor ≈ 4 pF.\nSized together with the startup network.\nLoop-gain qualification remains open.'
    core = cell(p, 'banba_core')
    core['annotations'][2]['text'] = 'SECOND PASS · lower bias and soft startup.\nMirror W/L = 8/4 µm; poly W = 1 µm.\nAll bodies/substrates explicitly tied.'
    core['annotations'][-1]['text'] = 'Ibranch ≈ VBE/RCA + ΔVBE/RPTAT\nVREF ≈ ROUT × Ibranch\nΔVBE ≈ VT × ln(8)\n\nResistor geometries selected by search.\nUse PDK results for actual values.'
    for name in ('tb_dc', 'tb_startup'):
        c = cell(p, name)
        c['specifications'] = [dict(name='Reference window', expression='final(V("VREF"))', unit='V', min='.57', max='.63')]
        if name == 'tb_dc':
            c['specifications'].append(dict(name='Supply current ceiling', expression='-final(I("VDD"))', unit='A', max='70u'))
        else:
            c['specifications'].extend([
                dict(name='Startup overshoot ceiling', expression='max(V("VREF"))', unit='V', max='.75'),
                dict(name='Fast startup settling', expression='settling(V("VREF"), .6, .03)', unit='s', max='250u')])
    slow = clone(cell(p, 'tb_startup'))
    slow.update(id=uid(), name='tb_slow_startup')
    for collection in ('devices', 'wires', 'labels', 'annotations'):
        for item in slow[collection]:
            item['id'] = uid()
    slow['specifications'][-1].update(name='Slow startup settling', max='1.25m')
    slow['annotations'][1]['text'] = 'Saved startup diagnostic: 1 ms supply ramp.\nPWL source, UIC, initial VREF = 0; run 2 ms.\nDiagnostic supply is explicitly 3.3 V.'
    p['cells'].append(slow)
    slow_settings = {**p['analysis'], 'type':'tran', 'step':'500n', 'stop':'2m',
        'diagnostic':dict(kind='startup', source='VDD', output='VREF', initial_node='VREF',
            initial_voltage='0', ramp='1m', supply='3.3', stop='2m',
            minimum='.57', maximum='.63', tail_fraction='.2')}
    p['simulation_setups'].append(dict(name='Banba slow supply startup', cell=slow['id'],
                                      engine='ngspice', settings=slow_settings))
    ac = clone(cell(p, 'tb_dc'))
    ac.update(id=uid(), name='tb_psrr', specifications=[])
    for collection in ('devices', 'wires', 'labels', 'annotations'):
        for item in ac[collection]:
            item['id'] = uid()
    next(d for d in ac['devices'] if d['name'] == 'VDD')['source']['ac'] = '1'
    ac['annotations'][1]['text'] = 'Supply rejection: 1 V small-signal AC input.\n3.3 V DC bias; sweep 1 Hz to 100 MHz.\nPSRR = −20 log10 |VREF / VDD|.'
    p['cells'].append(ac)
    p['simulation_setups'].append(dict(name='Banba supply rejection (1 V AC input)', cell=ac['id'], engine='ngspice',
        settings={**p['analysis'], 'type':'ac', 'start':'1', 'end':'100Meg', 'points':40}))
    medium = clone(cell(p, 'tb_startup'))
    medium.update(id=uid(), name='tb_medium_startup')
    for collection in ('devices', 'wires', 'labels', 'annotations'):
        for item in medium[collection]:
            item['id'] = uid()
    medium['annotations'][1]['text'] = 'Saved startup diagnostic: 10 µs supply ramp.\nPWL source, UIC, initial VREF = 0; run 500 µs.\nDiagnostic supply is explicitly 3.3 V.'
    p['cells'].append(medium)
    medium_settings = clone(slow_settings)
    medium_settings.update(step='100n', stop='500u')
    medium_settings['diagnostic'].update(ramp='10u', stop='500u')
    p['simulation_setups'].append(dict(name='Banba medium supply startup', cell=medium['id'], engine='ngspice', settings=medium_settings))
    entries = [dict(id='setup:'+str(i), **clone(s)) for i, s in enumerate(p['simulation_setups'][:2])]
    startup_plan = dict(id='banba_startup_pvt', name='Banba startup corners at 3.6 V',
        entries=[entries[1]], variables=dict(vdd='3.6'),
        corners=['nominal','ff','ss','fs','sf'], temperatures=[-40,125], voltages=[])
    precision_plan = dict(id='banba_accuracy', name='Banba accuracy with startup constraints',
        entries=entries, corners=['nominal'], temperatures=[-40,27,125], voltages=[])
    ramp_entries = [clone(entries[1])]
    for index in (3,5):
        e = dict(id='setup:'+str(index), **clone(p['simulation_setups'][index]))
        e['settings']['diagnostic']['supply'] = '3.6'
        ramp_entries.append(e)
    ramp_plan = dict(id='banba_ramp_corners', name='Banba three startup ramps at 3.6 V',
        entries=ramp_entries, variables=dict(vdd='3.6'), corners=['nominal','ff','ss','fs','sf'],
        temperatures=[-40,125], voltages=[])
    p['test_plans'] = [startup_plan, precision_plan, ramp_plan]
    p['design_notes'] = dict(stage='Second schematic pass; bounded model checks, not tapeout qualification.',
        topology_reference='https://doi.org/10.1109/4.760378',
        assumptions='3.3 V nominal, 0.6 V target, unbuffered output with 5 pF bench load, 1:8 PNP ratio.',
        tradeoffs='Lower bias and larger compensation reduce power/overshoot but increase area and settling time.',
        limitations='No mismatch, extracted layout, noise, load range or return-ratio qualification.')
    startup_spec = dict(kind='analog_optimizer', name='Banba second-pass startup sizing', strategy='grid', budget=120,
        axes=[dict(target='CTRACK.model_params.w', lower='160u', upper='210u', count=4,
                   links=[dict(target='CTRACK.model_params.l', ratio=1)]),
              dict(target='MNKICK.params.w', lower='.35u', upper='.65u', count=3)],
        objective=dict(entry_id='setup:1', expression='max(V("VREF"))', unit='V', goal='minimize'))
    precision_spec = dict(kind='analog_optimizer', name='Banba second-pass accuracy sizing', strategy='grid', budget=150,
        axes=[dict(target='RPTAT.model_params.l', lower='10.8u', upper='11u', count=5),
              dict(target='ROUT.model_params.l', lower='50u', upper='50.2u', count=5)],
        objective=dict(entry_id='setup:0', expression='final(V("VREF"))', unit='V', goal='target', target='.6'),
        gmid=dict(entry_id='setup:0', device='XDUT/XAMP/MPA', min='8', max='22', headroom='.1'))
    filter_spec = dict(kind='analog_optimizer', name='Banba output filter with three startup ramps', strategy='grid', budget=150,
        axes=[dict(target='COUT.model_params.w', lower='350u', upper='550u', count=5,
                   links=[dict(target='COUT.model_params.l', ratio=1)])],
        objective=dict(entry_id='setup:1', expression='settling(V("VREF"), .6, .03)', unit='s', goal='minimize'))
    configs = [dict(cell='startup', plan=startup_plan['id'], spec=startup_spec),
               dict(cell='banba_core', plan=precision_plan['id'], spec=precision_spec),
               dict(cell='banba_core', plan=ramp_plan['id'], spec=filter_spec)]
    validate(p)
    assert not erc(p), erc(p)
    return p, configs


if __name__ == '__main__':
    p, configs = build()
    OUT.mkdir(parents=True, exist_ok=True)
    p['pdk']['package_root'] = '../../../icstudio/assets/pdks/gf180mcuD'
    save_project(p, OUT/'banba.icproj')
    (OUT/'optimizer.json').write_text(json.dumps(configs, indent=2)+'\n')
    print('Created', OUT/'banba.icproj')
