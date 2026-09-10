from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.model import example,device,save_project,validate,clone
from icstudio.catalog import create_device
from icstudio.pdks import PDKRegistry
from icstudio.interchange import spice,export_xschem
from icstudio.xschem_io import import_package
from icstudio.engines import run_ngspice
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--pdk-root',type=Path,required=True);parser.add_argument('--ngspice',required=True);args=parser.parse_args()
root=Path(__file__).resolve().parents[1];registry=PDKRegistry(root/'build/pdk-registry');output=root/'build/verification-0.5.0';output.mkdir(exist_ok=True)
for folder,keys,supply in [('sky130A',['sky130_fd_pr/nfet_01v8.sym','sky130_fd_pr/nfet_01v8_lvt.sym','sky130_fd_pr/pfet_01v8.sym','sky130_fd_pr/pfet_01v8_hvt.sym'],1.8),('gf180mcuC',['symbols/nfet_03v3.sym','symbols/nfet_06v0.sym','symbols/pfet_03v3.sym','symbols/pfet_06v0.sym'],3.3),('ihp-sg13g2',['sg13g2_pr/sg13_lv_nmos.sym','sg13g2_pr/sg13_hv_nmos.sym','sg13g2_pr/sg13_lv_pmos.sym','sg13g2_pr/sg13_hv_pmos.sym'],1.2)]:
 key=registry.register_local(args.pdk_root/folder);tech=registry.technology(key);p=example('empty');p['name']=folder+' mixed models';p['pdk']=tech;p['analysis']['type']='op';c=p['cells'][0]
 c['devices']=[device('V','VDD',100,100,value=str(supply),nets={'p':'vdd','n':'0'}),device('V','VG',100,300,value=str(supply/2),nets={'p':'gate','n':'0'})]
 for i,k in enumerate(keys):
  d=create_device(tech,k,'M'+str(i+1),350+(i%2)*300,150+(i//2)*250);d['nets']={'d':'out'+str(i),'g':'gate','s':'vdd' if d['kind']=='PMOS' else '0','b':'vdd' if d['kind']=='PMOS' else '0'};c['devices'].append(d);c['devices'].append(device('R','R'+str(i),500+(i%2)*300,150+(i//2)*250,value='10k',nets={'p':'out'+str(i),'n':'0' if d['kind']=='PMOS' else 'vdd'},model_mode='generic'))
 validate(p);dir=output/folder;dir.mkdir(exist_ok=True);save_project(p,dir/'mixed-models.icproj');(dir/'mixed-models.cir').write_text(spice(p,settings=p['analysis']));export_xschem(p,dir/'xschem');q,report=import_package(dir/'xschem');assert [d.get('model_ref') for d in c['devices']]==[d.get('model_ref') for d in q['cells'][0]['devices']]
 if folder!='ihp-sg13g2':
  result=run_ngspice(p,p['top'],p['analysis'],args.ngspice,dir);(dir/'result.json').write_text(json.dumps(result,indent=2));print(folder,'ngspice passed',result['traces'],flush=True)
 else:print(folder,'model placement / deck / Xschem round trip passed; OSDI simulation not run',flush=True)
