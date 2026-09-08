"""Saved-testbench physical verification over a selected circuit hierarchy."""
from pathlib import Path
import json,re,shutil
from .model import clone,validate,design_digest,file_digest,now,atomic_write,save_project
from .testbenches import get,native_subcircuit,simulate
from .physical_cells import reachable,audit,ports
from .silicon_flow import STAGES,magic_script
from .engines import execute,netgen_lvs,tcl_word,require_lvs_match
from .sky130_flow import subcircuit


def run(p,testbench,output,tools,progress=lambda *_:None):
    out=Path(output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose a new or empty verification directory.')
    out.mkdir(parents=True,exist_ok=True);t=clone(get(p,testbench));cid=t['dut_cell'];by={c['id']:c for c in p['cells']};c=by[cid]
    report={'schema':1,'app_version':__import__('icstudio').__version__,'created':now(),'status':'running','cell_id':cid,'cell_name':c['name'],'testbench_id':t['id'],'testbench_name':t['name'],'testbench':t,'design_hash':design_digest(p),'stages':[],'qualification':'Selected native process circuit hierarchy with a saved electrical testbench. Extracted capacitance only; distributed resistance and fabrication signoff are outside this flow.'};resolved={};assets={}
    def publish():atomic_write(out/'report.json',json.dumps(report,indent=2,allow_nan=False))
    def stage(name,fn):
        row={'name':name,'status':'running'};report['stages'].append(row);publish();progress(len(report['stages'])/8,name.replace('_',' '))
        try:row['evidence']=fn();row['status']='passed'
        except InterruptedError:raise
        except Exception as e:row['status']='failed';row['error']=str(e);raise
        finally:publish()
        return row['evidence']
    def preflight():
        validate(p)
        from .process_adapters import adapter
        process=adapter(p['pdk'])
        errors=audit(p,cid)
        if errors:atomic_write(out/'link-findings.json',json.dumps(errors,indent=2));raise ValueError(errors[0]['message'])
        from .pdks import model_lines
        model_lines(p['pdk'],t['analysis'].get('corner','nominal'))
        assets.update(process.engine_assets(p['pdk']))
        for name in ('magic','netgen','ngspice'):
            candidate=tools.get(name,'') or name;f=Path(shutil.which(candidate) or candidate)
            if not f.is_file():raise ValueError('Configure '+name+' in Engine diagnostics & paths.')
            resolved[name]=str(f.resolve());atomic_write(out/(name+'-version.log'),execute([resolved[name],'-batch'] if name=='netgen' else [resolved[name],'--version'],out,timeout=15))
        save_project(p,out/'input.icproj');atomic_write(out/'testbench.json',json.dumps(t,indent=2));locks={str(f):file_digest(f) for f in assets.values()};atomic_write(out/'physical-assets-lock.json',json.dumps(locks,indent=2))
        from .physical import connectivity
        findings=[]
        for key in reachable(p,cid):findings += [{**i,'cell_id':key} for i in connectivity(p,key)['issues']]
        atomic_write(out/'connection-findings.json',json.dumps(findings,indent=2))
        return {'assets':locks,'tools':{n:{'path':v,'sha256':file_digest(v)} for n,v in resolved.items()},'corner':t['analysis'].get('corner','nominal'),'electrical_cells':[by[i]['name'] for i in reachable(p,cid)],'physical_cells':[by[i]['name'] for i in reachable(p,cid,True)],'connection_findings':len(findings)}
    try:
        stage('preflight',preflight)
        physical=clone(p);physical.pop('testbenches',None);physical['top']=cid;physical['cells']=[clone(by[key]) for key in reachable(p,cid,True)]
        from .interchange import export_layout
        export_layout(physical,out/'layout.gds');atomic_write(out/'schematic.spice',native_subcircuit(p,cid))
        def simulation(directory,source,interface=None):
            r=simulate(p,t,resolved['ngspice'],out/directory,source,interface);m=r['measurements'];m.update(waveform_file=directory+'/result.json',waveform_sha256=file_digest(out/directory/'result.json'));report['stages'][-1]['evidence']=m
            if m['status']!='passed':raise ValueError('; '.join(i['name']+': '+i.get('error','failed') for i in m['measurements'] if i['status']!='passed'))
            return m
        pre=stage('schematic_simulation',lambda:simulation('schematic',out/'schematic.spice'))
        setup=''
        for key in reachable(p,cid,True):
            if key==cid:continue
            child=by[key];setup+='load '+tcl_word(child['name'])+'\nselect top cell\nbox values 0 0 0 0\n'
            for i,port in enumerate(child['ports'],1):setup+='if {![port '+tcl_word(port)+' exists]} {error '+tcl_word('Missing child port '+child['name']+'.'+port)+'}\nport '+tcl_word(port)+' index '+str(i)+'\n'
        def magic(name,commands):return magic_script(resolved['magic'],assets['technology'],out/'layout.gds',c['name'],c['ports'],out/name,commands,setup)
        def drc():
            commands='drc style drc(full)\ndrc ignore none\ndrc check\ndrc catchup\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\n'
            commands+='set f [open findings.tsv w]\nforeach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\nputs "STUDIO_MAGIC_SCALE [cif scale out]"\n'
            commands+='set nav [open navigation.tsv w]\n'
            for key in reachable(p,cid,True):
                name=tcl_word(by[key]['name'])
                commands+='load '+name+'\nselect top cell\ndrc catchup\nset cellname '+name+'\n'
                commands+='foreach {reason boxes} [drc listall why] {foreach coords $boxes {puts $nav "$cellname\\t[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]\\t[cif scale out]"}}\nsave '+name+'\n'
            commands+='close $nav\n'
            log=magic('drc',commands);counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)
            if len(counts)!=1 or re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)!=['drc(full)']:raise ValueError('Magic did not report an unambiguous full DRC result.')
            report['drc_count']=int(counts[0])
            if report['drc_count']:raise ValueError(str(report['drc_count'])+' Magic DRC violations; see findings.tsv.')
            return {'violations':0,'style':'drc(full)','log':'drc/console.log'}
        stage('drc',drc)
        def extract(name,cap=False):
            commands='extract all\next2spice lvs\next2spice hierarchy on\next2spice subcircuit top on\next2spice scale off\next2spice blackbox off\n'
            if cap:commands+='ext2spice cthresh 0\n'
            magic(name,commands+'ext2spice -o extracted.spice')
            f=out/name/'extracted.spice';text=f.read_text();interface,_,_=subcircuit(text,c['name'])
            if len(interface)!=len(c['ports']) or set(interface)!=set(c['ports']):raise ValueError('Extracted circuit ports differ from the saved interface: '+str(interface))
            caps=len(re.findall(r'^C\S+\s',text,re.I|re.M))
            if cap and not caps:raise ValueError('No parasitic capacitor declarations were extracted.')
            return {'deck':name+'/extracted.spice','sha256':file_digest(f),'capacitors':caps,'subcircuits':re.findall(r'^\.subckt (\S+)',text,re.M|re.I)}
        stage('lvs_extraction',lambda:extract('lvs-extraction'))
        def lvs():
            log=netgen_lvs(resolved['netgen'],out/'schematic.spice',c['name'],out/'lvs-extraction/extracted.spice',c['name'],assets['setup'],out/'lvs')
            require_lvs_match(log)
            return {'unique_match':True,'log':'lvs/lvs.log'}
        stage('lvs',lvs);stage('capacitance_extraction',lambda:extract('parasitics',True))
        interface,_,_=subcircuit((out/'parasitics/extracted.spice').read_text(),c['name']);post=stage('post_layout_simulation',lambda:simulation('post-layout',out/'parasitics/extracted.spice',interface))
        report['comparison']=[{'name':a['name'],'unit':a['unit'],'before':a['value'],'after':b['value'],'delta':b['value']-a['value']} for a,b in zip(pre['measurements'],post['measurements']) if 'value' in a and 'value' in b]
        from .pdks import model_lines
        model_lines(p['pdk'],t['analysis'].get('corner','nominal'))
        if any(file_digest(Path(f))!=sha for f,sha in report['stages'][0]['evidence']['assets'].items()):raise ValueError('Physical technology changed during verification.')
        report['status']='passed'
    except InterruptedError:raise
    except Exception as e:
        report['status']='blocked' if not report['stages'] or report['stages'][-1]['name']=='preflight' else 'failed';report['error']=str(e)
        for name in STAGES:
            if name not in {s['name'] for s in report['stages']}:report['stages'].append({'name':name,'status':'not_run'})
    finally:
        # Retain comparable values even when a post-layout measurement exceeds a limit.
        measured={s['name']:s.get('evidence',{}).get('measurements',[]) for s in report['stages']}
        before={m['name']:m for m in measured.get('schematic_simulation',[])}
        after={m['name']:m for m in measured.get('post_layout_simulation',[])}
        report['comparison']=[{'name':name,'unit':a.get('unit',''),'before':a['value'],'after':after[name]['value'],
                               'delta':after[name]['value']-a['value'],'before_status':a['status'],'after_status':after[name]['status']}
                              for name,a in before.items() if 'value' in a and 'value' in after.get(name,{})]
        try:
            from .verification_navigation import collect
            report['findings']=collect(p,cid,out)
            atomic_write(out/'navigation.json',json.dumps(report['findings'],indent=2))
        except Exception as exc:report['navigation_warning']='Could not index all findings: '+str(exc)
        publish()
    return report
