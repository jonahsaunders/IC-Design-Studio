"""Create an explicit IHP isolation-box test package without rewriting projects.

The catalog enables the interface and guards the model's inner dimensions.
Upstream terminal order, model defaults and source assets stay unchanged. This is not qualification
of the complete geometry, voltage, physical or reliability envelope.
"""
import argparse, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import digest,file_digest
from icstudio.catalog import validate_catalog
from icstudio.ihp_isolation import constrain
from scripts.prepare_ihp_mim_qualification import CORRECTED_MANIFEST
from scripts.device_qualification_source import historical_input


@historical_input
def prepare(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new isolation-box package directory.')
    if file_digest(source/'package.json')!=CORRECTED_MANIFEST:
        raise ValueError('Use the exact reviewed IHP MIM-corrected package.')
    package=json.loads((source/'package.json').read_bytes())
    for name,h in package['files'].items():
        path=(source/name).resolve()
        if not path.is_relative_to(source) or file_digest(path)!=h:
            raise ValueError('Changed IHP source asset: '+name)
    entry=package['technology']['simulation']['catalog']['sg13g2_pr/isolbox.sym']
    if entry['unavailable']!='Invalid model terminals.' or entry['pin_order']!=['isosub','nwell','sub!']:
        raise ValueError('Unexpected isolation-box binding.')
    entry['unavailable']=''
    constrain(entry['parameters'],(source/entry['model_source']).read_bytes())
    validate_catalog(package['technology'])
    package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    output.mkdir(parents=True)
    for name,h in package['files'].items():
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,p)
        if file_digest(p)!=h:raise ValueError('IHP source changed during copy: '+name)
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),
                original_manifest_sha256=CORRECTED_MANIFEST,files=len(package['files']),
                change='Enable the exact three-terminal isolbox binding and require positive inner model dimensions; source assets unchanged.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/ihp-sg13g2')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.input,a.output),indent=2))
