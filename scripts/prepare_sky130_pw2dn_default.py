"""Build an isolated, unpromoted two-port RF pw2dn package from reviewed 5dda."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

BASE = '125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b'
REVISION = '5dda725c94efe3c2'
COMMON = 'sky130_fd_pr__model__parasitic__'
ROOT = Path(__file__).resolve().parents[1]
KEY = 'sky130_fd_pr/diode__' + COMMON + 'rf_diode_pw2dn.sym'
PREFIX = 'libs.tech/ngspice/icstudio-rf-pw2dn/'
MODEL = COMMON + 'rf_diode_pw2dn.model.spice'
PRIMITIVE = COMMON + 'diode_pw2dn_noresistor.model.spice'

def prepare(source, output):
    source, output = Path(source), Path(output)
    sys.path.insert(0, str(ROOT))
    from icstudio.model import clone, digest, file_digest
    from icstudio.catalog import validate_catalog
    from scripts.prepare_sky130_rf_qualification import public_sources, derivative, LOCK, SOURCE
    from scripts.verify_frozen_mim import unlinked
    source = unlinked(source).resolve()
    output = output.resolve()
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Output must be a new directory separate from the source.')
    if file_digest(unlinked(source/'package.json')) != BASE:
        raise ValueError('Expected exact 5dda source manifest.')
    package = json.loads((source/'package.json').read_bytes())
    if package['revision'] != REVISION or len(package['files']) != 426:
        raise ValueError('Unexpected predecessor revision or file count.')
    for name, expected in package['files'].items():
        path = unlinked(source/name).resolve()
        if not path.is_relative_to(source) or file_digest(path) != expected:
            raise ValueError('Changed predecessor asset: ' + name)
    lock, originals = public_sources()
    entry = package['technology']['simulation']['catalog'][KEY]
    old = clone(entry)
    if (not entry.get('unavailable') or entry['pin_order'] != ['d0','d1']
            or entry['prefix'] != 'D' or entry['model'] != COMMON+'rf_diode_pw2dn'):
        raise ValueError('Unexpected pw2dn predecessor binding.')
    entry.update(prefix='X', unavailable='', model_source=PREFIX+MODEL,
        parameters={'w':dict(default='2',positive=True,unit='um'),
                    'l':dict(default='2',positive=True,unit='um'),
                    'area':dict(default='w*l',positive=True,derived=True,computed=True,unit='um^2'),
                    'perim':dict(default='2*(w+l)',positive=True,derived=True,computed=True,unit='um')},
        emit_parameters={'area':'area','perim':'perim'})
    entry['notes'].append('Two-terminal rectangular pw2dn simulation candidate, d0 anode/d1 cathode, W/L in micrometres. Public wrapper derivative explicitly adds PJ={perim}; engine geometry/history guard required. Positive dimensions are not process limits. Three-terminal isolation and substrate parasitics, full operating envelope, measured accuracy and installed acceptance are unqualified.')
    additions={PREFIX+'original/'+n:originals[n] for n in (MODEL,PRIMITIVE)}
    additions.update({PREFIX+MODEL:derivative('pw2dn', originals[MODEL]),
        PREFIX+'library.spice':f'.include "original/{PRIMITIVE}"\n.include "{MODEL}"\n'.encode(),
        PREFIX+'LICENSE':(SOURCE/'LICENSE').read_bytes(),
        PREFIX+'source-lock.json':(SOURCE/'source-lock.json').read_bytes()})
    package['technology']['simulation']['includes'].append({'path':PREFIX+'library.spice'})
    proof={'schema':1,'source_manifest_sha256':BASE,'source_revision':REVISION,
           'source_lock_sha256':LOCK,'source':lock,'original_binding':old,'device':KEY,
           'terminal_mapping':{'d0':'c0 anode','d1':'c1 cathode'},
           'change':'Preserve originals; reviewed derivative adds PJ={perim} to dp. Explicit X calls derive area and perimeter from rectangular W/L.',
           'candidate_default':True,'production_default_promoted':False,'qualified':False,
           'scope':'Two-terminal simulation candidate only; positive geometry is not a physical operating limit. Three-terminal isolation and substrate parasitics, full operating envelope, measured RF accuracy and installed acceptance remain open.'}
    additions['ICSTUDIO-RF-PW2DN-CANDIDATE.json']=(json.dumps(proof,indent=2)+'\n').encode()
    for name, content in additions.items():
        if name in package['files']: raise ValueError('Candidate would replace predecessor asset: '+name)
        package['files'][name]=hashlib.sha256(content).hexdigest()
    validate_catalog(package['technology'])
    package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest(dict(files=package['files'],technology=package['technology']))[:16]
    output.mkdir(parents=True)
    for name, expected in package['files'].items():
        dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if name in additions: dest.write_bytes(additions[name])
        else: shutil.copyfile(source/name,dest)
        if file_digest(dest)!=expected: raise ValueError('Changed output asset: '+name)
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return {'revision':package['revision'],'manifest_sha256':file_digest(output/'package.json'),
            'predecessor_assets':426,'added_assets':sorted(additions),'qualified':False,'production_default_promoted':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',default=ROOT/'icstudio/assets/pdks/sky130A',type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
