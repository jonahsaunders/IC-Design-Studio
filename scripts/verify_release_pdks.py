"""Real ngspice regressions for the 0.6 PDK adapters and configured OSDI runtime."""
import argparse,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import example,device,clone,save_project
from icstudio.pdks import PDKRegistry
from icstudio.catalog import create_device,parameter_values
from icstudio.osdi import configure
from icstudio.engines import run_ngspice
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package

def circuit(tech,key,supply,analysis='op'):
    p=example('empty');p['pdk']=tech;p['name']=key;p['analysis'].update(type=analysis,start='1k',end='100g',points=8)
    d=create_device(tech,key,'DUT',420,250);entry=tech['simulation']['catalog'][key]
    p['cells'][0]['devices']=[device('V','VDD',100,120,value=str(supply),nets={'p':'vdd','n':'0'}),device('V','VG',100,340,value=str(supply/2),nets={'p':'gate','n':'0'})]
    if d['kind'] in ('NMOS','PMOS'):
        pm=d['kind']=='PMOS';d['nets']={'d':'out','g':'gate','s':'vdd' if pm else '0','b':'vdd' if pm else '0'}
        load='0' if pm else 'vdd'
        if key.endswith('_nf.sym'):d['model_params']['nf']='2'
    else:
        d['nets']={pin:('out' if i==0 else '0') for i,pin in enumerate(entry['pin_order'])};load='vdd'
        if entry['category']=='Bipolar':
            d['nets']={pin:('out' if i==0 else 'gate' if i==1 else 'vdd' if 'pnp' in key.lower() else '0') for i,pin in enumerate(entry['pin_order'])}
            load='0' if 'pnp' in key.lower() else 'vdd'
    p['cells'][0]['devices'] += [d,device('R','Rload',650,250,value='10k',nets={'p':load,'n':'out'},model_mode='generic')]
    return p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pdk-root',type=Path,required=True);parser.add_argument('--ngspice',required=True);parser.add_argument('--osdi',type=Path,required=True);parser.add_argument('--output',type=Path,default=ROOT/'build/verification-0.6.0/pdk-cases');parser.add_argument('--family',choices=['sky130A','gf180mcuC','ihp-sg13g2'],help='Rerun one family, retaining other-family evidence in the existing report.');args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);registry=PDKRegistry(ROOT/'build/release-pdk-registry');results=[];catalogs=[]
    cases={
        'sky130A':(1.8,['sky130_fd_pr/nfet_01v8.sym','sky130_fd_pr/pfet_01v8.sym','sky130_fd_pr/nfet3_01v8.sym','sky130_fd_pr/nfet_01v8_nf.sym']),
        'gf180mcuC':(3.3,['symbols/nfet_03v3.sym','symbols/pfet_06v0.sym','symbols/diode_nd2ps_03v3.sym','symbols/diode_pw2dw.sym']),
        'ihp-sg13g2':(1.2,['sg13g2_pr/sg13_lv_nmos.sym','sg13g2_pr/sg13_hv_nmos.sym','sg13g2_pr/sg13_lv_pmos.sym','sg13g2_pr/sg13_hv_pmos.sym','sg13g2_pr/rhigh.sym','sg13g2_pr/rppd.sym','sg13g2_pr/rsil.sym','sg13g2_pr/cap_cmomi.sym','sg13g2_pr/pnpMPA.sym'])}
    if args.family and (out/'report.json').exists():
        previous=json.loads((out/'report.json').read_text());results=[r for r in previous['cases'] if not r['pdk'].startswith(args.family+'@')];catalogs=[r for r in previous['catalogs'] if not r['pdk'].startswith(args.family+'@')]
    for family,(supply,keys) in cases.items():
        if args.family and family!=args.family:continue
        key=registry.register_local(args.pdk_root/family);tech=registry.technology(key);cat=tech['simulation']['catalog'];catalogs.append({'pdk':key,'placeable':sum(not e.get('unavailable') for e in cat.values()),'indexed':len(cat)})
        available=set.intersection(*(set(i['sections']) for i in tech['simulation']['includes'] if i.get('sections')))
        corners=['nominal']+([c for c in ('ss','ff') if c in available] if family=='sky130A' else [c for c in ('ss','ff','slow','fast') if c in available])
        if family=='gf180mcuC':corners=['nominal']+[c for c in ('ff','ss') if c in available]
        for model in keys:
            for corner in corners:
                folder=out/family/(Path(model).stem+'-'+corner);folder.mkdir(parents=True,exist_ok=True)
                record={'pdk':key,'device':model,'corner':corner,'status':'failed'}
                try:
                    p=circuit(tech,model,supply,'ac' if 'cap_cmomi' in model else 'op');p['analysis']['corner']=corner
                    if family=='ihp-sg13g2':p['simulation_runtime']={'osdi':configure(sorted(args.osdi.glob('*.osdi')))}
                    save_project(p,folder/'circuit.icproj');result=run_ngspice(p,p['top'],p['analysis'],args.ngspice,folder)
                    values=result['traces']['out'];assert values and all(math.isfinite(v) for v in values)
                    if p['analysis']['type']=='op':assert -.01<=values[0]<=supply+.01
                    else:assert values[-1]<values[0]
                    (folder/'result.json').write_text(json.dumps(result,indent=2));record.update(status='passed',samples=len(values),output_first=values[0],output_last=values[-1])
                    if corner=='nominal':
                        export_xschem(p,folder/'xschem');q,_=import_package(folder/'xschem')
                        before=p['cells'][0]['devices'][2];after=q['cells'][0]['devices'][2]
                        assert before['model_ref']==after['model_ref'];assert before['nets']==after['nets']
                        a=parameter_values(cat[model],before);b=parameter_values(cat[model],after)
                        assert a.keys()==b.keys() and all(math.isclose(a[k],b[k],rel_tol=5e-11,abs_tol=0) for k in a)
                        record['xschem_roundtrip']='passed'
                except Exception as exc:record['error']=str(exc)
                results.append(record);(out/'report.json').write_text(json.dumps({'catalogs':catalogs,'cases':results},indent=2));print(family,Path(model).stem,corner,record['status'],record.get('error','')[:200],flush=True)
    if any(r['status']!='passed' for r in results):raise SystemExit(1)
if __name__=='__main__':main()
