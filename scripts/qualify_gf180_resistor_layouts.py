"""Selected GF180 C/D resistor geometry with explicit local generator repairs.

Pinned upstream generator bytes and rule decks remain unchanged. The generation
script adds contact enclosure and guard clearance. This is a named local layout
variant, not an upstream-generator pass or complete process qualification.
"""
import argparse,json,math,re,subprocess,sys,traceback,xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,load_project,save_project,scalar
from icstudio.catalog import link_technology
from icstudio.layout import kdb,polygon
from icstudio.layout_import import read_layout
from icstudio.physical_cells import assign_port
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_standard_mos_layout import fault_detected
from scripts.qualify_ihp_resistor_layouts import regions,same_masks,rotated,altered,FAULTS

SOURCE=ROOT/'icstudio/assets/physical/gf180_resistors'
TARGETS=('gf180mcuC','gf180mcuD')
MODELS=('npolyf_s','npolyf_u','ppolyf_s','ppolyf_u','nplus_u','pplus_u','ppolyf_u_1k','ppolyf_u_1k_6p0')
SIZES=((1,1),(1,20),(20,1),(2,7),(7,2))


def prepare_source(out,target):
    lock=json.loads((SOURCE/'upstream-lock.json').read_bytes())
    if target not in TARGETS or lock['commit']!='aa3fc215a80d32437b8cca1cb3fdee819d18c4c9':raise ValueError('Unreviewed generator source.')
    for name,h in lock['files'].items():
        path=(SOURCE/name).resolve()
        if not path.is_relative_to(SOURCE.resolve()) or file_digest(path)!=h:raise ValueError('Changed public generator source: '+name)
    folder=out/target;folder.mkdir()
    flags=['-DTECHNAME='+target,'-DREVISION='+lock['commit'],'-DSTAGING_PATH=/nonexistent']+['-D'+f for f in lock['flags'][target]]
    for relative,name in [('gf180mcu/magic/gf180mcu.tcl','generator.tcl'),('common/pdk.tcl','pdk.tcl')]:
        result=subprocess.run([sys.executable,str(SOURCE/'common/preproc.py'),str(SOURCE/relative),str(folder/name),*flags],capture_output=True,timeout=60)
        (folder/(name+'.log')).write_bytes(result.stdout+result.stderr)
        if result.returncode or not (folder/name).is_file():raise ValueError('Pinned generator preprocessing failed.')
    return folder,dict(upstream=lock,flags=flags,prepared={n:file_digest(folder/n) for n in ('generator.tcl','pdk.tcl')})


def native_layers(tech):
    from icstudio.gf180_layout import prepare
    prepare(tech)
    # The pinned KLayout map names the resistor masks absent from the minimal
    # schematic layer palette. Preserve their native layer/datatype exactly.
    for prop in ET.parse(Path(tech['package_root'])/'libs.tech/klayout/gf180mcu.lyp').getroot().iter('properties'):
        match=re.fullmatch(r'(\S+) (\d+)/(\d+)@1',prop.findtext('source') or '')
        if not match:continue
        name,gds,datatype=match[1],int(match[2]),int(match[3])
        if not any((l['gds'],l['datatype'])==(gds,datatype) for l in tech['layers']):
            tech['layers'].append(dict(name=f'gf180_{name}_{gds}_{datatype}',gds=gds,datatype=datatype,color=prop.findtext('fill-color'),width=0,space=0))
    # Magic's pinned CIF output declares PRBNDRY at 0/0.
    if not any((l['gds'],l['datatype'])==(0,0) for l in tech['layers']):
        tech['layers'].append(dict(name='gf180_PRBNDRY',gds=0,datatype=0,color='#bbbb66',width=0,space=0))


def selected_reference(model,w,l):
    if model not in MODELS:raise ValueError('Unknown reviewed GF180 resistor.')
    return reference(f'.subckt coupon R1 R2 B\nX1 R1 R2 B {model} r_width={w:g}u r_length={l:g}u m=1\n.ends coupon\n','coupon')


