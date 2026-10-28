"""Selected public IHP resistor PCells through editable exchange and native checks.

Uses immutable bundled Magic generators with explicit Boolean terminal vias.
The optional M2-access view relocates both resistor ports to actual Metal2,
retaining the independent Metal1 body port. Native and port-only views preserve
native masks; the named m2-landing view adds only source-rule-derived Metal2
landing rectangles and preserves all other masks.
Selected straight, single-device geometries are not a continuous geometry range,
electrical characterization, statistical, density or fabrication qualification.
"""
import argparse,json,math,re,subprocess,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,load_project,save_project,scalar
from icstudio.catalog import link_technology
from icstudio.layout import kdb,polygon,rect
from icstudio.layout_import import read_layout
from icstudio.physical_cells import infer_ports,assign_port
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_standard_mos_layout import fault_detected
from scripts.qualification_geometry import regions,same_masks,rotated

MODELS=('rsil','rppd','rhigh')
SIZES=((.5,.5),(.5,20),(20,.5),(2,7),(7,2))
FAULTS=('terminal-open','body-open','terminal-short','reference-width','reference-model')
M2_MINIMUM_AREA_NM2=144000  # Pinned ihp-sg13g2-drc.tech M2.d, line 474.
VIA_SOURCE_HASHES={
    'ihp-sg13g2-res.tcl':'800c367d636e7dba8f9f3b15621d76a99b509416c0ebdf809631996489b799d1',
    'ihp-sg13g2-util.tcl':'8bfa9fcb33a035d7ba3253517f423dea245a4756a5a94f31160b254bcd7a454e',
    'ihp-sg13g2-via.tcl':'dc69231a313c84c5e67edc9b9ee3e00292eb698d971eaf50958b14e53b256efa',
    'ihp-sg13g2-drc.tech':'bec75c6c8aeb9720edcdfdcf1e2c132d9be4af42801dd61b45715d6c6ec68402',
}


def via_source_contract(tech):
    source=Path(tech['package_root'])/'libs.tech/magic'
    for name,expected in VIA_SOURCE_HASHES.items():
        if file_digest(source/name)!=expected:raise ValueError('Changed reviewed terminal-via source: '+name)
    rule='area allm2,obsm2 144000 200 "Metal2 minimum area < %a (M2.d)"'
    if rule not in (source/'ihp-sg13g2-drc.tech').read_text():raise ValueError('Reviewed M2.d rule differs.')
    return dict(files=VIA_SOURCE_HASHES,rule=rule,minimum_area_nm2=M2_MINIMUM_AREA_NM2,
                generator_vias=[0,1],guard_via_coverage=dict(viagb=0,viagt=0,viagl=0,viagr=0))






def selected_reference(model,w,l):
    if model not in MODELS:raise ValueError('Unknown reviewed resistor.')
    extra='' if model=='rsil' else ' b=0'
    return reference(f'.subckt coupon R1 R2 B\nX1 R1 R2 B {model} w={w:g}u l={l:g}u m=1{extra}\n.ends coupon\n','coupon')


