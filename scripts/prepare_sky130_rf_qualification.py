"""Build a separate SKY130 RF diode candidate from retained public originals.

This never modifies the default library. Geometry describes rectangular
junctions in micrometres; physical extraction and RF operating limits remain
qualification requirements. The application's automatic runtime guard applies.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import digest, file_digest, io_path
from icstudio.catalog import validate_catalog
from scripts.sky130_mim_source import previous_mim

BASE = '42cafd2b1407783d361cfbb276abe3ba9e97b2c06a716af6c9069c8426852413'
SOURCE = ROOT / 'icstudio/assets/qualification/sky130-rf'
LOCK = '9bbc32cb158ae7f842aee085abaa834df9576eb2a5fad0c00f81eeb07607b570'
COMMON = 'sky130_fd_pr__model__parasitic__'


def public_sources():
    if file_digest(SOURCE / 'source-lock.json') != LOCK:
        raise ValueError('The reviewed public RF source lock changed.')
    lock = json.loads((SOURCE / 'source-lock.json').read_bytes())
    result = {}
    for row in lock['files']:
        path = SOURCE / row['local_file']
        if file_digest(path) != row['sha256']:
            raise ValueError('Changed RF model original: ' + row['local_file'])
        result[path.name] = path.read_bytes()
    if file_digest(SOURCE / 'LICENSE') != lock['license_sha256']:
        raise ValueError('Changed RF source license.')
    return lock, result


def derivative(model, original):
    lock, sources = public_sources()
    name = COMMON + 'rf_diode_' + model + '.model.spice'
    if model not in ('ps2nw', 'pw2dn') or sources.get(name) != original:
        raise ValueError('Use the exact reviewed RF wrapper original.')
    if original.count(b'area = 1.0e-18') != 1:
        raise ValueError('Unexpected RF perimeter branch.')
    return (b'* IC Design Studio derivative: add the explicit perimeter to branch dp.\n'
            b'* Original source is retained under original/. Requires stable unscaled AREA/PJ runtime behavior.\n'
            + original.replace(b'area = 1.0e-18', b'area = 1.0e-18 pj = {perim}'))


def prepare(source, output):
    with previous_mim(source) as old:
        return _prepare(old, output)


def _prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new RF candidate package directory.')
    if file_digest(source / 'package.json') != BASE:
        raise ValueError('Use the exact reviewed default SKY130 source package.')
    lock, originals = public_sources()
    package = json.loads((source / 'package.json').read_bytes())
    for relative, expected in package['files'].items():
        path = (source / relative).resolve()
        if not path.is_relative_to(source) or file_digest(path) != expected:
            raise ValueError('Changed or unsafe base asset: ' + relative)
    additions = {}; base = 'libs.tech/ngspice/icstudio-rf-diodes/'; includes = []
    for name, content in originals.items():
        additions[base + 'original/' + name] = content
    additions[base + 'LICENSE'] = (SOURCE / 'LICENSE').read_bytes()
    changes = []
    for model in ('ps2nw', 'pw2dn'):
        name = COMMON + 'rf_diode_' + model + '.model.spice'
        additions[base + name] = derivative(model, originals[name])
        includes += ['.include "original/' + COMMON + 'diode_' + model + '_noresistor.model.spice"',
                     '.include "' + name + '"']
        key = 'sky130_fd_pr/diode__' + COMMON + 'rf_diode_' + model + '.sym'
        entry = package['technology']['simulation']['catalog'][key]
        if not entry.get('unavailable') or entry['pin_order'] != ['d0', 'd1'] or entry['prefix'] != 'D':
            raise ValueError('RF base binding differs from the reviewed terminal interface.')
        entry.update(prefix='X', unavailable='', model_source=base + name,
                     parameters={'w': dict(default='2', positive=True, unit='um'),
                                 'l': dict(default='2', positive=True, unit='um'),
                                 'area': dict(default='w*l', positive=True, derived=True, computed=True, unit='um^2'),
                                 'perim': dict(default='2*(w+l)', positive=True, derived=True, computed=True, unit='um')},
                     emit_parameters={'area': 'area', 'perim': 'perim'})
        entry['notes'].append('Explicit RF candidate: positive rectangular W/L in micrometres; '
                              'the runtime guard checks AREA/PJ history. Physical layout and RF operating envelope remain unqualified.')
        changes.append(dict(device=key, terminals={'d0': 'c0 anode', 'd1': 'c1 cathode'}, source_model=base + name))
    additions[base + 'library.spice'] = ('\n'.join(includes) + '\n').encode()
    package['technology']['simulation']['includes'].append(dict(path=base + 'library.spice'))
    note = dict(schema=1, qualified=False, default_promoted=False, base_manifest_sha256=BASE,
                source=lock, source_lock_sha256=LOCK, changes=changes,
                change='Keep public originals; separate derivatives add PJ={perim} only to dp. '
                       'Explicit X calls compute area/perimeter from positive rectangular W/L.')
    additions['ICSTUDIO-RF-CANDIDATE.json'] = (json.dumps(note, indent=2) + '\n').encode()
    validate_catalog(package['technology'])
    io_path(output).mkdir(parents=True)
    for relative, expected in package['files'].items():
        dest = output / relative; io_path(dest.parent).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(io_path(source / relative), io_path(dest))
        if file_digest(dest) != expected:
            raise ValueError('Source changed during RF candidate copy: ' + relative)
    for relative, content in additions.items():
        if relative in package['files']:
            raise ValueError('The RF candidate may not replace an existing base asset.')
        dest = output / relative; io_path(dest.parent).mkdir(parents=True, exist_ok=True)
        io_path(dest).write_bytes(content); package['files'][relative] = file_digest(dest)
    package['technology']['revision'] = ''
    package['revision'] = package['technology']['revision'] = digest(dict(files=package['files'], technology=package['technology']))[:16]
    io_path(output / 'package.json').write_bytes((json.dumps(package, sort_keys=True, indent=2) + '\n').encode())
    return dict(revision=package['revision'], manifest_sha256=file_digest(output / 'package.json'),
                qualified=False, default_promoted=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'icstudio/assets/pdks/sky130A')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output), indent=2))
