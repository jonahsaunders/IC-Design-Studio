"""Read stock SKY130, GF180MCU and IHP SG13G2 installations into a locked catalog."""
from __future__ import annotations
from pathlib import Path
from xml.etree import ElementTree
import json, re, shlex
from .model import example, digest, file_digest
from .catalog import create_device
from .symbol_io import import_symbol

FAMILIES = {
 'sky130': {'name':'SkyWater SKY130', 'docs':'https://skywater-pdk.readthedocs.io/en/main/', 'root':'sky130A'},
 'gf180mcu': {'name':'GlobalFoundries GF180MCU', 'docs':'https://gf180mcu-pdk.readthedocs.io/en/latest/', 'root':'gf180mcuD'},
 'ihp-sg13g2': {'name':'IHP SG13G2', 'docs':'https://ihp-open-pdk-docs.readthedocs.io/en/latest/', 'root':'ihp-sg13g2'},
}


def template_values(text):
    matches = list(re.finditer(r'(?<![\w])([A-Za-z_][\w]*)\s*=', text))
    return {m[1].lower(): text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip().strip('\\\"\'').strip() for i,m in enumerate(matches)}


def detect_root(path):
    root = Path(path).resolve()
    candidates = [root] + [root/n for n in ('sky130A','sky130B','gf180mcuA','gf180mcuB','gf180mcuC','gf180mcuD','ihp-sg13g2') if (root/n).is_dir()]
    valid = [p for p in candidates if (p/'libs.tech').is_dir()]
    if len(valid)!=1: raise ValueError('Select one PDK variant folder containing libs.tech (for example sky130A, gf180mcuD or ihp-sg13g2).')
    root=valid[0]
    if (root/'libs.tech/ngspice/sky130.lib.spice').exists(): family='sky130'
    elif (root/'libs.tech/ngspice/sm141064.ngspice').exists(): family='gf180mcu'
    elif (root/'libs.tech/ngspice/models/cornerMOSlv.lib').exists() or root.name=='ihp-sg13g2': family='ihp-sg13g2'
    else: raise ValueError('PDK layout is not recognized. Supported stock adapters: SKY130, GF180MCU and IHP SG13G2.')
    return root,family


def layer_table(root):
    files=sorted((root/'libs.tech/klayout').rglob('*.lyp'))
    layers=[]; pairs=set(); names=set()
    for file in files[:1]:
        for node in ElementTree.parse(file).getroot().iter():
            source=node.findtext('source','');m=re.match(r'^(\d+)/(\d+)(?:@.*)?$',source)
            if not m or (int(m[1]),int(m[2])) in pairs:continue
            raw=node.findtext('name','layer_'+m[1]+'_'+m[2]).split(' - ')[0]
            name=re.sub(r'[^A-Za-z0-9_.$-]','_',raw)[:55]
            if not name or not re.match('[A-Za-z_]',name):name='layer_'+name
            if name in names:name+='_'+m[1]+'_'+m[2]
            color=node.findtext('fill-color','#68a6f4')
            if not re.fullmatch('#[0-9a-fA-F]{6}',color):color='#68a6f4'
            layers.append(dict(name=name,gds=int(m[1]),datatype=int(m[2]),color=color,width=0,space=0));pairs.add((int(m[1]),int(m[2])));names.add(name)
    if not layers:raise ValueError('No numeric KLayout .lyp layer map was found under libs.tech/klayout.')
    return layers,files[:1]


def dependencies(root, paths):
    """Lock the full recursive include closure, including all declared corners."""
    todo=list(paths);found={};texts={}
    while todo:
        path=todo.pop().resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Model dependency is missing or outside the PDK: '+str(path))
        rel=path.relative_to(root).as_posix()
        if rel in found:continue
        text=path.read_text(encoding='utf-8',errors='replace');found[rel]=file_digest(path);texts[rel]=text
        for line in re.sub(r'\n\s*\+\s*',' ',text).splitlines():
            if not re.match(r'^\s*\.(include|inc|lib)\s',line,re.I):continue
            parts=shlex.split(line,comments=True)
            if parts[0].lower()=='.lib' and len(parts)<3:continue
            if len(parts)<2:raise ValueError('Invalid model include in '+rel)
            child=(path.parent/parts[1]).resolve()
            todo.append(child)
        if len(found)>20000:raise ValueError('PDK dependency limit exceeded.')
    return found,texts


