"""Captured external Xschem execution and managed Magic workspaces."""
import json
import os
import re
import shutil
from pathlib import Path
from .model import atomic_write, file_digest, digest, now, save_project
from .engines import execute, tcl_word

MAGIC_PROFILES = {
    'lvs': {'hierarchy':True,'blackbox':False,'merge':'none','scale':False,
            'capacitance_threshold':'infinite','resistance_threshold':'infinite','distributed_resistance':False},
    'capacitance': {'hierarchy':True,'blackbox':False,'merge':'none','scale':False,
                    'capacitance_threshold':0,'resistance_threshold':'infinite','distributed_resistance':False},
    'rc': {'hierarchy':True,'blackbox':False,'merge':'none','scale':False,
           'capacitance_threshold':0,'resistance_threshold':0,'distributed_resistance':True},
}


def executable_info(executable):
    path = Path(shutil.which(str(executable)) or executable).resolve()
    if not path.is_file(): raise ValueError('External executable is missing: ' + str(executable))
    return {'path':str(path), 'sha256':file_digest(path)}


def snapshot(source, destination, max_files=20000, max_bytes=256*1024*1024):
    source = Path(source).resolve(); destination = Path(destination).resolve()
    if destination.is_relative_to(source): raise ValueError('Place the output workspace outside the source folder.')
    files = {}; size = 0
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if any(part in ('.git','.venv','__pycache__','node_modules') for part in relative.parts): continue
        if path.is_symlink(): raise ValueError('Resolve symbolic links before capturing this tool workspace: ' + str(relative))
        if not path.is_file(): continue
        size += path.stat().st_size
        if len(files) >= max_files or size > max_bytes: raise ValueError('The external workspace exceeds its capture budget. Select a smaller project/library folder.')
        target = destination / relative; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target); files[relative.as_posix()] = file_digest(target)
    return files


def xschem_netlist(source, output, executable='xschem', libraries=(), rcfile=None, mode='simulation'):
    source = Path(source).resolve(); output = Path(output).resolve()
    if not source.is_file() or source.suffix != '.sch': raise ValueError('Choose an Xschem schematic.')
    if mode not in ('simulation','lvs'): raise ValueError('Choose simulation or LVS netlisting.')
    if output.exists() and any(output.iterdir()): raise ValueError('Choose an empty external Xschem workspace.')
    info = executable_info(executable); output.mkdir(parents=True,exist_ok=True)
    builtin=Path(__file__).parent/'assets'/'exchange'/'xschem'/'devices'
    roots = list(dict.fromkeys([source.parent]+[Path(p).resolve() for p in libraries]+[builtin.resolve()]))
    mappings = {}; captured = {}
    for index, root in enumerate(roots):
        target = output/'sources'/str(index)
        captured[str(index)] = snapshot(root,target); mappings[str(root)] = str(target)
    # Rebase captured literal absolute references. Dynamic Tcl is evaluated by
    # Xschem itself, in the explicit configuration selected for this run.
    for path in (output/'sources').rglob('*'):
        if not path.is_file(): continue
        try: text = path.read_text(encoding='utf-8')
        except UnicodeError: continue
        for before, after in sorted(mappings.items(),key=lambda row:-len(row[0])):
            text = text.replace(before,after)
        atomic_write(path,text)
    profile = output/'profile'; profile.mkdir()
    netlists = output/'netlists'; netlists.mkdir()
    startup = ''
    if rcfile:
        original = Path(rcfile).resolve(); startup = original.read_text(encoding='utf-8')+'\n'
        atomic_write(output/'selected-xschemrc',startup)
        for before, after in mappings.items(): startup = startup.replace(before,after)
    if any(os.pathsep in p for p in mappings.values()):raise ValueError('Xschem library paths cannot contain the platform path-list separator.')
    startup += 'set XSCHEM_LIBRARY_PATH '+tcl_word(os.pathsep.join(mappings.values()))+'\n'
    startup += 'set netlist_dir '+tcl_word(netlists)+'\nset USER_CONF_DIR '+tcl_word(profile)+'\n'
    startup += 'set lvs_netlist '+('1' if mode=='lvs' else '0')+'\n'
    rc = output/'xschemrc'; atomic_write(rc,startup)
    staged = Path(mappings[str(source.parent)])/source.name
    command = [info['path'],'-x','-q','-n','-s','--rcfile',str(rc),'-o',str(netlists),str(staged)]
    atomic_write(output/'command.json',json.dumps(command,indent=2))
    inputs = {str(p.relative_to(output)):file_digest(p) for p in (output/'sources').rglob('*') if p.is_file()}
    report = {'version':1,'created':now(),'tool':info,'mode':mode,'source':str(source),
              'inputs':inputs,'configuration_sha256':file_digest(rc),'status':'running',
              'scope':'Captured project and declared library roots. Dynamic references outside these roots require explicit additional libraries.'}
    atomic_write(output/'report.json',json.dumps(report,indent=2))
    try:
        log = execute(command,staged.parent,timeout=300)
        atomic_write(output/'engine.log',log)
        if re.search(r'unable to open|FATAL|not found|error executing|SKIPPING',log,re.I): raise ValueError('Xschem reported a netlisting error; inspect engine.log.')
        decks = list(netlists.glob('*.spice'))+list(netlists.glob('*.cir'))
        if not decks: raise ValueError('Xschem produced no SPICE netlist.')
        report.update(status='complete',netlists={p.name:file_digest(p) for p in decks})
    except Exception as exc:
        if not (output/'engine.log').is_file():atomic_write(output/'engine.log',str(exc))
        report.update(status='failed',error=str(exc)); atomic_write(output/'report.json',json.dumps(report,indent=2)); raise
    atomic_write(output/'report.json',json.dumps(report,indent=2)); return report


