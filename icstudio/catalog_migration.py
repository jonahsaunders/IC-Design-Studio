"""Reviewed rebinding of captured electrical definitions to locked PDK devices.

Keep the imported model closure and control program. Catalog matching changes
the editable device representation only after its emitted terminals/parameters
and model-file provenance have been checked. No model substitution is guessed.
"""
import hashlib
import math
import re
from pathlib import Path
from .model import clone, digest, validate
from .catalog import create_device, import_emitted_parameters, parameter_values
from .native_spice import render
from .spice_import import tokens, assignments


def catalog_signature(technology):
    return digest({'lock':technology.get('package_lock'), 'simulation':technology.get('simulation')})


def instance_name(device, binding):
    prefix=device.get('model_ref',{}).get('instance_prefix')
    if prefix is None:return binding['prefix']+'_'+device['name'].replace('/','_')
    if not re.fullmatch(r'[A-Za-z_]*',prefix):raise ValueError('Invalid migrated instance prefix.')
    name=prefix+device['name']
    if name[0].upper()!=binding['prefix']:raise ValueError('Device name no longer matches its SPICE model prefix.')
    return name


def symbol_context(device, technology):
    """Refresh imported artwork's parameter text from editable native values."""
    from .catalog import binding_for
    context={'name':device['name'],'value':device['value'],'symname':device.get('cell',''),
             **device.get('params',{}),**device.get('parameters',{}),**device.get('symbol_context',{})}
    if device.get('model_ref'):
        values=parameter_values(binding_for(technology,device),device)
        for key in set(context)|set(values):
            if key.lower() in values:context[key]=format(values[key.lower()],'.12g')
    context['name']=device['name'];return context


def emit(device, technology, mode='simulation'):
    from .catalog import binding_for
    binding=binding_for(technology,device)
    if not binding:raise ValueError('A catalog device requires a model binding.')
    if mode=='lvs' and device['model_ref'].get('lvs'):
        copy=clone(device);copy['native_spice']=clone(device['model_ref']['lvs'])
        context=symbol_context(device,technology)
        copy['native_spice']['parameters'].update({k:context[k] for k in copy['native_spice']['parameters'] if k in context})
        return render(copy)
    values=emitted_parameters(device,technology)
    return (instance_name(device,binding)+' '+' '.join(device['nets'][p] for p in binding['pin_order'])+
            ' '+binding['model']+''.join(' '+k+'='+v for k,v in values.items()))


def emitted_parameters(device,technology):
    """Keep validated live arithmetic in SPICE and avoid re-rounding source units.

    Evaluating diffusion expressions into literals changes ngspice's parameter
    evaluation and freezes those dimensions when the schematic is edited in
    Xschem. Validate with the catalog, then let the simulator evaluate them.
    """
    from .catalog import binding_for,numeric_formula
    binding=binding_for(technology,device);values=parameter_values(binding,device)
    mapping=binding.get('emit_parameters',{});inverse={source:target for target,source in mapping.items()}
    original=device.get('model_ref',{}).get('source_parameters',{});result={}
    for target,source in mapping.items():
        value=values[source];text=format(value,'.12g')
        raw=device.get('model_params',{}).get(source,binding['parameters'][source]['default'])
        raw=binding['parameters'][source].get('choices',{}).get(str(raw),raw)
        # MOS dimensions are stored in SI units and already scaled by the catalog.
        dimension=source in ('w','l') and device['kind'] in ('NMOS','PMOS')
        if not dimension:
            expression=str(raw).strip().strip('\\\"\'{}').lower()
            try:numeric_formula(expression,{})
            except (ValueError,SyntaxError):
                names=set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b',expression))&set(values)
                if names<=set(inverse):
                    expression=re.sub(r'\b[A-Za-z_][A-Za-z0-9_]*\b',lambda m:inverse.get(m[0],m[0]),expression)
                    text="'"+expression+"'"
        if text==format(value,'.12g') and target in original:
            candidate=str(original[target]).strip()
            try:
                # Only numeric source spellings are reused; current live formulas
                # come from editable parameters, never a stale source snapshot.
                from .model import scalar
                if math.isclose(scalar(candidate),value,rel_tol=1e-14,abs_tol=0):text=candidate
            except ValueError:pass
        result[target]=text
    return result