def library_sections(path):
    return re.findall(r'^\s*\.lib\s+([A-Za-z0-9_]+)\s*$',path.read_text(errors='replace'),re.M|re.I)


def scan_local(path, progress=lambda message: None):
    root,family=detect_root(path);progress('Reading technology and model libraries…')
    ng=root/'libs.tech/ngspice';includes=[]
    if family=='sky130': masters=[ng/'sky130.lib.spice'];nominal='tt'
    elif family=='gf180mcu':
        masters=[ng/'sm141064.ngspice'];nominal='typical'
        if (ng/'smbb000149.spice').is_file():masters.append(ng/'smbb000149.spice')
    else:
        masters=sorted((ng/'models').glob('corner*.lib'));nominal='typ'
        if not masters:raise ValueError('No IHP corner model libraries found.')
    for master in masters:
        sections=library_sections(master)
        if sections:
            selected=next((s for s in (nominal,'tt','typ','typical','mos_tt','cap_typ','res_typ','dio_tt','hbt_typ','hbt_tt') if s in sections),None)
            if not selected:selected=next((s for s in sections if s.endswith(('_typ','_tt'))),None)
            if not selected:raise ValueError('No recognized nominal corner in '+master.name)
            includes.append({'path':master.relative_to(root).as_posix(),'sections':{'nominal':selected,**{s:s for s in sections}}})
        else:includes.append({'path':master.relative_to(root).as_posix()})
    if family=='gf180mcu' and (ng/'design.ngspice').exists():
        masters.insert(0,ng/'design.ngspice');includes.insert(0,{'path':'libs.tech/ngspice/design.ngspice'})
    if family=='gf180mcu':
        master=next(i for i in includes if i['path'].endswith('sm141064.ngspice'))
        available=set(master['sections'].values())
        corners={'nominal':'typical','typical':'typical','ff':'ff','ss':'ss','fs':'fs','sf':'sf'}
        master['sections']={k:v for k,v in corners.items() if v in available}
        for item in includes:
            if item['path'].endswith('/smbb000149.spice'):
                if not set(corners.values())<=set(item.get('sections',{}).values()):
                    raise ValueError('Missing GF180 high-voltage corner section.')
                item['sections']=dict(corners)
        # The MOS sections do not include the other device families. Load a
        # consistent combination; mixed MOS corners use nominal passives/BJTs.
        for group in ('bjt','diode','res','mimcap','moscap'):
            sections={k:group+'_'+(v if v in ('ff','ss') else 'typical') for k,v in master['sections'].items()}
            if any(v not in available for v in sections.values()):raise ValueError('Missing GF180 '+group+' corner section.')
            includes.append({'path':master['path'],'sections':sections})
        # Current MIM corner sections select the metal-stack-specific models
        # from sm141064_mim.spice. The retained legacy symbols instead call
        # cap_mim_1f0ff/1f5ff/2f0ff, defined only in this separate section.
        # Keep both sets; the corner section above supplies their parameters.
        if 'cap_mim' in available:
            includes.append({'path':master['path'],'section':'cap_mim'})
        # Match the versioned package: keep its original complete include
        # order, then append the optional independent high-voltage library.
        includes.sort(key=lambda item:item['path'].endswith('/smbb000149.spice'))
    if family=='ihp-sg13g2':
        for item in includes:
            sections=item.get('sections',{})
            for alias,suffix in [('slow','ss'),('fast','ff')]:
                match=next((v for v in sections.values() if v.endswith('_'+suffix)),None)
                if match:sections[alias]=match
                elif sections:sections[alias]=sections['nominal']
    files,texts=dependencies(root,masters)
    models={};primitives={}
    for rel,text in texts.items():
        for m in re.finditer(r'^\s*\.subckt\s+(\S+)\s+([^\n]+)',re.sub(r'\n\s*\+\s*',' ',text),re.M|re.I):
            pins=[]
            for token in m[2].split():
                if '=' in token or token.lower() in ('params:','.param'):break
                pins.append(token)
            models[m[1].lower()]={'pins':pins,'file':rel,'prefix':'X'}
        for m in re.finditer(r'^\s*\.model\s+(\S+)\s+(\w+)',text,re.M|re.I):
            prefix={'d':'D','npn':'Q','pnp':'Q','r':'R','c':'C','l':'L'}.get(m[2].lower(),'M')
            definition={'pins':None,'file':rel,'prefix':prefix}
            models.setdefault(m[1].lower(),definition)
            primitives.setdefault((m[1].lower(),prefix),definition)
    layers,lyps=layer_table(root)
    for file in lyps:files[file.relative_to(root).as_posix()]=file_digest(file)
    # Managed installations must retain the same physical rule/setup assets as
    # Add folder registrations. These files participate in revision identity.
    for folder in ('libs.tech/magic','libs.tech/netgen'):
        for file in sorted((root/folder).rglob('*')):
            if file.is_file() and file.resolve().is_relative_to(root):files[file.relative_to(root).as_posix()]=file_digest(file)
    tech=example('empty')['pdk'];tech.update(name=FAMILIES[family]['name']+' · '+root.name,revision='',status='local assets indexed · device simulation unverified',layers=layers,
        family=family,documentation=FAMILIES[family]['docs'],simulation={'includes':includes,'devices':{},'catalog':{}})
    if family in ('sky130','gf180mcu'):tech['simulation']['ngspice_compatibility']='hsa'
    if family=='ihp-sg13g2':tech['simulation']['requires_osdi']=True
    tech['physical']={'magic_technology':next((r for r in files if r.endswith('/'+root.name+'.tech')),''),
                     'netgen_setup':next((r for r in files if r.endswith('/'+root.name+'_setup.tcl')),''),
                     'native_generators':['sky130_1v8_mos','sky130_inverter'] if family=='sky130' else []}
    catalog=tech['simulation']['catalog'];progress('Indexing Xschem devices…')
    symbol_roots=[d for d in (root/'libs.tech/xschem').iterdir() if d.is_dir() and (d.name.endswith(('_pr','_devices')) or d.name=='symbols')]
    symbols=sorted(p for directory in symbol_roots for p in directory.glob('*.sym')) if symbol_roots else sorted((root/'libs.tech/xschem').glob('*.sym'))
    if not symbols:raise ValueError('No Xschem symbols found under libs.tech/xschem.')
    for sym in symbols:
        if not sym.resolve().is_relative_to(root):continue
        rel=sym.relative_to(root).as_posix();key=str(sym.relative_to(root/'libs.tech/xschem')).replace('\\','/')
        entry={'label':sym.stem,'kind':'PDK','category':'Other','source':rel,'model':sym.stem,'unavailable':''}
        try:
            symbol,meta,notes=import_symbol(sym);symbol['primitives']=[p for p in symbol['primitives'] if p['kind']!='text' or p['text'].lower() not in symbol['pins']];defaults=template_values(meta.get('template',''));fmt=' '.join(meta.get('format','').replace('\n+',' ').split())
            if not symbol['pins']:raise ValueError('No electrical pins in this symbol.')
            # Recognize this exact upstream PNP template without evaluating Tcl.
            pnp_format='tcleval(@spiceprefix@name @pinlist @model a=[ev7 { @w * @l }] p=[ev7 { ( @w + @l ) * 2 }] m=[ev { @m }] )'
            if family=='ihp-sg13g2' and defaults.get('model')=='pnpMPA' and fmt.replace('\\','')==pnp_format:
                fmt="@spiceprefix@name @pinlist @model a='@w * @l' p='(@w + @l) * 2' m=@m"
                notes.append('Static pnpMPA geometry adapter; upstream Tcl is not executed.')

            # Upstream hidden-body templates become explicit, wireable terminals.
            if ' @pinlist @body ' in fmt:
                body='b' if family=='sky130' and set(symbol['pins'])==set('dgs') else 'body'
                symbol['pins'][body]=[60,0]
                symbol['pin_order']=list(symbol['pins'])
                fmt=fmt.replace(' @pinlist @body ',' @pinlist ')
                notes.append('Hidden body net exposed as terminal '+body+'; connect it explicitly.')
            # Parse only declarative pinlist/model/parameter formats. Unknown Tcl,
            # conditional pins and compound primitive formats are visibly blocked.
            match=re.fullmatch(r'(@spiceprefix@name|[XMRCLDQ]@name|@name) @pinlist ([^\s]+)(.*)',fmt)
            if not match:raise ValueError('Symbol requires an unsupported netlist format or script.')
            model=match[2]
            for param in re.findall(r'@(\w+)',model):model=model.replace('@'+param,defaults.get(param.lower(),''))
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_.$-]*',model):raise ValueError('Dynamic model selection requires an explicit adapter.')
            if family=='gf180mcu' and key=='symbols/nfet_06v0_nvt.sym' and model=='nfet_06v0':
                from .gf180_native_binding import reviewed_model
                native=models.get('nfet_06v0_nvt')
                if native is None:raise ValueError('Native-threshold model is absent from the selected library closure.')
                model=reviewed_model(sym.read_bytes(),(root/native['file']).read_bytes())
                symbol['attributes']['template']=symbol['attributes']['template'].replace('model=nfet_06v0\n','model=nfet_06v0_nvt\n')
                notes.append('Reviewed public native-threshold symbol correction: select nfet_06v0_nvt; upstream model equations are unchanged.')
            if family=='sky130' and key=='sky130_fd_pr/res_generic_li.sym' and model=='sky130_fd_pr__res_generic_li':
                from .sky130_li_binding import MODEL,reviewed_model
                canonical=primitives.get((MODEL,'R'))
                if canonical is None:raise ValueError('Local-interconnect resistor model is absent from the selected library closure.')
                model=reviewed_model(sym.read_bytes(),(root/canonical['file']).read_bytes())
                symbol['attributes']['template']=symbol['attributes']['template'].replace('model=res_generic_li\n','model=res_generic_l1\n')
                notes.append('Reviewed public local-interconnect spelling correction: res_generic_li symbol selects res_generic_l1. Original model equations retained.')
            entry['model']=model
            definition=models.get(model.lower())
            if definition is None:raise ValueError('Model is absent from the selected ngspice library closure.')
            # A literal @name uses the SPICE device prefix from its declared
            # template name. It must not become X merely because the library
            # also defines a same-named Monte Carlo wrapper subcircuit.
            template_name=defaults.get('name','')
            if match[1]=='@name' and 'spiceprefix' not in defaults and re.fullmatch(r'[RCLDQM][A-Za-z0-9_]+',template_name,re.I):
                explicit=template_name[0].upper()
                definition=primitives.get((model.lower(),explicit))
                if definition is None:raise ValueError('The @name template requires a matching primitive .model declaration.')
            if definition['pins'] is not None and len(definition['pins'])!=len(symbol['pins']):raise ValueError('Symbol and model terminal counts differ; explicit pin mapping is required.')
            prefix=defaults.get('spiceprefix',match[1][0] if not match[1].startswith('@') else definition['prefix']).upper()
            emitted={};computed={};remaining=match[3]
            # Only numeric @parameter references and bounded arithmetic are accepted.
            assignment=re.compile(r"\b(\w+)=('[^']*'|\"[^\"]*\"|[^\s]+)")
            for m in assignment.finditer(match[3]):
                target=m[1].lower();raw=m[2].strip("'\"");refs=re.findall(r'@(\w+)',raw)
                if not refs:raise ValueError('Literal netlist terms need an explicit adapter.')
                if re.fullmatch(r'@\w+',raw):emitted[target]=raw[1:].lower()
                else:
                    computed_key='emit_'+target
                    computed[computed_key]=re.sub(r'@(\w+)',lambda hit:hit[1].lower(),raw)
                    emitted[target]=computed_key
                remaining=remaining.replace(m[0],'',1)
            if remaining.strip():raise ValueError('Netlist format contains unsupported literal or computed terms.')
            kind=meta.get('type','').lower();kind='NMOS' if kind=='nmos' and set(symbol['pins'])==set('dgsb') else 'PMOS' if kind=='pmos' and set(symbol['pins'])==set('dgsb') else 'PDK'
            category=kind if kind!='PDK' else ('Resistors' if 'resistor' in meta.get('type','') else 'Capacitors' if 'cap' in meta.get('type','') else 'Bipolar' if 'npn' in meta.get('type','') or 'pnp' in meta.get('type','') else 'Diodes' if 'diode' in meta.get('type','') else 'Other')
            if family=='ihp-sg13g2' and model in ('ntap1','ptap1'):
                category='Resistors'
            params={}
            defaults.update(computed)
            needed=set(emitted.values())
            # Include numeric helper defaults used by emitted formulas.
            todo=list(needed)
            while todo:
                k=todo.pop()
                if k not in defaults:raise ValueError('Missing default for model parameter '+k)
                for dep in re.findall(r'\b[A-Za-z_]\w*\b',defaults[k].lower()):
                    if dep in defaults and dep not in needed:needed.add(dep);todo.append(dep)
            for k in sorted(needed):
                params[k]={'default':defaults[k].lower(),'positive':k in ('w','l','nf','ng','m','mult'),'integer':k in ('nf','ng'),'derived':k in computed}
            if family=='ihp-sg13g2' and model=='cap_cmomi' and 'feed' in params:
                if not re.search(r'(?im)^\.param\s+none=0\s+same=1\s+double=2\s*$',texts[definition['file']]):raise ValueError('Unrecognized capacitor feed encoding.')
                params['feed']['choices']={'none':0,'same':1,'double':2}
            if family=='ihp-sg13g2' and model=='isolbox':
                from .ihp_isolation import constrain
                constrain(params,(root/definition['file']).read_bytes())
            if family=='gf180mcu' and model in ('nfet_10v0_asym','pfet_10v0_asym'):
                from .gf180_hv import constrain,NOTE
                constrain(model,params,(root/definition['file']).read_bytes())
                notes.append(NOTE)
            if family=='ihp-sg13g2' and model in ('ntap1','ptap1'):
                from .ihp_taps import constrain
                constrain(model,params,(root/definition['file']).read_bytes())
            if family=='sky130':
                from .sky130_fixed_geometry import CONTRACTS,NOTE,constrain
                if model in CONTRACTS:
                    constrain(model,params,(root/definition['file']).read_bytes())
                    notes.append(NOTE)
            scale={k:1e6 if family=='sky130' else 1 for k in ('w','l')}
            entry.update(kind=kind,category=category,pin_order=list(symbol['pin_order']),prefix=prefix,parameters=params,emit_parameters=emitted,parameter_scale=scale,symbol=symbol,model_source=definition['file'],notes=notes)
            if kind in ('NMOS','PMOS') and not {'w','l'}<=params.keys():raise ValueError('MOS symbol does not declare width and length.')
            # Includes formula evaluation and catches unsupported parameter defaults.
            catalog[key]=entry;tech['package_lock']={'id':root.name,'revision':'scan'}
            from .catalog import validate_catalog
            validate_catalog({'simulation':{'catalog':{key:entry}}})
            create_device(tech,key,'CHECK')
        except (ValueError,KeyError,IndexError,SyntaxError,ZeroDivisionError) as e:entry['unavailable']=str(e)
        catalog[key]=entry;files[rel]=file_digest(sym)
    # Keep attribution and model compilation sources with managed copies.
    for pattern in ('LICENSE*','COPYING*','NOTICE*','SOURCES*','UPSTREAM-LOCK.json','VERILOG-A-SOURCE-LOCK.json'):
        for file in root.glob(pattern):
            if file.is_file():files[file.relative_to(root).as_posix()]=file_digest(file)
    if family=='ihp-sg13g2':
        for file in (root/'libs.tech/verilog-a').rglob('*'):
            if file.is_file() and file.suffix.lower() not in ('.osdi','.so','.dll','.o','.obj','.pyc'):
                files[file.relative_to(root).as_posix()]=file_digest(file)
    # Immutable content identity includes symbols, models and layer presentation.
    tech.pop('package_lock',None);revision=digest({'files':files,'technology':tech})[:16];tech['revision']=revision
    return {'schema':1,'id':root.name,'revision':revision,'source_root':str(root),'family':family,'files':files,'technology':tech}
