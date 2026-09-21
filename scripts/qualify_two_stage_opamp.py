"""Actual SKY130 Miller OTA: process verification, unchanged PVT limits and ECO.

Each geometry gets actual DRC/LVS/extraction once. The immutable extracted DUT
then runs in every saved fixture/condition, retaining all decks and raw results.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import itertools
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def condition(text):
    try:
        corner,temp,voltage=text.split(':')
        return corner,float(temp),float(voltage)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use CORNER:TEMPERATURE:VOLTAGE.') from exc


def summarize(directory, report):
    """Retain every requirement value without duplicating noise vector spectra."""
    from icstudio.model import file_digest,clone
    result={k:report[k] for k in ('schema','status','conditions','extraction','requirements_sha256',
                                  'process_lock','implementation_sha256','scope') if k in report}
    result['full_report_sha256']=file_digest(directory/'report.json')
    result['phases']=[]
    for phase in report['phases']:
        compact={k:clone(v) for k,v in phase.items() if k!='cases'}
        path=directory/phase.get('physical',{}).get('report','missing')
        if path.is_file():
            physical=json.loads(path.read_text())
            compact['physical']['sha256']=file_digest(path)
            compact['physical']['gates']=[dict(name=stage['name'],status=stage['status'],
                evidence={k:v for k,v in stage.get('evidence',{}).items() if k in
                    ('violations','style','unique_match','capacitors','resistors','mode','sha256','profile_sha256')})
                for stage in physical.get('stages',[]) if stage['name'] in ('drc','lvs','capacitance_extraction','integrity')]
            for stage in physical.get('stages',[]):
                normalization=stage.get('evidence',{}).get('profile',{}).get('capacitance_normalization')
                if normalization:
                    compact['physical']['capacitance_normalization']={k:clone(v) for k,v in normalization.items()
                        if k not in ('nets','conservation')}
                    compact['physical']['capacitance_normalization']['conservation']={k:v for k,v in normalization['conservation'].items() if k!='entries'}
        compact['cases']=[{k:v for k,v in row.items() if k in ('index','testbench','condition','status','requirements','error')}
                          for row in phase['cases']]
        ranges={}
        for row in compact['cases']:
            for metric in row.get('requirements',[]):
                for side in ('before','after'):
                    value=metric.get(side)
                    if isinstance(value,(float,int)):
                        key=metric['name']+'/'+side
                        data=ranges.setdefault(key,dict(unit=metric.get('unit',''),minimum=value,maximum=value))
                        data['minimum']=min(data['minimum'],value);data['maximum']=max(data['maximum'],value)
        compact['ranges']=ranges;result['phases'].append(compact)
    for key in ('eco','error'):
        if key in report:result[key]=report[key]
    if 'implementation_integrity' in report:result['implementation_integrity']=clone(report['implementation_integrity'])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--extraction',choices=['capacitance','rc'],default='capacitance')
    parser.add_argument('--conditions',nargs='+',type=condition,default=[('nominal',27.,1.8),('ss',0.,1.62),('ff',85.,1.98)])
    parser.add_argument('--full-pvt',action='store_true',help='Run every saved process/voltage/temperature combination')
    parser.add_argument('--workers',type=int,default=2)
    for engine in ('magic','netgen','ngspice'):
        parser.add_argument('--'+engine,default=shutil.which(engine) or str(ROOT/'build/runtime'/(engine+'-run')))
    args=parser.parse_args()
    if not 1<=args.workers<=8:parser.error('Use one to eight simulation workers.')
    from icstudio.model import clone,digest,file_digest,atomic_write,save_project,History
    from icstudio.two_stage_opamp import reference,generate_layout
    from icstudio.hierarchical_flow import run,verify_integrity
    from icstudio.testbenches import simulate
    from icstudio.layout_eco_hierarchy import propose
    from icstudio.layout_eco import apply
    from icstudio.physical_extraction import measurement_comparison
    from icstudio.analog_debug import comparison_rows
    out=args.output.resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose a new evidence directory.')
    out.mkdir(parents=True,exist_ok=True)
    package=json.loads((args.pdk/'package.json').read_text())
    tech=package['technology'];tech.update(package_root=str(args.pdk.resolve()),package_lock={key:package[key] for key in ('id','revision','files')})
    p,cid,key=reference(tech)
    plan=p['test_plans'][0]
    conditions=list(itertools.product(plan['corners'],plan['temperatures'],plan['voltages'])) if args.full_pvt else args.conditions
    tools={name:str(Path(shutil.which(getattr(args,name)) or getattr(args,name)).resolve()) for name in ('magic','netgen','ngspice')}
    definitions=digest(p['testbenches'])
    report=dict(schema=1,status='running',conditions=conditions,extraction=args.extraction,phases=[],
        requirements_sha256=definitions,process_lock={k:package[k] for k in ('id','revision')},
        implementation_sha256={name:file_digest(ROOT/name) for name in [
            'scripts/qualify_two_stage_opamp.py','icstudio/two_stage_opamp.py','icstudio/two_stage_opamp_layout.py',
            'icstudio/testbenches.py','icstudio/saved_bench_diagnostics.py','icstudio/saved_bias.py','icstudio/analog_diagnostics.py',
            'icstudio/engines.py','icstudio/hierarchical_flow.py','icstudio/physical_extraction.py',
            'icstudio/distributed_rc.py','icstudio/sky130_layout.py','icstudio/sky130_devices.py',
            'icstudio/magic_rc.py','icstudio/silicon_flow.py','icstudio/external_tools.py']},
        scope='Only the listed conditions and exact two-stage reference. External ideal bias current; process parasitics follow the recorded extraction deck. No silicon correlation or foundry signoff.')
    def publish():atomic_write(out/'report.json',json.dumps(report,indent=2,allow_nan=False))
    def qualify(project,name):
        directory=out/name
        save_project(project,directory/'design.icproj')
        phase=dict(name=name,design_hash=digest(project),cases=[],status='running')
        report['phases'].append(phase);publish()
        physical=run(project,key,directory/'physical',tools,physical_extraction={'mode':args.extraction},
                     progress=lambda _,message:print(name+': '+message,flush=True))
        phase['physical']=dict(status=physical['status'],report=str((directory/'physical/report.json').relative_to(out)),error=physical.get('error'))
        if physical['status']!='passed':
            phase['status']='failed';publish();return False
        source=directory/'physical/parasitics/extracted.spice'
        from icstudio.sky130_flow import subcircuit
        ports,_,_=subcircuit(source.read_text(),next(c['name'] for c in project['cells'] if c['id']==cid))
        source_hash=file_digest(source)
        def case(index,bench_id,condition):
            q=clone(project);t=next(t for t in q['testbenches'] if t['id']==bench_id)
            corner,temp,voltage=condition;t['analysis'].update(corner=corner,temperature=temp)
            fixture=next(c for c in q['cells'] if c['id']==t['bench_cell'])
            next(d for d in fixture['devices'] if d['name']=='VDD')['value']=str(voltage)
            work=directory/'cases'/f'{index:04d}'
            row=dict(index=index,testbench=t['name'],condition=dict(corner=corner,temperature=temp,voltage=voltage),status='failed')
            try:
                before=simulate(q,t,tools['ngspice'],work/'schematic')
                after=simulate(q,t,tools['ngspice'],work/'post-layout',source,ports)
                row['measurements']=measurement_comparison(before['measurements']['measurements'],after['measurements']['measurements'])
                row['requirements']=comparison_rows({'stages':[dict(name=stage,evidence=dict(measurements=wave['measurements']['measurements'],specifications=wave.get('specifications',[]))) for stage,wave in [('schematic_simulation',before),('post_layout_simulation',after)]]})
                row['diagnostics']={}
                for stage,wave in [('schematic',before),('post-layout',after)]:
                    diagnostic=clone(wave.get('diagnostics'))
                    if diagnostic and 'contributors' in diagnostic:
                        contributors=diagnostic.pop('contributors')
                        diagnostic.update(contributor_count=len(contributors),largest_contributors=contributors[:12])
                    row['diagnostics'][stage]=diagnostic
                row['waveforms']={stage:dict(path=str((work/stage/'result.json').relative_to(out)),sha256=file_digest(work/stage/'result.json')) for stage in ('schematic','post-layout')}
                passed=all(wave['measurements']['status']=='passed' and all(s['status']=='PASS' for s in wave.get('specifications',[])) for wave in (before,after))
                row['status']='passed' if passed else 'failed'
            except Exception as exc:row['error']=str(exc)
            return row
        jobs=[(index,t['id'],condition_) for index,(t,condition_) in enumerate(itertools.product(project['testbenches'],conditions),1)]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(case,*job) for job in jobs]
            for future in as_completed(futures):
                row=future.result();phase['cases'].append(row);phase['cases'].sort(key=lambda value:value['index']);publish()
                print(name+': '+row['testbench']+' '+str(row['condition'])+' '+row['status'],flush=True)
        if file_digest(source)!=source_hash:raise ValueError('Extracted DUT changed during the PVT campaign.')
        preflight=physical['stages'][0]['evidence']
        verify_integrity(directory/'physical',physical['provenance']['files'],preflight['assets'],preflight['tools'])
        phase['status']='passed' if all(row['status']=='passed' for row in phase['cases']) else 'failed'
        publish();return phase['status']=='passed'
    try:
        generate_layout(p,cid)
        initial=qualify(p,'initial')
        if not initial:
            report['status']='failed';return 1
        history=History(p)
        original_ids=[d['id'] for c in p['cells'] for d in c['devices']]
        def resize(project):
            for d in next(c for c in project['cells'] if c['id']==cid)['devices']:
                if d['name'] in ('M1','M2'):d['params']['l']='1.1u'
        history.commit(resize,'Resize matched input pair to L=1.1um')
        selection=[(cid,d['id']) for d in next(c for c in history.project['cells'] if c['id']==cid)['devices'] if d['name'] in ('M1','M2')]
        candidate,change=propose(history.project,cid,selection,strict_constraints=True)
        history.commit(lambda project:apply(project,candidate,change),'Update matched input-pair layout')
        if digest(history.project['testbenches'])!=definitions:raise ValueError('ECO changed the saved verification requirements.')
        if [d['id'] for c in history.project['cells'] for d in c['devices']]!=original_ids:raise ValueError('ECO replaced logical device identities.')
        atomic_write(out/'eco.json',json.dumps(change,indent=2,allow_nan=False))
        report['eco']=dict(device_ids_preserved=True,requirements_preserved=True,change='M1/M2 L:1um→1.1um',report='eco.json')
        report['status']='passed' if qualify(history.project,'after-eco') else 'failed'
        return 0 if report['status']=='passed' else 1
    except Exception as exc:
        report.update(status='failed',error=str(exc));raise
    finally:
        changed=[name for name,checksum in report['implementation_sha256'].items()
                 if not (ROOT/name).is_file() or file_digest(ROOT/name)!=checksum]
        report['implementation_integrity']=dict(status='failed' if changed else 'passed',changed=changed)
        if changed:report.update(status='failed',error='Implementation sources changed during qualification: '+', '.join(changed))
        publish()
        atomic_write(out/'summary.json',json.dumps(summarize(out,report),indent=2,allow_nan=False))
        if changed:raise ValueError(report['error'])


if __name__=='__main__':raise SystemExit(main())
