"""Prepare an explicit IHP SVaricap model-terminal order and geometry contract.

The unchanged public model declares G1, W, G2, bn; the public symbol lists G2,
W, G1, body. The model's asymmetric gate-coupling branch makes that swap visible.
Original projects and bundled package remain unchanged.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest
from icstudio.catalog import validate_catalog
from scripts.prepare_ihp_isolation_qualification import prepare as isolation_package
KEY='sg13g2_pr/sg13_svaricap.sym'
MODEL_SHA256='b6ae39c7334c75c222ecdee9d6b04c9be48657e91351429aebac47d1192a9abb'


def correct(entry,model):
    if hashlib.sha256(model).hexdigest()!=MODEL_SHA256:raise ValueError('Unreviewed SVaricap model source.')
    if entry['pin_order']!=['g2','nw','g1','body']:raise ValueError('Unexpected SVaricap symbol interface.')
    entry['pin_order']=['g1','nw','g2','body'];entry['symbol']['pin_order']=list(entry['pin_order'])
    for key,low,high in [('w',3.74e-6,9.74e-6),('l',.3e-6,.8e-6),('nx',1,10)]:
        entry['parameters'][key].update(minimum=low,maximum=high)
    entry['parameters']['nx']['integer']=True
    entry['notes'].append('Model order G1, W, G2, bn is mapped explicitly. W/L/Nx bounds follow the locked model parameter checks; full bias, RF, physical and reliability qualification remains separate.')


def prepare(source,output):
    source,output=Path(source).resolve(),Path(output).resolve();original=json.loads((source/'package.json').read_bytes())
    entry=clone(original['technology']['simulation']['catalog'][KEY]);correct(entry,(source/entry['model_source']).read_bytes())
    parent=isolation_package(source,output);package=json.loads((output/'package.json').read_bytes())
    package['technology']['simulation']['catalog'][KEY]=entry;validate_catalog(package['technology'])
    note=dict(schema=1,model_sha256=MODEL_SHA256,parent_isolation_package=parent,
        original_binding=original['technology']['simulation']['catalog'][KEY],
        contract='Model G1 W G2 bn maps to g1 nw g2 body; source-declared W/L/Nx bounds. Ny remains the model default of 1.',
        limits='Selected terminal integration only; no complete bias, RF, reliability, statistical or physical qualification.')
    path=output/'ICSTUDIO-SVARICAP-BINDING.json';path.write_bytes((json.dumps(note,indent=2)+'\n').encode());package['files'][path.name]=file_digest(path)
    package['technology']['revision']='';package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),original_manifest_sha256=file_digest(source/'package.json'),model_sha256=MODEL_SHA256)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/ihp-sg13g2');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
