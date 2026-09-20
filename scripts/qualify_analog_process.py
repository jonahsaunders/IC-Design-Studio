"""Pinned SKY130 analog references: PVT, independent decks and real physical faults."""
import argparse
import json
import shutil
import sys
import traceback
import subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest,atomic_write,save_project,scalar
from icstudio.analog import reference
from icstudio.analog_bank import generate
from icstudio.hierarchical_flow import run
from icstudio.testbenches import simulate
from icstudio.sky130_layout import layers
from qualify_layout_process import accept_result


# Independent hand-written circuit topology and dimensions, in the model's µm units.
REFERENCES={
    'current_mirror': ('IREF OUT VSS', [('a','IREF IREF VSS VSS','n',10),('b','OUT IREF VSS VSS','n',10)]),
    'differential_pair': ('INP INN OUTP OUTN TAIL VSS', [('a','OUTP INP TAIL VSS','n',10),('b','OUTN INN TAIL VSS','n',10)]),
    'amplifier': ('INP INN OUT BIAS VDD VSS', [('a','NREF INP TAIL VSS','n',10),('b','OUT INN TAIL VSS','n',10),
        ('c','NREF NREF VDD VDD','p',10),('d','OUT NREF VDD VDD','p',10),('e','TAIL BIAS VSS VSS','n',5)])}
DEFAULT_CONDITIONS=[('nominal',27),('ss',27),('ff',27),('nominal',0),('nominal',85)]


def condition(text):
    try:
        corner,temperature=text.split(':');temperature=scalar(temperature)
    except (ValueError,TypeError):raise argparse.ArgumentTypeError('Use CORNER:TEMPERATURE, for example nominal:27.')
    if corner not in ('nominal','tt','ss','ff','sf','fs') or temperature<=-273.15:
        raise argparse.ArgumentTypeError('Choose a deterministic process corner and temperature above absolute zero.')
    return corner,int(temperature) if temperature.is_integer() else temperature


def independent(kind):
    ports,devices=REFERENCES[kind]
    return '.subckt '+kind+' '+ports+'\n'+'\n'.join('X'+name+' '+nets+' sky130_fd_pr__'+pol+'fet_01v8 w='+str(w)+' l=1 nf=1' for name,nets,pol,w in devices)+'\n.ends '+kind+'\n'


def check_equivalent(native,other):
    if native['measurements']['status']!='passed' or other['measurements']['status']!='passed':
        raise ValueError('A reference measurement failed: '+str([native['measurements'],other['measurements']]))
    left=native['measurements']['measurements'];right=other['measurements']['measurements']
    if len(left)!=len(right) or len({r['name'] for r in left})!=len(left):
        raise ValueError('Independent reference measurement identities are incomplete or duplicated.')
    errors=[]
    for a,b in zip(left,right):
        if a['name']!=b['name'] or abs(a['value']-b['value'])>max(1e-10,abs(b['value'])*1e-4):
            errors.append(dict(name=a['name'],native=a['value'],independent=b['value']))
    if errors:raise ValueError('Independent netlist mismatch: '+str(errors))


def qualification_case(project,bench_id,corner,temperature,directory,tools,deck=None):
    """Run one isolated case; the caller owns qualification reporting."""
    try:
        q=clone(project);bench=next(t for t in q['testbenches'] if t['id']==bench_id)
        bench['analysis'].update(corner=corner,temperature=temperature)
        if deck is None:return run(q,bench_id,directory,tools)
        result=simulate(q,bench,tools['ngspice'],directory/'native')
        other=simulate(q,bench,tools['ngspice'],directory/'independent',deck)
        check_equivalent(result,other)
        return dict(status='passed',measurements=result['measurements'])
    except Exception as exc:return dict(status='failed',error=str(exc))


def qualification_results(jobs,workers):
    """Yield completed cases without allowing workers to mutate report rows."""
    if workers==1:
        for item,args in jobs:yield item,qualification_case(*args)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(qualification_case,*args):item for item,args in jobs}
        for future in as_completed(pending):yield pending[future],future.result()


