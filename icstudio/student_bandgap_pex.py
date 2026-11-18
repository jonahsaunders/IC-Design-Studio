"""Capacitance extraction and device/terminal readback for the GF180 lessons."""

from collections import Counter
import math
from pathlib import Path
import re
import shutil

from .getting_started import resource_root
from .model import clone, file_digest, scalar

MODELS = {
    'nfet_03v3': (4, ('w','l')), 'pfet_03v3': (4, ('w','l')),
    'npn_05p00x05p00': (4, ()), 'pnp_05p00x05p00': (3, ()),
    'ppolyf_u_1k': (3, ('r_width','r_length')),
    'cap_mim_2f0_m3m4_noshield': (2, ('c_width','c_length')),
}


def readback(text, top):
    from .sky130_flow import subcircuit

    ports, body, _ = subcircuit(text, top)
    signatures = Counter()
    capacitances = []
    for line in body.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith('*'):
            continue
        kind = fields[0][0].casefold()
        if kind == 'c':
            if len(fields) != 4:
                raise ValueError('Malformed parasitic capacitance.')
            value = scalar(fields[3])
            if not math.isfinite(value) or value<0:
                raise ValueError('Extracted capacitance must be finite and nonnegative.')
            capacitances.append((fields[1].casefold(),fields[2].casefold(),value))
            continue
        if kind != 'x':
            raise ValueError('Unsupported physical device or statement: '+line)
        models = [(i,f.casefold()) for i,f in enumerate(fields) if f.casefold() in MODELS]
        if len(models)!=1:
            raise ValueError('Unexpected extracted model name: '+line)
        index, model = models[0]
        count, dimensions = MODELS[model]
        if index!=count+1:
            raise ValueError('Unexpected terminal count: '+line)
        nets = [n.casefold() for n in fields[1:index]]
        params = {}
        for field in fields[index+1:]:
            name,value = field.lower().split('=',1)
            if name in params or not math.isfinite(scalar(value)):
                raise ValueError('Invalid or duplicate extracted model parameter.')
            params[name] = scalar(value)
        if any(params.get(key,1)!=1 for key in ('m','nf','par')):
            raise ValueError('Use explicit unit devices in the layout comparison.')
        # Magic truncates some printed values by 0.01 nm. Normalize
        # that output noise before comparing exact 5 nm grid dimensions.
        exact = [params[key]*2e8 for key in dimensions]
        size = tuple(round(value) for value in exact)
        if any(abs(value-snapped)>.02 for value,snapped in zip(exact,size)):
            raise ValueError('An extracted dimension is off the 5 nm layout grid.')
        if model.startswith(('pfet','nfet')):
            nets = [*sorted((nets[0],nets[2])),nets[1],nets[3]]
        elif model.startswith('ppoly'):
            nets = [*sorted(nets[:2]),nets[2]]
        elif model.startswith('cap'):
            size = tuple(sorted(size))
        signatures[(model,tuple(nets),size)] += 1
    return ports, signatures, capacitances


def compare_devices(reference, extracted, top):
    ports, schematic, _ = readback(reference, top)
    actual_ports, actual, caps = readback(extracted, top)
    if Counter(ports)!=Counter(actual_ports) or schematic!=actual:
        missing = list((schematic-actual).items())[:3]
        extra = list((actual-schematic).items())[:3]
        raise ValueError(f'Extracted ports, devices or dimensions differ. Missing {missing}. Extra {extra}.')
    legal_nodes = {n for (_,pins,_) in actual for n in pins} | {'0'}
    if not caps or any(a not in legal_nodes or b not in legal_nodes for a,b,_ in caps):
        raise ValueError('Extracted capacitance is absent or uses unknown circuit nets.')
    return actual_ports, dict(devices=sum(actual.values()), capacitors=len(caps),
                              sum_capacitance_F=sum(c for _,_,c in caps))


def tools_path():
    return resource_root()/'icstudio/assets/physical/student-bandgap/gf180mcuB.tech'


