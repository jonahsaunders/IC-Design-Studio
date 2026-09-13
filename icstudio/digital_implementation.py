"""Mapped implementation, timing and equivalence on immutable worker inputs."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .model import atomic_write, clone, design_digest, digest, file_digest, now
from .digital_design import config as cell_config


def logic_identity(config):
    return digest({'top':config['top'],'files':[f for f in config['files'] if f['role'] in ('rtl','include','data')],
                   'include_dirs':config.get('include_dirs',['.']),'defines':config.get('defines',{}),
                   'platform':{k:config.get('platform',{}).get(k) for k in ('fingerprint','corner')}})


def capture_upstream(project,cid,directory):
    from .job_store import read_result
    root=Path(directory).resolve();result=read_result(root/'result.json',project['id'])
    if result['cell_id']!=cid:raise ValueError('The upstream result belongs to a different cell.')
    data=result['digital_result']
    if data.get('logic_hash')!=logic_identity(cell_config(project,cid)):
        raise ValueError('RTL, definitions or technology changed. Run mapped synthesis for the current inputs.')
    if 'netlist' not in data['artifacts'] or not data.get('mapped'):raise ValueError('Choose a technology-mapped upstream result.')
    return {'root':str(root),'result_sha256':file_digest(root/'result.json'),'logic_hash':data['logic_hash'],
            'source_hash':data['source_hash'],'stage':data['stage'],'artifacts':clone(data['artifacts'])}


def verify_upstream(record):
    root=Path(record['root']).resolve()
    if file_digest(root/'result.json')!=record['result_sha256']:raise ValueError('The upstream result changed after this job was queued.')
    from .digital_flow import validate_result
    result=json.loads((root/'result.json').read_text());validate_result(result,root)
    if record['artifacts']!=result['digital_result']['artifacts']:raise ValueError('The upstream artifact binding changed.')
    return result


def quote(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'


def tcl_word(value):
    from .engines import tcl_word as word
    return word(str(value))


class Runner:
    def __init__(self,job,directory,progress):
        from .digital_flow import environment,stage_sources
        self.job=job;self.config=cell_config(job['project'],job['cell']);self.settings=job['settings'];self.tools=self.settings['tools'];self.progress=progress
        if environment(job)!=job.get('environment'):raise ValueError('The digital toolchain or platform changed. Prepare a new run.')
        self.root=Path(directory).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.sources=self.root/'sources';self.sources.mkdir();stage_sources(self.config,self.sources)
        self.tmp=self.root/'tmp';self.tmp.mkdir();self.log=self.root/'engine.log';atomic_write(self.log,'Digital '+self.settings['stage']+'\n')
        self.env={**os.environ,**{k:str(self.tmp) for k in ('TMPDIR','TMP','TEMP')}}
        self.commands=[];self.artifacts={};self.versions={};self.platform=self.config.get('platform')
        if self.platform:
            from .digital_platform import stage
            stage(self.platform,self.root/'platform')
        from .digital import input_manifest
        atomic_write(self.root/'inputs.json',json.dumps(input_manifest(self.config),indent=2))

    def command(self,args,message,cwd=None,fraction=.2,allow_failure=False):
        from .engines import execute
        cwd=Path(cwd or self.sources)
        self.commands.append({'argv':[str(a) for a in args],'cwd':cwd.relative_to(self.root).as_posix()})
        atomic_write(self.root/'commands.json',json.dumps(self.commands,indent=2));self.progress(fraction,message)
        def line(text):
            with self.log.open('a',encoding='utf-8') as output:output.write(text+'\n')
            self.progress(fraction,text[:1000])
        try:return execute(args,cwd,timeout=self.config.get('timeout',60),on_line=line,env=self.env)
        except (RuntimeError,subprocess.TimeoutExpired) as exc:
            line(str(exc))
            if not allow_failure:raise
            return str(exc)

    def add_artifact(self,key,path):
        from .digital_flow import artifact
        self.artifacts[key]=artifact(self.root,Path(path))

    def save_json(self,key,data,filename):
        atomic_write(self.root/filename,json.dumps(data,indent=2));self.add_artifact(key,self.root/filename)

    def libraries(self):
        return [self.root/'platform'/p for p in self.platform['corners'][self.platform['corner']]]

    def versions_check(self):
        for name,path in self.tools.items():
            flag='-V' if name in ('iverilog','vvp','yosys') else '-version' if name in ('sta','openroad') else '-v' if name=='klayout' else '--version'
            self.versions[name]=self.command([path,flag],'Checking '+name,fraction=.01).strip()[:12000]

    def constraints(self):
        files=[f for f in self.config['files'] if f['role']=='constraint']
        if len(files)!=1:raise ValueError('Mark exactly one SDC source as Constraint.')
        return self.sources/files[0]['path']


def mapped(runner):
    r=runner;upstream=r.settings.get('upstream')
    if upstream:
        verify_upstream(upstream)
        for key,name in (('netlist','netlist.v'),('hierarchy','netlist.json'),('statistics','statistics.json'),('netlist_index','netlist_index.json')):
            if key in upstream['artifacts']:
                shutil.copy2(Path(upstream['root'])/upstream['artifacts'][key]['path'],r.root/name);r.add_artifact(key,r.root/name)
        if 'hierarchy' not in r.artifacts:
            # Physical tools may change names/cells; regenerate a JSON view of that exact netlist.
            script='\n'.join('read_liberty -lib -ignore_miss_func '+quote(p) for p in r.libraries())+'\n'
            script+='read_verilog ../netlist.v\nhierarchy -check -top '+r.config['top']+'\nwrite_json ../netlist.json\ntee -o ../statistics.json stat -json\n'
            atomic_write(r.root/'import_netlist.ys',script);r.command([r.tools['yosys'],'-s',str(r.root/'import_netlist.ys')],'Indexing the captured mapped netlist')
            r.add_artifact('hierarchy',r.root/'netlist.json');r.add_artifact('statistics',r.root/'statistics.json')
    else:
        from .digital_flow import read_rtl
        libs=r.libraries()
        if len(libs)!=1:raise ValueError('Mapped synthesis currently requires one merged Liberty library per corner.')
        script='read_liberty -lib -ignore_miss_func '+quote(libs[0])+'\n'
        script+=read_rtl(r.config)+'\nhierarchy -check -top '+r.config['top']+'\nsynth -noabc -flatten -top '+r.config['top']+'\n'
        # ABC's retained workspace uses short relative paths, including in deeply nested jobs folders.
        script+='dfflibmap -liberty '+quote(libs[0])+'\nabc -nocleanup -liberty '+quote(libs[0])+'\nclean\n'
        if r.platform['name']=='sky130hd':script+='hilomap -singleton -hicell sky130_fd_sc_hd__conb_1 HI -locell sky130_fd_sc_hd__conb_1 LO\n'
        script+='check -assert\nwrite_verilog -noattr ../netlist.v\nwrite_json ../netlist.json\n'
        script+='tee -o ../statistics.json stat -json -liberty '+quote(libs[0])+'\n'
        atomic_write(r.root/'mapped.ys',script);r.command([r.tools['yosys'],'-s',str(r.root/'mapped.ys')],'Mapping '+r.config['top']+' to '+r.platform['name'])
        for key,name in (('netlist','netlist.v'),('hierarchy','netlist.json'),('statistics','statistics.json')):r.add_artifact(key,r.root/name)
    from .digital_reports import netlist_index
    data=json.loads((r.root/'netlist.json').read_text());index=netlist_index(data,r.config['files'])
    r.save_json('netlist_index',index,'netlist_index.json')
    module=data['modules'][r.config['top']]
    unmapped=[name for name,c in module.get('cells',{}).items() if c['type'].startswith('$')]
    if unmapped:raise ValueError('Technology mapping left unsupported cells: '+', '.join(unmapped[:10]))
    stats=json.loads((r.root/'statistics.json').read_text())
    area=stats.get('design',{}).get('area')
    if area is None:
        area=next((m.get('area') for name,m in stats.get('modules',{}).items() if name.lstrip('\\')==r.config['top']),None)
    return {'mapped':True,'statistics':{'cells':len(module.get('cells',{})),'area_um2':area},
            'summary':'Mapped synthesis complete · '+r.platform['name']+' / '+r.platform['corner']}


def timing_script(r):
    lines=['set_cmd_units -time ns -capacitance pF']
    lines += ['read_liberty '+tcl_word(p) for p in r.libraries()]
    lines += ['read_verilog '+tcl_word(r.root/'netlist.v'),'link_design '+r.config['top'],
              'read_sdc '+tcl_word(r.constraints())]
    upstream=r.settings.get('upstream',{})
    if 'spef' in upstream.get('artifacts',{}):
        verify_upstream(upstream);shutil.copy2(Path(upstream['root'])/upstream['artifacts']['spef']['path'],r.root/'parasitics.spef')
        r.add_artifact('spef',r.root/'parasitics.spef');lines.append('read_spef '+tcl_word(r.root/'parasitics.spef'))
        lines.append('set_propagated_clock [all_clocks]')
    lines += ['sta::redirect_file_begin '+tcl_word(r.root/'timing_units.txt'),
              'report_units','sta::redirect_file_end',
              'check_setup -verbose > '+tcl_word(r.root/'timing_checks.txt'),
              'report_checks -path_delay min_max -group_count 50 -format full_clock_expanded > '+tcl_word(r.root/'timing_full.txt'),
              'report_power > '+tcl_word(r.root/'power.txt'),
              'set out [open '+tcl_word(r.root/'timing_paths.tsv')+' w]',
              '''foreach {kind delay} {setup max hold min} {
  foreach path [find_timing_paths -path_delay $delay -group_count 50 -sort_by_slack] {
    set start [get_property [get_property $path startpoint] full_name]
    set end [get_property [get_property $path endpoint] full_name]
    set pins {}
    foreach point [get_property $path points] {lappend pins [get_property [get_property $point pin] full_name]}
    puts $out "$kind\\t$start\\t$end\\t[get_property $path slack]\\t[join $pins |]"
  }
}
close $out''']
    return 'if {[catch {\n'+'\n'.join(lines)+'\n} message]} {puts stderr $message; exit 1}\nexit 0\n'


def timing(r):
    from .digital_reports import timing_report
    data=mapped(r);atomic_write(r.root/'timing.tcl',timing_script(r))
    r.command([r.tools['sta'],'-no_init','-exit',str(r.root/'timing.tcl')],'Analyzing setup and hold timing',fraction=.6)
    report=timing_report(r.root);report['parasitics']='extracted SPEF' if 'spef' in r.artifacts else 'No extracted interconnect; pre-layout estimate'
    r.save_json('timing',report,'timing.json')
    r.add_artifact('timing_full',r.root/'timing_full.txt')
    r.add_artifact('power_report',r.root/'power.txt')
    from .digital_reports import power_report
    data['power']=power_report(r.root/'power.txt')
    upstream=r.settings.get('upstream',{})
    if 'layout_preview' in upstream.get('artifacts',{}):
        verify_upstream(upstream)
        shutil.copy2(Path(upstream['root'])/upstream['artifacts']['layout_preview']['path'],r.root/'layout_preview.json')
        r.add_artifact('layout_preview',r.root/'layout_preview.json')
    return {**data,'timing':report,'verdict':report['status'],'summary':'Timing '+report['status']+' · '+r.platform['corner']+' · '+report['parasitics']}


def equivalence(r):
    from .digital_flow import read_rtl
    from .digital_reports import eqy_report
    data=mapped(r)
    if any(c.isspace() for c in str(r.root)) or any(' ' in f['path'] for f in r.config['files']):
        raise ValueError('EQY requires run and source paths without spaces. Use a space-free jobs folder.')
    gold=read_rtl(r.config)+'\n'
    gate='\n'.join('read_liberty -ignore_miss_func '+quote(p) for p in r.libraries())
    script='[gold]\n'+gold+'prep -top '+r.config['top']+' -flatten\n\n[gate]\n'+gate+'\nread_verilog ../netlist.v\n'
    script+='hierarchy -check -top '+r.config['top']+'\nflatten\ntechmap -autoproc -map +/simcells.v\nprep -top '+r.config['top']+'\n'
    # Encode undefined state explicitly; EQY's SAT strategy can prove this case vacuously.
    script+='\n[strategy smtbmc]\nuse sby\nengine smtbmc bitwuzla\nxprop on\ndepth 30\n'
    atomic_write(r.root/'equivalence.eqy',script)
    r.env['PATH']=str(Path(r.tools['eqy']).parent)+os.pathsep+r.env.get('PATH','')
    r.env['YOSYS']=r.tools['yosys']
    r.command([r.tools['eqy'],'--yosys',r.tools['yosys'],'-f','-d','../proof','../equivalence.eqy'],
              'Proving the captured mapped netlist',fraction=.6,allow_failure=True)
    report=eqy_report(r.root/'proof');r.save_json('equivalence',report,'equivalence.json')
    for name in ('logfile.txt','partition.list','matched.ids'):
        if (r.root/'proof'/name).is_file():r.add_artifact('proof_'+name.replace('.','_'),r.root/'proof'/name)
    for i,name in enumerate(report['counterexamples']):r.add_artifact('counterexample_'+str(i),r.root/'proof'/name)
    if report['status']=='ERROR':raise ValueError('EQY could not complete a proof strategy. Inspect the retained proof logs.')
    return {**data,'equivalence':report,'verdict':report['status'],'summary':'Equivalence '+report['status']+' · captured mapped netlist'}


def run(job,directory,progress):
    from .digital_flow import validate_result
    from .digital import source_hash
    r=Runner(job,directory,progress);r.versions_check();stage=job['settings']['stage']
    if stage=='regression':
        from .digital_regression import execute
        data=execute(r)
    elif stage=='mapped':data=mapped(r)
    elif stage=='timing':data=timing(r)
    elif stage=='equivalence':data=equivalence(r)
    else:
        from .digital_physical import execute
        data=execute(r)
    r.add_artifact('log',r.log)
    from .digital_reports import diagnostics
    data.update(stage=stage,source_hash=source_hash(r.config),logic_hash=logic_identity(r.config),
                platform={key:r.platform.get(key) for key in ('name','corner','revision','fingerprint')} if r.platform else None,
                versions=r.versions,environment=job['environment'],artifacts=r.artifacts,
                diagnostics=diagnostics(r.log.read_text(),r.config['files']))
    result={'schema':1,'result_type':'digital','created':now(),'engine':'digital','project_id':job['project']['id'],
            'cell_id':job['cell'],'revision':job['project']['revision'],'design_hash':design_digest(job['project']),
            'settings':clone(job['settings']),'digital_result':data}
    validate_result(result,r.root);progress(1,data['summary']);return result
