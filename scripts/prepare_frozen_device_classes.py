"""Prepare the existing finite class fixtures; never run native tools.

Inputs exercise parallel CMIM saved benches, shared-bottom MiM and standard MOS
finger grouping. Model limits, tolerances and old acceptance recipes are unchanged.
"""
import argparse,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,load_project,save_project,uid,validate
from icstudio.testbenches import create,native_subcircuit
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_ihp_cmim_multiplicity import two_units,attach
from scripts.qualify_ihp_mim_layout import rotate
from scripts.qualify_sky130_mim_shared import shared_project
from scripts.qualify_sky130_mim2 import independent
from scripts.qualify_standard_mos_layout import technology
from scripts.qualify_ihp_hv_mos_layouts import fixture as hv_fixture,selected as hv_reference
from scripts.qualify_mos_finger_layouts import fixture as lv_fixture,selected as lv_reference
from scripts.qualification_geometry import rotated

def require(ok,message):
    if not ok:raise ValueError(message)
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def bench(project,kind):
    p=clone(project)
    if kind=='cmim':
        sources=[device('V','VIN',value='0',nets={'p':'vin','n':'0'})]
        nets={'C1':'vin','C2':'0'};p['analysis'].update(type='ac',start='100k',end='1meg',points=2,temperature=27,corner='nominal')
        measurement={'name':'finite_current','kind':'current','source':'VIN','at':'1meg'}
    else:
        sources=[device('V','VD',x=0,y=0,value='.5',nets={'p':'vd','n':'0'}),device('V','VG',x=0,y=300,value='1',nets={'p':'vg','n':'0'})]
        nets={'D':'vd','G':'vg','S':'0','B':'0'};p['analysis'].update(type='op',temperature=27,corner='nominal');measurement={'name':'finite_drain_current','kind':'current','source':'VD'}
    fixture={'id':uid(),'name':'fixture','ports':[],'shapes':[],'devices':sources+[device('X','DUT',cell=p['top'],nets=nets)]}
    p['cells'].append(fixture);t=create(p,fixture['id'],'device_class_'+kind);t['measurements']=[measurement];p['testbenches']=[t];p.pop('simulation_runtime',None);validate(p);return p,t

