"""Sampled IHP antenna and GF180 junction diode layouts and native connectivity.

Single rectangular devices with a separately contacted junction guard ring.
This does not qualify ESD/breakdown, continuous geometry, statistical behavior,
every diode family, complete-chip context or an installed release.
"""
import argparse,math,re,subprocess,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,load_project,save_project,scalar
from icstudio.catalog import link_technology
from icstudio.layout import kdb,polygon,rect
from icstudio.layout_import import read_layout
from icstudio.physical_cells import assign_port
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_standard_mos_layout import fault_detected
from scripts.qualify_ihp_resistor_layouts import regions,same_masks,rotated
from scripts.qualify_gf180_resistor_layouts import prepare_source,native_layers,SOURCE

MODELS={'ihp-sg13g2':('dantenna','dpantenna')}
for _target in ('gf180mcuC','gf180mcuD'):
    MODELS[_target]=('diode_nd2ps_03v3','diode_pd2nw_03v3','diode_nd2ps_06v0','diode_pd2nw_06v0')
SIZES=((.45,.45),(.45,20),(20,.45),(2,7),(7,2))
FAULTS=('anode-open','cathode-open','terminal-short','reference-reversed','reference-width','reference-model')


def layers(target):return ((8,0),(6,0)) if target=='ihp-sg13g2' else ((34,0),(33,0))


def center_is_anode(model):
    if not any(model in names for names in MODELS.values()):raise ValueError('Unknown reviewed diode.')
    return model=='dpantenna' or model.startswith('diode_pd2nw_')


def selected_reference(target,model,w,l,reversed_=False):
    if target not in MODELS or model not in MODELS[target]:raise ValueError('Unknown reviewed diode.')
    pins='K A' if reversed_ else 'A K'
    call=f'X1 {pins} {model} w={w:g}u l={l:g}u' if target=='ihp-sg13g2' else f'D1 {pins} {model} area={w*l*1e-12:.12g} pj={2*(w+l)*1e-6:.12g}'
    return reference(f'.subckt coupon A K\n{call}\n.ends coupon\n','coupon')


def label_ports(p,model,target):
    """Assign polarity from junction doping, independently of extracted nets."""
    original=clone(p);c=p['cells'][0];c['ports']=['A','K'];db=kdb();metal_pair,_=layers(target)
    metal=next(l['name'] for l in p['pdk']['layers'] if (l['gds'],l['datatype'])==metal_pair)
    components=list(regions(p)[metal_pair].each())
    if len(components)!=2:raise ValueError('Expected one diode contact and one separate guard conductor.')
    guards=[v for v in components if v.holes()==1];centers=[v for v in components if v.holes()==0]
    if len(guards)!=1 or len(centers)!=1 or not centers[0].inside(db.Point(0,0)):raise ValueError('Ambiguous diode/guard geometry.')
    # Upstream IHP D1 means central diffusion, which is the cathode for n-diode.
    # Remove those generic annotations before adding polarity-specific ports.
    c['layout_texts']=[t for t in c.get('layout_texts',[]) if t['text'] not in ('D1','D2')]
    central='A' if center_is_anode(model) else 'K'
    for name,poly in [(central,centers[0]),('K' if central=='A' else 'A',guards[0])]:
        point=poly.bbox().center()
        if not poly.inside(point):
            piece=max(db.Region(poly).decompose_trapezoids_to_region().each(),key=lambda v:v.area());point=piece.bbox().center()
        if not poly.inside(point):raise ValueError('Diode port is outside its conductor.')
        assign_port(p,c['id'],name,metal,[point.x,point.y])
    same_masks(original,p)