def implementation_sources():
    paths=list((ROOT/'icstudio').rglob('*.py'))+[ROOT/'scripts'/name for name in
        ('qualify_analog_process.py','qualify_process_rc.py','qualify_layout_process.py')]
    return {str(path.relative_to(ROOT)):file_digest(path) for path in sorted(paths)}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pdk',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--extraction',choices=('capacitance','rc'),default='capacitance')
    ap.add_argument('--circuits',nargs='+',choices=list(REFERENCES),default=list(REFERENCES))
    ap.add_argument('--conditions',nargs='+',type=condition,default=DEFAULT_CONDITIONS)
    ap.add_argument('--workers',type=int,choices=range(1,9),default=1,help='Concurrent independent cases per circuit (default: 1).')
    for name in ('magic','netgen','ngspice'):ap.add_argument('--'+name,default=shutil.which(name))
    a=ap.parse_args();out=a.out.resolve()
    if out.exists() and any(out.iterdir()):ap.error('Use an empty evidence directory.')
    out.mkdir(parents=True,exist_ok=True);report=dict(status='running',cases=[],extraction=a.extraction,workers=a.workers,
        circuits=list(dict.fromkeys(a.circuits)),conditions=list(dict.fromkeys(a.conditions)),
        scope='Only the listed single-finger references and conditions; '+
              ('actual process distributed RC, independent metal1 coupon and stale-evidence rejection.' if a.extraction=='rc' else 'extracted capacitance only.'))
    report['source']={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                     'files':{f:file_digest(ROOT/f) for f in ('scripts/qualify_analog_process.py','scripts/qualify_process_rc.py','icstudio/hierarchical_flow.py','icstudio/external_tools.py')}}
    source_files=implementation_sources();atomic_write(out/'source-files.json',json.dumps(source_files,indent=2))
    report['source'].update(implementation_sha256=digest(source_files),manifest='source-files.json',
                            manifest_sha256=file_digest(out/'source-files.json'))
    def publish():atomic_write(out/'qualification.json',json.dumps(report,indent=2))
    try:
        lock=json.loads((ROOT/'examples/sky130-qualification-lock.json').read_text());manifest=a.pdk/'package.json'
        if file_digest(manifest)!=lock['manifest_sha256']:raise ValueError('Pinned adapter manifest differs.')
        m=json.loads(manifest.read_text());root=a.pdk.resolve()
        for relative,expected in m['files'].items():
            path=(root/relative).resolve()
            if not path.is_relative_to(root) or file_digest(path)!=expected:raise ValueError('Locked asset differs: '+relative)
        tech=m['technology'];tech.update(package_root=str(root),package_lock=dict(id=m['id'],revision=m['revision'],files=m['files']))
        tools={name:getattr(a,name) for name in ('magic','netgen','ngspice')}
        if any(not path or not Path(path).is_file() for path in tools.values()):raise ValueError('Install Magic, Netgen and ngspice before qualification.')
        from icstudio.engines import execute
        pinned=json.loads((ROOT/'examples/physical-engine-lock.json').read_text());report['tools']={}
        for name,path in tools.items():
            version=execute([path,'-batch' if name=='netgen' else '--version'],out,timeout=20)
            atomic_write(out/(name+'-version.log'),version)
            if name in pinned and pinned[name]['version'] not in version:
                raise ValueError('Use the pinned '+name+' '+pinned[name]['version']+' build for qualification.')
            report['tools'][name]={'path':str(Path(path).resolve()),'sha256':file_digest(path),
                                   'version_file':name+'-version.log','version_sha256':file_digest(out/(name+'-version.log'))}
        report['process']=dict(id=m['id'],revision=m['revision'],manifest_sha256=file_digest(manifest))
        if a.extraction=='rc':
            from qualify_process_rc import coupon_probe
            item=dict(name='metal1-independent-rc-coupon',type='independent_rc_reference',status='running');report['cases'].append(item);publish()
            try:item.update(status='passed',evidence=coupon_probe(tech,tools,out/'metal1-rc-coupon'))
            except Exception as exc:item.update(status='failed',error=str(exc))
            publish()
        for kind in report['circuits']:
            p,cid,key=reference(tech,kind);generate(p,cid)
            for bench in p['testbenches']:bench['physical_extraction']={'mode':a.extraction}
            save_project(p,out/(kind+'.icproj'))
            deck=out/(kind+'-independent.spice');atomic_write(deck,independent(kind))
            jobs=[]
            for corner,temp in report['conditions']:
                for original in p['testbenches']:
                    name=f"{original['name']}-{corner}-{temp}";folder=out/name
                    item=dict(name=name,status='running',type='independent_simulation')
                    jobs.append((item,(p,original['id'],corner,temp,folder,tools,deck)))
            # RC is qualified at every selected PVT condition, through all stages.
            physical_conditions=report['conditions'] if a.extraction=='rc' else [('nominal',27)]
            for corner,temp in physical_conditions:
                for original in p['testbenches']:
                    name=original['name']+'-physical'+(f'-{corner}-{temp}' if a.extraction=='rc' else '')
                    item=dict(name=name,type='physical',status='running',engine_report=name+'/report.json',condition={'corner':corner,'temperature':temp})
                    jobs.append((item,(p,original['id'],corner,temp,out/name,tools)))
            # Register in the original order, regardless of completion order.
            report['cases'].extend(item for item,_ in jobs);publish();retained_results={}
            for item,result in qualification_results(jobs,a.workers):
                if item['type']=='independent_simulation':item.update(result)
                else:
                    item['status']=result['status']
                    if result.get('error'):item['error']=result['error']
                    if a.extraction=='rc' and result['status']=='passed':
                        from qualify_process_rc import process_evidence
                        try:
                            item['evidence']=process_evidence(result,out/item['name'])
                            retained_results[item['name']]=(result,out/item['name'])
                        except Exception as exc:item.update(status='failed',error=str(exc))
                publish()
            # Preserve the serial probe's last accepted case deterministically.
            retained=None
            for item,_ in jobs:
                if item['name'] in retained_results:retained=retained_results[item['name']]
            if a.extraction=='rc' and retained:
                from qualify_process_rc import stale_evidence_probe
                name=kind+'-stale-extraction';item=dict(name=name,type='deliberate_stale_evidence',status='running')
                try:item.update(stale_evidence_probe(*retained,out/name))
                except Exception as exc:item.update(status='failed',error=str(exc))
                report['cases'].append(item);publish()
            for fault in ('narrow-metal','route-open','wrong-channel-length')+(('route-short',) if a.extraction=='rc' else ()):
                q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);ls=layers(tech)
                if fault=='narrow-metal':
                    from icstudio.layout import rect
                    c['shapes'].append(rect(ls['m1'],-12000,0,100,100));stage='drc'
                elif fault=='route-open':
                    from icstudio.physical import erase
                    # A cut in the mirror's VSS bus is still connected through
                    # substrate taps. Cut a signal shared across the pair.
                    net={'current_mirror':'IREF','differential_pair':'TAIL','amplifier':'NREF'}[kind]
                    y=c['analog_bank']['buses'][net];erase(c,ls['m2'],[10000,y-400,11000,y+400]);stage='lvs'
                elif fault=='route-short':
                    from icstudio.layout import rect
                    # Bridge two otherwise separate metal2 buses; a setup failure
                    # or DRC error is not accepted as evidence of LVS detection.
                    first,second=list(c['analog_bank']['buses'].values())[:2]
                    c['shapes'].append(rect(ls['m2'],-4000,first-170,340,second-first+340));stage='lvs'
                else:
                    shape=next(s for s in c['shapes'] if s['layer']==ls['poly'] and s.get('generated_device'));shape['points'][1][0]+=50;stage='lvs'
                name=kind+'-'+fault;result=run(q,key,out/name,tools)
                if fault=='route-short':
                    from qualify_process_rc import accept_short_result
                    accepted=accept_short_result(result,out/name);stage='lvs_extraction_or_lvs'
                else:accepted=accept_result(result,stage,out/name)
                report['cases'].append(dict(name=name,type='deliberate_fault',expected_failure_stage=stage,status='passed' if accepted else 'failed',observed_status=result['status'],error=result.get('error'),engine_report=name+'/report.json'));publish()
        final_sources=implementation_sources()
        report['source'].update(final_implementation_sha256=digest(final_sources),verified_unchanged=final_sources==source_files)
        if final_sources!=source_files:raise ValueError('Qualification implementation changed while engines were running; rerun with frozen source.')
        report['status']='passed' if all(c['status']=='passed' for c in report['cases']) else 'failed'
    except Exception as exc:report.update(status='failed',error=str(exc),traceback=traceback.format_exc())
    publish();print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
