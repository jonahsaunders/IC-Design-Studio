"""Exercise the explicit public RF candidate through actual application paths.

Two models, three geometries, nominal DC/AC, polarity and width faults.
Automatic runtime proofs must pass on graphical and independent deck routes.
This does not qualify the physical or complete operating envelope.
"""
from pathlib import Path
import argparse,cmath,json,math,os,sys,traceback
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from icstudio.model import clone,device,example,save_project,file_digest
from icstudio.engines import run_ngspice,run_deck
from icstudio.catalog import create_device,parameter_values
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_catalog_interfaces import one
from scripts.verify_ngspice_diode_sequences import verify


def qualify(executable,package_root,output):
    out=Path(output).resolve();exe=Path(executable).resolve();source=Path(package_root).resolve()
    out.mkdir(exist_ok=False)
    package=json.loads((source/'package.json').read_bytes());tech=clone(package['technology']);tech.update(package_root=str(source),package_lock={k:package[k] for k in ('id','revision','files')})
    points=[dict(model=m,w=width,l=length,area=area,perim=perim,tag=f'd{i}{j}') for i,m in enumerate(('ps2nw','pw2dn')) for j,(width,length,area,perim) in enumerate(((2,2,4,8),(4,2,8,12),(10,10,100,40)))]
    common='sky130_fd_pr__model__parasitic__rf_diode_'
    def key(m):return 'sky130_fd_pr/diode__'+common+m+'.sym'
    def fixture():
        p=example('empty');p['pdk']=clone(tech);v=device('V','VG',value='0',nets={'p':'drive','n':'0'});v['source']['ac']='1';p['cells'][0]['devices']=[v]
        for row in points:
            d=create_device(tech,key(row['model']),'D'+row['tag']);d['model_params'].update(w=row['w'],l=row['l']);d['nets']={'d0':row['tag'],'d1':'0'}
            v=device('V','V'+row['tag'],value='0',nets={'p':row['tag'],'n':'drive'});v['source']['ac']='0';p['cells'][0]['devices'] += [v,d]
        return p
    def currents(r,analysis):
        expected=[i*.025 for i in range(25)] if analysis=='dc' else [1000*10**(i/5) for i in range(31)]
        assert len(r['x'])==len(expected) and all(math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-12) for x,y in zip(r['x'],expected))
        values={};amps={k.lower():v for k,v in r['currents'].items()};phases={k.lower():v for k,v in r.get('current_phase',{}).items()}
        for row in points:
            name='v'+row['tag'];v=amps[name]
            if analysis=='ac':v=[cmath.rect(a,math.radians(b)) for a,b in zip(v,phases[name])]
            assert len(v)==len(expected) and all(math.isfinite(abs(x)) for x in v);values[name]=v
        return values
    def compare(a,b,analysis):
        left=currents(a,analysis);right=currents(b,analysis)
        return {name:max(abs(x-y)/(1e-16+1e-6*abs(y)) for x,y in zip(left[name],values)) for name,values in right.items()}
    report=dict(status='RUNNING',qualified=False,chunk_complete=False,default_promoted=False,scope='Explicit RF candidate integration: two public derivatives, three rectangular geometries, selected DC/AC and terminal/geometry faults; not full RF or physical qualification.',host=sys.platform,manifest_sha256=file_digest(source/'package.json'),engine_sha256=file_digest(exe),runner_sha256=file_digest(__file__),interfaces=[],cases=[])
    for m in ('ps2nw','pw2dn'):
        r=one(tech,key(m),out/('interface-'+m));report['interfaces'].append(r);assert r['status']=='PASS',r
    for corner,temp in [('nominal',27)]:
        root=out/(corner+'-'+str(temp));root.mkdir();row=dict(corner=corner,temperature_c=temp,checks=[])
        s=dict(corner=corner,temperature=temp,source='VG',dc_start='0',dc_stop='.6',dc_step='.025',start='1k',end='1g',points=5)
        for analysis in ('dc','ac'):
            p=fixture();app=root/analysis/'application';ref=root/analysis/'independent';app.mkdir(parents=True);ref.mkdir();save_project(p,app/'input.icproj')
            actual=run_ngspice(p,p['top'],dict(s,type=analysis),str(exe),app);(app/'result.json').write_text(json.dumps(actual,indent=2))
            lines=['* Independent explicit RF model calls',*model_lines(tech,corner),'VG drive 0 0 AC 1']
            for r in points:lines += [f'V{r["tag"]} {r["tag"]} drive 0 AC 0',f'X{r["tag"]} {r["tag"]} 0 {common+r["model"]} area={r["area"]} perim={r["perim"]}']
            lines += [f'.temp {temp}', '.dc VG 0 .6 .025' if analysis=='dc' else '.ac dec 5 1k 1g','.end','']
            path=ref/'reference.cir';path.write_bytes(stage_model_deck(tech,'\n'.join(lines),ref).encode())
            expected=run_deck(p,p['top'],dict(deck=str(path),analysis=dict(s,type=analysis)),str(exe),ref);(ref/'result.json').write_text(json.dumps(expected,indent=2))
            errors=compare(actual,expected,analysis);assert max(errors.values())<=1,errors
            if analysis=='dc':dc=expected
            row['checks'].append(dict(analysis=analysis,status='PASS',errors=errors))
        for fault in ('reversed-pins','wrong-width'):
            p=fixture()
            for d in p['cells'][0]['devices']:
                if d.get('model_ref'):
                    if fault=='reversed-pins':d['nets']['d0'],d['nets']['d1']=d['nets']['d1'],d['nets']['d0']
                    else:d['model_params']['w']*=1.5
            dest=root/fault;dest.mkdir();save_project(p,dest/'input.icproj');bad=run_ngspice(p,p['top'],dict(s,type='dc'),str(exe),dest);(dest/'result.json').write_text(json.dumps(bad,indent=2));errors=compare(bad,dc,'dc');assert all(e>1 for e in errors.values()),errors
            row['checks'].append(dict(fault=fault,status='DETECTED',errors=errors))
        report['cases'].append(row)
    report['automatic_runtime_checks']=[]
    for path in out.rglob('rf-acceptance.json'):
        proof=json.loads(path.read_bytes());assert proof['status']=='PASS';report['automatic_runtime_checks'].append(dict(path=path.relative_to(out).as_posix(),sha256=file_digest(path)))
    assert len(report['automatic_runtime_checks'])==6
    report['status']='PASS';(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ngspice',required=True)
    ap.add_argument('--package',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();result=qualify(a.ngspice,a.package,a.output)
    print(result['status'],len(result['automatic_runtime_checks']),'automatic runtime checks')