def generate(tech,model,w,l,folder,magic,prepared):
    if model not in MODELS or (w,l) not in SIZES:raise ValueError('Use a reviewed sampled geometry.')
    folder.mkdir();target=tech['package_lock']['id'];source=Path(tech['package_root'])/'libs.tech/magic'
    script=f'''tech load {{{source/(target+'.tech')}}}
# Same 5 nm grid as the pinned upstream .magicrc; fixed contact-array seed.
scalegrid 1 10
drc euclidean on
random seed 12345
source {{{prepared/'generator.tcl'}}}
source {{{prepared/'pdk.tcl'}}}
# Local layout variant: enlarge enclosures on both axes and the well margin.
# Keep the original 0.23 um contact tile used to emit exact 0.22 um cuts.
dict set gf180mcu::ruleset sub_surround 0.20
rename gf180mcu::draw_contact gf180mcu::source_draw_contact
proc gf180mcu::draw_contact {{w h s o x atype ctype mtype {{orient vert}}}} {{
    return [gf180mcu::source_draw_contact $w $h [expr {{$s + 0.005}}] 0.11 $x $atype $ctype $mtype full]
}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [gf180mcu::{model}_defaults] [dict create w {w:g} l {l:g} rlcov 80 tbcov 80 endcov 80 res_diff_spacing 1.0 end_spacing 1.0]]
if {{[catch {{gf180mcu::{model}_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
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
    p,_=read_layout(folder/'coupon.gds');original=clone(p);link_technology(p,tech);c=p['cells'][0];c['ports']=['R1','R2','B'];db=kdb()
    metal=next(l['name'] for l in p['pdk']['layers'] if (l['gds'],l['datatype'])==(34,0));components=list(regions(p)[34,0].each())
    if len(components)!=3:raise ValueError('Expected two terminal conductors and one isolated guard ring.')
    guards=[v for v in components if v.holes()==1]
    if len(guards)!=1:raise ValueError('Expected one closed body conductor.')
    guard=guards[0];ends=sorted((v for v in components if v!=guard),key=lambda v:v.bbox().center().y,reverse=True)
    if len(ends)!=2 or ends[0].bbox().center().y<=0 or ends[1].bbox().center().y>=0:raise ValueError('Ambiguous resistor terminal positions.')
    for name,poly in [('R1',ends[0]),('R2',ends[1]),('B',guard)]:
        point=poly.bbox().center()
        if not poly.inside(point):
            pieces=db.Region(poly).decompose_trapezoids_to_region();piece=max(pieces.each(),key=lambda v:v.area());point=piece.bbox().center()
        if not poly.inside(point):raise ValueError('Port point lies outside its conductor.')
        assign_port(p,c['id'],name,metal,[point.x,point.y])
    same_masks(original,p);return p


def audit_extracted(path,model,w,l):
    lines=[line.split() for line in path.read_text().splitlines() if re.match(r'(?i)^x\S+\s',line)]
    if len(lines)!=1:raise ValueError('Expected exactly one extracted resistor.')
    row=lines[0]
    if len(row)<7 or row[4]!=model or set(row[1:3])!={'R1','R2'} or row[3]!='B':raise ValueError('Extracted resistor model/terminals differ.')
    params=dict(v.split('=',1) for v in row[5:] if '=' in v)
    for key,value in (('r_width',w),('r_length',l)):
        if key not in params or not math.isclose(scalar(params[key])*1e6,value,rel_tol=1e-10,abs_tol=1e-9):raise ValueError('Extracted dimension differs: '+key)
    return dict(model=model,terminals=row[1:4],width_um=w,length_um=l,sha256=file_digest(path))


def case(tech,model,w,l,out,tools,prepared):
    target=tech['package_lock']['id'];name=f'{target}-{model}-w{w:g}-l{l:g}';folder=out/name;folder.mkdir();row=dict(name=name,target=target,model=model,width_um=w,length_um=l,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,model,w,l,folder/'generator',tools['magic'],prepared);ref=selected_reference(model,w,l)
        save_project(p,folder/'saved.icproj');reopened=load_project(folder/'saved.icproj');same_masks(p,reopened)
        for angle in (0,90):
            q=reopened if angle==0 else rotated(reopened);baseline=folder/f'baseline-{angle}.gds';export_layout(q,baseline)
            exported=folder/f'rotation-{angle}.oas';export_layout(q,exported)
            ly=kdb().Layout();ly.read(str(exported));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['R1','R2','B'];same_masks(q,imported)
            outgds=folder/f'reimported-{angle}.gds';export_layout(imported,outgds)
            exchange=dict(full_gds=compare(baseline,outgds),oasis=compare(external,outgds,text_presentation=False))
            dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,ref)
            item=dict(rotation=angle,native_status=result['status'],drc_count=result.get('drc_count'),exchange=exchange,report_sha256=file_digest(dest/'report.json'))
            if result['status']!='passed':raise ValueError(result.get('error','Native verification failed.'))
            item['extracted']=audit_extracted(dest/'lvs-extraction/extracted.spice',model,w,l);row['layouts'].append(item)
        for fault in FAULTS:
            q=altered(p,fault,(34,0),(33,0)) if not fault.startswith('reference-') else p
            selected=selected_reference(model,w*1.2,l) if fault=='reference-width' else selected_reference(MODELS[(MODELS.index(model)+1)%len(MODELS)],w,l) if fault=='reference-model' else ref
            dest=folder/fault;result=run(q,q['top'],dest,tools,selected);detected=fault_detected(result,dest)
            row['faults'].append(dict(name=fault,kind='schematic reference' if fault.startswith('reference-') else 'physical geometry',detected=detected,status=result['status'],report_sha256=file_digest(dest/'report.json'),error=result.get('error')))
            if not detected:raise ValueError('Native checks did not detect '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2);ap.add_argument('--targets',nargs='+',choices=TARGETS,default=list(TARGETS));a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualification_geometry.py',ROOT/'scripts/qualify_ihp_resistor_layouts.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py')),*sorted(p for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts)]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('magic','netgen')};report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,processes={},source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in a.targets:
            tech,identity=load_technology(target);native_layers(tech);prepared,provenance=prepare_source(out,target);report['processes'][target]=dict(package=identity,generator=provenance)
            for model in MODELS:
                for w,l in ([(2,7)] if a.pilot else SIZES):jobs.append(pool.submit(case,tech,model,w,l,out,tools,prepared))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
