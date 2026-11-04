"""Add the exact public high-voltage library omitted by the earlier closure.

All existing assets and unrelated catalog entries remain unchanged. This
reconstructible package does not claim physical or full operating qualification.
"""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest
from icstudio.catalog import validate_catalog
from icstudio.pdk_import import scan_local
from icstudio.gf180_hv import MODEL_PATH,MODEL_SHA256,MODELS,CORNERS,NOTE,DOCUMENTATION
from scripts.gf180_hv_source import BASE,RETAINED,previous_hv
SOURCE=RETAINED/'smbb000149.spice'


def prepare(source,output,model=SOURCE):
    output=Path(output).resolve();model=Path(model).resolve()
    if output.exists():raise ValueError('Choose a new high-voltage package directory.')
    if file_digest(model)!=MODEL_SHA256:raise ValueError('Changed public GF180 high-voltage source.')
    with previous_hv(source) as base:
        base=Path(base).resolve();h=file_digest(base/'package.json')
        target=next((t for t,v in BASE.items() if h==v),None)
        if target is None:raise ValueError('Use an exact reviewed GF180 high-voltage base package.')
        package=json.loads((base/'package.json').read_bytes())
        lock=json.loads((base/'UPSTREAM-LOCK.json').read_bytes())['models']
        records=[v for v in lock['files'].values() if v['source']=='models/ngspice/smbb000149.spice']
        if len(records)!=1 or records[0]['sha256']!=MODEL_SHA256:raise ValueError('High-voltage source differs from the original upstream lock.')
        for rel,expected in package['files'].items():
            p=(base/rel).resolve()
            if not p.is_relative_to(base) or file_digest(p)!=expected:raise ValueError('Changed GF180 source asset: '+rel)
        output.mkdir(parents=True)
        for rel,expected in package['files'].items():
            dest=output/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/rel,dest)
            if file_digest(dest)!=expected:raise ValueError('GF180 source changed during copy: '+rel)
        dest=output/MODEL_PATH;shutil.copyfile(model,dest)
        if file_digest(dest)!=MODEL_SHA256:raise ValueError('GF180 high-voltage source changed during copy.')
        scanned=scan_local(output);catalog=package['technology']['simulation']['catalog']
        for name in MODELS:
            key='symbols/'+name+'.sym';entry=scanned['technology']['simulation']['catalog'][key]
            if entry.get('unavailable') or entry['model']!=name or entry['pin_order']!=['d','g','s','b'] or entry['prefix']!='X':
                raise ValueError('Unexpected GF180 high-voltage interface: '+name)
            catalog[key]=clone(entry)
        package['technology']['simulation']['includes'].append(dict(path=MODEL_PATH,sections=CORNERS))
        package['files'][MODEL_PATH]=MODEL_SHA256
        proof=dict(schema=1,base_manifest_sha256=h,base_revision=package['revision'],
            upstream_repository=lock['repository'],upstream_revision=lock['revision'],
            upstream_path=records[0]['source'],source_sha256=MODEL_SHA256,documentation=DOCUMENTATION,
            change=NOTE,qualified=False,scope=__doc__)
        note=output/'ICSTUDIO-HIGH-VOLTAGE.json';note.write_bytes((json.dumps(proof,indent=2)+'\n').encode())
        package['files'][note.name]=file_digest(note);validate_catalog(package['technology'])
        package['technology']['revision']='';package['revision']=package['technology']['revision']=digest(dict(files=package['files'],technology=package['technology']))[:16]
        (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
        return dict(target=target,revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),proof=proof)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--model',type=Path,default=SOURCE)
    a=ap.parse_args();print(json.dumps(prepare(a.input,a.output,a.model),indent=2))