def prepare(out,sky130=None,pilot=False):
    out=Path(out).absolute();require(not out.exists(),'fresh fixture directory');out.mkdir(parents=True);rows=[];sources={}
    def record(name,p,settings,expect,**facts):
        p=clone(p)
        for cell in p['cells']:
            cell.setdefault('wires',[]);cell.setdefault('junctions',[])
            for component in cell.get('devices',[]):component.setdefault('net_labels',clone(component.get('nets',{})))
        folder=out/name;folder.mkdir();save_project(p,folder/'input.icproj');captured=native_subcircuit(p,p['top']);(folder/'captured.spice').write_text(captured,encoding='utf-8')
        rows.append(dict(name=name,project=name+'/input.icproj',project_sha256=file_digest(folder/'input.icproj'),captured=name+'/captured.spice',captured_sha256=file_digest(folder/'captured.spice'),settings=settings,expected=expect,**facts))
    tech,_=load_technology('ihp-sg13g2')
    from icstudio.ihp_cmim_desktop_probe import fixture,FIELDS
    asset=ROOT/'icstudio/assets/qualification/ihp-cmim-reference';data,_=fixture(asset)
    for n in ('mask-only.json','SOURCE.json','LICENSE'):sources[str((asset/n).relative_to(ROOT)).replace('\\','/')]=file_digest(asset/n)
    base=example('empty');base['pdk']=clone(tech);c=base['cells'][0];c.update(name='coupon',ports=['C1','C2'])
    for field in FIELDS:c[field]=clone(data[field])
    base=two_units(base)
    selected=('m2-0','m1-0') if pilot else ('m2-0','pair-0','m2-90','pair-90','m1-0','m3-0','wrong-width-0')
    for name in selected:
        mode,angle=name.rsplit('-',1);layout=out/(name+'-layout.icproj');save_project(base if angle=='0' else rotate(base),layout);p,t=bench(attach(layout,tech,mode),'cmim')
        settings=dict(type='silicon',testbench=t['id'],physical_extraction={'mode':'capacitance'},physical_toolchain='included',tools={})
        record('cmim-'+name,p,settings,'passed' if mode in ('m2','pair') else 'failed',family='cmim',mode=mode,angle=int(angle))
    if not pilot:
        require(sky130 is not None,'physical SKY130 adapter required')
        from icstudio.interchange import export_layout
        from icstudio.layout_import import read_layout
        from icstudio.catalog import link_technology
        from icstudio.layout_verification import reference
        from icstudio.sky130_mim2_extract import MODELS
        import klayout.db as db
        skytech,_=technology('sky130A',Path(sky130))
        for plate in (1,2):
            original=out/f'plate{plate}.gds';export_layout(shared_project(skytech,plate),original)
            for mode,angle in (('positive',0),('positive',90),('missing-contact-group',0),('wrong-width',0),('wrong-count',0)):
                name=f'mim-p{plate}-{mode}-{angle}';layout=db.Layout();layout.read(str(original));cell=layout.top_cell()
                if mode=='missing-contact-group':
                    spec=MODELS[f'sky130_fd_pr__cap_mim_m3_{plate}'];caps=db.Region(cell.shapes(layout.layer(*spec['cap']))).merged();cuts=cell.shapes(layout.layer(*spec['cut']));kept=db.Region()
                    for cut in db.Region(cuts).each():
                        if (db.Region(cut)-caps).is_empty() or cut.bbox().top<10000:kept.insert(cut)
                    cuts.clear();cuts.insert(kept)
                cell.transform(db.Trans(angle//90,False,0,0));path=out/(name+'.gds');layout.write(str(path));p,_=read_layout(path);link_technology(p,skytech);p['cells'][0]['ports']=['P','N']
                size=(3,10,2) if mode=='wrong-width' else (2,10,1) if mode=='wrong-count' else (2,10,2)
                settings=dict(type='silicon',verification_mode='drc_lvs',physical_toolchain='included',tools={},reference=reference(independent(size,plate=plate),'device_coupon'))
                record(name,p,settings,'passed' if mode=='positive' else 'failed',family='shared-mim',plate=plate,angle=angle,mode=mode)
        size=(3.015,1.005,3,2)
        for target,hv in [('gf180mcuC',False),('gf180mcuD',False),('ihp-sg13g2',False),('ihp-sg13g2',True)]:
            tech,_=load_technology(target)
            for polarity in ('n','p'):
                p=rotated(hv_fixture(tech,polarity,size) if hv else lv_fixture(tech,target,polarity,size))
                for mode,fault in [('matching',None),('wrong-fingers','reference-fingers')]:
                    ref=hv_reference(polarity,size,fault) if hv else lv_reference(target,polarity,size,fault)
                    settings=dict(type='silicon',verification_mode='drc_lvs',physical_toolchain='included',tools={},reference=ref)
                    record(f'mos-{target}-'+('hv' if hv else 'standard')+f'-{polarity}-{mode}',p,settings,'passed' if fault is None else 'failed',family='mos',target=target,hv=hv,polarity=polarity,mode=mode)
                if target=='gf180mcuC' and polarity=='n':
                    for mode in ('matching','wrong-fingers'):
                        q=clone(p);q['cells'][0].pop('pdk_layouts',None)
                        if mode=='wrong-fingers':q['cells'][0]['devices'][0]['model_params']['nf']='4'
                        q,t=bench(q,'mos');settings=dict(type='silicon',testbench=t['id'],physical_toolchain='included',tools={})
                        record('mos-saved-'+mode,q,settings,'passed' if mode=='matching' else 'failed',family='mos-saved',mode=mode,target=target,hv=False,polarity=polarity)
    result=dict(schema=1,scope='Existing finite native contracts only; fixture preparation is not installed acceptance.',qualified=False,installed_acceptance=False,pilot=pilot,cases=rows,source_files=sources)
    write(out/'cases.json',result);return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--sky130',type=Path);ap.add_argument('--pilot',action='store_true');args=ap.parse_args();r=prepare(args.out,args.sky130,args.pilot);print(json.dumps(dict(cases=len(r['cases']),file=str(args.out/'cases.json'))))
