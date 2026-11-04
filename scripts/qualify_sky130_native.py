"""Real local engine controls for generic SKY130 geometry (no electrical claim)."""
import argparse, json, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
import klayout.db as k
from icstudio import digital_sky130_native as native
from icstudio.digital_flow import artifact
from icstudio.model import atomic_write,file_digest,clone
from icstudio.interchange import export_layout
from scripts.qualify_sky130_devices import fixture

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path,help='New evidence directory')
parser.add_argument('--klayout',required=True,type=Path,help='KLayout executable with Ruby DRC support')
args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
tool=str(args.klayout.resolve())
version=subprocess.check_output([tool,'-b','-v'],text=True).strip()
record=dict(schema=1,status='RUNNING',qualified=False,chunk_complete=False,driver_sha256=file_digest(__file__),
    engine=dict(version=version,sha256=file_digest(tool)),controls=[],
    scope='Actual native geometry execution through the production stage, with generic names and unrestricted process metal layers. '
          'Synthetic checkpoint tokens are test fixtures, not OpenDB extraction, LVS or full-design qualification.')

def run(name,gds,expected,category=None,implant_fault=False,implant_control=False):
    folder=gds.parent
    checkpoint=folder/'control.txt';checkpoint.write_text('Geometry-only control; no OpenDB checkpoint or electrical qualification.\n')
    r=SimpleNamespace(root=folder,platform={'name':'sky130hd','fingerprint':'geometry-control'},
        config={'top':name},artifacts={'gds':artifact(folder,gds),'checkpoint':artifact(folder,checkpoint)},
        tools={'klayout':tool},versions={'klayout':version})
    r.add_artifact=lambda key,path:r.artifacts.update({key:artifact(folder,path)})
    def save(key,value,path):
        atomic_write(folder/path,json.dumps(value,indent=2)+'\n');r.add_artifact(key,folder/path)
    r.save_json=save
    def command(args,message,**kwargs):
        result=subprocess.run(args,cwd=kwargs['cwd'],capture_output=True,text=True,timeout=180)
        atomic_write(folder/'stderr.log',result.stderr)
        if result.returncode:raise RuntimeError(result.stderr[-2000:])
        return result.stdout
    r.command=command
    rejected=False;start=time.monotonic()
    try:native.execute(r)
    except ValueError as error:
        if 'violations; inspect the retained report' not in str(error):raise
        rejected=True
    report=json.loads((folder/'sky130-native/report.json').read_bytes())
    item=dict(name=name,expected=expected,status=report['status'],rejected=rejected,
        categories=report['categories'],markers=report['markers'],violations=report['violations'],
        gds_sha256=file_digest(gds),report_sha256=file_digest(folder/'sky130-native/report.json'),
        elapsed_seconds=time.monotonic()-start)
    record['controls'].append(item)
    assert rejected==(expected=='FAIL'),item
    if category:assert report['violations'].get(category,0)>0,item
    if implant_control:
        from scripts.sky130_raw_feol import audit as raw_audit
        from icstudio.digital_sky130_rules_lock import FILES
        assert file_digest(REPO/'scripts/sky130_raw_feol.py')==FILES['helpers/scripts/sky130_raw_feol.py']
        raw=raw_audit(gds)
        atomic_write(folder/'raw-implants.json',json.dumps(raw,indent=2)+'\n')
        item['raw_implants']={key:raw[key] for key in ('status','violations','checker_sha256','gds_sha256')}
        item['raw_implants']['failed_rules']={r['rule']:r['violations'] for r in raw['checks'] if r['violations']}
        item['raw_implants']['report_sha256']=file_digest(folder/'raw-implants.json')
        item['combined_status']='FAIL' if rejected or raw['violations'] else 'PASS'
        assert (raw['status']=='FAIL')==implant_fault,item
        if implant_fault:
            assert item['raw_implants']['failed_rules'].get('n/psd.9.'+('n' if name.startswith('nmos') else 'p'),0)>0,item
            item['limitation']='Pinned native deck misses this removed-implant fault; the retained mandatory Studio raw-implant profile detects it.'
    print(json.dumps(item),flush=True)

try:
    for name,layer,box,expected,category in [
        ('custom_m1_block',(68,20),(0,0,1000,1000),'PASS',None),
        ('custom_top_metal_block',(72,20),(0,0,2000,5000),'PASS',None),
        ('custom_offgrid_fault',(68,20),(1,0,1001,1000),'FAIL','m1_OFFGRID'),
        ('custom_width_fault',(68,20),(0,0,100,1000),'FAIL',None)]:
        folder=out/name;folder.mkdir();layout=k.Layout();layout.dbu=.001;top=layout.create_cell(name)
        top.shapes(layout.layer(*layer)).insert(k.Box(*box));gds=folder/'layout.gds';layout.write(str(gds))
        run(name,gds,expected,category)
    for core in (False,True):
        for covered in (False,True):
            name=f'contact_core_{int(core)}_covered_{int(covered)}';folder=out/name;folder.mkdir()
            layout=k.Layout();layout.dbu=.001;top=layout.create_cell(name)
            shapes={(67,44):(0,0,170,170),(68,20):(-200,-200,370,370)}
            if core:shapes[(81,2)]=(-1000,-1000,1000,1000)
            if covered:shapes[(67,20)]=(-200,-200,370,370)
            for pair,box in shapes.items():top.shapes(layout.layer(*pair)).insert(k.Box(*box))
            gds=folder/'layout.gds';layout.write(str(gds))
            run(name,gds,'PASS' if covered else 'FAIL',None if covered else 'MR_mcon.CON.10')
    pdk=REPO/'icstudio/assets/pdks/sky130A'
    package=json.loads((pdk/'package.json').read_bytes())
    tech=package['technology'];tech.update(package_root=str(pdk),package_lock={key:package[key] for key in ('id','revision','files')})
    for kind in ('nmos-parallel','pmos-parallel'):
        project,cell=fixture(tech,kind,w=2,l=.5)
        for fault in (False,True):
            p=clone(project);c=p['cells'][0];name=kind.replace('-','_')+('_missing_implant' if fault else '_valid')
            c['name']=name;folder=out/name;folder.mkdir()
            if fault:
                from icstudio.sky130_devices import layers
                mask=layers(tech)['nsdm' if kind.startswith('nmos') else 'psdm']
                before=len(c['shapes']);c['shapes']=[s for s in c['shapes'] if s['layer']!=mask]
                assert len(c['shapes'])<before
            atomic_write(folder/'input.icproj',json.dumps(p,indent=2)+'\n')
            gds=folder/'layout.gds';export_layout(p,gds)
            # The first execution exposed that this native deck reconstructs
            # implants. Keep the missed fault visible and require the existing
            # independent raw-mask predicate that the application also runs.
            run(name,gds,'PASS',implant_fault=fault,implant_control=True)
    record['status']='PASS'
finally:
    if record['status']=='RUNNING':record['status']='FAIL'
    atomic_write(out/'record.json',json.dumps(record,indent=2)+'\n')
