"""Saved-testbench physical verification over a selected circuit hierarchy."""
from pathlib import Path
import json,re,shutil
from .model import clone,validate,design_digest,digest,file_digest,now,atomic_write,save_project
from .testbenches import get,native_subcircuit,simulate
from .physical_cells import reachable,audit,ports
from .silicon_flow import STAGES,magic_script
from .engines import execute,netgen_lvs,tcl_word,require_lvs_match
from .sky130_flow import subcircuit

VERIFICATION_STAGES = [*STAGES, 'integrity']


def verify_integrity(directory, files, assets, tools):
    """Re-read evidence after simulation so a changing input cannot pass a report."""
    directory=Path(directory)
    if any(not Path(f).is_file() or file_digest(Path(f))!=sha for f,sha in assets.items()):
        raise ValueError('Physical technology changed during verification.')
    if any(not (directory/name).is_file() or file_digest(directory/name)!=sha for name,sha in files.items()):
        raise ValueError('Physical extraction or input evidence changed during verification.')
    if any(not Path(info['path']).is_file() or file_digest(Path(info['path']))!=info['sha256'] for info in tools.values()):
        raise ValueError('A physical verification executable changed during verification.')
    return {'files':clone(files),'assets':clone(assets),'tools':clone(tools),'verified':True}


def record_stage(report,name,fn,publish,progress):
    row={'name':name,'status':'running'};report['stages'].append(row);publish();progress(len(report['stages'])/len(VERIFICATION_STAGES),name.replace('_',' '))
    try:row['evidence']=fn();row['status']='passed'
    except InterruptedError:raise
    except Exception as e:row['status']='failed';row['error']=str(e);raise
    finally:publish()
    return row['evidence']


