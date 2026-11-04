"""Exercise every bundled catalog entry without claiming model/PDK qualification.

The expected mapping here is the locked catalog, not an independently reviewed
upstream model interface. Source reconciliation remains a separate chunk-7 gate.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,example,file_digest,save_project,load_project
from icstudio.catalog import create_device,parameter_values
from icstudio.catalog_migration import instance_name
from icstudio.interchange import spice,export_xschem
from icstudio.xschem_io import import_package
from scripts.qualify_standard_mos import PROFILES,load_technology,write


def compare(entry,before,after):
    a=parameter_values(entry,before);b=parameter_values(entry,after)
    if before['model_ref']!=after['model_ref'] or before['nets']!=after['nets']:
        raise ValueError('Changed catalog identity or terminal mapping.')
    if a.keys()!=b.keys() or any(not math.isfinite(v) or not math.isfinite(b[k])
        or not math.isclose(v,b[k],rel_tol=5e-11,abs_tol=0) for k,v in a.items()):
        raise ValueError('Changed model parameters.')
    return len(a)


def require_rejection(project,change):
    candidate=clone(project);change(candidate['cells'][0]['devices'][0])
    try:spice(candidate)
    except ValueError as error:return str(error)
    raise ValueError('Invalid catalog device was silently emitted.')


def one(tech,key,folder):
    entry=tech['simulation']['catalog'][key];row={'device':key,'status':'RUNNING'}
    try:
        if entry.get('unavailable'):
            try:create_device(tech,key,'DUT')
            except ValueError as error:
                if str(error)!=entry['unavailable']:raise
                return dict(device=key,status='EXPECTED_UNSUPPORTED',reason=str(error),electrical_device_created=False)
            raise ValueError('An unavailable catalog entry became placeable.')
        folder.mkdir(parents=True);p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='catalog_coupon'
        d=create_device(p['pdk'],key,'DUT',400,300)
        d['nets']={pin:'N'+str(i+1) for i,pin in enumerate(entry['pin_order'])};c['devices']=[d]
        save_project(p,folder/'input.icproj');q=load_project(folder/'input.icproj')
        row['native_parameter_count']=compare(entry,d,q['cells'][0]['devices'][0])
        text=spice(q);(folder/'native.cir').write_bytes(text.encode())
        name=instance_name(d,entry);line=next(line for line in text.splitlines() if line.startswith(name+' '))
        fields=line.split();n=len(entry['pin_order'])
        if fields[1:n+1]!=[d['nets'][pin] for pin in entry['pin_order']] or fields[n+1]!=entry['model']:
            raise ValueError('Emitted model or terminal order differs from the locked catalog.')
        for rotation in (0,90):
            p['cells'][0]['devices'][0]['rotation']=rotation;dest=folder/('xschem-'+str(rotation))
            export_xschem(p,dest);after,_=import_package(dest)
            if len(after['cells'][0]['devices'])!=1:raise ValueError('Changed electrical device count.')
            compare(entry,d,after['cells'][0]['devices'][0])
        row['roundtrips']=['native','xschem-0','xschem-90']
        row['invalid_controls']={
            'unknown-model':require_rejection(p,lambda v:v['model_ref'].update(device='__missing__')),
            'wrong-revision':require_rejection(p,lambda v:v['model_ref'].update(revision='__wrong__')),
            'unknown-parameter':require_rejection(p,lambda v:v['model_params'].update(__unknown__='1'))}
        for key in entry.get('parameters',{}):
            def invalid(v,key=key):
                (v['params'] if v['kind'] in ('NMOS','PMOS') and key in ('w','l') else v['model_params'])[key]='NaN'
            row['invalid_controls']['nonfinite-'+key]=require_rejection(p,invalid)
        row.update(status='PASS',input_sha256=file_digest(folder/'input.icproj'),native_sha256=file_digest(folder/'native.cir'))
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    if folder.is_dir():write(folder/'record.json',row)
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,processes={},cases=[],
        scope='Bundled catalog save/reopen, emitted terminal/model order, Studio Xschem exchange and malformed-input rejection. No upstream interface reconciliation, valid operating envelope, external Xschem execution, electrical or physical qualification.',
        source_sha256=file_digest(__file__),source_files_sha256=file_digest(out/'source-files.json'))
    for target in PROFILES:
        tech,identity=load_technology(target);report['processes'][target]=identity
        for key in sorted(tech['simulation']['catalog']):
            row=one(tech,key,out/target/Path(key).stem);row['target']=target;report['cases'].append(row)
            write(out/'qualification.json',report)
            print(target,key,row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and all(r['status'] in ('PASS','EXPECTED_UNSUPPORTED') for r in report['cases']) else 'FAIL'
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
