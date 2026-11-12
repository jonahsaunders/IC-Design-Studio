"""Versioned IHP tap bindings; preserve every original model and symbol byte."""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest
from icstudio.pdk_import import scan_local
from icstudio.ihp_taps import MODELS,SYMBOLS,NOTE
from scripts.ihp_tap_source import BASE,base_input


@base_input
def prepare(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new IHP tap package directory.')
    if file_digest(source/'package.json')!=BASE:raise ValueError('Use the exact reviewed IHP source package.')
    package=json.loads((source/'package.json').read_bytes())
    for name,h in package['files'].items():
        p=(source/name).resolve()
        if not p.is_relative_to(source) or not p.is_file() or file_digest(p)!=h:
            raise ValueError('Changed IHP source asset: '+name)
    for name,h in MODELS.items():
        if file_digest(source/'libs.tech/ngspice/models'/name)!=h:
            raise ValueError('Changed IHP tap model: '+name)
    scanned=scan_local(source)
    for model in SYMBOLS:
        key='sg13g2_pr/'+model+'.sym';entry=scanned['technology']['simulation']['catalog'][key]
        if entry.get('unavailable') or entry['model']!=model or entry['pin_order']!=['p','m']:
            raise ValueError('Unexpected IHP tap interface: '+model)
        package['technology']['simulation']['catalog'][key]=clone(entry)
    output.mkdir(parents=True)
    for name,h in package['files'].items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
        if file_digest(target)!=h:raise ValueError('IHP source changed during copy: '+name)
    record=dict(schema=1,source_manifest_sha256=BASE,source_revision=package['revision'],
        symbol_hashes=SYMBOLS,model_hashes=MODELS,change=NOTE,qualified=False,
        scope='Declarative two-terminal schematic model bindings. No complete operating envelope or physical qualification.')
    note=output/'ICSTUDIO-TAP-BINDINGS.json';note.write_bytes((json.dumps(record,indent=2)+'\n').encode())
    package['files'][note.name]=file_digest(note);package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),proof=record)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/ihp-sg13g2');ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
