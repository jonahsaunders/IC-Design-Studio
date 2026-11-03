"""Native electrical definitions and portable SPICE generation.

No Xschem parser, source records, installation or template evaluator is used.
Device programs contain explicit literal, parameter, terminal and instance
tokens. SPICE expressions remain expressions for the selected simulator.
"""
import hashlib
import json
import re
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from .model import clone, validate, atomic_write, scalar


def native(project):
    return project.get('spice', {}).get('version') == 1


def lvs_defaults(text, technology=None, *, lvs_extractor=None):
    """Canonicalize only explicit, literal unit defaults of known PDK devices."""
    changes=[]
    def instance(match):
        original=match[0];logical=re.sub(r'\n[ \t]*\+[ \t]*',' ',original)
        if not re.search(r'(?i)\ssky130_fd_pr__cap_var_(?:lvt|hvt)(?=\s|$)',logical):return original
        if len(re.findall(r'(?i)\sVM\s*=',logical))!=1:return original
        # VM defaults to 1 in these PDK subcircuits. Never discard m, W/L,
        # a non-unit VM, an expression, or a similarly named unknown model.
        canonical,count=re.subn(r'(?i)[ \t]+VM[ \t]*=[ \t]*(?:1(?:\.0*)?|1(?:\.0*)?e[+-]?0)(?=\s|$)','',logical)
        if count:changes.append(dict(instance=logical.split()[0],parameter='VM',default='1'))
        return canonical if count else original
    text=re.sub(r'(?im)^[ \t]*x\S+[^\n]*(?:\n[ \t]*\+[^\n]*)*',instance,text)
    if (technology or {}).get('package_lock',{}).get('id')=='ihp-sg13g2':
        text,ihp_changes=ihp_lvs_defaults(text,technology);changes.extend(ihp_changes)
        text,resistor_changes=ihp_resistor_lvs_defaults(text,technology);changes.extend(resistor_changes)
        text,capacitor_changes=ihp_cmim_lvs_reference(text,technology,extractor=lvs_extractor);changes.extend(capacitor_changes)
    return text,changes


