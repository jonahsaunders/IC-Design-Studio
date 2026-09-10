"""Shared ngspice control-program execution and waveform parsing."""
import array,cmath,hashlib,json,math,os,re,shlex,shutil,sys
from pathlib import Path
from .model import clone,validate,digest,design_digest,now,atomic_write,file_digest

def find_ngspice(configured=''):
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    names=('ngspice.exe','ngspice_con.exe') if sys.platform=='win32' else ('ngspice',)
    configured=str(configured).strip().strip('"')
    embedded=[root/'icstudio/assets/runtime/ngspice'/name for name in names]
    managed='/icstudio/assets/runtime/ngspice/' in configured.replace('\\','/').lower()
    # Older releases saved their bundled executable as a setting. Prefer this
    # release's bundle when upgrading, while retaining custom engine choices.
    candidates=([os.environ.get('ICSTUDIO_NGSPICE')]+embedded+[configured]) if managed else [configured,os.environ.get('ICSTUDIO_NGSPICE')]+embedded
    folders=[root/'engines/ngspice']
    if sys.platform=='win32':
        drive=os.environ.get('SystemDrive','C:')+'/'
        folders.extend([Path(drive)/'Spice64/bin',Path(drive)/'Spice/bin'])
        for key in ('ProgramFiles','LOCALAPPDATA'):
            if os.environ.get(key):folders.append(Path(os.environ[key])/'ngspice/bin')
    candidates.extend(folder/name for folder in folders for name in names)
    candidates.extend(shutil.which(name) for name in names)
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()),None)


def runtime_environment(executable):
    """Point the child at its packaged initializer without changing the GUI's environment."""
    scripts=Path(executable).resolve().parent
    return {**os.environ,'SPICE_SCRIPTS':str(scripts)} if (scripts/'spinit').is_file() else None


def probes(project):
    top=next(c for c in project['cells'] if c['id']==project['top']);nets={l['name'] for l in top.get('labels',[]) if l['name']!='0'}
    if not nets:
        nets={n for d in top.get('devices',[]) for n in d.get('nets',{}).values() if n and n!='0'}
    selected=[n for n in ('vref','avdd','v1','v2') if n in nets]
    return ' '.join('v('+n+')' for n in (selected or sorted(nets)[:8]))


def prepare_program(text,directory,settings):
    """Keep analysis ordering, loop/reset semantics and measurements intact."""
    root=Path(directory).resolve();(root/'waveforms').mkdir(exist_ok=True);(root/'outputs').mkdir(exist_ok=True)
    selected=settings.get('probes','').strip()
    if not re.fullmatch(r'(?:[vi]\([A-Za-z0-9_.$:/+\[\]-]+\)\s*)*',selected):raise ValueError('Waveform probes use v(net) or i(source), separated by spaces.')
    # ngspice treats brackets/operators as expression syntax unless the node
    # name is quoted. Keep the public v(data[0]) selector, quote only emission.
    selected=re.sub(r'([vi])\(([^)]+)\)',lambda m:m[1]+'('+('"'+m[2]+'"' if re.search(r'[$:/+\[\]-]',m[2]) else m[2])+')',selected)
    # Restrict only filesystem/OS actions. Ordinary ngspice control flow is kept.
    output_roots={}
    for line in text.splitlines():
        match=re.match(r'\s*shell\s+mkdir\s+-p\s+(.+?)\s*$',line,re.I)
        if match:
            old=match[1].strip('"\'');output_roots[old]='outputs/'+hashlib.sha256(old.encode()).hexdigest()[:8]
    for old,new in sorted(output_roots.items(),key=lambda item:-len(item[0])):
        text=text.replace(old,new);(root/new).mkdir(parents=True,exist_ok=True)
    output=[];inside=False;count=0;loops=[];case_count=0
    for line in text.splitlines():
        stripped=line.strip();cmd=stripped.split()[0].lower() if stripped else ''
        if cmd=='.control':
            inside=True;output.extend([line,'set filetype=binary','let studio_case=0']);continue
        if cmd=='.endc':inside=False
        if not inside or not stripped or stripped.startswith('*'):output.append(line);continue
        # ngspice stores control identifiers in lower case; echo preserves case
        # and otherwise fails to expand uppercase names used by alter/foreach.
        line=re.sub(r'\$(&?)([A-Za-z_][A-Za-z0-9_.]*)',lambda m:'$'+m[1]+m[2].lower(),line)
        if cmd in ('shell','!'):
            if re.fullmatch(r'shell\s+mkdir\s+-p\s+outputs/[a-f0-9]+',stripped,re.I):output.append('echo Output directory prepared by IC Design Studio');continue
            if re.fullmatch(r'shell\s+ls\s+-lah\s+outputs/[a-f0-9]+',stripped,re.I):output.append('echo Output files are available from the run artifacts');continue
            raise ValueError('The simulation program contains an unsupported operating-system command: '+stripped)
        if cmd in ('source','cd','chdir','edit','pre_osdi','osdi','load','hardcopy','codemodel','attach','aspice') or '`' in line:
            raise ValueError('The simulation program requires an external action that cannot run here: '+stripped)
        # Imported redirections and writers may only write beneath outputs/.
        paths=re.findall(r'>>?\s*(\S+)',line) if cmd=='echo' else []
        if cmd in ('wrdata','write'):
            parts=shlex.split(stripped,posix=True)
            if len(parts)<2:raise ValueError('Missing output file in '+cmd)
            paths.append(parts[1])
        for raw in paths:
            raw=raw.strip('"\'')
            if re.match(r'^(?:[A-Za-z]:|/|\\)',raw) or '..' in Path(raw).parts:raise ValueError('Output path must be relative to this run: '+raw)
            if '$' not in raw:(root/raw).parent.mkdir(parents=True,exist_ok=True)
        if cmd in ('plot','gnuplot'):output.append('* Interactive plot available in Studio: '+stripped);continue
        if cmd=='foreach':
            parts=stripped.split();loops.append((parts[1],max(1,len(parts)-2)))
        elif cmd in ('if','while','dowhile','repeat'):loops.append(('',1))
        elif cmd=='end' and loops:loops.pop()
        if cmd in ('op','tran','dc','ac','noise'):
            count+=1;case_count+=math.prod(n for _,n in loops)
            context=' '.join(k+'=$'+k.lower() for k,_ in loops if k)
            output+=['let const.studio_case=const.studio_case+1','echo ICSTUDIO_CASE_BEGIN $&const.studio_case '+cmd+' '+context,line,
                'set filetype=binary','write waveforms/case{$&const.studio_case}.raw '+selected,
                'echo ICSTUDIO_CASE_END $&const.studio_case '+cmd+' '+context]
        else:output.append(line)
    if not count:raise ValueError('The schematic contains no ngspice control analyses. Add op, tran, dc or ac in a simulation program component.')
    return '\n'.join(output)+'\n',case_count,output_roots


