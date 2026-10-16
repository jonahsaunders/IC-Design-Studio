"""Create an installable SKY130 package with explicit resistor multiplicity."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import digest,file_digest
from icstudio.sky130_resistor_models import BASE_SHA256,relative,corrected


def prepare(source,output):
    from scripts.sky130_qualification_source import original_package
    with original_package(source) as original:
        return prepare_original(original,output)


def prepare_original(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new SKY130 adapter directory.')
    package=json.loads((source/'package.json').read_bytes())
    if package['id']!='sky130A' or package['revision']!='b1f441fabee1ed85':raise ValueError('Use the reviewed bundled SKY130 package.')
    technology=json.loads(json.dumps(package['technology']));technology['revision']=''
    if digest({'files':package['files'],'technology':technology})[:16]!=package['revision']:raise ValueError('Changed SKY130 package metadata.')
    for rel,expected in package['files'].items():
        p=(source/rel).resolve()
        if not p.is_relative_to(source) or not p.is_file() or file_digest(p)!=expected:raise ValueError('Changed SKY130 source asset: '+rel)
    additions={relative(name):corrected(name,(source/relative(name)).read_bytes()) for name in BASE_SHA256}
    provenance=dict(schema=1,source_manifest_sha256=file_digest(source/'package.json'),source_revision=package['revision'],
        change='Declare and explicitly forward the parallel M factor to immediate resistor and nested parasitic/model calls. Model equations and statistical MULT expressions are unchanged.',
        files={rel:dict(original_sha256=package['files'][rel],corrected_sha256=hashlib.sha256(data).hexdigest()) for rel,data in additions.items()},
        scope='Selected local electrical integration only. Complete operating envelopes, noise, statistical behavior and physical qualification remain separate requirements.',
        license='Apache-2.0 upstream notices and LICENSE retained; modified files identify IC Design Studio changes.')
    additions['ICSTUDIO-RESISTOR-CORRECTION.json']=(json.dumps(provenance,indent=2)+'\n').encode()
    for rel,data in additions.items():package['files'][rel]=hashlib.sha256(data).hexdigest()
    package['technology']['revision']='';package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    output.mkdir(parents=True)
    for rel,expected in package['files'].items():
        target=output/rel;target.parent.mkdir(parents=True,exist_ok=True)
        if rel in additions:target.write_bytes(additions[rel])
        else:shutil.copyfile(source/rel,target)
        if file_digest(target)!=expected:raise ValueError('SKY130 asset changed during preparation: '+rel)
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(id=package['id'],revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),files=len(package['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/sky130A');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.input,a.output),indent=2))