def ihp_cmim_lvs_reference(text,technology,*,extractor=None):
    """Project the pinned IHP MiM simulation symbol to its physical LVS view.

    This changes no simulation output and makes no physical-model or operating
    envelope claim. A complete, consistent C-form reference remains untouched.
    """
    from .model import file_digest
    if not re.search(r'(?im)^[ \t]*[xc]\S+[^\n]*(?:\n[ \t]*\+[^\n]*)*\s+cap_cmim(?=\s|$)',text):return text,[]
    root=Path(technology['package_root']).resolve();files=technology['package_lock']['files']
    entries=[e for e in technology.get('simulation',{}).get('catalog',{}).values()
             if e.get('model')=='cap_cmim' and not e.get('unavailable')]
    if len(entries)!=1:raise ValueError('IHP cap_cmim LVS requires the unique locked catalog binding.')
    entry=entries[0];symbol='libs.tech/xschem/sg13g2_pr/cap_cmim.sym';model='libs.tech/ngspice/models/capacitors_mod.lib'
    if (entry.get('source')!=symbol or entry.get('model_source')!=model or entry.get('prefix')!='X'
            or entry.get('pin_order')!=['c0','c1'] or entry.get('emit_parameters')!={'w':'w','l':'l','m':'m','mm_ok':'mm_ok'}):
        raise ValueError('IHP cap_cmim catalog interface differs from the locked symbol.')
    for name in (symbol,model):
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not files.get(name) or file_digest(path)!=files[name]:
            raise ValueError('IHP cap_cmim source is missing or changed: '+name)
    source=(root/symbol).read_text(encoding='utf-8')
    if ('format="@spiceprefix@name @pinlist @model w=@w l=@l m=@m mm_ok=@mm_ok"' not in source or
            'lvs_format="C@name @pinlist @model w=@w l=@l m=@m"' not in source):
        raise ValueError('IHP cap_cmim simulation or LVS format differs.')
    proof=dict(source=symbol,sha256=files[symbol],model_source=model,model_sha256=files[model]);changes=[]
    if extractor!='magic':
        reader=Path(__file__).resolve().parent/'assets/physical/ihp_klayout_lvs/rule_decks/custom_reader.lvs'
        reader_sha='c71b6713d8a62055d3d8e9e75a7f5f78140001bf76e3fa573b9883fab5e49f06'
        if file_digest(reader)!=reader_sha:raise ValueError('IHP cap_cmim public physical reader changed.')
        proof.update(geometry_reader='rule_decks/custom_reader.lvs',geometry_reader_sha256=reader_sha,
                     geometry_formula='A=w*l; P=2*(w+l), per unit; m retained separately')
    multipliers={'':Decimal(1),'t':Decimal('1e12'),'g':Decimal('1e9'),'meg':Decimal('1e6'),'k':Decimal('1e3'),
                 'm':Decimal('1e-3'),'u':Decimal('1e-6'),'n':Decimal('1e-9'),'p':Decimal('1e-12'),'f':Decimal('1e-15')}
    def number(value):
        found=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(meg|[tgkmunpf]?)',value,re.I)
        if not found:raise ValueError('IHP cap_cmim LVS requires finite literal parameters.')
        try:
            literal=Decimal(found[1])
            if len(literal.as_tuple().digits)>10000:raise ValueError('IHP cap_cmim literal has excessive precision.')
            with localcontext() as context:
                context.prec=max(32,len(literal.as_tuple().digits)+1)
                out=literal*multipliers[found[2].lower()]
        except DecimalException as exc:raise ValueError('Invalid IHP cap_cmim LVS parameter.') from exc
        if not out.is_finite():raise ValueError('IHP cap_cmim LVS requires finite literal parameters.')
        return out
    def instance(match):
        original=match[0];line=re.sub(r'\n[ \t]*\+[ \t]*',' ',original);parts=line.split()
        if not any(v.lower()=='cap_cmim' for v in parts[3:]):return original
        if len(parts)<5 or parts[3].lower()!='cap_cmim':raise ValueError('IHP cap_cmim LVS requires exactly two ordered terminals.')
        physical=parts[0][0].lower()=='c';fields={}
        if physical and extractor=='magic':
            raise ValueError('IHP cap_cmim C-form reference requires the public IHP KLayout checker; use an X-form reference with Magic.')
        for part in parts[4:]:
            if part.count('=')!=1:raise ValueError('Malformed IHP cap_cmim LVS parameter.')
            key,value=part.split('=',1);key=key.lower()
            if key not in (('w','l','m','a','p') if physical else ('w','l','m','mm_ok')) or key in fields:
                raise ValueError('Unsupported or duplicated IHP cap_cmim LVS parameter.')
            fields[key]=value
        if not {'w','l','m'}<=set(fields):raise ValueError('IHP cap_cmim LVS requires w, l and m.')
        w,l,m=(number(fields[k]) for k in ('w','l','m'))
        if min(w,l,m)<=0:raise ValueError('IHP cap_cmim LVS geometry and multiplicity must be positive.')
        if 'mm_ok' in fields and number(fields['mm_ok']) not in (0,1):raise ValueError('IHP cap_cmim mm_ok must be literal zero or one.')
        if extractor=='magic':
            if 'mm_ok' not in fields:
                changes.append(dict(instance=parts[0],physical_instance=parts[0],changed=False,reason='Validated locked cap_cmim Magic X physical reference',proof=proof))
                return original
            result=' '.join(part for part in parts if not part.lower().startswith('mm_ok='))
            changes.append(dict(instance=parts[0],physical_instance=parts[0],changed=True,reason='Locked cap_cmim physical LVS omits simulation-only mm_ok; Magic retains X representation',proof=proof))
            return result
        precision=max(len(w.as_tuple().digits)+len(l.as_tuple().digits)+4,
                      max(w.adjusted(),l.adjusted())-min(w.as_tuple().exponent,l.as_tuple().exponent)+4,32)
        if precision>10000:raise ValueError('IHP cap_cmim dimensions exceed supported literal precision.')
        try:
            with localcontext() as context:
                context.prec=precision;area=w*l;perimeter=2*(w+l)
        except DecimalException as exc:raise ValueError('Invalid IHP cap_cmim geometry calculation.') from exc
        if not area.is_finite() or not perimeter.is_finite():raise ValueError('Nonfinite IHP cap_cmim physical geometry.')
        if physical:
            for key,wanted in (('a',area),('p',perimeter)):
                if key in fields and number(fields[key])!=wanted:raise ValueError('IHP cap_cmim explicit area or perimeter contradicts dimensions.')
            missing=[f'{key}={value}' for key,value in (('A',area),('P',perimeter)) if key.lower() not in fields]
            if not missing:
                changes.append(dict(instance=parts[0],physical_instance=parts[0],changed=False,reason='Validated locked cap_cmim physical reference',proof=proof))
                return original
            changes.append(dict(instance=parts[0],physical_instance=parts[0],changed=True,reason='Derive missing per-unit physical area/perimeter from the locked reader',proof=proof))
            return original+' '+' '.join(missing)
        name='C'+parts[0]
        result=f'{name} {parts[1]} {parts[2]} {parts[3]} w={fields["w"]} l={fields["l"]} m={fields["m"]} A={area} P={perimeter}'
        changes.append(dict(instance=parts[0],physical_instance=name,changed=True,reason='Locked cap_cmim physical LVS view; mm_ok is simulation-only',proof=proof))
        return result
    projected=re.sub(r'(?im)^[ \t]*[xc]\S+[^\n]*(?:\n[ \t]*\+[^\n]*)*',instance,text)
    cmim_lvs_unique_names(projected)
    return projected,changes