def generate(tech,target,model,w,l,folder,magic,prepared=None):
    if model not in MODELS.get(target,()) or (w,l) not in SIZES:raise ValueError('Use a reviewed sampled geometry.')
    folder.mkdir();source=Path(tech['package_root'])/'libs.tech/magic'
    if target=='ihp-sg13g2':
        setup=f'tech load {{{source/"ihp-sg13g2.tech"}}}\nscalegrid 1 2\ndrc euclidean on\nrandom seed 12345\nsource {{{source/"ihp-sg13g2.tcl"}}}\n';ns='sg13g2';options='doports 1 vias 0'
    else:
        setup=f'tech load {{{source/(target+".tech")}}}\nscalegrid 1 10\ndrc euclidean on\nrandom seed 12345\nsource {{{prepared/"generator.tcl"}}}\nsource {{{prepared/"pdk.tcl"}}}\n';ns='gf180mcu'
        # Named local variant, leaving upstream source and diode dimensions
        # intact: widen guard diffusion and all contact metal enclosures.
        options='guard 0 dev_spacing 0.50 end_surround 0.075 metal_surround 0.11 end_contact_size 0.25 rlcov 80 tbcov 80'
    script=setup+f'''load coupon -silent
box values 0 0 0 0
set parameters [dict merge [{ns}::{model}_defaults] [dict create w {w:g} l {l:g} {options}]]
if {{[catch {{{ns}::{model}_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
select top cell
box select
save coupon
gds write coupon.gds
puts GENERATOR_COMPLETE
quit -noprompt
'''
    (folder/'generate.tcl').write_bytes(script.encode());(folder/'empty.magicrc').write_bytes(b'')
    r=subprocess.run([magic,'-dnull','-noconsole','-rcfile','empty.magicrc','generate.tcl'],cwd=folder,capture_output=True,timeout=120)
    log=r.stdout+r.stderr;(folder/'console.log').write_bytes(log)
    if r.returncode or log.count(b'GENERATOR_COMPLETE')!=1 or b'GENERATOR_FAILED' in log or re.search(rb'\d+ problems occurred',log):raise ValueError('Native generator failed; see console.log.')
    p,_=read_layout(folder/'coupon.gds');raw=clone(p);link_technology(p,tech);label_ports(p,model,target);same_masks(raw,p);return p