def extraction_commands(profile='lvs', overrides=None):
    if profile not in MAGIC_PROFILES: raise ValueError('Unknown Magic extraction profile.')
    settings = {**MAGIC_PROFILES[profile], **(overrides or {})}
    if set(settings) != set(MAGIC_PROFILES['lvs']): raise ValueError('Unknown Magic extraction option.')
    if settings['merge'] not in ('none','conservative','aggressive'): raise ValueError('Invalid device merge policy.')
    for key in ('hierarchy','blackbox','scale','distributed_resistance'):
        if type(settings[key]) is not bool: raise ValueError('Extraction flags must be boolean.')
    for key in ('capacitance_threshold','resistance_threshold'):
        value = settings[key]
        if value != 'infinite':
            from .model import scalar
            if scalar(value)<0: raise ValueError('Extraction thresholds cannot be negative.')
            settings[key] = scalar(value)
    lines = ['extract all','ext2spice lvs','ext2spice subcircuit top on','ext2spice renumber off','ext2spice global off']
    for key in ('hierarchy','blackbox','scale'): lines.append('ext2spice '+key+' '+('on' if settings[key] else 'off'))
    lines += ['ext2spice merge '+settings['merge'], 'ext2spice cthresh '+str(settings['capacitance_threshold']),
              'ext2spice rthresh '+str(settings['resistance_threshold'])]
    if settings['distributed_resistance']:
        lines += ['ext2sim labels on','ext2sim','extresist all','ext2spice extresist on']
    else: lines.append('ext2spice extresist off')
    return '\n'.join(lines)+'\n',settings


def magic_workspace(project, cid, output, executable='magic', technology=None, profile='lvs'):
    from .interoperability import tool_asset, project_contract
    from .interchange import export_layout
    from .physical_cells import ports, reachable
    from .silicon_flow import magic_script
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()): raise ValueError('Choose an empty Magic workspace.')
    info = executable_info(executable)
    if technology is None:
        from .process_adapters import ADAPTERS
        adapter = ADAPTERS.get(project['pdk'].get('package_lock',{}).get('id'))
        technology = tool_asset(project['pdk'],'magic','technology',adapter.technology_file if adapter else None)
    technology = Path(technology).resolve()
    if not technology.is_file(): raise ValueError('Choose a matching Magic technology file.')
    output.mkdir(parents=True,exist_ok=True)
    # Capture the technology dependency folder, including relative support files.
    snapshot(technology.parent, output/'technology')
    staged_tech = output/'technology'/technology.name
    export_layout(project,output/'layout.gds'); save_project(project,output/'project.icproj')
    # Magic accepts its legacy property 98 as the native cell-use name.
    # Current versions write standard property 61; reimport accepts both.
    from .layout import kdb
    layout=kdb().Layout();layout.read(str(output/'layout.gds'))
    for cell in layout.each_cell():
        for inst in cell.each_inst():
            marker=inst.property(126)
            if isinstance(marker,str) and marker.startswith('icstudio:'):
                inst.delete_property(125);inst.delete_property(126)
                inst.delete_property(61);inst.set_property(98,'studio_'+marker[9:])
    layout.write(str(output/'layout.gds'))
    for suffix,key in (('.report.json','file_hash'),('.exchange.json','layout_hash')):
        file=output/('layout.gds'+suffix);meta=json.loads(file.read_text());meta[key]=file_digest(output/'layout.gds');atomic_write(file,json.dumps(meta,indent=2))
    atomic_write(output/'interoperability.json',json.dumps(project_contract(project),indent=2))
    by = {c['id']:c for c in project['cells']}; setup = ''
    for key in reachable(project,cid,True):
        c = by[key]; physical = ports(project,key)
        if set(v['name'] for v in physical) != set(c['ports']): raise ValueError(c['name']+': assign every physical port before export to Magic.')
        setup += 'load '+tcl_word(c['name'])+'\nselect top cell\nbox values 0 0 0 0\n'
        for index, name in enumerate(c['ports'],1):
            pin = next(v for v in physical if v['name']==name)
            setup += 'if {![port '+tcl_word(name)+' exists]} {port '+tcl_word(name)+' make '+str(index)+'}\n'
            setup += 'if {![port '+tcl_word(name)+' exists]} {error '+tcl_word('Missing port '+name)+'}\n'
            setup += 'port '+tcl_word(name)+' index '+str(index)+'\n'
            for attr in ('class','use','shape'):
                if attr in pin: setup += 'port '+tcl_word(name)+' '+attr+' '+tcl_word(pin[attr])+'\n'
    commands, settings = extraction_commands(profile)
    log = magic_script(info['path'],staged_tech,output/'layout.gds',by[cid]['name'],by[cid]['ports'],output/'native',
                       'writeall force\n'+commands+'ext2spice -o extracted.spice',setup)
    deck = output/'native'/'extracted.spice'
    if not deck.is_file(): raise ValueError('Magic produced no extracted netlist.')
    interface=check_extracted_interface(deck,by[cid]['name'],by[cid]['ports'],project['pdk'])
    report = {'version':1,'created':now(),'tool':info,'project_hash':digest(project),'top':by[cid]['name'],
              'profile':profile,'settings':settings,'interface':interface,'technology_file':staged_tech.relative_to(output).as_posix(),'technology_sha256':file_digest(staged_tech),
              'files':{p.relative_to(output).as_posix():file_digest(p) for p in output.rglob('*') if p.is_file()},
              'status':'complete','scope':'Engine execution. Use a matching LVS setup and saved testbench to qualify electrical behavior.'}
    atomic_write(output/'workspace.json',json.dumps(report,indent=2)); return report


