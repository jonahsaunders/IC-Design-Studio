"""Create a portable, editable fixture around the unchanged imported detector."""
from pathlib import Path
from icstudio.model import clone, device, uid, save_project, load_project
from icstudio.native_migration import review_path

ROOT = Path(__file__).resolve().parents[1]


def create(project, output):
    output = Path(output).resolve()
    model = ROOT / 'icstudio/assets/pdks/sky130A/libs.tech/ngspice/sky130.lib.spice'
    source = output / 'bench-models.sch'
    source.write_text('v {xschem version=3.4.4 file_version=1.2}\nK {}\nG {}\nV {}\nS {}\nE {}\n'
        'C {devices/code_shown.sym} 100 100 0 0 {name=MODELS only_toplevel=false value=".lib '
        + model.as_posix() + ' tt"}\n', encoding='utf-8')
    models = review_path(source)['candidate']
    if models is None: raise ValueError('Cannot embed the pinned SKY130 models in the detector bench.')
    p = clone(project)
    for key, asset in models['spice']['assets'].items():
        if key in p['spice']['assets'] and p['spice']['assets'][key] != asset:
            raise ValueError('Conflicting embedded bench model identity.')
        p['spice']['assets'][key] = asset
    p['spice']['bench_library_lock'] = models['spice']['library_lock']
    dut = next(c for c in p['cells'] if c['id'] == p['top'])
    bench = dict(id=uid(), name='detector_dc_bench', ports=[], devices=[], shapes=[],
        spice_statements=[d['native_spice']['text'] for c in models['cells'] for d in c['devices']],
        annotations=[dict(id=uid(), x=100, y=30,
            text='Rising DC sweep: 3–6 V. Set Vbit0–Vbit3 to 0 or 1.8 V for codes 0–15. Run with F5.')])
    bench['devices'].append(device('X', 'XDUT', 560, 280, cell=dut['id'], parameters={},
        nets={port: '0' if port in ('avss', 'dvss') else port.replace('[', '_').replace(']', '') for port in dut['ports']}))
    supplies = [('Vavdd', 'avdd', '3'), ('Vdvdd', 'dvdd', '1.8'), ('Vena', 'ena', '1.8'), ('Vbg', 'vbg', '1.2')]
    supplies += [(f'Vbit{i}', f'vtrip_{i}', '0') for i in range(4)]
    for i, (name, node, value) in enumerate(supplies):
        bench['devices'].append(device('V', name, 120+(i//4)*180, 100+(i%4)*150,
            value=value, nets={'p': node, 'n': '0'}))
    bench['devices'] += [device('I', 'Ibias', 760, 120, value='600n', nets={'p': 'avdd', 'n': 'ibias'}),
                         device('R', 'Rload', 900, 300, value='1meg', nets={'p': 'ovout', 'n': '0'})]
    p['cells'].insert(0, bench); p['top'] = bench['id']; p['name'] = 'SKY130 overvoltage detector DC bench'
    p['analysis'].update(type='dc', engine='ngspice', source='Vavdd', dc_start='3', dc_stop='6',
                         dc_step='.01', temperature=27, dc_startup=True, corner='nominal')
    path = output / 'overvoltage-bench.icproj'
    save_project(p, path)
    return load_project(path)
