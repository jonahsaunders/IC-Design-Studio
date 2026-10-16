"""Fresh IHP MIM layout checks with independent geometry and physical faults."""
import argparse,json,re,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest
from icstudio.catalog import link_technology
from icstudio.layout_import import read_layout
from icstudio.layout import kdb,polygon,rect
from icstudio.layout_verification import run,reference
from icstudio.physical_cells import infer_ports,assign_port
from icstudio.pdks import PDKRegistry
from scripts.qualify_standard_mos import write
from scripts.qualify_standard_mos_layout import fault_detected
from scripts.prepare_ihp_mim_qualification import prepare

SIZES=((2.3,2.3),(3,3),(7,7),(10,10),(2.3,10),(10,2.3))


def regions(project):
    db=kdb();cell=project['cells'][0];layers={r['name']:(r['gds'],r['datatype']) for r in project['pdk']['layers']};result={}
    for shape in cell['shapes']:
        key=layers[shape['layer']];result.setdefault(key,db.Region()).insert(polygon(shape))
    return {key:value.merged() for key,value in result.items()}


def spacing_oracle(project):
    """Measure same-cap connected components on exported mask shapes in nm.

    This test oracle uses polygon intersection/dilation, independent of Magic
    native tiles, CIF traversal and the native DRC error classification.
    """
    db=kdb();rs=regions(project);caps=rs.get((36,0),db.Region());cuts=rs.get((129,0),db.Region());metal=rs.get((126,0),db.Region())
    if caps.is_empty() or metal.is_empty():raise ValueError('Missing capacitor/metal geometry in spacing oracle.')
    failures=[]
    for cap in caps.each():
        c=db.Region(cap);contacts=cuts & c;unrelated=db.Region()
        for component in metal.each():
            r=db.Region(component)
            if (r & contacts).is_empty():unrelated.insert(component)
        intrusion=c & unrelated.sized(600)
        failures.append(dict(contact_area_nm2=contacts.area(),violation_area_nm2=intrusion.area()))
    return dict(status='PASS' if all(r['contact_area_nm2']>0 and r['violation_area_nm2']==0 for r in failures) else 'FAIL',capacitors=failures)


def generate(tech,w,l,folder,magic):
    folder.mkdir();source=Path(tech['package_root'])/'libs.tech/magic'
    script=f'''tech load {{{source/'ihp-sg13g2.tech'}}}
source {{{source/'ihp-sg13g2.tcl'}}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sg13g2::cap_cmim_defaults] [dict create w {w} l {l} doports 1]]
if {{[catch {{sg13g2::cap_cmim_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
select top cell
box select
save coupon
gds write coupon.gds
puts GENERATOR_COMPLETE
quit -noprompt
'''
    (folder/'generate.tcl').write_bytes(script.encode());(folder/'empty.magicrc').write_bytes(b'')
    result=subprocess.run([magic,'-dnull','-noconsole','-rcfile','empty.magicrc','generate.tcl'],cwd=folder,capture_output=True,timeout=120)
    log=result.stdout+result.stderr;(folder/'console.log').write_bytes(log)
    if result.returncode or log.count(b'GENERATOR_COMPLETE')!=1 or b'GENERATOR_FAILED' in log:raise ValueError('IHP upstream PCell did not finish.')
    p,_=read_layout(folder/'coupon.gds');link_technology(p,tech);c=p['cells'][0];c['ports']=['C1','C2']
    before=regions(p);db=kdb();ports=infer_ports(p,c)
    if {r['name'] for r in ports}!=set(c['ports']):raise ValueError('Missing generated capacitor terminal.')
    for pin in ports:
        metal=db.Region()
        for shape in c['shapes']:
            if shape['layer']==pin['layer']:metal.insert(polygon(shape))
        if not any(poly.inside(db.Point(*pin['point'])) for poly in metal.each()):raise ValueError('Generator port is outside its conductor.')
        assign_port(p,c['id'],pin['name'],pin['layer'],pin['point'])
    after=regions(p)
    if set(before)!=set(after) or any(not (before[key]^after[key]).is_empty() for key in before):raise ValueError('Assigning terminals changed a mask.')
    return p


def rotate(p):
    q=clone(p);c=q['cells'][0]
    for shape in c['shapes']:shape['points']=[[-y,x] for x,y in shape['points']]
    for text in c.get('layout_texts',[]):text['x'],text['y']=-text['y'],text['x']
    for port in c['layout_ports']:port['point']=[-port['point'][1],port['point'][0]]
    return q