def read_plot(path,selected=None):
    """Read native ngspice binary or ASCII raw files, preserving sample points."""
    from .engines import parse_raw
    data=Path(path).read_bytes()
    if b'Binary:' not in data:
        variables,rows,complex_data=parse_raw(path);columns=list(zip(*rows)) if rows else []
        header=data.split(b'Values:',1)[0].decode('utf-8','replace')
    else:
        head,body=data.split(b'Binary:',1);body=body.removeprefix(b'\r\n').removeprefix(b'\n');header=head.decode('utf-8','replace')
        count=int(re.search(r'No\. Variables:\s*(\d+)',header)[1]);points=int(re.search(r'No\. Points:\s*(\d+)',header)[1]);complex_data='complex' in re.search(r'Flags:\s*(.+)',header)[1]
        if not 0<count<=10000 or not 0<points<=5_000_000:raise ValueError('Unsupported waveform dimensions.')
        variables=[line.split()[1] for line in header.rsplit('Variables:',1)[1].strip().splitlines()]
        values=array.array('d');width=count*(2 if complex_data else 1)
        if len(body)!=8*points*width:raise ValueError('Truncated or unsupported ngspice binary waveform.')
        values.frombytes(body);columns=[]
        for j in range(count):
            columns.append([complex(values[i*width+j*2],values[i*width+j*2+1]) for i in range(points)] if complex_data else values[j::count])
    traces={};phase={};currents={};current_phase={}
    for name,values in zip(variables[1:],columns[1:]):
        if selected and name not in selected:continue
        name=re.sub(r'^v\((.*)\)$',r'\1',name);is_current=name.endswith('#branch') or name.startswith('i(')
        key=name.removesuffix('#branch') if is_current else name
        target=currents if is_current else traces;target[key]=[abs(v) if complex_data else float(v) for v in values]
        if complex_data:(current_phase if is_current else phase)[key]=[math.degrees(cmath.phase(v)) for v in values]
    if not traces and currents:traces={k+' (A)':v for k,v in currents.items()}
    xs=[float(v.real if complex_data else v) for v in columns[0]]
    if any(not math.isfinite(v) for values in [xs]+list(traces.values())+list(currents.values()) for v in values):raise ValueError('The simulator returned non-finite waveform data.')
    plotname=re.search(r'Plotname:\s*([^\n]+)',header)[1]
    kind='tran' if 'Transient' in plotname else 'ac' if 'AC' in plotname else 'dc' if 'DC' in plotname else 'noise' if 'Noise' in plotname else 'op'
    return {'x':xs,'x_order':'ascending' if all(a<=b for a,b in zip(xs,xs[1:])) else 'unsorted','traces':traces,'phase':phase,'currents':currents,'current_phase':current_phase,'plot_kind':kind,'plot_name':plotname,'x_label':{'tran':'Time (s)','dc':'Sweep value','ac':'Frequency (Hz)','noise':'Frequency (Hz)','op':'Operating point'}[kind],'y_label':'Voltage magnitude (V)' if complex_data else 'Voltage (V)','operating_point':{n:v[0] for n,v in traces.items()} if kind=='op' else {}}


