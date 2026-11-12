"""Create an explicit package whose varactor VM means parallel single devices.

The original VM=1 model, including substrate parasitics, stays byte-for-byte
unchanged. A named wrapper applies the ngspice subcircuit multiplier to that
single device. Original projects and the bundled default are not rewritten.
"""
import argparse, hashlib, json, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from icstudio.model import clone, digest, file_digest
from icstudio.catalog import validate_catalog
from scripts.device_qualification_source import historical_input

BASE_MANIFEST = '177e57626c06cb5d103aab04c4bc82983bc4ba96f2e08e4bc04006ade6cd8e2d'
WRAPPER = 'libs.tech/ngspice/icstudio-parallel-varactors.spice'


@historical_input
def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists(): raise ValueError('Choose a new parallel-varactor package directory.')
    if file_digest(source/'package.json') != BASE_MANIFEST:
        raise ValueError('Use the exact reviewed SKY130 device package.')
    package = json.loads((source/'package.json').read_bytes())
    for name, expected in package['files'].items():
        path = (source/name).resolve()
        if not path.is_relative_to(source) or file_digest(path) != expected:
            raise ValueError('Changed SKY130 source asset: '+name)
    lines = ['* IC Design Studio parallel-varactor adapter, GPL-3.0-or-later.',
             '* Uses unchanged Apache-2.0 public SKY130 unit models; original notices retained.',
             '* VM is a positive parallel multiplier of the original VM=1 device.',
             '* Separate package contract; no model accuracy or physical qualification claim.']
    originals = {}
    for kind in ('hvt', 'lvt'):
        key = 'sky130_fd_pr/cap_var_'+kind+'.sym'
        e = package['technology']['simulation']['catalog'][key]; originals[key] = clone(e)
        if e['pin_order'] != ['c0', 'c1', 'b'] or e['model'] != 'sky130_fd_pr__cap_var_'+kind:
            raise ValueError('Unexpected public varactor interface.')
        model = 'icstudio_cap_var_'+kind+'_parallel'
        lines += [f'.subckt {model} c0 c1 b w=.5 l=.5 copies=1',
                  f'Xunit c0 c1 b sky130_fd_pr__cap_var_{kind} w={{w}} l={{l}} vm=1 m={{copies}}',
                  '.ends '+model]
        e.update(model=model, model_source=WRAPPER, emit_parameters={'w': 'w', 'l': 'l', 'copies': 'vm'})
        e['parameters']['vm']['positive'] = True
        e['notes'].append('VM uses the explicit IC Design Studio parallel-single-device wrapper; upstream VM=1 model unchanged.')
    package['technology']['simulation']['includes'].append({'path': WRAPPER})
    validate_catalog(package['technology'])
    provenance = dict(schema=1, original_manifest_sha256=BASE_MANIFEST, original_bindings=originals,
        contract='Positive VM is the parallel multiplier of the untouched upstream VM=1 subcircuit, including both substrate capacitors.',
        limits='Selected local integration must be qualified separately. Statistical independence, complete operating ranges and layout extraction remain unqualified.')
    additions = {WRAPPER: ('\n'.join(lines)+'\n').encode(),
                 'ICSTUDIO-PARALLEL-VARACTORS.json': (json.dumps(provenance, indent=2)+'\n').encode()}
    for name, data in additions.items(): package['files'][name] = hashlib.sha256(data).hexdigest()
    package['technology']['revision'] = ''
    package['revision'] = package['technology']['revision'] = digest({'files': package['files'], 'technology': package['technology']})[:16]
    output.mkdir(parents=True)
    for name, expected in package['files'].items():
        path = output/name; path.parent.mkdir(parents=True, exist_ok=True)
        if name in additions: path.write_bytes(additions[name])
        else: shutil.copyfile(source/name, path)
        if file_digest(path) != expected: raise ValueError('SKY130 asset changed during copy: '+name)
    (output/'package.json').write_bytes((json.dumps(package, sort_keys=True, indent=2)+'\n').encode())
    return dict(revision=package['revision'], manifest_sha256=file_digest(output/'package.json'), original_manifest_sha256=BASE_MANIFEST)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=ROOT/'icstudio/assets/pdks/sky130A')
    ap.add_argument('--output', type=Path, required=True); a = ap.parse_args()
    print(json.dumps(prepare(a.input, a.output), indent=2))