def check_embedded_catalog(project):
    """Do not silently use a different catalog against the captured model files."""
    devices=[d for c in project['cells'] for d in c['devices'] if d.get('model_ref')]
    if not devices:return
    proof=project.get('spice',{}).get('catalog_binding',{})
    if proof.get('signature')!=catalog_signature(project['pdk']):
        raise ValueError('The embedded model catalog changed. Review native catalog migration again.')
    available={a['sha256'] for a in project['spice']['assets'].values()}
    for d in devices:
        hashes=proof.get('models',{}).get(d['model_ref']['device'],[])
        if not hashes or not set(hashes)<=available:
            raise ValueError(d['name']+': this catalog model is not in the captured model closure. Import its libraries and review migration again.')


def rebase_embedded_proof(previous, current):
    """Follow rewritten include paths only when exported model bytes match."""
    replacements={}
    for path,asset in current['native_migration']['archive']['source_files'].items():
        if not asset['kind'].startswith('Model'):continue
        sha=hashlib.sha256(asset['text'].encode()).hexdigest()
        if sha!=asset['sha256']:raise ValueError('Captured model provenance changed.')
        ident=hashlib.sha256((path+'\0'+sha).encode()).hexdigest()[:24]
        if ident in current['spice']['assets']:replacements[sha]=current['spice']['assets'][ident]['sha256']
    required={a['sha256'] for a in previous['spice']['assets'].values()}
    if not required<=replacements.keys():
        raise ValueError('Captured PDK model files changed or were removed. Review a new catalog migration before accepting different model definitions.')
    proof=clone(previous['spice']['catalog_binding'])
    proof['models']={key:[replacements[sha] for sha in hashes] for key,hashes in proof['models'].items()}
    return proof


def _source_hashes(project, technology):
    previous=project['spice'].get('catalog_binding',{})
    if previous.get('signature')==catalog_signature(technology):
        verified=clone(project);verified['pdk']=technology;check_embedded_catalog(verified)
        return clone(previous['models'])
    from .pdks import model_lines
    # Validate every locked file, including model dependencies and catalog symbols.
    model_lines(technology)
    root=Path(technology['package_root']).resolve()
    files=project.get('native_migration',{}).get('archive',{}).get('source_files',{})
    source={}
    for path,asset in files.items():
        if not asset['kind'].startswith('Model'):continue
        if hashlib.sha256(asset['text'].encode()).hexdigest()!=asset['sha256']:
            raise ValueError('Captured model provenance changed; import the original project again.')
        ident=hashlib.sha256((path+'\0'+asset['sha256']).encode()).hexdigest()[:24]
        embedded=project['spice']['assets'].get(ident)
        if embedded:source.setdefault(asset['sha256'],[]).append(embedded['sha256'])
    definitions={};texts={}
    for relative in technology['package_lock']['files']:
        path=root/relative
        if path.suffix.lower() not in ('.spice','.lib','.ngspice','.cir','.mod'):continue
        text=path.read_bytes().decode('utf-8');texts[relative]=text
        for name in re.findall(r'(?im)^\s*\.(?:model|subckt)\s+(\S+)',text):definitions.setdefault(name.casefold(),[]).append(relative)
    proof={}
    for key,entry in technology['simulation']['catalog'].items():
        if entry.get('unavailable'):continue
        candidates=[entry['model_source']] if entry.get('model_source') else definitions.get(entry['model'].casefold(),[])
        hashes=[]
        for relative in candidates:
            if relative not in texts:continue
            sha=hashlib.sha256(texts[relative].encode()).hexdigest()
            hashes+=source.get(sha,[])
        if hashes:proof[key]=sorted(set(hashes))
    # Re-review of an unchanged, already embedded catalog needs no source archive.
    return proof


def _statement(device):
    symbolic=clone(device)
    symbolic['nets']={pin:'studio_terminal_'+str(i) for i,pin in enumerate(device['symbol']['pin_order'])}
    lines=re.sub(r'\r?\n[ \t]*\+[ \t]*',' ',render(symbolic)).strip().splitlines()
    if len(lines)!=1:raise ValueError('Compound device statements need an explicit adapter.')
    parts=tokens(lines[0]);inverse={v:k for k,v in symbolic['nets'].items()}
    index=1
    while index<len(parts) and parts[index] in inverse:index+=1
    order=[inverse[v] for v in parts[1:index]]
    if len(order)!=len(device['nets']) or len(set(order))!=len(order):
        raise ValueError('Every emitted terminal must map to one symbol pin, including the body terminal.')
    return parts,order,index


