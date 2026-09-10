"""Declarative Xschem semantics shared by capture and native migration."""
import re
from pathlib import Path
from .model import NET, clone


def globals_in(text):
    text=re.sub(r'\n\s*\+\s*',' ',text)
    names=[]
    for line in text.splitlines():
        fields=line.split()
        if fields and fields[0].lower()=='.global':
            for name in fields[1:]:
                if not NET.fullmatch(name):raise ValueError('Unsupported global net name: '+name)
                names.append(name)
    return list(dict.fromkeys(names))


def ordered_symbol(reader, symbol, attrs, props, path):
    """Resolve @pinlist through a literal .subckt or captured include closure.

    Executable definitions stay in the external Xschem path. A conflicting
    interface is an error, never a guessed terminal permutation.
    """
    definition=props.get('spice_sym_def',attrs.get('spice_sym_def',''))
    formats=[props.get(key,attrs.get(key,'')) for key in ('format','lvs_format')]
    if not definition or not any('@pinlist' in fmt for fmt in formats):return symbol
    if 'tcleval' in definition or re.search(r'@[A-Za-z_]',definition):
        raise ValueError('Dynamic subcircuit definitions require Netlist with Xschem.')
    texts=[definition];visited=set()
    def include(text,parent):
        for line in re.sub(r'\n\s*\+\s*',' ',text).splitlines():
            match=re.match(r'^\s*\.(?:include|inc|lib)\s+("[^"]+"|\x27[^\x27]+\x27|\S+)(.*)$',line,re.I)
            if not match:continue
            ref=match[1].strip('"\x27')
            target=next((d['path'] for d in reader.deps if d['parent']==str(parent) and d['reference']==ref and d['path']),None)
            if target and target not in visited:
                visited.add(target);asset=reader.files.get(Path(target))
                if asset:texts.append(asset['text']);include(asset['text'],target)
    include(definition,path)
    declarations=[]
    for text in texts:
        for match in re.finditer(r'(?im)^\s*\.subckt\s+(\S+)([^\n]*)',re.sub(r'\n\s*\+\s*',' ',text)):
            pins=[]
            for field in match[2].split():
                if '=' in field or field.lower()=='params:':break
                pins.append(field)
            declarations.append((match[1],pins))
    preferred=str(props.get('model',Path(path).stem)).casefold()
    matches=[pins for name,pins in declarations if name.casefold()==preferred]
    if not matches and len(declarations)==1:matches=[declarations[0][1]]
    if not matches:raise ValueError('Cannot resolve the subcircuit terminal order. Use Netlist with Xschem or select an explicit model definition.')
    order=matches[0]
    if any(pins!=order for pins in matches) or len(order)!=len(set(order)) or set(order)!=set(symbol['pins']):
        raise ValueError('Subcircuit ports disagree with symbol pins: '+Path(path).name)
    result=clone(symbol);result['pin_order']=order
    result['port_order_source']='spice_sym_def'
    return result
