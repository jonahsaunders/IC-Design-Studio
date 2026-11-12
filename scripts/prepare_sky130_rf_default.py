"""Bind the reviewed two-terminal RF ps2nw model in a new default revision.

This is a sampled simulation binding, not full RF device qualification. The
pw2dn candidate remains separate: its substrate/isolation behavior is unresolved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import clone, digest, file_digest
from icstudio.catalog import validate_catalog
from scripts.sky130_rf_source import BASE, previous_rf
from scripts.prepare_sky130_rf_qualification import COMMON, SOURCE, LOCK, public_sources, derivative

KEY = 'sky130_fd_pr/diode__' + COMMON + 'rf_diode_ps2nw.sym'
PREFIX = 'libs.tech/ngspice/icstudio-rf-ps2nw/'
MODEL = COMMON + 'rf_diode_ps2nw.model.spice'
PRIMITIVE = COMMON + 'diode_ps2nw_noresistor.model.spice'


def prepare(source, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new SKY130 RF default package directory.')
    with previous_rf(source) as source:
        source = Path(source).resolve()
        if file_digest(source/'package.json') != BASE:
            raise ValueError('Use the exact reviewed SKY130 MiM default package.')
        package = json.loads((source/'package.json').read_bytes())
        for name, expected in package['files'].items():
            path = (source/name).resolve()
            if not path.is_relative_to(source) or not path.is_file() or file_digest(path) != expected:
                raise ValueError('Changed SKY130 source asset: ' + name)
        lock, originals = public_sources()
        entry = package['technology']['simulation']['catalog'][KEY]
        old = clone(entry)
        if (not entry.get('unavailable') or entry['pin_order'] != ['d0', 'd1']
                or entry['prefix'] != 'D' or entry['model'] != COMMON+'rf_diode_ps2nw'):
            raise ValueError('Unexpected RF ps2nw source binding.')
        entry.update(prefix='X', unavailable='', model_source=PREFIX+MODEL,
            parameters={'w':dict(default='2', positive=True, unit='um'),
                        'l':dict(default='2', positive=True, unit='um'),
                        'area':dict(default='w*l', positive=True, derived=True, computed=True, unit='um^2'),
                        'perim':dict(default='2*(w+l)', positive=True, derived=True, computed=True, unit='um')},
            emit_parameters={'area':'area', 'perim':'perim'})
        entry['notes'].append('IC Design Studio: two-terminal public RF ps2nw simulation binding, d0 anode/d1 cathode. Positive rectangular W/L are in micrometres. Explicit PJ perimeter correction; automatic engine geometry/history check required. Sampled checks only: complete RF operating envelope, substrate parasitics and measured accuracy remain unqualified.')
        includes = f'.include "original/{PRIMITIVE}"\n.include "{MODEL}"\n'
        additions = {PREFIX+'original/'+name:originals[name] for name in (MODEL, PRIMITIVE)}
        additions.update({PREFIX+MODEL:derivative('ps2nw', originals[MODEL]),
            PREFIX+'library.spice':includes.encode(), PREFIX+'LICENSE':(SOURCE/'LICENSE').read_bytes(),
            PREFIX+'source-lock.json':(SOURCE/'source-lock.json').read_bytes()})
        package['technology']['simulation']['includes'].append(dict(path=PREFIX+'library.spice'))
        proof = dict(schema=1, source_manifest_sha256=BASE, source_revision=package['revision'],
            source_lock_sha256=LOCK, source=lock, original_binding=old,
            device=KEY, terminal_mapping={'d0':'c0 anode', 'd1':'c1 cathode'},
            change='Bind the reviewed X subcircuit; derive area/perimeter from rectangular W/L. Preserve the public originals; derivative adds PJ={perim} to dp only.',
            scope='Sampled two-terminal simulation integration only. Complete operating envelope, statistical behavior, substrate parasitics, measured RF accuracy and final installed acceptance remain unqualified.',
            qualified=False, default_promoted=True,
            excluded='rf_diode_pw2dn remains unavailable in the default; no electrical model of its three-terminal isolation is asserted.',
            license='Original Apache-2.0 model files and license retained with an explicit modification notice. Application integration is GPL-3.0-or-later.')
        additions['ICSTUDIO-RF-PS2NW-BINDING.json'] = (json.dumps(proof, indent=2)+'\n').encode()
        validate_catalog(package['technology'])
        for name, content in additions.items():
            if name in package['files']:
                raise ValueError('The RF default may not replace an existing source asset.')
            package['files'][name] = hashlib.sha256(content).hexdigest()
        package['technology']['revision'] = ''
        package['revision'] = package['technology']['revision'] = digest(dict(files=package['files'], technology=package['technology']))[:16]
        output.mkdir(parents=True)
        for name, expected in package['files'].items():
            dest = output/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if name in additions:dest.write_bytes(additions[name])
            else:shutil.copyfile(source/name, dest)
            if file_digest(dest) != expected:
                raise ValueError('SKY130 source changed during RF default copy: ' + name)
        (output/'package.json').write_bytes((json.dumps(package, sort_keys=True, indent=2)+'\n').encode())
        return dict(revision=package['revision'], manifest_sha256=file_digest(output/'package.json'), proof=proof)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=ROOT/'icstudio/assets/pdks/sky130A')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(prepare(a.input, a.output), indent=2))