def _bind(device, technology, key, parts, order, index):
    entry=technology['simulation']['catalog'][key]
    if entry.get('unavailable'):raise ValueError(entry['unavailable'])
    if parts[0][0].upper()!=entry['prefix'] or parts[index].casefold()!=entry['model'].casefold():
        raise ValueError('The selected catalog entry emits a different model or device prefix.')
    if len(entry['pin_order'])!=len(order):raise ValueError('The selected model has a different terminal count.')
    if not parts[0].endswith(device['name']):raise ValueError('The instance format cannot preserve designator edits.')
    prefix=parts[0][:-len(device['name'])]
    result=create_device(technology,key,device['name'])
    from .catalog import numeric_formula
    values=assignments(parts[index+1:]);pending=dict(values);resolved={}
    for _ in range(len(values)+1):
        for name,raw in list(pending.items()):
            try:resolved[name]=numeric_formula(raw,resolved)
            except (ValueError,SyntaxError,ZeroDivisionError):continue
            del pending[name]
        if not pending:break
    if pending:raise ValueError('Unresolved model expressions: '+', '.join(pending)+'. Keep the native SPICE definition until its parameter context is explicit.')
    import_emitted_parameters(entry,result,{k:str(v) for k,v in resolved.items()})
    # Keep arithmetic dependent on editable dimensions instead of freezing
    # diffusion areas/perimeters to their initial numeric values.
    mapping=entry.get('emit_parameters',{})
    for target,raw in values.items():
        expression=str(raw).strip().strip('\\\"\'{}').lower()
        try:numeric_formula(expression,{})
        except (ValueError,SyntaxError):
            expression=re.sub(r'\b[A-Za-z_][A-Za-z0-9_]*\b',lambda m:mapping.get(m[0],m[0]),expression)
            source=mapping[target]
            if source in ('w','l') and result['kind'] in ('NMOS','PMOS'):raise ValueError('Dimension expressions require a native parameter context.')
            result['model_params'][source]=expression
    # Defaults must not silently add behavior absent from the imported statement.
    emitted=parameter_values(entry,result);mapping=entry.get('emit_parameters',{})
    if set(values)!=set(mapping):raise ValueError('Emitted parameter sets differ; review the model adapter instead of adding or dropping defaults.')
    for target,raw in values.items():
        expected=resolved[target]
        if not math.isclose(expected,emitted[mapping[target]],rel_tol=1e-10,abs_tol=0):raise ValueError('Parameter units or formula differ for '+target+'.')
    rename=dict(zip(order,entry['pin_order']))
    preserved=clone(device);preserved.pop('native_spice',None)
    preserved.update({k:clone(result[k]) for k in ('kind','model_ref','model_params','params')})
    preserved['model_ref']['instance_prefix']=prefix
    preserved['model_ref']['source_parameters']=clone(values)
    if device['native_spice'].get('lvs_tokens'):
        definition=clone(device['native_spice']);definition['tokens']=definition.pop('lvs_tokens')
        for token in definition['tokens']:
            if token['kind']=='terminal':token['value']=rename[token['value']]
        preserved['model_ref']['lvs']=definition
    for field in ('nets','net_labels','terminal_ids','net_ids'):
        if field in preserved:preserved[field]={rename[k]:v for k,v in preserved[field].items()}
    symbol=preserved['symbol']
    for field in ('pins','pin_meta','pin_ids'):
        if field in symbol:symbol[field]={rename.get(k,k):v for k,v in symbol[field].items()}
    symbol['pin_order']=[rename[k] for k in device['symbol']['pin_order']]
    return preserved,rename