def run_program(project,cid,settings,executable,directory,progress,netlist,engine_label,library_lock,case_key):
    from .engines import execute
    root=Path(directory).resolve();text=netlist(project,root);settings={**settings,'probes':settings.get('probes') or probes(project)}
    program,total,relocations=prepare_program(text,root,settings);atomic_write(root/'input.cir',program)
    atomic_write(root/'output-paths.json',json.dumps(relocations,indent=2));cases=[];active={};log_path=root/'engine.log'
    def line_received(line):
        with log_path.open('a',encoding='utf-8') as out:out.write(line+'\n')
        m=re.search(r'ICSTUDIO_CASE_(BEGIN|END)\s+(\d+)\s+(\w+)(.*)',line)
        if m:
            number=int(m[2]);item=active.setdefault(number,{'number':number,'analysis':m[3],'context':m[4].strip(),'file':'waveforms/case'+str(number)+'.raw','state':'Running'})
            if m[1]=='END':
                item['state']='Complete' if (root/item['file']).is_file() else 'Failed'
                if item not in cases:cases.append(item)
            atomic_write(root/'cases.json',json.dumps({'total':total,'cases':list(active.values())},indent=2))
            progress(min(.97,.03+.94*len(cases)/max(total,1)),f"Case {number}/{total}: {item['analysis']} {item['context']} · {item['state']}")
    progress(.02,'Starting preserved ngspice program');args=[executable,'-n','-D','ngbehavior=hsa','-b','input.cir']
    log=execute(args,root,timeout=int(settings.get('timeout',7200)),on_line=line_received,env=runtime_environment(executable))
    diagnostics=[line.strip() for line in log.splitlines() if re.search(r'(^\s*error\b|\bfailed\b|no such vector|no such device|unknown parameter|unknown subckt|singular matrix|timestep too small)',line,re.I)]
    # Associate native ngspice measurement readouts with the analysis that
    # produced them; a finished analysis does not imply a passed requirement.
    current=None;by_number={item['number']:item for item in cases}
    for line in log.splitlines():
        if line.startswith('Total analysis time'):current=None
        start=re.search(r'ICSTUDIO_CASE_BEGIN\s+(\d+)',line)
        if start:current=by_number.get(int(start[1]));continue
        measurement=re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s+=\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\b(.*)$',line)
        if current is not None and measurement:current.setdefault('measurements',[]).append({'name':measurement[1],'value':float(measurement[2]),'details':measurement[3].strip()})
    specifications=next(c for c in project['cells'] if c['id']==cid).get('specifications',[])
    for item in cases:
        if item['state']=='Complete':
            plot=read_plot(root/item['file']);item.update(points=len(plot['x']),traces=list(plot['traces']))
            if specifications:
                from .specifications import evaluate_rows
                item['specifications']=evaluate_rows(specifications,{**plot,'settings':settings})
                item['spec_status']='ERROR' if any(s['status']=='ERROR' for s in item['specifications']) else 'FAIL' if any(s['status']=='FAIL' for s in item['specifications']) else 'PASS'
    complete=[item for item in cases if item['state']=='Complete']
    if not complete:raise ValueError('No analysis produced waveforms. '+log[-8000:])
    first=next((item for item in complete if item['analysis']=='tran'),complete[0]);plot=read_plot(root/first['file'])
    result={'schema':1,'created':now(),'engine':engine_label,'engine_hash':file_digest(executable),'project_id':project['id'],'revision':project['revision'],'design_hash':design_digest(project),'pdk_hash':digest(project['pdk']),'rule_hash':digest(project['pdk']['layers']),'cell_id':cid,'settings':settings,'warnings':list(dict.fromkeys(diagnostics)),'log':log,case_key:cases,'case_directory':str(root),'active_case':first['number'],'output_paths':relocations,'program_status':'Needs review' if diagnostics or len(complete)!=total else 'Complete','library_lock':library_lock,**plot}
    atomic_write(root/'cases.json',json.dumps({'total':total,'cases':cases},indent=2));progress(1,f"Finished {len(complete)}/{total} analyses · {result['program_status']}");return result
