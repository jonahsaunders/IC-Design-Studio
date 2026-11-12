"""Prepare a separately versioned SKY130 package with the documented LI model."""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest
from icstudio.pdk_import import scan_local
from icstudio.sky130_li_binding import DOCUMENTATION,MODEL,MODEL_SHA256,SYMBOL_SHA256
from scripts.sky130_li_source import BASE,base_input
KEY='sky130_fd_pr/res_generic_li.sym'


@base_input
def prepare(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new SKY130 LI package directory.')
    if file_digest(source/'package.json')!=BASE:raise ValueError('Use the exact reviewed SKY130 default package.')
    package=json.loads((source/'package.json').read_bytes())
    for name,h in package['files'].items():
        p=(source/name).resolve()
        if not p.is_relative_to(source) or not p.is_file() or file_digest(p)!=h:raise ValueError('Changed SKY130 source asset: '+name)
    scanned=scan_local(source);entry=scanned['technology']['simulation']['catalog'][KEY]
    if entry.get('unavailable') or entry['model']!=MODEL or entry['prefix']!='R' or entry['pin_order']!=['m','p']:raise ValueError('Unexpected local-interconnect model interface.')
    package['technology']['simulation']['catalog'][KEY]=clone(entry)
    record=dict(schema=1,source_manifest_sha256=BASE,source_revision=package['revision'],source_symbol_sha256=SYMBOL_SHA256,source_model_sha256=MODEL_SHA256,documentation=DOCUMENTATION,
        change='Map the source res_generic_li symbol to its documented local-interconnect resistor model sky130_fd_pr__res_generic_l1. Original files and all other catalog bindings retained.',qualified=False)
    output.mkdir(parents=True)
    for name,h in package['files'].items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
        if file_digest(target)!=h:raise ValueError('SKY130 source changed during copy: '+name)
    note=output/'ICSTUDIO-LI-BINDING.json';note.write_bytes((json.dumps(record,indent=2)+'\n').encode());package['files'][note.name]=file_digest(note)
    package['technology']['revision']='';package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),proof=record)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/sky130A');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
