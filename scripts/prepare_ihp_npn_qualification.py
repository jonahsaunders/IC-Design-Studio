"""Create a separate pinned IHP package for local NPN DRC qualification."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import digest,file_digest
from icstudio.ihp_npn_rules import RELATIVE_PATH,BASE_SHA256,corrected
from scripts.ihp_tap_source import base_input


@base_input
def prepare(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new IHP NPN package directory.')
    package=json.loads((source/'package.json').read_bytes())
    if package['id']!='ihp-sg13g2' or package['revision']!='1e24ec25b491028b':raise ValueError('Use the locked default IHP source package.')
    technology=json.loads(json.dumps(package['technology']));technology['revision']=''
    if digest({'files':package['files'],'technology':technology})[:16]!=package['revision']:raise ValueError('Invalid IHP metadata revision.')
    for name,h in package['files'].items():
        path=(source/name).resolve()
        if not path.is_relative_to(source) or not path.is_file() or file_digest(path)!=h:raise ValueError('Changed IHP source asset: '+name)
    fixed=corrected((source/RELATIVE_PATH).read_bytes())
    record=dict(schema=1,source_revision=package['revision'],source_manifest_sha256=file_digest(source/'package.json'),
        source_commit='5e6d592e4002946a4616f798c357f0f3c06cf3b6',base_sha256=BASE_SHA256,corrected_sha256=hashlib.sha256(fixed).hexdigest(),
        change='Intersect the original grown-NPN seed with the original active set, then traverse each disconnected component. No rule operand, distance, illegal mask, extraction or model change.',
        scope='Local public NPN checker correction; full layout DRC/LVS remains required. Not foundry or complete PDK qualification.',
        license='Original Apache-2.0 notices and license preserved; local correction explicitly identified.')
    additions={RELATIVE_PATH:fixed,'ICSTUDIO-NPN-CORRECTION.json':(json.dumps(record,indent=2)+'\n').encode()}
    for name,data in additions.items():package['files'][name]=hashlib.sha256(data).hexdigest()
    package['technology']['revision']='';package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    output.mkdir(parents=True)
    for name,h in package['files'].items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True)
        if name in additions:target.write_bytes(additions[name])
        else:shutil.copyfile(source/name,target)
        if file_digest(target)!=h:raise ValueError('IHP transfer verification failed: '+name)
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),correction=record)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/ihp-sg13g2');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