def generate(tech,model,w,l,folder,magic,vias=0):
    if model not in MODELS or (w,l) not in SIZES:raise ValueError('Use a reviewed sampled geometry.')
    if type(vias) is not int or vias not in (0,1):raise ValueError('Terminal vias is a Boolean option (0 or 1).')
    if vias:via_source_contract(tech)
    folder.mkdir();source=Path(tech['package_root'])/'libs.tech/magic'
    # Model/dimensions come only from the finite reviewed cases above.
    script=f'''tech load {{{source/'ihp-sg13g2.tech'}}}
source {{{source/'ihp-sg13g2.tcl'}}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sg13g2::{model}_defaults] [dict create w {w:g} l {l:g} doports 1 vias {vias} viagb 0 viagt 0 viagl 0 viagr 0]]
if {{[catch {{sg13g2::{model}_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
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
    if r.returncode or log.count(b'GENERATOR_COMPLETE')!=1 or b'GENERATOR_FAILED' in log or re.search(rb'\d+ problems occurred',log):
        raise ValueError('Native generator failed; see console.log.')
    p,_=read_layout(folder/'coupon.gds');raw=clone(p);link_technology(p,tech);c=p['cells'][0];c['ports']=['R1','R2','B']
    ports=infer_ports(p,c)
    if len(ports)!=3 or {v['name'] for v in ports}!=set(c['ports']):raise ValueError('Missing/ambiguous native resistor ports.')
    for port in ports:
        metal=kdb().Region()
        for s in c['shapes']:
            if s['layer']==port['layer']:metal.insert(polygon(s))
        if not any(poly.inside(kdb().Point(*port['point'])) for poly in metal.merged().each()):raise ValueError('Port lies outside its conductor.')
        assign_port(p,c['id'],port['name'],port['layer'],port['point'])
    same_masks(raw,p);return p


def terminal_stack_audit(p,vias=1):
    """Independent metal/cut graph; resistive poly never forms an ideal wire.

    All three M1 components must have distinct positive-area contact support.
    Each optional upper access has its own M2 component and actual Via1 cuts
    fully within both metals. The body remains a third contacted M1 component.
    Native DRC separately enforces the full foundry enclosure/spacing rules.
    """
    db=kdb();rs=regions(p);c=p['cells'][0]
    ports={v['name']:v for v in c['layout_ports']}
    if set(ports)!={'R1','R2','B'}:raise ValueError('Stack audit requires exactly R1/R2/B.')
    metals=list(rs[(8,0)].merged().each());upper=list(rs.get((10,0),db.Region()).merged().each())
    cuts=list(rs[(6,0)].merged().each());viacuts=list(rs.get((19,0),db.Region()).merged().each())
    assigned=[];upperassigned=[];result={}
    def selected(polys,pt,label):
        found=[(i,poly) for i,poly in enumerate(polys) if poly.inside(db.Point(*pt))]
        if len(found)!=1:raise ValueError(label+' must select one connected conductor.')
        return found[0]
    for name in ('R1','R2','B'):
        port=ports[name];index,metal=selected(metals,port['point'],name+' M1');assigned.append(index)
        region=db.Region(metal);contacts=[v for v in cuts if not (db.Region(v)&region).is_empty()]
        if not contacts:raise ValueError(name+' has no contact support.')
        lower=rs.get((1,0) if name=='B' else (5,0),db.Region())
        if any(not (db.Region(v)-region).is_empty() or not (db.Region(v)-lower).is_empty() for v in contacts):
            raise ValueError(name+' contact cuts are not enclosed by both lower material and M1.')
        item=dict(m1_component=index,contact_components=len(contacts),port_layer=port['layer'])
        if name!='B' and vias:
            idx,m2=selected(upper,port['point'],name+' M2');upperassigned.append(idx);m2reg=db.Region(m2)
            connecting=[v for v in viacuts if (db.Region(v)-region).is_empty() and (db.Region(v)-m2reg).is_empty()]
            if not connecting:raise ValueError(name+' has no complete M1/Via1/M2 path.')
            item.update(m2_component=idx,via1_cuts=len(connecting),m2_area_um2=m2reg.area()/1e6)
        elif name=='B' and port['layer']!='Metal1.drawing':raise ValueError('Body must remain on Metal1.')
        result[name]=item
    if len(set(assigned))!=3 or (vias and len(set(upperassigned))!=2):raise ValueError('Terminal/body conductor components are shorted.')
    return result


def upper_access(p):
    """Move labels/ports, not masks; duplicate lower labels cannot hide opens."""
    q=clone(p);c=q['cells'][0]
    for port in list(c['layout_ports']):
        if port['name'] in ('R1','R2'):assign_port(q,c['id'],port['name'],'Metal2.drawing',port['point'])
    same_masks(p,q);terminal_stack_audit(q)
    return q


def m2_landing(p):
    """Named local routing landing, source M2.d minimum area, 5 nm grid.

    Keep each native rectangular upper terminal's height; only extend both
    horizontal sides equally by the smallest 5 nm amount reaching M2.d.
    Resistor, contact, via and body geometry must remain byte-independent XOR
    equal. This is an explicit routing addition, never a native generator fix.
    """
    q=clone(p);db=kdb();before=regions(p);changes=[]
    if p['pdk']['grid']!=5:raise ValueError('Reviewed M2 landing requires the pinned 5 nm grid.')
    for poly in before[(10,0)].each():
        region=db.Region(poly);box=poly.bbox()
        if not (region^db.Region(box)).is_empty():raise ValueError('Reviewed upper terminal must be rectangular.')
        if region.area()>=M2_MINIMUM_AREA_NM2:continue
        step=math.ceil((M2_MINIMUM_AREA_NM2-region.area())/(2*box.height()*5))*5
        q['cells'][0]['shapes'].append(rect('Metal2.drawing',box.left-step,box.bottom,box.width()+2*step,box.height()))
        changes.append(dict(original_box_nm=[box.left,box.bottom,box.right,box.top],extension_each_side_nm=step,
                            original_area_nm2=region.area(),landing_area_nm2=(box.width()+2*step)*box.height()))
    after=regions(q)
    if set(before)!=set(after) or any(not (before[k]^after[k]).is_empty() for k in before if k!=(10,0)) or not (before[(10,0)]-after[(10,0)]).is_empty():
        raise ValueError('M2 landing changed an unauthorized mask.')
    return q,changes


def missing_via(p):
    q=clone(p);db=kdb();c=q['cells'][0];pt=next(v['point'] for v in c['layout_ports'] if v['name']=='R1')
    metal=[v for v in regions(p)[(8,0)].each() if v.inside(db.Point(*pt))]
    if len(metal)!=1:raise ValueError('R1 does not select one lower conductor.')
    selected=db.Region(metal[0]);removed=[s for s in c['shapes'] if s['layer']=='Via1.drawing' and not (db.Region(polygon(s))&selected).is_empty()]
    if not removed:raise ValueError('No R1 Via1 cuts selected.')
    c['shapes']=[s for s in c['shapes'] if s not in removed]
    return q




def altered(p,fault,metal_pair=(8,0),contact_pair=(6,0)):
    q=clone(p);c=q['cells'][0];db=kdb();ls={(l['gds'],l['datatype']):l['name'] for l in q['pdk']['layers']}
    ports={v['name']:v for v in c['layout_ports']}
    if fault in ('terminal-open','body-open'):
        pin=ports['R1' if fault=='terminal-open' else 'B'];metal=regions(q)[metal_pair]
        selected=[poly for poly in metal.each() if poly.inside(db.Point(*pin['point']))]
        if len(selected)!=1:raise ValueError('Port does not select one connected conductor.')
        region=db.Region(selected[0]);removed=[s for s in c['shapes'] if s['layer']==ls[contact_pair] and not (db.Region(polygon(s))&region).is_empty()]
        if not removed:raise ValueError('No contacts selected by the negative control.')
        c['shapes']=[s for s in c['shapes'] if s not in removed]
    elif fault=='terminal-short':
        a,b=[ports[k]['point'] for k in ('R1','R2')];width=400
        c['shapes'] += [rect(ls[metal_pair],min(a[0],b[0])-width//2,a[1]-width//2,abs(a[0]-b[0])+width,width),
            rect(ls[metal_pair],b[0]-width//2,min(a[1],b[1])-width//2,width,abs(a[1]-b[1])+width)]
    else:raise ValueError('Unknown physical resistor control.')
    return q


def audit_extracted(path,model,w,l):
    text=path.read_text();lines=[line.split() for line in text.splitlines() if re.match(r'(?i)^x\S+\s',line)]
    if len(lines)!=1:raise ValueError('Expected exactly one extracted resistor.')
    row=lines[0]
    if len(row)<7 or row[4]!=model or set(row[1:3])!={'R1','R2'} or row[3]!='B':
        raise ValueError('Extracted resistor model or terminals differ.')
    params=dict(v.split('=',1) for v in row[5:] if '=' in v)
    for key,value in (('w',w),('l',l)):
        if key not in params or not math.isclose(scalar(params[key])*1e6,value,rel_tol=1e-10,abs_tol=1e-9):
            raise ValueError('Extracted resistor dimension differs: '+key)
    return dict(model=model,terminals=row[1:4],width_um=w,length_um=l,sha256=file_digest(path))


def audit_open_extracted(path,model,w,l,fault):
    """A physical open must alter its actual native node, not just DRC status."""
    rows=[v.split() for v in path.read_text().splitlines() if re.match(r'(?i)^x\S+\s',v)]
    if len(rows)!=1 or len(rows[0])<7 or rows[0][4]!=model:raise ValueError('Open control lost the resistor identity.')
    row=rows[0];params=dict(v.split('=',1) for v in row[5:] if '=' in v)
    for key,value in (('w',w),('l',l)):
        if key not in params or not math.isclose(scalar(params[key])*1e6,value,rel_tol=1e-10,abs_tol=1e-9):raise ValueError('Open control changed resistor '+key)
    if fault=='missing-via':
        if row[1] in ('R1','R2','B') or row[2:4]!=['R2','B']:raise ValueError('Missing-via did not independently open R1.')
    elif fault=='body-open':
        if set(row[1:3])!={'R1','R2'} or row[3] in ('R1','R2','B'):raise ValueError('Body control did not independently open B.')
    else:raise ValueError('Unknown reviewed open control.')
    return dict(model=model,terminals=row[1:4],width_um=w,length_um=l,sha256=file_digest(path))


def case(tech,model,w,l,out,tools,vias=0,access='native'):
    name=f'{model}-w{w:g}-l{l:g}'+(f'-vias{vias}-{access}' if vias or access!='native' else '');folder=out/name;folder.mkdir();row=dict(name=name,model=model,width_um=w,length_um=l,vias=vias,access=access,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,model,w,l,folder/'generator',tools['magic'],vias);ref=selected_reference(model,w,l)
        if vias:row['native_stack']=terminal_stack_audit(p)
        if access=='m2-landing':p,row['m2_landings']=m2_landing(p)
        if access.startswith('m2'):p=upper_access(p)
        save_project(p,folder/'saved.icproj');reopened=load_project(folder/'saved.icproj');same_masks(p,reopened)
        for angle in (0,90):
            q=reopened if angle==0 else rotated(reopened)
            baseline=folder/f'baseline-{angle}.gds';export_layout(q,baseline)
            exported=folder/f'rotation-{angle}.oas';export_layout(q,exported)
            # Import an independent OASIS rewrite, without an application sidecar.
            ly=kdb().Layout();ly.read(str(exported));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['R1','R2','B']
            same_masks(q,imported)
            if vias:
                found=infer_ports(imported,imported['cells'][0]);imported['cells'][0]['layout_ports']=found
                stack=terminal_stack_audit(imported)
                if access.startswith('m2') and any(stack[n]['port_layer']!='Metal2.drawing' for n in ('R1','R2')):raise ValueError('Upper access port layer changed during exchange.')
            outgds=folder/f'reimported-{angle}.gds';export_layout(imported,outgds)
            # OASIS has no native text appearance. Require full presentation
            # agreement with the original GDS as well as electrical anchors
            # and geometry agreement with the independently rewritten OASIS.
            exchange=dict(full_gds=compare(baseline,outgds),oasis=compare(external,outgds,text_presentation=False))
            dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,ref)
            item=dict(rotation=angle,native_status=result['status'],drc_count=result.get('drc_count'),exchange=exchange,report_sha256=file_digest(dest/'report.json'))
            if result['status']!='passed':raise ValueError(result.get('error','Native verification failed.'))
            if vias:item['stack']=stack
            item['extracted']=audit_extracted(dest/'lvs-extraction/extracted.spice',model,w,l);row['layouts'].append(item)
        for fault in FAULTS+(('missing-via',) if access.startswith('m2') else ()):
            q=missing_via(p) if fault=='missing-via' else altered(p,fault) if not fault.startswith('reference-') else p
            graph_error=None
            if vias and fault in ('body-open','missing-via'):
                try:terminal_stack_audit(q)
                except ValueError as error:graph_error=str(error)
                if graph_error is None:raise ValueError('Independent graph did not detect '+fault)
            selected=selected_reference(model,w*1.2,l) if fault=='reference-width' else selected_reference(MODELS[(MODELS.index(model)+1)%len(MODELS)],w,l) if fault=='reference-model' else ref
            dest=folder/fault;result=run(q,q['top'],dest,tools,selected);detected=fault_detected(result,dest)
            evidence={}
            if vias and fault in ('body-open','missing-via'):
                stages={s['name']:s['status'] for s in result['stages']}
                if stages.get('lvs_extraction')!='passed' or stages.get('lvs')!='failed' or (fault=='missing-via' and stages.get('drc')!='passed'):
                    raise ValueError('Open control lacks native extraction/LVS witness: '+fault)
                evidence=dict(extracted=audit_open_extracted(dest/'lvs-extraction/extracted.spice',model,w,l,fault),native_stages=stages)
            row['faults'].append(dict(name=fault,kind='schematic reference' if fault.startswith('reference-') else 'physical geometry',detected=detected,status=result['status'],graph_error=graph_error,report_sha256=file_digest(dest/'report.json'),error=result.get('error'),**evidence))
            if not detected:raise ValueError('Native checks did not detect '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True)
    ap.add_argument('--vias',type=int,choices=(0,1),default=0);ap.add_argument('--access',choices=('native','m2','m2-landing'),default='native')
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2);a=ap.parse_args()
    if a.access.startswith('m2') and a.vias!=1:ap.error('M2 access requires terminal vias=1.')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualification_geometry.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tech,identity=load_technology('ihp-sg13g2');tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('magic','netgen')}
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,process=identity,vias=a.vias,access=a.access,via_source_contract=via_source_contract(tech) if a.vias else None,selected_sizes_um=[list(v) for v in ([(2,7)] if a.pilot else SIZES)],deferred_classes=['guard-ring via coverage','snake','array','other guard/isolation options'],source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,model,w,l,out,tools,a.vias,a.access) for model in MODELS for w,l in ([(2,7)] if a.pilot else SIZES)]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