def review(project, technology, choices=None, require_complete=True):
    """Return a candidate plus per-device matches; source is never modified."""
    from .catalog import link_technology
    from .electrical_identity import terminal_id
    from .wiring import rebuild
    p=clone(project);choices=choices or {};rows=[];unmatched=0;converted=0
    if not p.get('spice'):raise ValueError('Convert the source to a native SPICE project before catalog matching.')
    proof=_source_hashes(p,technology)
    link_technology(p,technology)
    catalog=technology.get('simulation',{}).get('catalog',{})
    def partition(cell):
        groups={}
        for d in cell['devices']:
            for pin,net in d['nets'].items():groups.setdefault(net,[]).append(terminal_id(d,pin))
        return sorted(sorted(v) for v in groups.values())
    for cell in p['cells']:
        before=partition(cell)
        for device in cell['devices']:
            if device.get('model_ref'):continue
            info=device.get('native_spice',{})
            if info.get('type')!='device' or device['kind']=='X':continue
            source_key=cell['name']+'/'+device['name']
            chosen=choices.get(source_key,choices.get(device['id'],''))
            row={'cell':cell['id'],'object':device['id'],'source_key':source_key,'subject':device['name'],'status':'Needs attention','detail':'','choices':[],'selected':chosen}
            try:
                parts,order,index=_statement(device)
                # Generic sources/passives already have independent native emission;
                # only devices referring to a model require catalog rebinding.
                if parts[0][0].upper() in 'RCLVI' and index<len(parts):
                    try:
                        from .model import scalar
                        scalar(parts[index]);row.update(status='Migrated',detail='Native primitive retained with its exact electrical definition.');rows.append(row);continue
                    except ValueError:pass
                    if parts[0][0].upper() in 'VI' and (parts[index].upper() in ('DC','AC') or parts[index].upper().startswith(('PULSE(','SIN(','PWL('))):
                        row.update(status='Migrated',detail='Native source waveform retained.');rows.append(row);continue
                if index>=len(parts):raise ValueError('No model identifier in the device statement.')
                matches=[k for k,e in catalog.items() if not e.get('unavailable') and e['model'].casefold()==parts[index].casefold() and e['prefix']==parts[0][0].upper() and len(e['pin_order'])==len(order)]
                row['choices']=matches
                selected=chosen
                if not selected and len(matches)==1:selected=matches[0]
                if not selected:
                    exact=[k for k in matches if catalog[k].get('label')==info.get('model_name')]
                    if len(exact)==1:selected=exact[0]
                if not selected:raise ValueError('Choose a matching catalog entry.' if matches else 'No matching model in this PDK revision. The original device is preserved.')
                row['selected']=selected
                if selected not in matches:raise ValueError('The selected catalog entry does not match this model and terminal count.')
                if selected not in proof:raise ValueError('The model definition does not match the captured files in this PDK revision. Original models are preserved.')
                bound,rename=_bind(device,technology,selected,parts,order,index)
                if device.get('physical_binding'):raise ValueError('Remove or review the existing geometry binding before changing terminal roles.')
                for label in cell.get('labels',[]):
                    anchor=label.get('anchor',{})
                    if anchor.get('kind')=='pin' and anchor.get('id')==device['id']:anchor['pin']=rename[anchor['pin']]
                for pin in cell.get('layout_pins',[]):
                    if pin['device_id']==device['id']:pin['pin']=rename[pin['pin']]
                device.clear();device.update(bound);converted+=1
                row.update(status='Migrated',selected=selected,detail='Catalog '+selected+': model source, emitted terminal order, numeric parameters and units verified. Original symbol geometry and instance name retained.')
            except (ValueError,KeyError,IndexError,SyntaxError) as exc:row['detail']=str(exc);unmatched+=1
            rows.append(row)
        rebuild(cell,p)
        if partition(cell)!=before:raise ValueError('Catalog migration changed terminal connectivity.')
    p['spice']['catalog_binding']={'version':1,'signature':catalog_signature(technology),'models':proof}
    check_embedded_catalog(p);validate(p)
    status='Complete' if not unmatched and all(r.get('status')=='Migrated' for r in p.get('native_migration',{}).get('items',[])) else 'Needs attention'
    report={'version':1,'status':status,'converted':converted,'unmatched':unmatched,'items':rows,'pdk':clone(technology['package_lock'])}
    p.setdefault('native_migration',{})['catalog']=report
    p['native_migration']['status']=status
    warnings=[r for r in p.get('native_migration',{}).get('items',[]) if r.get('status')!='Migrated']
    return {'candidate':None if require_complete and unmatched else p,'status':status,'items':rows+warnings,'converted':converted,'unmatched':unmatched}