def magic_tool(configured=''):
    direct = configured or shutil.which('magic')
    if direct:
        executable = Path(direct).resolve()
        if not executable.is_file():
            raise ValueError('Select an existing Magic executable in Engine setup.')
        return dict(magic=str(executable), magic_sha256=file_digest(executable))
    from .physical_backend import available
    runtime = available()
    if not runtime:
        raise ValueError('Set up Magic under Tools → Physical tools setup, or select a local Magic executable.')
    executable = Path(runtime['root'])/'opt/icstudio/bin/magic'
    return dict(magic=str(executable), magic_sha256=file_digest(executable), runtime=runtime)


def extract(project, cell, magic, directory, runtime=None):
    from .engines import execute, tcl_word
    from .interchange import export_layout
    from .model import atomic_write
    from .sky130_flow import subcircuit
    from .student_bandgap_layout import check
    from .testbenches import native_subcircuit

    check(project)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    layout = clone(project)
    layout['cells'] = [clone(cell)]
    layout['top'] = cell['id']
    for key in ('testbenches','test_plans','simulation_setups','implementation_views'):
        layout.pop(key,None)
    gds = directory/'layout.gds'
    export_layout(layout,gds)
    # Use actual layer numbers. Studio layer names differ between the
    # process catalog and the archived Banba layout.
    metal = {layer['name']: {34:'m1',36:'m2',42:'m3',46:'m4'}.get(layer['gds'])
             for layer in project['pdk']['layers'] if layer['datatype']==0}
    devices = {d['id']:d for d in cell['devices']}
    names = set(cell['ports'])
    top = cell['name']
    tech = directory/'gf180mcuB.tech'
    shutil.copy2(tools_path(),tech)
    lines = ['drc off','tech load '+tcl_word(tech.name),'scalegrid 1 10','gds read '+tcl_word(gds.name),
             'load '+tcl_word(top),'select top cell']
    for pin in cell['layout_pins']:
        net = devices[pin['device_id']]['nets'][pin['pin']]
        if net not in names:
            names.add(net)
            layer = metal[pin['layer']]
            x,y = (value/1000 for value in pin['point'])
            lines.extend([f'box values {x}um {y}um {x}um {y}um', f'label {tcl_word(net)} center {layer}'])
    lines.extend(['extract do local','extract all','ext2spice lvs','ext2spice merge none',
                  'ext2spice cthresh 0','ext2spice -o extracted-c.spice','quit -noprompt'])
    script = directory/'extract.tcl'
    atomic_write(script,'\n'.join(lines)+'\n')
    command = [magic]
    if runtime:
        from .digital_runtime import identity, wsl
        identity(runtime)
        if runtime['kind']=='wsl':
            distro = ['--distribution',runtime['distro']]
            native_path = wsl([*distro,'--exec','wslpath','-a','-u',str(directory)])
            command = [shutil.which('wsl.exe') or 'wsl.exe',*distro,'--cd',native_path,
                       '--exec','/opt/icstudio/bin/magic']
    try:
        log = execute([*command,'-dnull','-noconsole',script.name],directory,timeout=120)
    except RuntimeError as error:
        atomic_write(directory/'magic.log', str(error))
        raise
    atomic_write(directory/'magic.log',log)
    clean = log.replace("Warning: Calma reading is not undoable!  I hope that's OK.",'')
    clean = re.sub(r'^WARNING: RLIMIT_NOFILE is above 1024 and Tcl_Version<9 '
                   r'this may cause runtime issues \[rlim_cur=\d+\]\s*$', '', clean, flags=re.M)
    if re.search(r'error|warning|do not match|missing|couldn.t load|unknown command',clean,re.I):
        raise ValueError('Magic reported an extraction problem. Open the saved Magic log.')
    path = directory/'extracted-c.spice'
    extracted = path.read_text(encoding='utf-8')
    reference = native_subcircuit(project, cell['id'])
    atomic_write(directory/'schematic.spice',reference)
    # Strip the top-level wrapper directives. The simulator fixture supplies
    # its own run commands and PDK includes.
    ports, identity = compare_devices(reference,extracted,top)
    _,_,text = subcircuit(extracted,top)
    atomic_write(path,text)
    identity.update(layout_sha256=file_digest(gds), extracted_sha256=file_digest(path),
                    technology_sha256=file_digest(tech), magic_sha256=file_digest(magic),
                    scope='Magic capacitance and device geometry with named-terminal and dimension readback')
    return path, ports, identity
