"""Run preserved Xschem circuits with ngspice; retain every analysis and output.

The built-in netlister expands declarative symbol formats without executing Tcl.
Simulation expressions and control flow are interpreted by ngspice itself.
"""
import array,cmath,hashlib,json,math,os,re,shlex,shutil,sys
from pathlib import Path
from .model import clone,validate,digest,design_digest,now,atomic_write,file_digest
from .xschem_project import properties,records


def compatible(p):return p.get('xschem_exchange',{}).get('mode')=='compatible'


def format_device(d,child=None):
    info=d['xschem'];s=info['symbol'];attrs=s.get('attributes',{});props={**properties(attrs.get('template','')),**info['properties'],'name':d['name']}
    props.update(pinlist=' '.join(d['nets'][p] for p in s['pin_order']),symname=child['name'] if child else Path(info['reference']).stem)
    fmt=props.get('format',attrs.get('format',''))
    compact=re.sub(r'\s+','',fmt.replace('\\',''))
    # Exact upstream source probe template; never eval arbitrary Tcl.
    if attrs.get('type')=='vsource' and compact=='tcleval([expr{@savecurrent?"@name@pinlist@value.saveI(?1@name)":"@name@pinlist@value"}])':
        fmt='@name @pinlist @value'
        if props.get('savecurrent') in ('true','1'):fmt+='\n.save i(@name)'
    if 'tcleval' in fmt:raise ValueError(d['name']+': this custom symbol uses a Tcl netlisting program. Export the project and netlist it in Xschem.')
    def replace(m):
        token=m[0]
        if token.startswith('@@'):
            if token[2:] not in d['nets']:raise ValueError(d['name']+': unknown terminal '+token)
            return d['nets'][token[2:]]
        key=token[1:]
        if key not in props:
            if token.startswith('%'):return key
            if key in ('extra','spiceprefix'):return ''
            raise ValueError(d['name']+': missing symbol parameter '+key)
        return str(props[key])
    line=re.sub(r'@@?[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*',replace,fmt)
    if not line.strip():raise ValueError(d['name']+': no SPICE format is defined.')
    if 'tcleval' in line:raise ValueError(d['name']+': dynamic Tcl parameters require Xschem netlisting.')
    return line


def netlist(project,directory):
    """Resolve model paths into an isolated run folder and emit exact parameters."""
    from .wiring import rebuild
    p=clone(project);validate(p);exchange=p['xschem_exchange']
    if exchange.get('unresolved'):raise ValueError('Simulation needs these files: '+'; '.join(exchange['unresolved']))
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    files=exchange['source_files']
    # ngspice 42's .lib reader splits even quoted absolute paths at spaces.
    # A source-path identity also keeps identical wrappers from different
    # libraries separate when their relative dependencies differ.
    mapping={path:directory/'models'/('model_'+hashlib.sha256((path+'\0'+data['sha256']).encode()).hexdigest()[:24]+'.spice') for path,data in files.items() if data['kind'].startswith('Model')}
    if any(hashlib.sha256(data['text'].encode('utf-8')).hexdigest()!=data['sha256'] for data in files.values()):raise ValueError('An imported source asset changed without updating its recorded identity. Reimport the edited source files before running.')
    def rewrite(text,parent):
        def one(m):
            ref=m[2].strip('"\'');target=next((mapping[d['path']] for d in exchange['resolved_dependencies'] if d['parent']==parent and d['reference']==ref and d['path'] in mapping),None)
            if target is None:raise ValueError('Unresolved model include: '+ref)
            return m[1]+' '+target.relative_to(directory).as_posix()
        return re.sub(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)',lambda m:(one(m)+m[3]) if m[1].lower()!='.lib' or m[3].strip() else m[0],text)
    for path,target in mapping.items():atomic_write(target,rewrite(files[path]['text'],path))
    atomic_write(directory/'model-files.json',json.dumps({str(target.relative_to(directory)):path for path,target in mapping.items()},indent=2))
    by={c['id']:c for c in p['cells']};top=by[p['top']];lines=['* '+p['name']+' — Xschem compatible netlist'];definitions=set()
    if p.get('global_nets'):lines.append('.global '+' '.join(p['global_nets']))
    for c in [top]+[c for c in p['cells'] if c is not top]:
        rebuild(c,p)
        if c is not top:lines.append('.subckt '+c['name']+' '+' '.join(c['ports']))
        for r in c['xschem']['records']:
            if r[0]=='S' and len(r)>1 and r[1].strip():lines.append(rewrite(r[1],c['xschem']['path']))
        commands=[]
        for d in c['devices']:
            info=d.get('xschem')
            if info is None:raise ValueError('Use Xschem library components in this imported project: '+d['name'])
            if info.get('missing'):raise ValueError('Missing symbol for '+d['name'])
            props=info['properties'];attrs=info['symbol'].get('attributes',{})
            if props.get('spice_ignore',attrs.get('spice_ignore'))=='short':raise ValueError('Replace the shorted symbol '+d['name']+' with an explicit wire.')
            if info['kind']=='netlist_commands':
                if c is top or props.get('only_toplevel','false') not in ('true','1'):commands.append(rewrite(props.get('value',''),c['xschem']['path']))
                continue
            lines.append(format_device(d,by.get(d.get('cell'))))
            definition=props.get('spice_sym_def',attrs.get('spice_sym_def'))
            if definition:definitions.add(rewrite(definition,info['symbol_path']))
        lines.extend(commands)
        if c is not top:lines.append('.ends '+c['name'])
    lines.extend(sorted(definitions));lines.append('.end')
    text='\n'.join(lines)+'\n';atomic_write(directory/'source.cir',text)
    atomic_write(directory/'library-lock.json',json.dumps(exchange.get('library_lock',{}),indent=2));return text


from .spice_program import find_ngspice, runtime_environment, probes, prepare_program, read_plot, run_program

def run(project,cid,settings,executable,directory,progress=lambda *_:None):
    return run_program(project,cid,settings,executable,directory,progress,netlist,
                       'ngspice · Xschem program',project['xschem_exchange'].get('library_lock',{}),'xschem_cases')