def check_extracted_interface(deck,top,expected,technology):
    from .interoperability import compare_interfaces
    text=re.sub(r'\n\s*\+\s*',' ',Path(deck).read_text())
    declarations=[m for m in re.finditer(r'(?im)^\s*\.subckt\s+(\S+)([^\n]*)',text) if m[1].casefold()==top.casefold()]
    if len(declarations)!=1:raise ValueError('Extraction must contain exactly one top subcircuit: '+top)
    actual=[]
    for token in declarations[0][2].split():
        if '=' in token or token.lower()=='params:':break
        actual.append(token)
    result=compare_interfaces(expected,actual,technology.get('interoperability',{}).get('net_aliases',{}))
    if not result['equal']:raise ValueError('Extracted port order differs from the schematic: '+str(result))
    return result


def magic_workspace_export(workspace,output,executable='magic'):
    """Capture edited native cells, export through Magic, then review in Studio."""
    from .model import load_project
    workspace=Path(workspace).resolve();output=Path(output).resolve()
    report=json.loads((workspace/'workspace.json').read_text())
    if report.get('version')!=1 or report.get('status')!='complete':raise ValueError('Choose a completed managed Magic workspace.')
    if output.exists() and any(output.iterdir()):raise ValueError('Choose an empty Magic review output folder.')
    for name,expected in report['files'].items():
        path=(workspace/name).resolve()
        if not path.is_relative_to(workspace):raise ValueError('Invalid workspace path.')
        if name.startswith('technology/') or name in ('project.icproj','layout.gds.icstudio.json','layout.gds.exchange.json'):
            if not path.is_file() or file_digest(path)!=expected:raise ValueError('A locked workspace input changed: '+name)
    info=executable_info(executable);output.mkdir(parents=True,exist_ok=True)
    snapshot(workspace/'native',output/'native');snapshot(workspace/'technology',output/'technology')
    technology=(output/report['technology_file']).resolve()
    if not technology.is_relative_to(output/'technology') or not technology.is_file():raise ValueError('Invalid workspace technology binding.')
    native=output/'native';target=output/'edited.gds'
    script='load '+tcl_word(report['top'])+'\ngds write '+tcl_word(target)+'\nputs STUDIO_MAGIC_COMPLETE\n'
    wrapped='if {[catch {\n'+script+'} err]} {puts stderr "STUDIO_MAGIC_ERROR $err"}\nquit -noprompt\n'
    rc=output/'startup.tcl';atomic_write(rc,'tech load '+tcl_word(technology)+'\n');atomic_write(output/'export.tcl',wrapped)
    log=execute([info['path'],'-dnull','-noconsole','-rcfile',str(rc)],native,timeout=240,input_text=wrapped)
    atomic_write(output/'engine.log',log)
    if 'STUDIO_MAGIC_COMPLETE' not in log or 'STUDIO_MAGIC_ERROR' in log or not target.is_file():raise ValueError('Magic export failed. Inspect engine.log.')
    for suffix in ('.icstudio.json','.exchange.json','.report.json'):
        shutil.copy2(workspace/('layout.gds'+suffix),Path(str(target)+suffix))
    result={'version':1,'source_workspace':str(workspace),'layout':str(target),'tool':info,
            'native_inputs':{p.relative_to(native).as_posix():file_digest(p) for p in native.rglob('*.mag')},
            'status':'ready_for_review'}
    atomic_write(output/'review-source.json',json.dumps(result,indent=2));return result