def altered(p,fault):
    q=clone(p);c=q['cells'][0];ls={(r['gds'],r['datatype']):r['name'] for r in q['pdk']['layers']}
    if fault=='missing-contacts':c['shapes']=[s for s in c['shapes'] if s['layer']!=ls[129,0]]
    elif fault=='wrong-width':
        for s in c['shapes']:
            if s['layer']==ls[36,0]:
                edge=max(x for x,y in s['points']);s['points']=[[x+100 if x==edge else x,y] for x,y in s['points']]
    elif fault=='plate-short':
        c['shapes'] += [rect(ls[126,0],0,-820,6000,1640),rect(ls[67,0],0,-1000,6200,2000),rect(ls[125,0],5000,-210,420,420)]
    elif fault.startswith('unrelated-'):
        distance=int(fault.split('-')[1]);edge=max(s['points'][i][0] for s in c['shapes'] if s['layer']==ls[36,0] for i in range(len(s['points'])))
        c['shapes'].append(rect(ls[126,0],edge+distance,-1000,1640,2000))
    else:raise ValueError('Unknown IHP physical control.')
    return q


def summarize(report,folder):
    return dict(native_status=report['status'],drc_count=report.get('drc_count'),error=report.get('error'),
        stages={s['name']:s['status'] for s in report['stages']},report_sha256=file_digest(folder/'report.json'))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/prepare_ihp_mim_qualification.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,cases=[],
        scope='Selected standard IHP cap_cmim geometries, import/port assignment, local MIM DRC correction, native full DRC/LVS and physical faults. No RF, complete operating-envelope, chip, or foundry qualification.',
        source_files_sha256=file_digest(out/'source-files.json'))
    try:
        report['adapter']=prepare(ROOT/'icstudio/assets/pdks/ihp-sg13g2',out/'adapter')
        registry=PDKRegistry(out/'registry');key=registry.install(out/'adapter/package.json');tech=registry.technology(key)
        tools={'magic':a.magic,'netgen':a.netgen}
        baseline=None
        for w,l in SIZES:
            p=generate(tech,w,l,out/f'generator-{w:g}-{l:g}',a.magic)
            selected=reference(f'.subckt coupon C1 C2\nX1 C1 C2 cap_cmim w={w:g}u l={l:g}u m=1\n.ends coupon\n','coupon')
            for rotation in (0,90):
                q=p if rotation==0 else rotate(p);name=f'{w:g}-{l:g}-r{rotation}';folder=out/name;oracle=spacing_oracle(q)
                native=run(q,q['top'],folder,tools,selected);row=dict(name=name,oracle=oracle,**summarize(native,folder))
                row['status']='PASS' if native['status']=='passed' and oracle['status']=='PASS' else 'FAIL';report['cases'].append(row);write(out/'qualification.json',report);print(name,row['status'],row.get('error'),flush=True)
            if (w,l)==(7,7):baseline=(p,selected)
        p,selected=baseline
        for fault in ('missing-contacts','wrong-width','plate-short','unrelated-595','unrelated-600','unrelated-605'):
            q=altered(p,fault);folder=out/fault;native=run(q,q['top'],folder,tools,selected);row=dict(name=fault,oracle=spacing_oracle(q),**summarize(native,folder))
            findings=(folder/'drc/findings.tsv').read_text() if (folder/'drc/findings.tsv').exists() else ''
            row['mim_e_detected']='(MIM.e)' in findings
            if fault.startswith('unrelated-'):
                expect=fault=='unrelated-595';row['scope']='MIM.e boundary control only; other native spacing findings are retained and are not waived.'
                valid=row['stages']['preflight']=='passed' and row['stages']['layout_export']=='passed' and row['drc_count'] is not None and row['mim_e_detected']==expect and (row['oracle']['status']=='FAIL')==expect
            else:
                row['native_connectivity_fault_detected']=fault_detected(native,folder);valid=row['native_connectivity_fault_detected']
                if fault=='missing-contacts':valid=valid and '(MIM.h)' in findings
            row['status']='PASS' if valid else 'FAIL';report['cases'].append(row);write(out/'qualification.json',report);print(fault,row['status'],row.get('error'),flush=True)
        report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
        report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    except Exception as error:report.update(status='FAIL',error=repr(error),traceback=traceback.format_exc());print(report['error'],flush=True)
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
