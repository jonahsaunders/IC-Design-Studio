"""Actual-engine acceptance and rejected-fault matrix for the 0.10 physical slice."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone, save_project, atomic_write, file_digest, validate, uid, device, example
from icstudio.analog import reference
from icstudio.analog_layout import generate_mirror
from icstudio.gf180_layout import reference_project, generate_inverter, install_mos, layers, MODELS
from icstudio.characterization import run as characterize, read_case, csv_text
from icstudio.hierarchical_flow import run
from icstudio.physical import erase, connectivity
from icstudio.physical_cells import assign_port, transform_selection
from icstudio.layout import rect
from icstudio.testbenches import create
from icstudio.catalog import link_technology, create_device


def technology(root):
    m=json.loads((root/'package.json').read_text());t=m['technology'];t.update(package_root=str(root),package_lock={k:m[k] for k in ('id','revision','files')})
    for rel,sha in m['files'].items():
        if file_digest(root/rel)!=sha:raise ValueError('Locked asset changed: '+rel)
    return t


def single_mos(tech, kind, width='2u', length='.28u'):
    p=example('empty');link_technology(p,tech);p['name']='GF180 '+kind+' physical qualification';top=p['cells'][0];top['name']='device_fixture'
    c={'id':uid(),'name':'gf180_'+kind.lower(),'ports':['D','G','S','B'],'devices':[],'shapes':[]};p['cells'].append(c)
    key=next(k for k,b in tech['simulation']['catalog'].items() if not b.get('unavailable') and b['model']==MODELS[kind] and b['pin_order']==['d','g','s','b'] and b.get('emit_parameters',{}).get('w')=='w')
    d=create_device(p['pdk'],key,'MDEVICE',350,200);d['params'].update(w=width,l=length);d['nets']={'d':'D','g':'G','s':'S','b':'B'};c['devices']=[d]
    pmos=kind=='PMOS';top['devices']=[device('V','VD',100,100,value='1.5' if pmos else '1.8',nets={'p':'force','n':'0'}),device('V','VSENSE',250,100,value='0',nets={'p':'force','n':'drain'}),device('V','VG',100,300,value='2.4' if pmos else '.9',nets={'p':'gate','n':'0'}),device('V','VS',100,500,value='3.3' if pmos else '0',nets={'p':'source','n':'0'}),device('X','XDUT',400,200,cell=c['id'],nets={'D':'drain','G':'gate','S':'source','B':'source'})]
    p['analysis'].update(type='op',corner='nominal');from icstudio.wiring import migrate
    for cell in p['cells']:migrate(cell,p)
    t=create(p,top['id'],'device_op');t['measurements']=[{'name':'drain_current','kind':'current','source':'VSENSE','min':'-10m' if pmos else '1n','max':'-1n' if pmos else '10m'}];p['testbenches']=[t]
    install_mos(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return validate(p),c['id'],t['id']


def main():
    a=argparse.ArgumentParser();a.add_argument('--pdks',required=True);a.add_argument('--output',required=True)
    for name in ('magic','netgen','ngspice'):a.add_argument('--'+name,required=True)
    args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True);tools={n:getattr(args,n) for n in ('magic','netgen','ngspice')};reports=[]
    def record(name,passed,**extra):
        reports.append({'name':name,'passed':bool(passed),**extra});atomic_write(out/'regression.json',json.dumps(reports,indent=2));print(name,passed,flush=True)
    def case(name,p,key,status='passed',stage=None):
        print('Running '+name,flush=True);r=run(p,key,out/name,tools);ok=r['status']==status and (stage is None or any(s['name']==stage and s['status']=='failed' for s in r['stages']))
        if r.get('navigation_warning'):ok=False
        record(name,ok,expected=status,observed=r['status'],error=r.get('error'),report=name+'/report.json');return r
    sky=technology(Path(args.pdks).resolve()/'sky130A');gf=technology(Path(args.pdks).resolve()/'gf180mcuC')
    p,cid,key=reference(sky);generate_mirror(p,cid);save_project(p,out/'sky130-mirror.icproj');r=case('sky130-mirror-op',p,key)
    record('mirror-ratio-pre-and-post',r['status']=='passed' and all(40e-6<m['before']<60e-6 and 40e-6<m['after']<60e-6 for m in r.get('comparison',[]) if m['name']=='output_current'))
    t=p['testbenches'][1];spec={**t['characterization'],'compare_layout':True};r=characterize(p,t['id'],spec,tools['ngspice'],out/'mirror-dc-comparison',tools=tools);atomic_write(out/'mirror-dc-comparison.csv',csv_text(r));record('mirror-dc-comparison',r['status']=='passed',summary=r['summary'])
    if r['status']=='passed':
        rows=[(read_case(r,i),read_case(r,i,'post-layout')) for i in range(3)]
        record('mirror-dc-compliance',all(a['currents']['vsense'][0]<1e-8 and a['currents']['vsense'][-1]>40e-6 and b['currents']['vsense'][0]<1e-8 and b['currents']['vsense'][-1]>40e-6 for a,b in rows))
    q=clone(p);t=q['testbenches'][0];t['analysis'].update(type='tran',step='20p',stop='42n');t['measurements'][0]['at']='18n';t['measurements'][1]['at']='18n';fixture=next(c for c in q['cells'] if c['id']==t['bench_cell']);v=next(d for d in fixture['devices'] if d['name']=='VOUT');v['source'].update(type='sine',low='1.2',high='1.5',period='20n',delay='0',duty='.5');r=case('mirror-transient-output-sine',q,t['id'])
    for corner in ('ss','ff'):
        q=clone(p);q['testbenches'][0]['analysis'].update(corner=corner,temperature=85 if corner=='ss' else 0);case('mirror-'+corner,q,key)
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);transform_selection(q,cid,[s['id'] for s in c['shapes']],10000,20000,90,True,include_annotations=True);case('mirror-complete-transform',q,key)
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);c['shapes'].append(rect('metal1' if 'metal1' in {l['name'] for l in sky['layers']} else __import__('icstudio.sky130_layout',fromlist=['layers']).layers(sky)['m1'],20000,20000,100,100));r=case('reject-mirror-drc',q,key,'failed','drc');record('navigate-mirror-drc',any(i['code']=='MAGIC.DRC' and i['cell_id']==cid and i.get('objects') for i in r.get('findings',[])))
    from icstudio.sky130_layout import layers as sky_layers
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);erase(c,sky_layers(sky)['m2'],[3000,-1000,4000,0]);r=case('reject-mirror-open',q,key,'failed','lvs');record('navigate-mirror-open',any(i['code']=='LVS.OPEN' and i.get('net')=='IREF' for i in r.get('findings',[])))
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);shape=next(s for s in c['shapes'] if s['layer']==sky_layers(sky)['poly']);shape['points'][1][0]+=100;case('reject-mirror-matching',q,key,'blocked','preflight')
    q,cid=reference_project(gf);generate_inverter(q,cid);key=q['testbenches'][0]['id'];save_project(q,out/'gf180-inverter.icproj');case('gf180-inverter-nominal',q,key)
    for corner in ('ss','ff'):
        sample=clone(q);sample['testbenches'][0]['analysis'].update(corner=corner,temperature=85 if corner=='ss' else 0);case('gf180-inverter-'+corner,sample,key)
    t=q['testbenches'][0];r=characterize(q,key,t['characterization'],tools['ngspice'],out/'gf180-load-comparison',tools=tools);atomic_write(out/'gf180-load-comparison.csv',csv_text(r));record('gf180-load-comparison',r['status']=='passed',summary=r['summary'])
    for kind in ('NMOS','PMOS'):
        for name,width,length in (('minimum','1u','.28u'),('long','1u','2u'),('wide','10u','.28u')):
            sample,dcid,dkey=single_mos(gf,kind,width,length);save_project(sample,out/('gf180-'+kind.lower()+'-'+name+'.icproj'));r=case('gf180-'+kind.lower()+'-'+name,sample,dkey)
            record('gf180-'+kind.lower()+'-'+name+'-current-agreement',r['status']=='passed' and abs(r['comparison'][0]['delta']/r['comparison'][0]['before'])<.05)
    sample,dcid,dkey=single_mos(gf,'NMOS');cell=next(c for c in sample['cells'] if c['id']==dcid);pin=next(v for v in cell['layout_pins'] if v['pin']=='b');x,y=pin['point'];erase(cell,layers(sample['pdk'])['contact'],[x-200,y-200,x+200,y+200]);case('reject-gf180-body-contact',sample,dkey,'failed','lvs')
    from icstudio.ring_oscillator import reference as ring_reference,generate as generate_ring
    sample,rcid,rkey=ring_reference(sky);generate_ring(sample,rcid);child=next(c for c in sample['cells'] if c['name']=='inverter');fault=rect(sky_layers(sky)['m1'],20000,20000,100,100);child['shapes'].append(fault);r=case('reject-child-drc-navigation',sample,rkey,'failed','drc');record('navigate-child-local-coordinates',any(i['code']=='MAGIC.DRC' and i['cell_id']==child['id'] and fault['id'] in i.get('objects',[]) for i in r.get('findings',[])))
    sample=clone(q);c=next(c for c in sample['cells'] if c['id']==cid);ls=layers(sample['pdk']);c['shapes'].append(rect(ls['m1'],20000,20000,100,100));case('reject-gf180-drc',sample,key,'failed','drc')
    sample=clone(q);c=next(c for c in sample['cells'] if c['id']==cid);path=next(s for s in c['shapes'] if s.get('generated_route') and s['net']=='Y');x=path['points'][1][0];erase(c,ls['m1'],[x-400,3000,x+400,4000]);case('reject-gf180-open',sample,key,'failed','lvs')
    sample=clone(q);c=next(c for c in sample['cells'] if c['id']==cid);shape=next(s for s in c['shapes'] if s['layer']==ls['poly']);shape['points'][1][0]+=100;r=case('reject-gf180-dimensions',sample,key,'failed','lvs');record('navigate-gf180-property',any(i['code']=='NETGEN.PROPERTY' and i.get('object')==c['devices'][0]['id'] for i in r.get('findings',[])))
    sample=clone(q);sample['testbenches'][0]['measurements'][0]['max']='40p';r=case('reject-gf180-post-layout-limit',sample,key,'failed','post_layout_simulation');record('retain-failed-post-layout-value',bool(r.get('comparison')) and r['comparison'][0].get('after_status')=='failed')
    sample=clone(q);sample['testbenches'][0]['measurements'][0]['max']='1p';case('reject-gf180-limits',sample,key,'failed','schematic_simulation')
    print('PASS' if all(r['passed'] for r in reports) else 'FAIL',len(reports),'checks',flush=True);return 0 if all(r['passed'] for r in reports) else 1


if __name__=='__main__':raise SystemExit(main())
