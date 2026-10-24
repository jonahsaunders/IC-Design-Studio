"""Capture IHP fill rules and extraction helpers inside a digital platform."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import atomic_write, clone, digest, file_digest
from icstudio.digital_platform import inventory, verify

HELPERS = ('prepare_ihp_block_fill.py', 'check_ihp_fill_rules.py',
           'check_ihp_flat_capacitance.py', 'ihp_cell_capacitance.py',
           'ihp_magic_export.py', 'ihp_native_capacitance.py')
LOCKS = ('ihp-fill-source-lock.json', 'ihp-active-fill-source-lock.json')
RECIPE = 'ihp-signal-clearance-block-fill-v1'


def prepare(platform, output, *, cache=None):
    verify(platform)
    if platform['name'] != 'ihp-sg13g2' or platform.get('ihp_fill'):
        raise ValueError('Attach fill once to a captured IHP digital platform.')
    base = Path(platform['root']).resolve(); output = Path(output).resolve()
    if not output.is_relative_to(base) or output == base or output.exists():
        raise ValueError('Use a new fill resource directory inside the platform.')
    fill = json.loads((ROOT/'examples'/LOCKS[0]).read_text())
    active = json.loads((ROOT/'examples'/LOCKS[1]).read_text())
    sources = [('macros/'+r['file'], r) for r in fill['files']]
    sources += [('magic/'+Path(r['path']).name, r) for r in active['sources']['magic']['files'] if r['path'].endswith('.tech')]
    sources += [('manual/'+Path(r['path']).name, r) for r in active['sources']['manual']['files'] if r['path'].endswith('.pdf')]
    sources.append(('LICENSE', dict(sha256=file_digest(ROOT/'icstudio/assets/pdks/ihp-sg13g2/LICENSE'),
                                   local=ROOT/'icstudio/assets/pdks/ihp-sg13g2/LICENSE')))
    captured = {}
    for name, row in sources:
        local = row.get('local')
        cached = Path(cache)/Path(name).name if cache else None
        if local:
            data = Path(local).read_bytes()
        elif cached is not None and cached.is_file():
            data = cached.read_bytes()
        else:
            with urllib.request.urlopen(row['url'], timeout=60) as response:
                data = response.read(16*1024*1024+1)
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Pinned IHP source changed: '+name)
        captured[name] = data
    deck = base/platform.get('directory','.')/'drc/sg13g2_maximal.lydrc'
    data = deck.read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(data).hexdigest() != fill['native_drc']['sha256']:
        raise ValueError('The captured maximal IHP deck changed.')
    captured['sg13g2_maximal.lydrc'] = data
    for name in HELPERS:
        captured['helpers/scripts/'+name] = (ROOT/'scripts'/name).read_bytes()
    for name in LOCKS:
        captured['helpers/examples/'+name] = (ROOT/'examples'/name).read_bytes()
    captured['helpers/scripts/__init__.py'] = b''
    output.mkdir(parents=True)
    for name, data in captured.items():
        target = output/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
    record = dict(schema=1, recipe=RECIPE, revision=fill['revision'], qualified=False,
                  scope='Standard-cell block fill and unchanged nominal circuit model; complete-chip and field calibration remain separate.',
                  files=inventory(output, sorted(captured)))
    atomic_write(output/'preparation.json', json.dumps(record,indent=2)+'\n')
    result = clone(platform); relative = output.relative_to(base).as_posix()
    added = [relative+'/'+name for name in [*captured,'preparation.json']]
    original = [r['path'] for r in result['files']]
    if set(added) & set(original):
        raise ValueError('IHP fill resources overlap the original platform capture.')
    result['files'] = inventory(base, original+added)
    result['fingerprint'] = digest(result['files'])
    result['ihp_fill'] = dict(recipe=RECIPE, directory=relative,
                              preparation_sha256=file_digest(output/'preparation.json'))
    verify(result)
    return result


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cache',type=Path);p.add_argument('--manifest',type=Path,required=True)
    a=p.parse_args()
    if a.manifest.exists():raise ValueError('Preserve the existing platform manifest.')
    result=prepare(json.loads(a.platform.read_text()),a.output,cache=a.cache)
    atomic_write(a.manifest,json.dumps(result,indent=2)+'\n')
