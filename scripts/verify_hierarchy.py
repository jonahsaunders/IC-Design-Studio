"""Installed-engine gate for shared physical cells and saved testbenches."""
import argparse,json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,save_project,atomic_write,scalar
from icstudio.pdk_import import scan_local
from icstudio.ring_oscillator import reference,generate
from icstudio.sky130_layout import reference_project,generate_inverter,layers
from icstudio.hierarchical_flow import run
from icstudio.silicon_flow import run as inverter_run
from icstudio.interchange import export_layout,export_xschem
from icstudio.import_review import propose_layout_change
from icstudio.layout import kdb,rect
from icstudio.physical_cells import ports
from icstudio.physical import erase
from icstudio.engines import execute,tcl_word,magic_import,run_deck
from icstudio.testbenches import measure
from icstudio.pdks import model_lines
from icstudio.xschem_io import import_package


def main():
    a=argparse.ArgumentParser();a.add_argument('--pdk',required=True);a.add_argument('--output',required=True)
    for tool in ('magic','netgen','ngspice','xschem'):a.add_argument('--'+tool,required=True)
    a.add_argument('--xschem-workdir');args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);tools={n:getattr(args,n) for n in ('magic','netgen','ngspice')}
    m=scan_local(args.pdk);tech=m['technology'];tech['package_root']=str(Path(args.pdk).resolve());tech['package_lock']={'id':m['id'],'revision':m['revision'],'files':m['files']}
    base,cid,tbid=reference(tech);generate(base,cid);save_project(base,out/'ring-oscillator.icproj');reports=[]
    def record(item):reports.append(item);atomic_write(out/'regression.json',json.dumps(reports,indent=2))
    def case(name,p,expected='passed',failed_stage=None,key=tbid):
        print(name,flush=True);r=run(p,key,out/name,tools);ok=r['status']==expected
        if failed_stage:ok &= any(s['name']==failed_stage and s['status']=='failed' for s in r['stages'])
        record({'name':name,'expected':expected,'observed':r['status'],'report':name+'/report.json','passed':ok});return r
    case('ring-nominal',base)
    for corner in ('ss','ff'):
        p=clone(base);p['testbenches'][0]['analysis']['corner']=corner;case('ring-'+corner,p)
    p=clone(base);t=p['testbenches'][0];t['analysis']['temperature']='85';t['initial_conditions']['n2']='1.6';t['measurements'][0]['threshold']='.8';bench=next(c for c in p['cells'] if c['id']==t['bench_cell']);next(d for d in bench['devices'] if d['name']=='VDD')['value']='1.6';case('ring-1v6-85c',p)
    for nf in (2,3,4,8):
        p,inv=reference_project(tech);c=next(c for c in p['cells'] if c['id']==inv)
        for d in c['devices']:d['params']['w']=str(nf*(.5 if d['kind']=='NMOS' else 1))+'u';d['model_params']['nf']=str(nf)
        generate_inverter(p,inv);save_project(p,out/('inverter-'+str(nf)+'f.icproj'));name='inverter-'+str(nf)+'f';print(name,flush=True);r=inverter_run(p,inv,out/name,tools);record({'name':name,'expected':'passed','observed':r['status'],'report':name+'/report.json','passed':r['status']=='passed'})
    p=clone(base);c=next(c for c in p['cells'] if c['id']==cid);c['shapes'].append(rect(layers(tech)['m1'],10000,20000,100,100));case('reject-parent-drc',p,'failed','drc')
    p=clone(base);c=next(c for c in p['cells'] if c['id']==cid);path=next(s for s in c['shapes'] if s['kind']=='path' and s.get('net')=='N1');x,y=path['points'][1];erase(c,layers(tech)['m1'],[x+700,y-500,x+1200,y+500]);case('reject-ring-open',p,'failed','lvs')
    p=clone(base);c=next(c for c in p['cells'] if c['name']=='inverter');n=c['devices'][0];gate=next(s for s in c['shapes'] if s['layer']==layers(tech)['poly'] and s.get('device_id')==n['id']);gate['points'][1][0]+=50;case('reject-child-dimensions',p,'failed','lvs')
    p=clone(base);p['testbenches'][0]['measurements'][0]['max']='1meg';case('reject-invalid-limits',p,'blocked','preflight')
    p=clone(base);p['testbenches'][0]['measurements'][0]['max']='1G';case('reject-frequency-limit',p,'failed','schematic_simulation')
    p=clone(base);t=p['testbenches'][0];t['initial_conditions']={n:'0' for n in t['initial_conditions']};bench=next(c for c in p['cells'] if c['id']==t['bench_cell']);next(d for d in bench['devices'] if d['name']=='VDD')['value']='0';case('reject-no-oscillation',p,'failed','schematic_simulation')
    # Real KLayout database edit of parent metal with shared cell references intact.
    x,y=next(pt['point'] for pt in ports(base,cid) if pt['name']=='OUT');box=[x-170,y-170,x+1000,y+170];exported=out/'klayout-edit.oas';export_layout(base,exported);db=kdb();ly=db.Layout();ly.read(str(exported));ly.cell('ring_oscillator').shapes(ly.layer(68,20)).insert(db.Box(*box));ly.write(str(exported));p,notes=propose_layout_change(base,exported);atomic_write(out/'klayout-review.json',json.dumps(notes,indent=2));case('klayout-ring-edit',p)
    # Actual Magic native edit; copy every saved child so the hierarchy resolves.
    edit=out/'magic-native-edit';edit.mkdir();
    for f in (out/'ring-nominal/drc').glob('*.mag'):shutil.copy2(f,edit/f.name)
    mag=edit/'ring_oscillator.mag';techfile=Path(args.pdk).resolve()/'libs.tech/magic/sky130A.tech';script='load '+tcl_word(mag)+'\nbox values '+' '.join(str(v/1000)+'um' for v in box)+'\npaint metal1\nsave '+tcl_word(mag)+'\nquit -noprompt\n';atomic_write(edit/'edit.tcl',script);atomic_write(edit/'edit.log',execute([tools['magic'],'-dnull','-noconsole','-T',str(techfile)],edit,input_text=script));magic_import(tools['magic'],mag,techfile,out/'magic-conversion');p,notes=propose_layout_change(base,out/'magic-conversion/imported.gds');atomic_write(out/'magic-review.json',json.dumps(notes,indent=2));case('magic-ring-edit',p)
    # Xschem emits a real three-level netlist. Edit the reusable child once and
    # verify all three instances still refer to it on import and simulation.
    exchange=out/'xschem';export_xschem(base,exchange);(exchange/'profile').mkdir();rc=exchange/'xschemrc';atomic_write(rc,'set XSCHEM_LIBRARY_PATH '+tcl_word(exchange)+'\nset netlist_dir '+tcl_word(exchange)+'\nset USER_CONF_DIR '+tcl_word(exchange/'profile')+'\nset XSCHEM_TMP_DIR '+tcl_word(exchange)+'\nset undo_type disk\n');cwd=Path(args.xschem_workdir).resolve() if args.xschem_workdir else exchange
    child=next(c for c in base['cells'] if c['name']=='inverter');n=next(d for d in child['devices'] if d['kind']=='NMOS')
    for mode in ('original','edited'):
        if mode=='edited':
            f=exchange/'inverter.sch';lines=f.read_text().splitlines()
            for i,line in enumerate(lines):
                if 'symbols/'+n['id']+'.sym' in line:lines[i]=re.sub(r'(?<!\w)w=\S+','w=1.5',line)
            f.write_text('\n'.join(lines)+'\n')
        q,notes=import_package(exchange);c=next(c for c in q['cells'] if c['id']==cid);assert len(c['devices'])==3 and {d['cell'] for d in c['devices']}=={child['id']};assert q['testbenches']==base['testbenches'];assert [d['nets'] for d in c['devices']]==[d['nets'] for cc in base['cells'] if cc['id']==cid for d in cc['devices']]
        if mode=='edited':assert scalar(next(d for cc in q['cells'] if cc['id']==child['id'] for d in cc['devices'] if d['kind']=='NMOS')['params']['w'])==1.5e-6
        directory=exchange/mode;directory.mkdir();save_project(q,directory/'reimported.icproj');atomic_write(directory/'import-review.json',json.dumps(notes,indent=2));log=execute([args.xschem,'-x','-q','-n','-s','--rcfile',rc,'-o',exchange,exchange/'ring_testbench.sch'],cwd,timeout=30);atomic_write(directory/'netlisting.log',log)
        if re.search(r'unable to open|FATAL|not found|error executing|SKIPPING',log,re.I):raise ValueError('Xschem reported netlisting errors.')
        native=(exchange/'ring_testbench.spice').read_text();assert len(re.findall(r'^\.subckt inverter\b',native,re.M|re.I))==1;assert re.search(r'^\.subckt ring_oscillator\b',native,re.M|re.I)
        atomic_write(directory/'xschem.spice',native);text='* Xschem ring oscillator with saved startup and observation window\n'+'\n'.join(model_lines(q['pdk']))+'\n'+re.sub(r'^\.end\s*$','',native,flags=re.M|re.I)+'\n.tran 2p 8n uic\n.ic v(n1)=0 v(n2)=1.8 v(out)=0\n.save v(n1) v(n2) v(out)\n.end\n';atomic_write(directory/'testbench.cir',text);r=run_deck(q,q['top'],{'type':'deck','deck':str(directory/'testbench.cir')},args.ngspice,directory);atomic_write(directory/'result.json',json.dumps(r));measurements=measure(r,q['testbenches'][0]);atomic_write(directory/'measurements.json',json.dumps(measurements,indent=2));record({'name':'xschem-'+mode,'expected':'passed','observed':measurements['status'],'passed':measurements['status']=='passed','measurements':measurements})
    print(json.dumps(reports,indent=2));return 0 if all(r['passed'] for r in reports) else 1

if __name__=='__main__':raise SystemExit(main())