def cmim_lvs_unique_names(text):
    """Reject C-name collisions within each SPICE subcircuit containing MiM."""
    seen={};cmim=set();scope='';logical=re.sub(r'\n[ \t]*\+[ \t]*',' ',text)
    for line in logical.splitlines():
        parts=line.split()
        if not parts or parts[0].startswith('*'):continue
        if parts[0].lower()=='.subckt':scope=' '.join(parts[1:2]).casefold();continue
        if parts[0].lower()=='.ends':scope='';continue
        if not parts[0].lower().startswith('c'):continue
        key=(scope,parts[0].casefold());seen[key]=seen.get(key,0)+1
        if len(parts)>3 and parts[3].lower()=='cap_cmim':cmim.add(key)
    if any(seen[key]>1 for key in cmim):raise ValueError('IHP cap_cmim physical LVS instance name collides within its subcircuit.')


def ihp_lvs_defaults(text, technology):
    """Follow the locked upstream core-MOS LVS format for statistical mm_ok.

    IHP's simulation template enables mismatch; its LVS template has W/L/ng/m
    only. Netgen's setup currently does not remove mm_ok. Never drop geometry,
    multiplicity, unknown values, or parameters of other device classes.
    """
    from .model import file_digest
    root=Path(technology['package_root']).resolve();files=technology['package_lock']['files']
    proofs={};changes=[]
    for model in ('sg13_lv_nmos','sg13_lv_pmos'):
        entries=[b for b in technology['simulation']['catalog'].values()
                 if b.get('model')==model and Path(b.get('source','')).stem==model and not b.get('unavailable')]
        if len(entries)!=1:continue
        entry=entries[0];rel=entry['source'];path=(root/rel).resolve()
        if not path.is_relative_to(root) or not files.get(rel) or file_digest(path)!=files[rel]:
            raise ValueError('The IHP LVS symbol is missing or changed.')
        source=path.read_text(encoding='utf-8')
        if ('lvs_format="M@name @pinlist @model w=@w l=@l ng=@ng m=@m"' in source
                and 'format="@spiceprefix@name @pinlist @model w=@w l=@l ng=@ng m=@m mm_ok=@mm_ok"' in source):
            proofs[model]=dict(source=rel,sha256=files[rel])
    def instance(match):
        original=match[0];logical=re.sub(r'\n[ \t]*\+[ \t]*',' ',original)
        tokens=logical.split()
        if len(tokens)<6 or tokens[5].lower() not in proofs:return original
        if len(re.findall(r'(?i)\smm_ok\s*=',logical))!=1:return original
        rewritten,count=re.subn(r'(?i)[ \t]+mm_ok[ \t]*=[ \t]*(?:0(?:\.0*)?|1(?:\.0*)?)(?=\s|$)','',logical)
        if count:changes.append(dict(instance=tokens[0],parameter='mm_ok',reason='Statistical simulation flag omitted by the locked upstream LVS format',proof=proofs[tokens[5].lower()]))
        return rewritten if count else original
    return re.sub(r'(?im)^[ \t]*[xm]\S+[^\n]*(?:\n[ \t]*\+[^\n]*)*',instance,text),changes


