"""Finite native IHP guard-via class, separate from historical terminal-via scope."""
import argparse,json,re,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qualify_ihp_resistor_layouts import *
from scripts import qualify_ihp_resistor_layouts as baseline
CONTRACT_PATH=ROOT/'docs/qualification/ihp-resistor-guard-vias-v1.json'
EXPECTED_CONTRACT_SHA256='eba71edf69a52b3a7d28778e4eb2cf873ae7536b151cc020d9c4eeff9a5eb1ba'
EXPECTED_PROFILE_SHA256='54e229b30cdf187ec25958935e332e393cddab42001c026b5acdf02d95f8e79b'
CONTRACT=json.loads(CONTRACT_PATH.read_text())

def generate(tech,model,w,l,folder,magic,coverage):
    if model not in MODELS or (w,l) not in SIZES:raise ValueError('Use a reviewed sampled geometry.')
    via_source_contract(tech)
    if coverage not in CONTRACT['coverage_cases'].values():raise ValueError('Unreviewed guard coverage.')
    parameters=' '.join(k+' '+coverage.get(k,'0') for k in ('viagb','viagt','viagl','viagr'))
    folder.mkdir();source=Path(tech['package_root'])/'libs.tech/magic'
    # Model/dimensions come only from the finite reviewed cases above.
    script=f'''tech load {{{source/'ihp-sg13g2.tech'}}}
source {{{source/'ihp-sg13g2.tcl'}}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sg13g2::{model}_defaults] [dict create w {w:g} l {l:g} doports 1 vias 0 {parameters}]]
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


def body_components(p):
    db=kdb();rs=regions(p);ports={v['name']:v for v in p['cells'][0]['layout_ports']}
    b=ports['B'];lower=[x for x in rs[(8,0)].merged().each() if x.inside(db.Point(*b['point']))]
    if len(lower)!=1:raise ValueError('B must select one M1 component.')
    return db.Region(lower[0])


def guard_access(p,coverage):
    db=kdb();body=body_components(p);rs=regions(p);candidates=[]
    for poly in rs.get((10,0),db.Region()).merged().each():
        upper=db.Region(poly)
        cuts=[v for v in rs.get((19,0),db.Region()).merged().each() if (db.Region(v)-body).is_empty() and (db.Region(v)-upper).is_empty()]
        if cuts:candidates.append((poly,cuts))
    if not candidates:raise ValueError('No actual guard M2/Via1 landing.')
    side=next(k for k in ('viagb','viagt','viagl','viagr') if coverage.get(k,'0')!='0')
    def rank(item):
        b=item[0].bbox()
        return {'viagb':b.bottom,'viagt':-b.top,'viagl':b.left,'viagr':-b.right}[side]
    poly,cuts=min(candidates,key=rank);point=cuts[0].bbox().center()
    q=clone(p);assign_port(q,q['cells'][0]['id'],'B','Metal2.drawing',[point.x,point.y]);same_masks(p,q)
    return q


def guard_audit(p):
    db=kdb();ports={v['name']:v for v in p['cells'][0]['layout_ports']}
    if ports['B']['layer']!='Metal2.drawing':raise ValueError('Guard access must be M2.')
    q=clone(p);assign_port(q,q['cells'][0]['id'],'B','Metal1.drawing',ports['B']['point'])
    result=terminal_stack_audit(q,vias=0);body=body_components(p);rs=regions(p)
    uppers=[x for x in rs[(10,0)].merged().each() if x.inside(db.Point(*ports['B']['point']))]
    if len(uppers)!=1:raise ValueError('B must select exactly one M2 component.')
    upper=db.Region(uppers[0]);cuts=[v for v in rs.get((19,0),db.Region()).merged().each() if (db.Region(v)-body).is_empty() and (db.Region(v)-upper).is_empty()]
    if not cuts:raise ValueError('B lacks complete M1/Via1/M2 path.')
    result['B'].update(port_layer='Metal2.drawing',via1_cuts=len(cuts),m2_area_nm2=upper.area())
    return result


def fault_layout(p,fault):
    q=clone(p);c=q['cells'][0];db=kdb();ports={v['name']:v for v in c['layout_ports']}
    if fault=='guard-contact-open':return altered(p,'body-open')
    if fault=='guard-via-open':
        rs=regions(p);poly=[x for x in rs[(10,0)].merged().each() if x.inside(db.Point(*ports['B']['point']))]
        if len(poly)!=1:raise ValueError('Ambiguous selected upper guard.')
        upper=db.Region(poly[0]);removed=[s for s in c['shapes'] if s['layer']=='Via1.drawing' and not (db.Region(polygon(s))&upper).is_empty()]
        if not removed:raise ValueError('Fault removed no cuts.')
        c['shapes']=[s for s in c['shapes'] if s not in removed];return q
    if fault=='guard-short':
        a,b=[ports[n]['point'] for n in ('B','R1')];width=400
        c['shapes'] += [rect('Metal1.drawing',min(a[0],b[0])-200,a[1]-200,abs(a[0]-b[0])+width,width),rect('Metal1.drawing',b[0]-200,min(a[1],b[1])-200,width,abs(a[1]-b[1])+width)]
        return q
    raise ValueError('Unknown guard fault.')


def execute_case(tech,model,label,coverage,out,tools):
    folder=out/(model+'-'+label);folder.mkdir();row=dict(model=model,coverage=coverage,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,model,2,7,folder/'generator',tools['magic'],coverage)
        p=guard_access(p,coverage);row['graph']=guard_audit(p)
        save_project(p,folder/'saved.icproj');reopened=load_project(folder/'saved.icproj');same_masks(p,reopened)
        ref=selected_reference(model,2,7)
        for angle in (0,90):
            q=reopened if angle==0 else rotated(reopened);guard_audit(q)
            gds=folder/f'baseline-{angle}.gds';export_layout(q,gds)
            oasis=folder/f'rotation-{angle}.oas';export_layout(q,oasis)
            ly=kdb().Layout();ly.read(str(oasis));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['R1','R2','B'];imported['cells'][0]['layout_ports']=infer_ports(imported,imported['cells'][0]);same_masks(q,imported);graph=guard_audit(imported)
            target=folder/f'reimported-{angle}.gds';export_layout(imported,target)
            exchange=dict(full_gds=compare(gds,target),oasis=compare(external,target,text_presentation=False))
            dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,ref)
            item=dict(rotation=angle,status=result['status'],graph=graph,exchange=exchange,report_sha256=file_digest(dest/'report.json'));row['layouts'].append(item)
            if result['status']!='passed':raise ValueError('Native positive failed: '+str(result.get('error')))
            item['extracted']=audit_extracted(dest/'lvs-extraction/extracted.spice',model,2,7)
        for fault in ('guard-via-open','guard-contact-open','guard-short','reference-width','reference-model'):
            q=clone(p);r=ref;graph_error=None
            if fault=='reference-width':r=selected_reference(model,3,7)
            elif fault=='reference-model':r=selected_reference('rppd' if model!='rppd' else 'rhigh',2,7)
            else:q=fault_layout(p,fault)
            try:guard_audit(q)
            except ValueError as exc:graph_error=str(exc)
            if fault.startswith('reference-'):same_masks(p,q)
            dest=folder/fault;result=run(q,q['top'],dest,tools,r)
            detected=fault_detected(result,dest);item=dict(name=fault,detected=detected,status=result['status'],graph_error=graph_error,report_sha256=file_digest(dest/'report.json'));row['faults'].append(item)
            if not detected:raise ValueError('Native fault escaped: '+fault)
            if fault in ('guard-via-open','guard-contact-open'):
                if not graph_error:raise ValueError('Independent graph missed open.')
                stages={v['name']:v['status'] for v in result['stages']}
                if stages.get('lvs_extraction')!='passed' or stages.get('lvs')!='failed':raise ValueError('Missing native extraction/LVS open witness.')
                item['native_stages']=stages
                item['extracted']=audit_open_extracted(dest/'lvs-extraction/extracted.spice',model,2,7,'body-open')
        row['status']='PASS'
    except Exception as exc:row.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row



def verify_tool_profile(profile,tools):
    prefixes={Path(v).parent.parent for v in tools.values()}
    if len(prefixes)!=1:raise ValueError('Native tools require same authenticated prefix.')
    prefix=prefixes.pop()
    for name,selected in tools.items():
        expected=prefix/'bin'/name
        if Path(selected).resolve()!=expected.resolve() or 'bin/'+name not in profile['installed']:raise ValueError('Selected native executable is not its named profile entry.')
    for rel,entry in profile['installed'].items():
        path=prefix/rel
        if 'sha256' in entry and (not path.is_file() or file_digest(path)!=entry['sha256']):raise ValueError('Changed native profile file: '+rel)
        if 'symlink' in entry and (not path.is_symlink() or str(path.readlink())!=entry['symlink']):raise ValueError('Changed native profile link: '+rel)
    for name,entry in profile['runtime_dependencies'].items():
        if file_digest(Path(name))!=entry['sha256']:raise ValueError('Changed native runtime dependency: '+name)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True);ap.add_argument('--tool-profile',type=Path,required=True);a=ap.parse_args()
    if file_digest(CONTRACT_PATH)!=EXPECTED_CONTRACT_SHA256:raise ValueError('Unreviewed guard contract.')
    if file_digest(a.tool_profile)!=EXPECTED_PROFILE_SHA256:raise ValueError('Unreviewed native tool profile.')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tech,identity=load_technology('ihp-sg13g2');via_source_contract(tech)
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen')};profile=json.loads(a.tool_profile.read_text())
    verify_tool_profile(profile,tools)
    sources=[Path(__file__),CONTRACT_PATH,Path(baseline.__file__),ROOT/'scripts/qualification_geometry.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={str(p.relative_to(ROOT)):file_digest(p) for p in sources};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes());(out/'contract.json').write_bytes(CONTRACT_PATH.read_bytes())
    report=dict(schema=1,status='RUNNING',qualified=False,chunk_complete=False,contract_sha256=file_digest(CONTRACT_PATH),tool_profile_sha256=file_digest(a.tool_profile),process=identity,cases=[])
    for model in CONTRACT['models']:
        for label,coverage in CONTRACT['coverage_cases'].items():
            row=execute_case(tech,model,label,coverage,out,tools);report['cases'].append(row);write(out/'qualification.json',report);print(model,label,row['status'],row.get('error',''),flush=True)
    verify_tool_profile(profile,tools)
    report['implementation_unchanged']=before=={str(p.relative_to(ROOT)):file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and all(x['status']=='PASS' for x in report['cases']) else 'FAIL';write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
