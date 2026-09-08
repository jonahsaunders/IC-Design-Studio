"""Verify the active custom SKY130 inverter, retaining independent engine evidence."""
from pathlib import Path
import json,re,shutil
from .model import clone,digest,design_digest,file_digest,now,atomic_write,save_project,uid,device,validate
from .engines import execute,tcl_word,netgen_lvs,run_ngspice,run_deck,require_lvs_match
from .sky130_flow import subcircuit,logic_metrics
from .sky130_layout import inverter_devices,audit

STAGES=['preflight','schematic_simulation','drc','lvs_extraction','lvs','capacitance_extraction','post_layout_simulation']


def testbench(p,cid):
    n,q=inverter_devices(p,cid);out=clone(p);c=next(c for c in out['cells'] if c['id']==cid)
    mapping={n['nets']['g']:'vin',n['nets']['d']:'vout',n['nets']['s']:'0',q['nets']['s']:'vdd'}
    top={'id':uid(),'name':'studio_physical_testbench','ports':[],'shapes':[], 'devices':[
        device('V','VDD',100,100,value='1.8',nets={'p':'vdd','n':'0'}),
        device('V','VIN',100,300,nets={'p':'vin','n':'0'},source={'type':'pulse','low':'0','high':'1.8','period':'20n','delay':'2n','duty':'0.5','ac':'1'}),
        device('X','XDUT',350,200,cell=cid,nets=mapping),device('C','CL',550,200,value='5f',nets={'p':'vout','n':'0'})]}
    out['cells']=[c,top];out['top']=top['id'];out['analysis'].update(type='tran',step='20p',stop='62n',corner=p['analysis'].get('corner','nominal'))
    return validate(out),mapping


def magic_script(executable,technology,gds,cell,ports,directory,commands,setup=""):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    rc=directory/'startup.tcl'
    atomic_write(rc,'tech load '+tcl_word(technology)+'\ndrc euclidean on\n')
    script='gds read '+tcl_word(gds)+'\n'+setup+'load '+tcl_word(cell)+'\nselect top cell\nbox values 0 0 0 0\n'
    # GDS label datatypes carry net names. Give the named interface a stable port order.
    for i,port in enumerate(ports,1):
        word=tcl_word(port)
        script+='if {![port '+word+' exists]} {error '+tcl_word('Missing layout port '+port)+'}\nport '+word+' index '+str(i)+'\n'
    script+=commands+'\nputs STUDIO_MAGIC_COMPLETE\n'
    wrapped='if {[catch {\n'+script+'} err]} {puts stderr "STUDIO_MAGIC_ERROR $err"}\nquit -noprompt\n'
    atomic_write(directory/'run.tcl',wrapped)
    try:log=execute([executable,'-dnull','-noconsole','-rcfile',str(rc)],directory,timeout=240,input_text=wrapped)
    except Exception as e:atomic_write(directory/'console.log',str(e));raise
    atomic_write(directory/'console.log',log)
    if 'STUDIO_MAGIC_COMPLETE' not in log or re.search(r'STUDIO_MAGIC_ERROR|contained errors|Malformed line|Illegal keyword|Error:.*required by this techfile|invalid command name',log,re.I):
        raise ValueError('Magic could not complete the commands. See '+str(directory/'console.log'))
    return log