def ihp_resistor_lvs_defaults(text,technology):
    """Apply the pinned resistor symbols' physical LVS view for Boolean mm_ok.

    Their simulation view exposes the statistical selector; their LVS view
    explicitly omits it. Keep the original schematic separately. This is a
    physical reference projection, never a statistical simulation equivalence.
    Unknown/duplicate/nonliteral values and every geometry/body/model token stay.
    """
    from .model import file_digest
    root=Path(technology['package_root']).resolve();files=technology['package_lock']['files'];proofs={};changes=[]
    for model in ('rsil','rppd','rhigh'):
        entries=[entry for entry in technology['simulation']['catalog'].values()
                 if entry.get('model')==model and Path(entry.get('source','')).stem==model and not entry.get('unavailable')]
        if len(entries)!=1:continue
        entry=entries[0];relative=entry['source'];path=(root/relative).resolve()
        if not path.is_relative_to(root) or not files.get(relative) or file_digest(path)!=files[relative]:
            raise ValueError('The IHP resistor LVS symbol is missing or changed.')
        source=path.read_text(encoding='utf-8');lvs=re.findall(r'(?m)^lvs_format="([^"\n]*)"',source);simulation=re.findall(r'(?m)^format="([^"\n]*)"',source)
        required=('w=@w','l=@l','m=@m')+(('b=@b',) if model!='rsil' else ())
        if (len(lvs)==len(simulation)==1 and all(token in lvs[0] and token in simulation[0] for token in required)
                and '@body' in lvs[0] and '@model' in lvs[0] and '@body @model' in simulation[0]
                and 'mm_ok=@mm_ok' in simulation[0] and 'mm_ok' not in lvs[0]
                and entry.get('prefix')=='X' and entry.get('pin_order')==['p','m','body']):
            proofs[model]=dict(source=relative,sha256=files[relative])
    def instance(match):
        original=match[0];logical=re.sub(r'\n[ \t]*\+[ \t]*',' ',original);tokens=logical.split()
        if len(tokens)<5 or tokens[4].lower() not in proofs:return original
        if len(re.findall(r'(?i)\smm_ok\s*=',logical))!=1:return original
        rewritten,count=re.subn(r'(?i)[ \t]+mm_ok[ \t]*=[ \t]*(?:0(?:\.0*)?|1(?:\.0*)?)(?=\s|$)','',logical)
        if count:changes.append(dict(instance=tokens[0],parameter='mm_ok',reason='Statistical selector omitted by the locked upstream resistor LVS format',proof=proofs[tokens[4].lower()]))
        return rewritten if count else original
    return re.sub(r'(?im)^[ \t]*x\S+[^\n]*(?:\n[ \t]*\+[^\n]*)*',instance,text),changes


