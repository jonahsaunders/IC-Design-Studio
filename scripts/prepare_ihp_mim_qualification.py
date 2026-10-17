"""Prepare or copy the verified IHP package with the local MIM DRC correction."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import digest,file_digest
from icstudio.ihp_mim_rules import RELATIVE_PATH,BASE_SHA256,CORRECTED_SHA256,SOURCE_URL,corrected
from scripts.device_qualification_source import historical_input

BASE_REVISION='3abac20fcb57e184'
CORRECTED_REVISION='d03f47cdf46a85a0'
CORRECTED_MANIFEST='63616ff9b0af1ec391e325d8f5a44ec7a5a45b420ce9a1e0946fbb14b028057c'

@historical_input
def prepare(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new IHP adapter directory.')
    package=json.loads((source/'package.json').read_bytes())
    if package['id']!='ihp-sg13g2' or package['revision'] not in (BASE_REVISION,CORRECTED_REVISION):
        raise ValueError('Use a pinned IHP source or corrected package.')
    # Verify every source asset before creating anything. The content revision
    # also binds the catalog, layer map, model selections and engine contracts.
    technology=json.loads(json.dumps(package['technology']));technology['revision']=''
    if digest({'files':package['files'],'technology':technology})[:16]!=package['revision']:
        raise ValueError('IHP source package metadata does not match its revision.')
    for rel,expected in package['files'].items():
        path=(source/rel).resolve()
        if not path.is_relative_to(source) or not path.is_file() or file_digest(path)!=expected:
            raise ValueError('Changed IHP source asset: '+rel)
    if package['revision']==CORRECTED_REVISION:
        if file_digest(source/'package.json')!=CORRECTED_MANIFEST:
            raise ValueError('Changed corrected IHP manifest.')
        output.mkdir(parents=True)
        for rel in ['package.json',*package['files']]:
            target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,target)
            expected=CORRECTED_MANIFEST if rel=='package.json' else package['files'][rel]
            if file_digest(target)!=expected:raise ValueError('IHP asset changed during copy: '+rel)
        return dict(id=package['id'],revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),files=len(package['files']))
    updated=corrected((source/RELATIVE_PATH).read_bytes())
    provenance=dict(schema=1,source_manifest_sha256=file_digest(source/'package.json'),
        source_revision=package['revision'],source_url=SOURCE_URL,
        base_sha256=BASE_SHA256,corrected_sha256=CORRECTED_SHA256,
        change='Copy the existing MIM-contact and top-metal sets into fresh CIF planes before their connectivity traversal. The rule, distance and extraction remain unchanged.',
        scope='Local MIM DRC implementation correction; each layout still requires full DRC/LVS. No complete PDK or foundry qualification.',
        license='Upstream Apache-2.0 notice and license retained. Local modification identified in the rule file and this record.')
    additions={RELATIVE_PATH:updated,'ICSTUDIO-MIM-CORRECTION.json':(json.dumps(provenance,indent=2)+'\n').encode()}
    for rel,data in additions.items():package['files'][rel]=hashlib.sha256(data).hexdigest()
    package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    output.mkdir(parents=True)
    for rel,expected in package['files'].items():
        target=output/rel;target.parent.mkdir(parents=True,exist_ok=True)
        if rel in additions:target.write_bytes(additions[rel])
        else:shutil.copyfile(source/rel,target)
        if file_digest(target)!=expected:raise ValueError('IHP asset changed during preparation: '+rel)
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(id=package['id'],revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),files=len(package['files']))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/ihp-sg13g2');ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    print(json.dumps(prepare(args.input,args.output),indent=2))