def altered(p,fault,target):
    q=clone(p);c=q['cells'][0];db=kdb();metal_pair,contact_pair=layers(target)
    ls={(l['gds'],l['datatype']):l['name'] for l in p['pdk']['layers']};ports={v['name']:v for v in c['layout_ports']}
    if fault in ('anode-open','cathode-open'):
        pin=ports['A' if fault=='anode-open' else 'K'];selected=[poly for poly in regions(q)[metal_pair].each() if poly.inside(db.Point(*pin['point']))]
        if len(selected)!=1:raise ValueError('Port does not select one conductor.')
        region=db.Region(selected[0]);removed=[s for s in c['shapes'] if s['layer']==ls[contact_pair] and not (db.Region(polygon(s))&region).is_empty()]
        if not removed:raise ValueError('No contacts selected by the negative control.')
        c['shapes']=[s for s in c['shapes'] if s not in removed]
    elif fault=='terminal-short':
        a,b=[ports[k]['point'] for k in ('A','K')];width=400
        c['shapes'] += [rect(ls[metal_pair],min(a[0],b[0])-width//2,a[1]-width//2,abs(a[0]-b[0])+width,width),
            rect(ls[metal_pair],b[0]-width//2,min(a[1],b[1])-width//2,width,abs(a[1]-b[1])+width)]
    else:raise ValueError('Unknown physical diode control.')
    return q


def audit_extracted(path,target,model,w,l):
    rows=[line.split() for line in path.read_text().splitlines() if re.match(r'(?i)^[xd]\S+\s',line)]
    if len(rows)!=1:raise ValueError('Expected exactly one extracted diode.')
    row=rows[0];prefix='X' if target=='ihp-sg13g2' else 'D'
    if len(row)<6 or not row[0].upper().startswith(prefix) or row[1:4]!=['A','K',model]:raise ValueError('Extracted diode polarity or model differs.')
    params=dict(v.split('=',1) for v in row[4:] if '=' in v)
    expected={'w':w*1e-6,'l':l*1e-6} if target=='ihp-sg13g2' else {'area':w*l*1e-12,'pj':2*(w+l)*1e-6}
    for key,value in expected.items():
        if key not in params or not math.isclose(scalar(params[key]),value,rel_tol=1e-9,abs_tol=abs(value)*1e-10):raise ValueError('Extracted diode dimension differs: '+key)
    return dict(model=model,terminals=row[1:3],parameters=expected,sha256=file_digest(path))


def detected_fault(result,folder):
    stages={s['name']:s['status'] for s in result.get('stages',[])}
    if result.get('status')!='failed' or any(stages.get(s)!='passed' for s in ('preflight','layout_export')):return False
    if fault_detected(result,folder):return True
    log=folder/'lvs/lvs.log'
    return (result.get('status')=='failed' and stages.get('preflight')=='passed'
        and stages.get('lvs_extraction')=='passed' and stages.get('lvs')=='failed'
        and stages.get('integrity')=='passed' and log.is_file()
        and 'Final result: Top level cell failed pin matching.' in log.read_text())


def case(tech,target,model,w,l,out,tools,prepared):
    name=f'{target}-{model}-w{w:g}-l{l:g}';folder=out/name;folder.mkdir();row=dict(name=name,target=target,model=model,width_um=w,length_um=l,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,target,model,w,l,folder/'generator',tools['magic'],prepared);ref=selected_reference(target,model,w,l)
        save_project(p,folder/'saved.icproj');reopened=load_project(folder/'saved.icproj');same_masks(p,reopened)
        for angle in (0,90):
            q=reopened if angle==0 else rotated(reopened);baseline=folder/f'baseline-{angle}.gds';export_layout(q,baseline)
            exported=folder/f'rotation-{angle}.oas';export_layout(q,exported)
            ly=kdb().Layout();ly.read(str(exported));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['A','K'];same_masks(q,imported)
            outgds=folder/f'reimported-{angle}.gds';export_layout(imported,outgds)
            exchange=dict(full_gds=compare(baseline,outgds),oasis=compare(external,outgds,text_presentation=False))
            # IHP's diode W/L follow layout x/y, unlike a resistor path. Both
            # public models use only W*L and 2*(W+L), unchanged by rotation.
            rw,rl=(l,w) if angle==90 and target=='ihp-sg13g2' else (w,l)
            dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,selected_reference(target,model,rw,rl))
            item=dict(rotation=angle,native_status=result['status'],drc_count=result.get('drc_count'),exchange=exchange,report_sha256=file_digest(dest/'report.json'))
            if result['status']!='passed':raise ValueError(result.get('error','Native verification failed.'))
            item['extracted']=audit_extracted(dest/'lvs-extraction/extracted.spice',target,model,rw,rl);row['layouts'].append(item)
        for fault in FAULTS:
            q=altered(p,fault,target) if not fault.startswith('reference-') else p
            selected=selected_reference(target,model,w,l,True) if fault=='reference-reversed' else selected_reference(target,model,w*1.2,l) if fault=='reference-width' else selected_reference(target,MODELS[target][(MODELS[target].index(model)+1)%len(MODELS[target])],w,l) if fault=='reference-model' else ref
            dest=folder/fault;result=run(q,q['top'],dest,tools,selected);detected=detected_fault(result,dest)
            row['faults'].append(dict(name=fault,kind='schematic reference' if fault.startswith('reference-') else 'physical geometry',detected=detected,status=result['status'],report_sha256=file_digest(dest/'report.json'),error=result.get('error')))
            if not detected:raise ValueError('Native checks did not detect '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2);ap.add_argument('--targets',nargs='+',choices=tuple(MODELS),default=list(MODELS));a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualify_ihp_resistor_layouts.py',ROOT/'scripts/qualify_gf180_resistor_layouts.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py')),*sorted(p for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts)]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('magic','netgen')};report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,processes={},source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in a.targets:
            tech,identity=load_technology(target);prepared=None;provenance=None
            if target.startswith('gf180'):native_layers(tech);prepared,provenance=prepare_source(out,target)
            report['processes'][target]=dict(package=identity,generator=provenance)
            for model in MODELS[target]:
                for w,l in ([(2,7)] if a.pilot else SIZES):jobs.append(pool.submit(case,tech,target,model,w,l,out,tools,prepared))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