def render(device, child=None, mode='simulation'):
    definition = device['native_spice']
    if definition['type'] == 'program':
        return definition['text']
    output = []
    from .native_vectors import signals
    def terminal(pin):
        return device['nets'][pin] if pin in device['nets'] else ' '.join(device['nets'][name] for name in signals(pin))
    if mode not in ('simulation','lvs'):raise ValueError('Choose simulation or LVS emission.')
    for token in definition.get('lvs_tokens',definition['tokens']) if mode=='lvs' else definition['tokens']:
        kind, value = token['kind'], token.get('value', '')
        if kind == 'literal': output.append(value)
        elif kind == 'instance': output.append(device['name'])
        elif kind == 'terminal': output.append(terminal(value))
        elif kind == 'terminals': output.append(' '.join(terminal(p) for p in device['symbol']['pin_order']))
        elif kind == 'cell': output.append(child['name'] if child else definition['model_name'])
        elif kind == 'parameter':
            if value not in definition['parameters']:
                raise ValueError(device['name'] + ': missing native parameter ' + value)
            output.append(str(definition['parameters'][value]))
        else: raise ValueError('Unknown native device token: ' + kind)
    text=''.join(output)
    if mode=='lvs':text,_=lvs_defaults(text)
    return text


def validate_device(device):
    definition = device.get('native_spice', {})
    if definition.get('diode_geometry') not in (None,'pre46-scale-1e-6'):
        raise ValueError('Unsupported explicit diode geometry convention.')
    if definition.get('version') != 1 or definition.get('type') not in ('device', 'program'):
        raise ValueError('Invalid native electrical definition for ' + device['name'])
    if not device.get('symbol'):
        raise ValueError('Native electrical definitions require an explicit symbol and terminal order.')
    if definition['type'] == 'program':
        if device['nets'] or not isinstance(definition.get('text'), str):
            raise ValueError('A simulation program has text and no electrical terminals.')
    else:
        if not isinstance(definition.get('parameters'), dict) or not definition.get('tokens'):
            raise ValueError('A native device needs parameters and an emission program.')
        for key, value in definition['parameters'].items():
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or not isinstance(value, str) or '\n' in value or '\r' in value:
                raise ValueError('Invalid native device parameter: ' + str(key))
            if 'tcleval' in value:
                raise ValueError('Executable Xschem expressions must be migrated before editing this parameter.')
        render(device, {'name': 'child'})
        if 'lvs_tokens' in definition:render(device, {'name':'child'}, 'lvs')


def asset_path(ident):
    if not re.fullmatch(r'[a-f0-9]{24}', ident):
        raise ValueError('Invalid native model asset identity.')
    return 'models/' + ident + '.spice'


