"""Finite two-unit IHP cap_cmim physical multiplicity source experiment.

Two source-drawn contacted devices share both electrodes. This is not arbitrary
array, installed, statistical, parasitic, operating or family qualification.
"""
import argparse
import hashlib
import json
import sys
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device
from icstudio.interchange import export_layout, spice
from icstudio.layout import rect
from icstudio.model import clone, digest, file_digest, load_project, save_project, validate
from icstudio.silicon_flow import job
from icstudio.testbenches import native_subcircuit
from icstudio.layout_verification import reference
from scripts.qualify_ihp_mim_layout import generate, rotate
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_ihp_cmim_reference import catalog_project
from scripts.check_ihp_cmim_enclosures import safe_path
from scripts.qualify_ihp_cmim_enclosures import source_locked_contract

KEY = 'sg13g2_pr/cap_cmim.sym'
CASES = ('m2-0', 'pair-0', 'm2-90', 'pair-90', 'm1-0', 'm3-0', 'wrong-wire-0', 'missing-contact-0', 'wrong-width-0', 'physical-width-0')

def require(condition, message):
    if not condition: raise ValueError(message)

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def two_units(original,second=None):
    q=clone(original);cell=q['cells'][0];shift=7700 if second else 7600; duplicate=clone((second or original)['cells'][0]['shapes'])
    for shape in duplicate:
        shape['id']=uuid.uuid4().hex[:16]
        shape['points']=[[x+shift,y] for x,y in shape['points']]
    cell['shapes'].extend(duplicate)
    layers={(v['gds'],v['datatype']):v['name'] for v in q['pdk']['layers']}
    cell['shapes'].append(rect(layers[(126,0)],3000,-3300,shift-6000,6600))
    return q

def attach(layout, technology, mode):
    p,_=catalog_project(layout,technology,7,7);cell=p['cells'][0];first=cell['devices'][0]
    if mode in ('m1','m2','m3','missing-contact','physical-width'):
        first['model_params']['m']=2 if mode in ('missing-contact','physical-width') else int(mode[1:])
    else:
        second=create_device(technology,KEY,'C2');second['x']=200
        second['nets']={'c0':'C2','c1':'C1'} if mode=='wrong-wire' else {'c0':'C1','c1':'C2'}
        second['net_labels']=dict(second['nets']);second['model_params'].update(w='0.000007',l='0.000007',m=1,mm_ok=1)
        if mode=='wrong-width':second['model_params']['w']='0.0000072'
        cell['devices'].append(second)
    validate(p);return p

def run_case(project, folder, tools):
    folder.mkdir();save_project(project,folder/'catalog.icproj');saved=load_project(folder/'catalog.icproj')
    require(digest(saved)==digest(project),'Save/reopen differs.')
    raw=native_subcircuit(saved,saved['top']);simulation=spice(saved,saved['top'],hierarchical=False)
    (folder/'captured-reference.spice').write_text(raw,encoding='utf-8')
    (folder/'simulation-before.spice').write_text(simulation,encoding='utf-8')
    export_layout(saved,folder/'selected.oas')
    settings=dict(type='silicon',verification_mode='drc_lvs',tools=tools,reference=reference(raw,'coupon'),
                  lvs_extractor='ihp-klayout',drc_engine='ihp-public')
    import icstudio.engines as engines
    original_execute=engines.execute;commands=[]
    def capture(args,cwd,*rest,**kwargs):
        if len(args)>2 and args[1:3]==['-batch','lvs']:
            commands.append(dict(argv=args,cwd=str(cwd),setup_sha256=file_digest(args[5]),
                                 schematic_sha256=file_digest(folder/'job/physical-flow/schematic-lvs.spice'),
                                 extracted_sha256=file_digest(folder/'job/physical-flow/lvs-extraction/extracted.spice')))
        return original_execute(args,cwd,*rest,**kwargs)
    engines.execute=capture
    try:result=job(saved,saved['top'],settings,folder/'job',lambda *_:None)
    finally:engines.execute=original_execute
    write(folder/'netgen-command.json',commands);write(folder/'result.json',result)
    flow=folder/'job/physical-flow';require((flow/'schematic.spice').read_text()==raw,'Original reference changed.')
    require(spice(saved,saved['top'],hierarchical=False)==simulation,'Simulation changed during physical projection.')
    report=result['silicon_report'];return dict(status=report['status'],stages={r['name']:r['status'] for r in report['stages']},
        report_sha256=file_digest(flow/'report.json'),reference_sha256=file_digest(flow/'schematic.spice'))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    for n in ('magic','netgen','klayout'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=safe_path(a.output.absolute()).resolve();require(not out.is_relative_to(ROOT),'Output is inside source tree.')
    tools={n:str(safe_path(getattr(a,n).absolute()).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    out.mkdir(parents=True,exist_ok=False)
    source=source_locked_contract()
    for name in ('qualify_ihp_cmim_multiplicity.py','check_ihp_cmim_multiplicity.py'):
        source['scripts/'+name]=file_digest(ROOT/'scripts'/name)
    for name in ('icstudio/assets/physical/ihp_klayout_lvs/rule_decks/custom_combiner.lvs',
                 'icstudio/assets/physical/ihp_klayout_lvs/rule_decks/custom_reader.lvs',
                 'docs/qualification/ihp-cmim-applicability-v1/04_06_cap.rst'):
        source[name]=file_digest(ROOT/name)
    report=dict(status='RUNNING',scope=__doc__,qualified=False,installed_acceptance=False,cases=[],source_files=source,
                tool_sha256={n:file_digest(v) for n,v in tools.items()},runtime_scope='Selected launcher bytes only, not complete runtime.')
    try:
        tech,report['package']=load_technology('ihp-sg13g2');original=generate(tech,7,7,out/'generator',tools['magic'])
        base=two_units(original);wide=two_units(original,generate(tech,7.2,7,out/'generator-wide',tools['magic']))
        for name in CASES:
            mode,angle=name.rsplit('-',1);candidate=wide if mode=='physical-width' else base
            physical=clone(candidate) if angle=='0' else rotate(candidate)
            if mode=='missing-contact':
                layer=next(v['name'] for v in physical['pdk']['layers'] if (v['gds'],v['datatype'])==(129,0))
                physical['cells'][0]['shapes']=[s for s in physical['cells'][0]['shapes'] if s['layer']!=layer or min(x for x,y in s['points'])<4000]
            layout=out/(name+'-layout.icproj');save_project(physical,layout);project=attach(layout,tech,mode)
            observed=run_case(project,out/name,tools)
            report['cases'].append(dict(name=name,observed=observed));write(out/'report.json',report)
        require(all(file_digest(ROOT/name)==value for name,value in source.items()) and
                all(file_digest(tools[name])==value for name,value in report['tool_sha256'].items()),'Source or selected launcher changed.')
        report['status']='OBSERVED'
        write(out/'report.json',report)
        from scripts.check_ihp_cmim_multiplicity import verify_evidence
        report['independent_readback']=verify_evidence(out)
    except Exception as exc:report.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(out/'report.json',report);print(json.dumps(dict(status=report['status'],cases=len(report['cases']),error=report.get('error'))))
    return int(report['status']=='FAIL')

if __name__=='__main__':raise SystemExit(main())
