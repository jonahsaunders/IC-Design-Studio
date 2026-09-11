from __future__ import annotations
import json,os,shutil,signal,subprocess,time
from pathlib import Path
from .model import digest,file_digest,design_digest,now,atomic_write
from .interchange import spice

def diagnostics(config=None):
    config=config or {};out=[]
    for name in ('ngspice','klayout','magic','netgen'):
        path=config.get(name) or shutil.which(name)
        if name=='ngspice':
            from .spice_program import find_ngspice
            path=find_ngspice(config.get(name,''))
        out.append({'name':name,'path':path or '', 'status':'available' if path and Path(path).is_file() else 'not installed'})
    return out

def execute(args,cwd,timeout=180,input_text=None,on_line=None,env=None):
    proc=subprocess.Popen([str(x) for x in args],cwd=cwd,env=env,stdin=subprocess.PIPE if input_text else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',shell=False,start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    prior=None
    try:
        def stopped(*_): raise InterruptedError('Job cancelled.')
        try:prior=signal.signal(signal.SIGTERM,stopped)
        except ValueError:pass
        if on_line is None:out,_=proc.communicate(input=input_text,timeout=timeout)
        else:
            import queue,threading
            if input_text:proc.stdin.write(input_text);proc.stdin.close()
            stream=queue.Queue();lines=[];deadline=time.monotonic()+timeout
            def reader():
                try:
                    for line in proc.stdout:stream.put(line)
                finally:stream.put(None)
            thread=threading.Thread(target=reader,daemon=True);thread.start()
            while True:
                if time.monotonic()>deadline:raise subprocess.TimeoutExpired(args,timeout)
                try:line=stream.get(timeout=.2)
                except queue.Empty:continue
                if line is None:break
                lines.append(line);on_line(line.rstrip('\r\n'))
            proc.wait(timeout=max(.1,deadline-time.monotonic()));out=''.join(lines)
        if proc.returncode:raise RuntimeError(f'{Path(str(args[0])).name} exited with code {proc.returncode}.\n{out[-12000:]}')
        return out
    finally:
        if proc.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
            else:
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            if os.name!='nt':
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        if proc.stdout:proc.stdout.close()
        if proc.stdin:proc.stdin.close()
        if prior is not None:signal.signal(signal.SIGTERM,prior)

def parse_raw(path):
    text=Path(path).read_text(encoding='utf-8',errors='strict');header,body=text.split('Values:',1)
    import re
    count=int(re.search(r'No\. Variables:\s*(\d+)',header)[1]);points=int(re.search(r'No\. Points:\s*(\d+)',header)[1]);complex_data='complex' in re.search(r'Flags:\s*(.+)',header)[1]
    variables=[]
    for line in header.rsplit('Variables:',1)[1].strip().splitlines():
        parts=line.split()
        if len(parts)>=3:variables.append(parts[1])
    if len(variables)!=count or points>1000000 or count>10000:raise ValueError('Unsupported raw-file dimensions.')
    values=[line.strip() for line in body.strip().splitlines() if line.strip()];rows=[];pos=0
    for i in range(points):
        row=[]
        for j in range(count):
            line=values[pos];pos+=1;part=line.split()[-1]
            if complex_data:
                real,imag=part.split(',');row.append(complex(float(real),float(imag)))
            else:row.append(float(part))
        rows.append(row)
    return variables,rows,complex_data

def ngspice_command(project,executable,raw,deck):
    from .osdi import verified
    verified(project)
    args=[executable,'-n','-D','filetype=ascii']
    mode=project['pdk'].get('simulation',{}).get('ngspice_compatibility')
    if project.get('spice',{}).get('version')==1 and not mode:mode='hsa'
    if mode:
        if mode!='hsa':raise ValueError('Unsupported locked ngspice compatibility mode.')
        args+=['-D','ngbehavior='+mode]
    return args+['-b','-r',str(raw),str(deck)]

def run_ngspice(p,cid,settings,executable,directory,progress=lambda *_:None):
    import cmath,math
    from .osdi import preload,verified
    directory=Path(directory).resolve();deck=directory/'input.cir';raw=directory/'result.raw'
    from .operating_data import save_directive,extras
    from .native_spice import native
    if native(p):
        from .native_analysis import deck as native_deck
        text,aliases=native_deck(p,cid,settings,directory)
    else:
        directive,aliases=save_directive(p,cid);text=spice(p,cid,settings,hierarchical=False)
        if settings['type']=='op':text=text.rsplit('.end',1)[0]+directive+'\n.end\n'
    from .pdks import stage_model_deck
    text=stage_model_deck(p['pdk'],text,directory)
    atomic_write(deck,preload(p,text,directory));atomic_write(directory/'runtime-lock.json',json.dumps({'osdi':verified(p)},indent=2));progress(.05,'Starting ngspice batch worker')
    if raw.exists():raw.unlink()
    from .spice_program import runtime_environment
    try:log=execute(ngspice_command(p,executable,raw,deck),directory,timeout=int(settings.get('timeout',180)),env=runtime_environment(executable))
    except Exception as exc:
        atomic_write(directory/'engine.log',str(exc));raise
    atomic_write(directory/'engine.log',log)
    if not raw.exists():raise ValueError('ngspice produced no raw file. See the engine log.')
    variables,rows,is_complex=parse_raw(raw);typ=settings['type'];traces={};phase={}
    scale=0;xs=[abs(r[scale]) if is_complex else r[scale] for r in rows]
    if typ=='op':xs=list(range(len(rows)))
    for j,n in enumerate(variables):
        if n.startswith('v(') and n.endswith(')') and not n.startswith('v(@'):
            name=n[2:-1];traces[name]=[abs(r[j]) if is_complex else r[j] for r in rows]
            if is_complex:phase[name]=[math.degrees(cmath.phase(r[j])) for r in rows]
    if typ=='noise' and 'onoise_spectrum' in variables:
        j=variables.index('onoise_spectrum');traces={settings['output']:[float(r[j]) for r in rows]}
    if not traces:raise ValueError('No voltage or noise traces were returned by ngspice.')
    exe_path=Path(executable) if Path(executable).is_file() else Path(shutil.which(executable) or executable)
    currents,current_phase,devices=extras(variables,rows,is_complex,aliases)
    progress(1,'ngspice completed')
    return {'schema':1,'created':now(),'engine':'ngspice · native graphical analysis' if native(p) else 'ngspice (installed executable)','engine_hash':file_digest(exe_path),'project_id':p['id'],'revision':p['revision'],'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'rule_hash':digest(p['pdk']['layers']),'cell_id':cid,'settings':settings,'x':xs,'x_label':{'tran':'Time (s)','dc':'Source value','ac':'Frequency (Hz)','noise':'Frequency (Hz)','op':'Operating point'}[typ],'y_label':'Noise (V/√Hz)' if typ=='noise' else 'Voltage magnitude (V)' if is_complex else 'Voltage (V)','traces':traces,'phase':phase,'operating_point':{n:v[0] for n,v in traces.items()} if typ=='op' else {},'currents':currents,'current_phase':current_phase,'device_operating_point':devices if typ=='op' else {},'operating_currents':{n:v[0] for n,v in currents.items()} if typ=='op' else {},'warnings':['This graphical run excludes saved control-program commands and uses embedded circuit/model definitions. AC and noise points are per decade.'] if native(p) else ['Locked technology model bindings are used when configured; otherwise generic level-1 models apply. External AC points are points per decade.'],'log':log}

def tcl_word(value):
    # Literal Tcl word: prevent substitutions and preserve spaces/Unicode.
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('[','\\[').replace(']','\\]').replace('\n','\\n').replace('\r','\\r')+'"'

def magic_convert(executable,gds,technology,output,top):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    script=f'gds read {tcl_word(Path(gds).resolve())}\nload {tcl_word(top)}\nwriteall force\nquit -noprompt\n'
    log=execute([executable,'-dnull','-noconsole','-T',str(Path(technology).resolve())],output,input_text=script)
    if not list(output.glob('*.mag')):raise RuntimeError('Magic returned no native cells. Check technology and top-cell name.\n'+log)
    atomic_write(output/'conversion.log',log);return log

def netgen_lvs(executable,schematic,schematic_cell,extracted,layout_cell,setup,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);log=output/'lvs.log'
    lhs=f'{tcl_word(Path(schematic).resolve())} {tcl_word(schematic_cell)}';rhs=f'{tcl_word(Path(extracted).resolve())} {tcl_word(layout_cell)}'
    text=execute([executable,'-batch','lvs',lhs,rhs,str(Path(setup).resolve()),str(log),'-json'],output)
    report=log.read_text(errors='replace') if log.exists() else text
    atomic_write(output/'console.log',text)
    # Only surface raw evidence; deck-dependent log text does not imply signoff.
    return report


def require_lvs_match(log):
    """A unique device match does not establish an unchanged, connected interface."""
    import re
    bad=r'Circuits do not match|Property errors|Netlists do not match|disconnected node:|\(no matching pin\)|pin lists[^\n]*altered'
    if (not re.search(r'Circuits match uniquely\.',log)
            or not re.search(r'Cell pin lists are equivalent\.',log)
            or re.search(bad,log,re.I)):
        raise ValueError('Netgen did not establish a unique match with equivalent connected pins and no property errors. See lvs/lvs.log.')


def magic_extract(executable,gds,technology,top,output,profile='rc'):
    """Run Magic's extraction sequence with separate LVS and distributed-RC profiles."""
    gds=Path(gds).resolve();technology=Path(technology).resolve();output=Path(output).resolve()
    if not gds.is_file() or not technology.is_file():raise ValueError('GDS and technology files are required.')
    if not top or profile not in ('lvs','capacitance','rc'):raise ValueError('Choose a top cell and an LVS, capacitance or RC profile.')
    if output.exists() and any(output.iterdir()):raise ValueError('Use an empty extraction directory.')
    output.mkdir(parents=True,exist_ok=True)
    from .external_tools import extraction_commands
    commands,settings=extraction_commands(profile)
    atomic_write(output/'profile.json',json.dumps(settings,indent=2))
    script=f'gds read {tcl_word(gds)}\nload {tcl_word(top)}\nselect top cell\nextract do local\n'+commands
    script+='ext2spice\nquit -noprompt\n';atomic_write(output/'extract.tcl',script)
    log=execute([executable,'-dnull','-noconsole','-T',str(technology)],output,input_text=script);atomic_write(output/'extraction.log',log)
    decks=list(output.glob('*.spice'))+list(output.glob('*.spc'))
    if not decks:raise RuntimeError('Magic returned no extracted SPICE deck. Inspect extraction.log.')
    report={'engine':'Magic','profile':profile,'gds_hash':file_digest(gds),'technology_hash':file_digest(technology),'script_hash':file_digest(output/'extract.tcl'),'decks':{p.name:file_digest(p) for p in decks},'qualification':'Requires destination-tool and PDK-specific regression; engine completion is not foundry signoff.'}
    atomic_write(output/'extraction.json',json.dumps(report,indent=2));return report


def run_deck(p,cid,settings,executable,directory,progress=lambda *_:None):
    """Run an explicit extracted/testbench deck and retain its exact input bytes."""
    import math,cmath
    deck=Path(settings['deck']).resolve();directory=Path(directory).resolve()
    if not deck.is_file():raise ValueError('The SPICE deck does not exist.')
    raw=directory/'deck.raw';atomic_write(directory/'deck-snapshot.cir',deck.read_bytes());progress(.05,'Running external SPICE testbench')
    log=execute(ngspice_command(p,executable,raw,deck),deck.parent);atomic_write(directory/'engine.log',log)
    variables,rows,complex_data=parse_raw(raw);xs=[float(r[0].real if complex_data else r[0]) for r in rows];traces={};phase={};currents={};current_phase={}
    for j,name in enumerate(variables):
        if name.startswith('v(') and name.endswith(')') and not name.startswith('v(@'):
            net=name[2:-1];traces[net]=[abs(r[j]) if complex_data else r[j] for r in rows]
            if complex_data:phase[net]=[math.degrees(cmath.phase(r[j])) for r in rows]
        if name.startswith('i(') and name.endswith(')'):
            source=name[2:-1];currents[source]=[abs(r[j]) if complex_data else r[j] for r in rows]
            if complex_data:current_phase[source]=[math.degrees(cmath.phase(r[j])) for r in rows]
    if not traces:raise ValueError('The deck produced no node-voltage traces.')
    progress(1,'External testbench completed')
    return {'schema':1,'created':now(),'engine':'ngspice external testbench','engine_hash':file_digest(Path(executable) if Path(executable).is_file() else Path(shutil.which(executable))),'project_id':p['id'],'revision':p['revision'],'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'rule_hash':digest(p['pdk']['layers']),'cell_id':cid,'settings':settings,'deck_hash':file_digest(deck),'x':xs,'x_label':variables[0],'y_label':'Voltage magnitude (V)' if complex_data else 'Voltage (V)','traces':traces,'phase':phase,'currents':currents,'current_phase':current_phase,'operating_point':{},'warnings':['External deck connectivity is not automatically proven equivalent to the active schematic. Run LVS and retain its extraction report. Included model dependencies must be locked separately.'],'log':log}

def magic_import(executable,source,technology,output):
    """Convert an existing Magic cell tree through its real technology engine."""
    source=Path(source).resolve();output=Path(output).resolve()
    if not source.is_file() or source.suffix.lower()!='.mag':raise ValueError('Choose an existing Magic .mag cell.')
    if not Path(technology).is_file():raise ValueError('A matching Magic technology file is required.')
    if output.exists() and any(output.iterdir()):raise ValueError('Choose an empty Magic import output directory.')
    from .magic_dependencies import closure
    dependencies=closure(source)
    output.mkdir(parents=True,exist_ok=True);target=output/'imported.gds'
    search=tcl_word('+'+str(source.parent));script=f'path search {search}\nload {tcl_word(source.stem)}\ngds write {tcl_word(target)}\nfeedback save {tcl_word(output/"feedback.txt")}\nputs STUDIO_IMPORT_COMPLETE\n'
    script='if {[catch {\n'+script+'} err]} {puts stderr "STUDIO_IMPORT_ERROR $err"}\nquit -noprompt\n'
    atomic_write(output/'import.tcl',script)
    log=execute([executable,'-dnull','-noconsole','-T',str(Path(technology).resolve())],source.parent,input_text=script);atomic_write(output/'conversion.log',log)
    if not target.exists() or 'STUDIO_IMPORT_COMPLETE' not in log or 'STUDIO_IMPORT_ERROR' in log:raise RuntimeError('Magic import did not complete. Review the conversion log and technology selection.')
    from .interchange import import_layout
    from .model import save_project
    project,report=import_layout(target)
    feedback=output/'feedback.txt'
    if feedback.is_file() and feedback.stat().st_size:
        report.append('Magic reported conversion feedback. Inspect feedback.txt and conversion.log before verification.')
    evidence={'source':str(source),'source_hash':file_digest(source),'dependencies':dependencies,'technology':file_digest(technology),'report':report,
              'feedback':feedback.read_text(errors='replace') if feedback.is_file() else ''}
    project['layout_source']['magic_import']=evidence
    save_project(project,output/'imported.icproj');atomic_write(output/'import-report.json',json.dumps(evidence,indent=2));return str(output/'imported.icproj')