def run(p,cid,output,tools,progress=lambda *_:None):
    out=Path(output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use an empty physical verification output directory.')
    out.mkdir(parents=True,exist_ok=True)
    report={'schema':1,'created':now(),'status':'running','design_hash':design_digest(p),'cell_id':cid,
            'stages':[], 'qualification':'Custom SKY130 inverter; capacitance extraction only. No distributed interconnect resistance or foundry signoff.'}
    resolved={};assets={};c=next(c for c in p['cells'] if c['id']==cid)
    def publish():atomic_write(out/'report.json',json.dumps(report,indent=2,allow_nan=False))
    def stage(name,fn):
        item={'name':name,'status':'running'};report['stages'].append(item);publish();progress(len(report['stages'])/8,name.replace('_',' '))
        try:item['evidence']=fn();item['status']='passed'
        except InterruptedError:raise
        except Exception as e:item['status']='failed';item['error']=str(e);publish();raise
        publish();return item['evidence']
    def preflight():
        validate(p);inverter_devices(p,cid)
        findings=audit(p,cid)
        if findings:raise ValueError(findings[0]['message'])
        if not c['shapes']:raise ValueError('Generate or import the inverter layout first.')
        from .pdks import model_lines
        model_lines(p['pdk'],p['analysis'].get('corner','nominal'))
        root=Path(p['pdk'].get('package_root','')).resolve()
        for name,rel in [('technology','libs.tech/magic/sky130A.tech'),('setup','libs.tech/netgen/sky130A_setup.tcl')]:
            f=root/rel
            if not f.is_file():raise ValueError('Missing physical PDK asset '+rel+'. Add the full PDK folder in PDK manager and relink it to this project.')
            assets[name]=f
        for name in ('magic','netgen','ngspice'):
            candidate=tools.get(name,'') or name;f=Path(shutil.which(candidate) or candidate)
            if not f.is_file():raise ValueError('Configure the '+name+' executable in Engine diagnostics and paths.')
            resolved[name]=str(f.resolve())
        lock={str(f):file_digest(f) for f in assets.values()}
        atomic_write(out/'physical-assets-lock.json',json.dumps(lock,indent=2))
        for name,exe in resolved.items():
            version=execute([exe,'-batch'] if name=='netgen' else [exe,'--version'],out,timeout=15)
            atomic_write(out/(name+'-version.log'),version)
        save_project(p,out/'input.icproj')
        return {'assets':lock,'tools':{n:{'path':v,'sha256':file_digest(v)} for n,v in resolved.items()},'corner':p['analysis'].get('corner','nominal'),'supply_V':1.8,'load_F':5e-15}
    try:
        stage('preflight',preflight)
        bench,mapping=testbench(p,cid);save_project(bench,out/'testbench.icproj')
        from .interchange import spice,export_layout
        from .pdks import model_lines
        physical=clone(p);physical['cells']=[clone(c)];physical['top']=cid
        export_layout(physical,out/'layout.gds')
        # Export the same catalog devices used by the simulator for LVS.
        _,_,native=subcircuit(spice(bench,hierarchical=True),c['name']);atomic_write(out/'schematic.spice',native)
        def simulate():
            d=out/'schematic';d.mkdir();r=run_ngspice(bench,bench['top'],bench['analysis'],resolved['ngspice'],d)
            atomic_write(d/'result.json',json.dumps(r));return logic_metrics(r)
        pre=stage('schematic_simulation',simulate)
        def magic(name,commands):return magic_script(resolved['magic'],assets['technology'],out/'layout.gds',c['name'],c['ports'],out/name,commands)
        def drc():
            commands='drc style drc(full)\ndrc ignore none\ndrc check\ndrc catchup\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\n'
            commands+='set f [open findings.tsv w]\nforeach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\n'
            commands+='puts "STUDIO_MAGIC_SCALE [cif scale out]"\nsave '+tcl_word(c['name'])
            log=magic('drc',commands);matches=re.findall(r'^STUDIO_DRC_COUNT\s+(\d+)\s*$',log,re.M)
            if len(matches)!=1:raise ValueError('Magic did not report an unambiguous DRC count.')
            count=int(matches[0]);report['drc_count']=count
            if re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)!=['drc(full)']:raise ValueError('Magic did not select the required full DRC style.')
            if count:raise ValueError(f'Magic reports {count} DRC violations. See drc/findings.tsv and drc/console.log.')
            return {'violations':count,'log':'drc/console.log','style':re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)}
        stage('drc',drc)
        def extract(name,cap=False):
            commands='extract all\next2spice lvs\next2spice subcircuit top on\next2spice scale off\n'
            if cap:commands+='ext2spice cthresh 0\n'
            magic(name,commands+'ext2spice -o extracted.spice')
            f=out/name/'extracted.spice';ports,body,_=subcircuit(f.read_text(),c['name'])
            if set(ports)!=set(c['ports']):raise ValueError('Extracted interface differs from schematic ports: '+str(ports))
            caps=len(re.findall(r'^C\S+\s',body,re.I|re.M))
            if cap and not caps:raise ValueError('No parasitic capacitors were extracted.')
            return {'deck':name+'/extracted.spice','sha256':file_digest(f),'capacitors':caps}
        stage('lvs_extraction',lambda:extract('lvs-extraction'))
        def lvs():
            log=netgen_lvs(resolved['netgen'],out/'schematic.spice',c['name'],out/'lvs-extraction/extracted.spice',c['name'],assets['setup'],out/'lvs')
            require_lvs_match(log)
            return {'unique_match':True,'log':'lvs/lvs.log'}
        stage('lvs',lvs);stage('capacitance_extraction',lambda:extract('parasitics',True))
        def post():
            d=out/'post-layout';d.mkdir();f=out/'parasitics/extracted.spice';ports,_,_=subcircuit(f.read_text(),c['name'])
            deck='* Studio custom inverter extracted testbench\n'+'\n'.join(model_lines(p['pdk'],p['analysis'].get('corner','nominal')))+'\n'
            deck+='.include "'+f.as_posix()+'"\nVDD vdd 0 1.8\nVIN vin 0 PULSE(0 1.8 2n 200f 200f 10n 20n)\nXDUT '+' '.join(mapping[k] for k in ports)+' '+c['name']+'\nCL vout 0 5f\n.tran 20p 62n\n.save v(vin) v(vout)\n.end\n'
            atomic_write(d/'testbench.cir',deck);r=run_deck(bench,bench['top'],{'type':'deck','deck':str(d/'testbench.cir')},resolved['ngspice'],d)
            atomic_write(d/'result.json',json.dumps(r));metrics=logic_metrics(r);metrics['delay_delta_s']=metrics['mean_delay_s']-pre['mean_delay_s'];return metrics
        stage('post_layout_simulation',post)
        if any(file_digest(Path(f))!=sha for f,sha in report['stages'][0]['evidence']['assets'].items()):raise ValueError('Physical PDK assets changed during the run.')
        model_lines(p['pdk'],p['analysis'].get('corner','nominal'))
        report['status']='passed'
    except InterruptedError:raise
    except Exception as e:
        report['status']='blocked' if report['stages'][-1]['name']=='preflight' else 'failed';report['error']=str(e)
        for name in STAGES:
            if name not in {s['name'] for s in report['stages']}:report['stages'].append({'name':name,'status':'not_run'})
    finally:publish()
    return report


