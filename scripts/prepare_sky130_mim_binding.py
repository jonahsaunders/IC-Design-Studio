"""Version the second MiM's MF mapping without modifying upstream assets."""
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
from scripts.sky130_mim_source import BASE, previous_mim

KEY = 'sky130_fd_pr/cap_mim_m3_2.sym'
SYMBOL = 'libs.tech/xschem/' + KEY
MODEL = 'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__cap_mim_m3_2.model.spice'
NOTE = 'ICSTUDIO-MIM2-BINDING.json'


def prepare(source, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new SKY130 MiM package directory.')
    with previous_mim(source) as source:
        source = Path(source).resolve()
        if file_digest(source/'package.json') != BASE:
            raise ValueError('Use the exact reviewed SKY130 LI default package.')
        package = json.loads((source/'package.json').read_bytes())
        for name, expected in package['files'].items():
            path = (source/name).resolve()
            if not path.is_relative_to(source) or not path.is_file() or file_digest(path) != expected:
                raise ValueError('Changed SKY130 source asset: ' + name)
        entry = package['technology']['simulation']['catalog'][KEY]
        old = clone(entry)
        if (entry['model'] != 'sky130_fd_pr__cap_mim_m3_2'
                or entry['pin_order'] != ['c0', 'c1'] or entry['prefix'] != 'X'
                or entry['emit_parameters'] != {'w':'w', 'l':'l', 'vm':'mf', 'm':'mf'}):
            raise ValueError('Unexpected second MiM source binding.')
        model = (source/MODEL).read_text(encoding='utf-8')
        symbol = (source/SYMBOL).read_text(encoding='utf-8')
        if ('.subckt  sky130_fd_pr__cap_mim_m3_2 c0 c1 w=1 l=1 mf=1' not in model
                or '/sqrt(wc*lc*mf)' not in model or 'VM=@MF m=@MF' not in symbol):
            raise ValueError('Unexpected public second MiM parameter contract.')
        entry['emit_parameters'] = {'w':'w', 'l':'l', 'mf':'mf', 'm':'mf'}
        entry['notes'].append('IC Design Studio: MF feeds the declared model mf parameter and ngspice m multiplier; the upstream symbol incorrectly emits VM. Original source assets retained.')
        validate_catalog(package['technology'])
        proof = dict(schema=1, source_manifest_sha256=BASE, source_revision=package['revision'],
            original_binding=old, sources={p:file_digest(source/p) for p in (SYMBOL, MODEL)},
            change='Emit mf=MF and m=MF for the second MiM. The public subcircuit declares mf and uses it in its mismatch-area denominator; it has no vm parameter.',
            scope='Model-interface correction only. Full statistical, operating, physical and silicon accuracy qualification remain separate.',
            license='Original Apache-2.0 models, symbols and notices remain byte-identical. This metadata correction is GPL-3.0-or-later.')
        additions = {NOTE:(json.dumps(proof, indent=2)+'\n').encode()}
        for name, data in additions.items():
            package['files'][name] = hashlib.sha256(data).hexdigest()
        package['technology']['revision'] = ''
        package['revision'] = package['technology']['revision'] = digest({'files':package['files'], 'technology':package['technology']})[:16]
        output.mkdir(parents=True)
        for name, expected in package['files'].items():
            dest = output/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if name in additions:
                dest.write_bytes(additions[name])
            else:
                shutil.copyfile(source/name, dest)
            if file_digest(dest) != expected:
                raise ValueError('SKY130 source changed during copy: ' + name)
        (output/'package.json').write_bytes((json.dumps(package, sort_keys=True, indent=2)+'\n').encode())
        return dict(revision=package['revision'], manifest_sha256=file_digest(output/'package.json'), proof=proof)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=ROOT/'icstudio/assets/pdks/sky130A')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(prepare(a.input, a.output), indent=2))