def netlist(project, directory, mode='simulation'):
    from .wiring import rebuild
    from .interchange import source_spec, spice_name
    from .design_ops import parameters, resolved_device
    p = clone(project); validate(p)
    root = Path(directory).resolve(); root.mkdir(parents=True, exist_ok=True)
    assets = p['spice']['assets']
    from .catalog_migration import check_embedded_catalog, emit
    check_embedded_catalog(p)
    for ident, asset in assets.items():
        if hashlib.sha256(asset['text'].encode()).hexdigest() != asset['sha256']:
            raise ValueError('Model checksum mismatch: ' + asset.get('name', ident))
        atomic_write(root / asset_path(ident), asset['text'])
    atomic_write(root / 'model-files.json', json.dumps({asset_path(k): v['name'] for k, v in assets.items()}, indent=2))
    atomic_write(root / 'library-lock.json', json.dumps(p['spice'].get('library_lock', {}), indent=2))
    by = {c['id']: c for c in p['cells']}; top = by[p['top']]
    lines = ['* IC Design Studio native circuit: ' + p['name']]; definitions = set()
    from .native_vectors import devices as vector_devices, ports as vector_ports, global_nets
    if p.get('global_nets'):lines.append('.global '+' '.join(global_nets(p)))
    if p.get('parameters'):
        lines.append('.param ' + ' '.join(k + '=' + str(v) for k, v in p['parameters'].items()))
    for c in [top] + [c for c in p['cells'] if c is not top]:
        rebuild(c, p)
        defaults = {**c.get('spice_parameters', {}), **c.get('parameters', {})}
        if c is not top or mode=='lvs':
            lines.append('.subckt ' + c['name'] + ' ' + ' '.join(vector_ports(c['ports'])) + ''.join(' ' + k + '=' + str(v) for k, v in defaults.items()))
        elif defaults:
            lines.append('.param ' + ' '.join(k + '=' + str(v) for k, v in defaults.items()))
        context = parameters(c.get('parameters', {}), parameters(p.get('parameters', {})))
        lines.extend(c.get('spice_statements', [])); commands = []
        for original in vector_devices(c,p):
            d = original; definition = d.get('native_spice')
            if d.get('model_ref'):
                line=emit(d,p['pdk'],mode)
                from .ngspice_compat import legacy_catalog,declare
                from .catalog import binding_for
                if mode=='simulation' and (d['model_ref'].get('diode_geometry')=='pre46-scale-1e-6'
                        or legacy_catalog(p['pdk'],binding_for(p['pdk'],d))):
                    line=declare(line)
                lines.append(line);continue
            if definition:
                if definition['type'] == 'program':
                    if c is top or not definition.get('only_toplevel'):
                        commands.append(definition['text'])
                else:
                    line=render(d, by.get(d.get('cell')), mode)
                    if mode=='simulation' and definition.get('diode_geometry')=='pre46-scale-1e-6':
                        from .ngspice_compat import declare
                        line=declare(line)
                    lines.append(line)
                    if definition.get('definition'): definitions.add(definition['definition'])
                continue
            d = resolved_device(d, context); kind = d['kind']
            if kind == 'X':
                lines.append(d['name'] + ' ' + ' '.join(d['nets'][pin] for pin in vector_ports(by[d['cell']]['ports'])) + ' ' + by[d['cell']]['name'] + ''.join(' ' + k + '=' + str(v) for k, v in d.get('parameters', {}).items()))
                continue
            name = spice_name(d); nets = ' '.join(d['nets'].values())
            if kind in ('R', 'C', 'L'): suffix = str(scalar(d['value']))
            elif kind in ('V', 'I'): suffix = source_spec(d)
            elif kind in ('NMOS', 'PMOS'):
                pa = d['params']; model = 'studio_' + d['id']; polarity = -1 if kind == 'PMOS' else 1
                definitions.add(f'.model {model} {kind} (LEVEL=1 VTO={polarity*scalar(pa["vto"])} KP={scalar(pa["kp"])} LAMBDA={scalar(pa["lambda"])})')
                suffix = f'{model} W={scalar(pa["w"])} L={scalar(pa["l"])}'
            else: raise ValueError(d['name'] + ': migrate or bind this device before native SPICE generation.')
            lines.append(name + ' ' + nets + ' ' + suffix)
        lines.extend(commands)
        if c is not top or mode=='lvs': lines.append('.ends ' + c['name'])
    lines.extend(sorted(definitions)); lines.append('.end')
    text = '\n'.join(lines) + '\n'
    if mode=='lvs':
        from .native_analysis import circuit_text
        text=circuit_text(text)+'.end\n'
        cmim_lvs_unique_names(text)
    atomic_write(root / 'source.cir', text)
    return text


def run(project, cid, settings, executable, directory, progress=lambda *_: None):
    from .spice_program import run_program
    return run_program(project, cid, settings, executable, directory, progress, netlist,
                       'ngspice · native program', project['spice'].get('library_lock', {}), 'analysis_cases')
