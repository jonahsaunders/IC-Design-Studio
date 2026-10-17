"""Version the fixed internal geometry contract without modifying model assets."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest
from icstudio.catalog import validate_catalog
from icstudio.sky130_fixed_geometry import CONTRACTS,NOTE,constrain
from scripts.device_qualification_source import historical_input
from scripts.prepare_sky130_vpp_binding import prepare as parent_prepare


@historical_input
def prepare(source,output):
    source,output=Path(source),Path(output)
    parent=parent_prepare(source,output)
    package=json.loads((output/'package.json').read_bytes());original={}
    for key,entry in package['technology']['simulation']['catalog'].items():
        if entry.get('model') not in CONTRACTS:continue
        original[key]=clone(entry)
        constrain(entry['model'],entry['parameters'],(output/entry['model_source']).read_bytes())
        entry['notes'].append(NOTE)
    if len(original)!=7:raise ValueError('Unexpected fixed-geometry catalog coverage.')
    validate_catalog(package['technology'])
    note=dict(schema=1,parent=parent,original_bindings=original,contracts=CONTRACTS,scope=NOTE,
              upstream_assets_changed=False,complete_device_qualification=False)
    path=output/'ICSTUDIO-FIXED-GEOMETRY.json';path.write_bytes((json.dumps(note,indent=2)+'\n').encode())
    package['files'][path.name]=file_digest(path);package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),
                original_manifest_sha256=file_digest(source/'package.json'),changed_bindings=sorted(original))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/sky130A');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
