"""Real-engine regression of custom geometry, deliberate faults and layout exchanges."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,save_project,atomic_write,file_digest
from icstudio.pdk_import import scan_local
from icstudio.sky130_layout import reference_project,generate_inverter,layers
from icstudio.silicon_flow import run,magic_script
from icstudio.interchange import export_layout
from icstudio.import_review import propose_layout_change
from icstudio.layout import kdb,rect
from icstudio.physical import erase


def main():
    a=argparse.ArgumentParser();a.add_argument('--pdk',required=True);a.add_argument('--output',required=True)
    for tool in ('magic','netgen','ngspice'):a.add_argument('--'+tool,required=True)
    args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);tools={n:getattr(args,n) for n in ('magic','netgen','ngspice')}
    m=scan_local(args.pdk);t=m['technology'];t['package_root']=str(Path(args.pdk).resolve());t['package_lock']={'id':m['id'],'revision':m['revision'],'files':m['files']}
    base,cid=reference_project(t);generate_inverter(base,cid);save_project(base,out/'custom-inverter.icproj');reports=[]
    def case(name,p,expected='passed',failed_stage=None):
        print(name,flush=True);r=run(p,cid,out/name,tools);item={'name':name,'expected':expected,'observed':r['status'],'report':name+'/report.json','passed':r['status']==expected}
        if failed_stage:item['passed'] &= any(s['name']==failed_stage and s['status']=='failed' for s in r['stages'])
        reports.append(item);atomic_write(out/'regression.json',json.dumps(reports,indent=2));return r
    case('nominal',base)
    for corner in ('ss','ff'):
        p=clone(base);p['analysis']['corner']=corner;case(corner,p)
    p=clone(base);c=next(c for c in p['cells'] if c['id']==cid)
    for d in c['devices']:d['params'].update(w='0.42u',l='0.155u')
    generate_inverter(p,cid,True);case('minimum-width',p)
    p=clone(base);c=next(c for c in p['cells'] if c['id']==cid)
    for d in c['devices']:d['params'].update(w='1.5u' if d['kind']=='NMOS' else '3u',l='0.35u')
    generate_inverter(p,cid,True);case('resized',p)
    p=clone(base);c=next(c for c in p['cells'] if c['id']==cid);c['shapes'].append(rect(layers(p['pdk'])['m1'],10000,0,100,100));case('reject-drc',p,'failed','drc')
    p=clone(base);c=next(c for c in p['cells'] if c['id']==cid);erase(c,layers(p['pdk'])['m1'],[1400,3000,1900,3500]);case('reject-open',p,'failed','lvs')
    p=clone(base);c=next(c for c in p['cells'] if c['id']==cid);n=c['devices'][0];poly=next(s for s in c['shapes'] if s['layer']==layers(p['pdk'])['poly'] and s.get('device_id')==n['id']);poly['points'][1][0]+=50;case('reject-dimensions',p,'failed','lvs')
    # A real KLayout database edit written as OASIS and reviewed into the native design.
    exported=out/'klayout-edit.oas';export_layout(base,exported);db=kdb();ly=db.Layout();ly.read(str(exported));ly.cell(c['name']).shapes(ly.layer(68,20)).insert(db.Box(1480,2000,2400,2340));ly.write(str(exported));p,notes=propose_layout_change(base,exported);atomic_write(out/'klayout-review.json',json.dumps(notes,indent=2));case('klayout-edit',p)
    # Convert the saved native Magic cell with the real matching technology engine.
    # The extra metal stub is a harmless external edit, not a copied standard cell.
    mag=out/'nominal/drc'/ (c['name']+'.mag')
    if mag.is_file():
        from icstudio.engines import execute,tcl_word,magic_import
        edit=out/'magic-edit-source';edit.mkdir();copied=edit/mag.name;copied.write_bytes(mag.read_bytes());tech=Path(args.pdk).resolve()/'libs.tech/magic/sky130A.tech'
        script='load '+tcl_word(copied)+'\nbox values 1.48um 2um 2.4um 2.34um\npaint metal1\nsave '+tcl_word(copied)+'\nquit -noprompt\n';atomic_write(edit/'edit.tcl',script);atomic_write(edit/'edit.log',execute([tools['magic'],'-dnull','-noconsole','-T',str(tech)],edit,input_text=script))
        magic_import(tools['magic'],copied,tech,out/'magic-conversion');p,notes=propose_layout_change(base,out/'magic-conversion/imported.gds');atomic_write(out/'magic-review.json',json.dumps(notes,indent=2));case('magic-edit',p)
    else:reports.append({'name':'magic-edit','passed':False,'error':'Native Magic cell was not produced.'})
    atomic_write(out/'regression.json',json.dumps(reports,indent=2));return 0 if all(r['passed'] for r in reports) else 1

if __name__=='__main__':raise SystemExit(main())