def run(p,testbench,output,tools,progress=lambda *_:None,physical_extraction=None):
    out=Path(output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose a new or empty verification directory.')
    out.mkdir(parents=True,exist_ok=True);t=clone(get(p,testbench));cid=t['dut_cell'];by={c['id']:c for c in p['cells']};c=by[cid]
    report={'schema':2,'app_version':__import__('icstudio').__version__,'created':now(),'status':'running','cell_id':cid,'cell_name':c['name'],'testbench_id':t['id'],'testbench_name':t['name'],'testbench':t,'design_hash':design_digest(p),'revision':p['revision'],'stages':[],'qualification':'Saved-testbench process verification. Qualification applies only to the recorded circuit, extraction model and operating condition; no fabrication signoff.'};resolved={};assets={};generated={};choice={}
    def publish():atomic_write(out/'report.json',json.dumps(report,indent=2,allow_nan=False))
    def stage(name,fn):
        return record_stage(report,name,fn,publish,progress)
    def preflight():
        validate(p)
        from .physical_extraction import normalize_extraction
        choice.update(normalize_extraction(physical_extraction if physical_extraction is not None else t.get('physical_extraction')))
        report['physical_extraction']=clone(choice)
        report['qualification'] += {'capacitance':' Process capacitance only; no distributed resistance.',
                                   'rc':' Process distributed RC uses the recorded Magic profile and technology deck.',
                                   'calibrated_rc':' Coupon-calibrated Manhattan interconnect on LVS-matched schematic devices; ideal pads, no device extraction, cross-layer coupling or field-solver qualification.'}[choice['mode']]
        if choice['mode']=='calibrated_rc':
            from .physical_extraction import calibrated_network
            # Fail unsupported geometry or missing calibration before expensive engines.
            calibrated_network(p,cid,choice,t['analysis'].get('corner','nominal'))
        fixture=by[t['bench_cell']]
        report['conditions']={'model_corner':t['analysis'].get('corner','nominal'),
                              'temperature':t['analysis'].get('temperature',27),
                              'analysis':clone(t['analysis']),
                              'sources':[{k:clone(d[k]) for k in ('name','kind','value','source','nets') if k in d}
                                         for d in fixture['devices'] if d['kind'] in ('V','I')]}
        from .process_adapters import physical_adapter
        process=physical_adapter(p['pdk'])
        from .process_adapters import ADAPTERS
        style=p['pdk'].get('interoperability',{}).get('tools',{}).get('magic',{}).get('drc_style','drc(full)' if process.id in ADAPTERS else None)
        if not isinstance(style,str) or not style:raise ValueError('Declare the Magic drc_style in this PDK interoperability contract before saved-bench verification.')
        report['magic_drc_style']=style
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
        return {'assets':locks,'tools':{n:{'path':v,'sha256':file_digest(v),'version_file':n+'-version.log','version_sha256':file_digest(out/(n+'-version.log'))} for n,v in resolved.items()},'corner':t['analysis'].get('corner','nominal'),'electrical_cells':[by[i]['name'] for i in reachable(p,cid)],'physical_cells':[by[i]['name'] for i in reachable(p,cid,True)],'connection_findings':len(findings)}
    try:
        stage('preflight',preflight)
        physical=clone(p);physical.pop('testbenches',None);physical.pop('test_plans',None);physical['top']=cid;physical['cells']=[clone(by[key]) for key in reachable(p,cid,True)]
        from .interchange import export_layout
        export_layout(physical,out/'layout.gds');atomic_write(out/'schematic.spice',native_subcircuit(p,cid))
        generated.update({name:file_digest(out/name) for name in ('layout.gds','schematic.spice','input.icproj','testbench.json')})
        def simulation(directory,source,interface=None):
            r=simulate(p,t,resolved['ngspice'],out/directory,source,interface);m=r['measurements'];m.update(specifications=r.get('specifications',[]),waveform_file=directory+'/result.json',waveform_sha256=file_digest(out/directory/'result.json'));report['stages'][-1]['evidence']=m
            if m['status']!='passed':raise ValueError('; '.join(i['name']+': '+i.get('error','failed') for i in m['measurements'] if i['status']!='passed'))
            return m
        stage('schematic_simulation',lambda:simulation('schematic',out/'schematic.spice'))
        setup=''
        for key in reachable(p,cid,True):
            if key==cid:continue
            child=by[key];setup+='load '+tcl_word(child['name'])+'\nselect top cell\nbox values 0 0 0 0\n'
            for i,port in enumerate(child['ports'],1):setup+='if {![port '+tcl_word(port)+' exists]} {error '+tcl_word('Missing child port '+child['name']+'.'+port)+'}\nport '+tcl_word(port)+' index '+str(i)+'\n'
        def magic(name,commands):return magic_script(resolved['magic'],assets['technology'],out/'layout.gds',c['name'],c['ports'],out/name,commands,setup)
        def drc():
            commands='drc style '+tcl_word(report['magic_drc_style'])+'\ndrc ignore none\ndrc check\ndrc catchup\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\n'
            commands+='set f [open findings.tsv w]\nforeach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\nputs "STUDIO_MAGIC_SCALE [cif scale out]"\n'
            commands+='set nav [open navigation.tsv w]\n'
            for key in reachable(p,cid,True):
                name=tcl_word(by[key]['name'])
                commands+='load '+name+'\nselect top cell\ndrc catchup\nset cellname '+name+'\n'
                commands+='foreach {reason boxes} [drc listall why] {foreach coords $boxes {puts $nav "$cellname\\t[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]\\t[cif scale out]"}}\nsave '+name+'\n'
            commands+='close $nav\n'
            log=magic('drc',commands);counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)
            if len(counts)!=1 or re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)!=[report['magic_drc_style']]:raise ValueError('Magic did not report an unambiguous result for the declared DRC style.')
            report['drc_count']=int(counts[0])
            if report['drc_count']:raise ValueError(str(report['drc_count'])+' Magic DRC violations; see findings.tsv.')
            return {'violations':0,'style':report['magic_drc_style'],'log':'drc/console.log'}
        stage('drc',drc)
        def extract(name,cap=False):
            from .external_tools import extraction_commands
            selected=choice['mode'] if cap else 'lvs'
            if selected=='calibrated_rc':
                from .physical_extraction import calibrated_network
                network,extracted=calibrated_network(p,cid,choice,t['analysis'].get('corner','nominal'))
                atomic_write(out/name/'network.json',json.dumps(network,indent=2,allow_nan=False))
                atomic_write(out/name/'extracted.spice',native_subcircuit(extracted,cid))
                generated[name+'/network.json']=file_digest(out/name/'network.json')
                profile={**choice,'corner':network['corner'],'coefficient_hash':network['coefficient_hash'],
                         'network_hash':network['network_hash'],'calibration':network['calibration'],
                         'qualification':network['qualification']}
                report['conditions']['rc_corner']=network['corner']
            else:
                commands,profile=extraction_commands(selected)
                magic(name,commands+'ext2spice -o extracted.spice')
            atomic_write(out/name/'profile.json',json.dumps(profile,indent=2))
            f=out/name/'extracted.spice';text=f.read_text();interface,_,_=subcircuit(text,c['name'])
            from .external_tools import check_extracted_interface
            check_extracted_interface(f,c['name'],c['ports'],p['pdk'])
            caps=len(re.findall(r'^C\S+\s',text,re.I|re.M))
            resistors=len(re.findall(r'^R\S+\s',text,re.I|re.M))
            if cap and not caps:raise ValueError('No parasitic capacitor declarations were extracted.')
            if selected=='rc':
                baseline=next(s['evidence']['resistors'] for s in report['stages'] if s['name']=='lvs_extraction')
                if resistors<=baseline:raise ValueError('Process RC extraction added no distributed resistors. Check the Magic technology resistance model or explicitly choose capacitance extraction.')
            generated.update({name+'/'+part:file_digest(out/name/part) for part in ('extracted.spice','profile.json')})
            return {'deck':name+'/extracted.spice','sha256':file_digest(f),'capacitors':caps,'resistors':resistors,
                    'mode':selected,'profile':profile,'profile_file':name+'/profile.json',
                    'profile_sha256':generated[name+'/profile.json'],'subcircuits':re.findall(r'^\.subckt (\S+)',text,re.M|re.I)}
        stage('lvs_extraction',lambda:extract('lvs-extraction'))
        def lvs():
            log=netgen_lvs(resolved['netgen'],out/'schematic.spice',c['name'],out/'lvs-extraction/extracted.spice',c['name'],assets['setup'],out/'lvs')
            require_lvs_match(log)
            return {'unique_match':True,'log':'lvs/lvs.log'}
        stage('lvs',lvs);stage('capacitance_extraction',lambda:extract('parasitics',True))
        interface,_,_=subcircuit((out/'parasitics/extracted.spice').read_text(),c['name']);stage('post_layout_simulation',lambda:simulation('post-layout',out/'parasitics/extracted.spice',interface))
        def integrity():
            from .pdks import model_lines
            model_lines(p['pdk'],t['analysis'].get('corner','nominal'))
            preflight=report['stages'][0]['evidence']
            evidence=verify_integrity(out,generated,preflight['assets'],preflight['tools'])
            failed_specs=[m for s in report['stages'] for m in s.get('evidence',{}).get('specifications',[]) if m['status']!='PASS']
            if failed_specs:raise ValueError('Saved design specifications failed: '+', '.join(m['name'] for m in failed_specs))
            return evidence
        stage('integrity',integrity)
        report['status']='passed'
    except InterruptedError:raise
    except Exception as e:
        report['status']='blocked' if not report['stages'] or report['stages'][-1]['name']=='preflight' else 'failed';report['error']=str(e)
        for name in VERIFICATION_STAGES:
            if name not in {s['name'] for s in report['stages']}:report['stages'].append({'name':name,'status':'not_run'})
    finally:
        from .analog_debug import comparison_rows
        report['requirement_comparison']=comparison_rows(report)
        # Retain comparable values even when a post-layout measurement exceeds a limit.
        measured={s['name']:s.get('evidence',{}).get('measurements',[]) for s in report['stages']}
        before={m['name']:m for m in measured.get('schematic_simulation',[])}
        after={m['name']:m for m in measured.get('post_layout_simulation',[])}
        from .physical_extraction import measurement_comparison
        report['measurement_comparison']=measurement_comparison(list(before.values()),list(after.values()))
        # Existing waveform/review consumers format numeric pairs directly.
        # Keep missing measurements in the complete comparison and stage evidence.
        report['comparison']=[row for row in report['measurement_comparison'] if row['before'] is not None and row['after'] is not None]
        report['provenance']={'design_hash':design_digest(p),'revision':p['revision'],'pdk_hash':digest(p['pdk']),
                              'testbench_hash':digest(t),'extraction_hash':digest(choice),'files':generated}
        try:
            from .verification_navigation import collect
            report['findings']=collect(p,cid,out)
            atomic_write(out/'navigation.json',json.dumps(report['findings'],indent=2))
        except Exception as exc:report['navigation_warning']='Could not index all findings: '+str(exc)
        publish()
    return report