def job(p,cid,settings,directory,progress):
    output=Path(directory)/'physical-flow'
    if settings.get('testbench'):
        from .hierarchical_flow import run as hierarchical_run
        report=hierarchical_run(p,settings['testbench'],output,settings.get('tools',{}),progress);cid=report['cell_id']
    else:report=run(p,cid,output,settings.get('tools',{}),progress)
    issues=[]
    if report['status']!='passed':issues.append({'severity':'error','code':'PHYSICAL.'+report['status'].upper(),'object':'','message':report.get('error','Physical workflow incomplete'),'fingerprint':digest(report)})
    if 'findings' in report:issues.extend(report['findings'])
    else:
        from .verification_navigation import collect
        issues.extend(collect(p,cid,output))
    return {'schema':1,'created':now(),'project_id':p['id'],'revision':p['revision'],'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']), 'rule_hash':digest(p['pdk']['layers']), 'cell_id':cid,'settings':settings,'engine':'Magic / Netgen / ngspice','engine_hash':digest(report['stages'][0].get('evidence',{})),'x':[],'x_label':'','y_label':'','traces':{},'phase':{},'operating_point':{},'warnings':[report['qualification']], 'physical_result':{'issues':issues,'qualification':report['qualification']},'silicon_report':report,'evidence_directory':str(output)}
