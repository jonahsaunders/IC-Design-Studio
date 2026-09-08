"""Explicit, bounded SPICE-to-native import for editable circuits.

Reject unsupported statements rather than silently discarding circuit behavior.
PDK models resolve only against the selected locked technology.
"""
import re,shlex
from pathlib import Path
from .model import example,clone,uid,device,validate,scalar,PINS
from .catalog import create_device
from .xschem_io import source_value


def tokens(line):
    # Preserve quoted/braced arithmetic as a single token, including spaces.
    return re.findall(r"(?:[^\s\"'{}]+|\"[^\"]*\"|'[^']*'|\{[^{}]*\})+", line)


def assignments(parts):
    out={}
    for token in parts:
        if token.lower()=='params:':continue
        if '=' not in token:raise ValueError('Expected parameter=value assignment.')
        key,raw=token.split('=',1);key=key.lower()
        if key in out:raise ValueError('Duplicate parameter '+key)
        if raw.startswith(("'", '\"')):raw='{'+raw[1:-1]+'}'
        out[key]=raw
    return out


def import_spice(path,technology=None):
    path=Path(path);text=path.read_text(encoding='utf-8')
    if len(text)>10_000_000:raise ValueError('SPICE import is limited to 10 MB.')
    p=example('empty');p['name']=path.stem
    if technology:p['pdk']=clone(technology)
    top=p['cells'][0];cells={};current=top;models={};rows=[];report=[]
    lines=re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines()
    for number,line in enumerate(lines,1):
        line=line.strip()
        if not line or line.startswith('*'):continue
        if number==1 and not re.match(r'^[RCLVIMX]\w*\s',line,re.I) and not line.startswith('.'):continue
        parts=tokens(line);command=parts[0].lower()
        if command=='.subckt':
            if current is not top:raise ValueError('Nested .subckt declarations are unsupported.')
            end=next((i for i,t in enumerate(parts[2:],2) if '=' in t or t.lower()=='params:'),len(parts))
            c={'id':uid(),'name':parts[1],'ports':parts[2:end],'parameters':assignments(parts[end:]),'devices':[],'shapes':[]}
            if c['name'].lower() in cells:raise ValueError('Duplicate SPICE subcircuit.')
            cells[c['name'].lower()]=c;p['cells'].append(c);current=c
        elif command=='.ends':
            if current is top:raise ValueError('Unexpected .ends.')
            current=top
        elif command=='.model':
            match=re.fullmatch(r'\.model\s+(\S+)\s+(nmos|pmos)\s*\((.*)\)',line,re.I)
            if not match:raise ValueError('Only level-1 MOS .model cards can become generic native devices; use a PDK catalog for other models.')
            values=dict((k.lower(),v) for k,v in re.findall(r'(\w+)\s*=\s*([^\s)]+)',match[3]))
            if scalar(values.get('level',1))!=1 or set(values)-{'level','vto','kp','lambda'}:raise ValueError('MOS model contains unsupported parameters.')
            models[match[1].lower()]=(match[2].upper(),values)
        elif command in ('.include','.inc','.lib'):
            if not technology or not technology.get('package_lock'):raise ValueError('External model includes require a linked and locked PDK.')
            root=Path(technology['package_root']).resolve();file=(path.parent/parts[1].strip('\"\'')).resolve()
            if not file.is_relative_to(root) or file.relative_to(root).as_posix() not in technology['package_lock']['files']:raise ValueError('SPICE include is not part of the linked PDK lock.')
            if command=='.lib' and len(parts)==3:
                include=next((i for i in technology.get('simulation',{}).get('includes',[]) if i['path']==file.relative_to(root).as_posix()),None)
                aliases=[k for k,v in (include or {}).get('sections',{}).items() if v==parts[2]]
                if not aliases:raise ValueError('Imported model corner is not configured in this PDK.')
                p['analysis']['corner']='nominal' if 'nominal' in aliases else aliases[0]
        elif command=='.param':
            (p if current is top else current).setdefault('parameters',{}).update(assignments(parts[1:]))
        elif command=='.op':p['analysis']['type']='op'
        elif command=='.tran' and len(parts)==3:p['analysis'].update(type='tran',step=parts[1],stop=parts[2])
        elif command=='.temp' and len(parts)==2:p['analysis']['temperature']=scalar(parts[1])
        elif command=='.end':break
        elif command.startswith('.'):
            raise ValueError(f'Line {number}: {parts[0]} is not supported for editable import. Use Run SPICE testbench to execute the original deck.')
        else:rows.append((current,line,number))
    if current is not top:raise ValueError('Unterminated .subckt.')
    catalog=p['pdk'].get('simulation',{}).get('catalog',{})
    for cell,line,number in rows:
        parts=tokens(line);name=parts[0];kind=name[0].upper();x=180+(len(cell['devices'])%4)*240;y=160+(len(cell['devices'])//4)*200
        try:
            matches=[(key,e) for key,e in catalog.items() if not e.get('unavailable') and e.get('prefix')==kind and len(parts)>len(e['pin_order'])+1 and parts[len(e['pin_order'])+1].lower()==e['model'].lower()]
            if matches:
                key,e=matches[0];count=len(e['pin_order']);d=create_device(p['pdk'],key,name,x,y);d['nets']=dict(zip(e['pin_order'],parts[1:count+1]))
                from .catalog import import_emitted_parameters
                import_emitted_parameters(e,d,assignments(parts[count+2:]))
            elif kind in ('R','C','L'):
                if len(parts)!=4:raise ValueError('Passive model cards require a PDK device adapter.')
                d=device(kind,name,x,y,value=parts[3],nets=dict(zip(PINS[kind],parts[1:3])),model_mode='generic')
            elif kind in ('V','I'):
                d=device(kind,name,x,y,nets=dict(zip(PINS[kind],parts[1:3])));source_value(d,' '.join(parts[3:]))
            elif kind=='M':
                model=parts[5].lower()
                if model not in models:raise ValueError('MOS .model definition is missing or not a supported level-1 model.')
                polarity,pa=models[model];d=device(polarity,name,x,y,nets=dict(zip(PINS[polarity],parts[1:5])),model_mode='generic');dims=dict(t.lower().split('=',1) for t in parts[6:])
                if set(dims)-{'w','l'}:raise ValueError('Unsupported MOS instance parameter.')
                d['params'].update(w=dims.get('w','2u'),l=dims.get('l','.18u'),vto=str(abs(scalar(pa.get('vto','.45')))),kp=pa.get('kp','100u'),**{'lambda':pa.get('lambda','.02')})
            elif kind=='X':
                end=next((i for i,t in enumerate(parts) if '=' in t),len(parts));model=parts[end-1];nets=parts[1:end-1];params=assignments(parts[end:])
                if model.lower() in cells:
                    child=cells[model.lower()]
                    if len(nets)!=len(child['ports']):raise ValueError('Subcircuit terminal count mismatch.')
                    d=device('X',name,x,y,cell=child['id'],nets=dict(zip(child['ports'],nets)),parameters=params)
                else:
                    matches=[(k,e) for k,e in catalog.items() if e.get('model','').lower()==model.lower() and not e.get('unavailable') and len(e['pin_order'])==len(nets)]
                    if not matches:raise ValueError('No compatible model in the linked PDK: '+model)
                    key,e=matches[0];d=create_device(p['pdk'],key,name,x,y);d['nets']=dict(zip(e['pin_order'],nets));mapping=e.get('emit_parameters',{})
                    from .catalog import import_emitted_parameters
                    import_emitted_parameters(e,d,params)
            else:raise ValueError('Unsupported SPICE device '+kind)
            cell['devices'].append(d)
        except (ValueError,IndexError,KeyError) as e:raise ValueError(f'Line {number}: {e}') from e
    if not top['devices'] and len(p['cells'])>1:p['cells'].remove(top);p['top']=p['cells'][0]['id']
    validate(p);report.append('Imported explicit terminal nets and generated schematic positions. Original drawing geometry is not part of SPICE.');return p,report
