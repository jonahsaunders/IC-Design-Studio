import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
"""Explicit corrected corner-safe routing experiment; original native failures retained."""
from scripts.qualify_ihp_guard_vias import *
from scripts import qualify_ihp_guard_vias as raw
from scripts.ihp_guard_corner_conditioner import condition
CONTRACT_PATH=ROOT/'docs/qualification/ihp-resistor-guard-corner-safe-v2.json'
EXPECTED_CONTRACT_SHA256='04ed8338f7a5c24cc09253dfff288e03cd935085974f654139f194596ce681a9'
CONTRACT=json.loads(CONTRACT_PATH.read_text())

def generate(tech,model,w,l,folder,magic,coverage):
    source=Path(tech['package_root'])/'libs.tech/magic/ihp-sg13g2-cifout.tech'
    if file_digest(source)!=CONTRACT['cifout_sha256'] or CONTRACT['cifout_rule'] not in source.read_text():raise ValueError('Changed reviewed cut-array source.')
    p=raw.generate(tech,model,w,l,folder,magic,coverage)
    q,record=condition(p,model,coverage,CONTRACT)
    write(folder.parent/'conditioning.json',record)
    return q

def execute_case(tech,model,label,coverage,out,tools):
    folder=out/(model+'-'+label);folder.mkdir();row=dict(model=model,coverage=coverage,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,model,2,7,folder/'generator',tools['magic'],coverage)
        row['conditioning']=json.loads((folder/'conditioning.json').read_text())
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



def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True);ap.add_argument('--tool-profile',type=Path,required=True);a=ap.parse_args()
    if file_digest(CONTRACT_PATH)!=EXPECTED_CONTRACT_SHA256:raise ValueError('Unreviewed guard contract.')
    if file_digest(a.tool_profile)!=EXPECTED_PROFILE_SHA256:raise ValueError('Unreviewed native tool profile.')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tech,identity=load_technology('ihp-sg13g2');via_source_contract(tech)
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen')};profile=json.loads(a.tool_profile.read_text())
    verify_tool_profile(profile,tools)
    sources=[Path(__file__),CONTRACT_PATH,Path(baseline.__file__),Path(raw.__file__),ROOT/'scripts/ihp_guard_corner_conditioner.py',ROOT/'scripts/qualification_geometry.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={str(p.relative_to(ROOT)):file_digest(p) for p in sources};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes());(out/'contract.json').write_bytes(CONTRACT_PATH.read_bytes())
    report=dict(schema=1,status='RUNNING',qualified=False,chunk_complete=False,contract_sha256=file_digest(CONTRACT_PATH),tool_profile_sha256=file_digest(a.tool_profile),process=identity,cases=[])
    for model in CONTRACT['models']:
        for label,coverage in CONTRACT['coverage_cases'].items():
            row=execute_case(tech,model,label,coverage,out,tools);report['cases'].append(row);write(out/'qualification.json',report);print(model,label,row['status'],row.get('error',''),flush=True)
    verify_tool_profile(profile,tools)
    report['implementation_unchanged']=before=={str(p.relative_to(ROOT)):file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and all(x['status']=='PASS' for x in report['cases']) else 'FAIL';write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
