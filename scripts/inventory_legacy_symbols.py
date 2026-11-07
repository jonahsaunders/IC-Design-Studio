"""Bounded source facts for the nine reviewed legacy symbol views; never execute them."""
import ast
import hashlib
import io
import re
import shlex
import tokenize
import xml.etree.ElementTree as ET

IDENT=r'[A-Za-z_][A-Za-z_0-9]*'
PIN=IDENT+r'(?:\[\d+(?::\d+)?\])?'
NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
sha=lambda text:hashlib.sha256(text.encode()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)
def hashed(text):return dict(expression_sha256=sha(text),expression_bytes=len(text.encode()),evaluated=False)
def literal(value,pattern=IDENT):
    require(isinstance(value,str) and len(value)<=256 and re.fullmatch(pattern,value),'unreviewed literal identifier');return value

def records(text):
    """Fully consume Xschem records while distinguishing braced data from operators."""
    require(len(text)<=100000,'source size bound');rows=[];i=0;line=1
    while i<len(text):
        if text[i].isspace():line+=text[i]=='\n';i+=1;continue
        if text[i]=='#':
            end=text.find('\n',i);i=len(text) if end<0 else end;continue
        start=line;tokens=[]
        while i<len(text) and text[i]!='\n':
            if text[i].isspace():i+=1;continue
            if text[i]=='{':
                begin=i+1;i+=1;depth=1;escaped=False
                while i<len(text) and depth:
                    ch=text[i]
                    if escaped:escaped=False
                    elif ch=='\\':escaped=True
                    elif ch=='{':depth+=1
                    elif ch=='}':depth-=1
                    line+=ch=='\n';i+=1
                require(depth==0,'unterminated Xschem block');tokens.append(('block',text[begin:i-1]))
            else:
                begin=i
                while i<len(text) and not text[i].isspace():
                    require(text[i] not in '{}"\\','unexpected Xschem word delimiter');i+=1
                tokens.append(('word',text[begin:i]))
            require(i==len(text) or text[i].isspace(),'adjacent Xschem tokens without separator')
        require(tokens and tokens[0][0]=='word','missing record operator');rows.append((start,tokens))
        require(len(rows)<=1000,'record bound')
    return rows

def properties(text):
    lexer=shlex.shlex(text,posix=True);lexer.whitespace_split=True;lexer.commenters='';out={}
    for token in lexer:
        require('=' in token,'unparsed property token');key,value=token.split('=',1);literal(key)
        require(key not in out,'duplicate property');out[key]=value
    return out

def headerless_xschem(text):
    source=records(text);require(source and source[0][1][0]==('word','K'),'expected reviewed headerless symbol')
    rows=[];attrs=None;pins=[];graphics=[]
    for line,tokens in source:
        op=tokens[0][1]
        if op=='K':
            require(attrs is None and len(tokens)==2 and tokens[1][0]=='block','duplicate/malformed symbol attributes')
            attrs=properties(tokens[1][1]);require(set(attrs)=={'type','format','template','extra'} and attrs['type']=='primitive','unreviewed symbol attributes')
        elif op in ('B','L'):
            require(len(tokens)==7 and all(k=='word' for k,v in tokens[:6]) and tokens[6][0]=='block','unreviewed box/line record')
            require(re.fullmatch(r'\d+',tokens[1][1]) and all(re.fullmatch(NUMBER,v) and len(v)<=32 for k,v in tokens[2:6]),'unreviewed coordinates')
            props=properties(tokens[6][1])
            if op=='B' and tokens[1][1]=='5':
                require(set(props)=={'name','dir'} and props['dir'] in ('in','out','inout'),'unreviewed terminal attributes')
                name=literal(props['name'],PIN);require(name not in pins,'duplicate pin');pins.append(name)
                rows.append(dict(kind='xschem-pin-declaration',name=name,line=line,direction=props['dir'],source_sequence=len(pins)-1,electrical_order_inferred=False))
            else:
                require(not props,'unreviewed drawing attributes');graphics.append(dict(operator=op,line=line,record_sha256=sha(repr(tokens))))
        elif op=='T':
            require(len(tokens)==9 and tokens[1][0]=='block' and tokens[-1][0]=='block' and all(k=='word' and re.fullmatch(NUMBER,v) and len(v)<=32 for k,v in tokens[2:8]),'unreviewed text record')
            props=properties(tokens[-1][1]);require(set(props)<= {'hcenter'} and all(v in ('true','false') for v in props.values()),'unreviewed text attributes')
            graphics.append(dict(operator=op,line=line,text_sha256=sha(tokens[1][1]),record_sha256=sha(repr(tokens))))
        else:raise ValueError('unreviewed Xschem operator '+op)
    require(attrs is not None and pins,'missing symbol or pin declarations')
    defaults=properties(attrs['template']);require('name' in defaults,'missing instance identity')
    for key,value in defaults.items():literal(value)
    extra=attrs['extra'].split();require(len(extra)==len(set(extra)) and set(extra)==set(defaults)-{'name'},'unreviewed extra/template relation')
    for key,value in defaults.items():rows.append(dict(kind='xschem-template-parameter',name=key,default_literal=value,template_sha256=sha(attrs['template'])))
    for index,key in enumerate(extra):rows.append(dict(kind='xschem-extra-attribute',name=key,source_sequence=index))
    pieces=attrs['format'].split();require(len(pieces)>=3 and pieces[0]=='@name','unreviewed format prefix');model=literal(pieces[-1])
    expanded={}
    for pin in pins:
        match=re.fullmatch('('+IDENT+r')\[(\d+):(\d+)\]',pin)
        if match:
            a,b=int(match[2]),int(match[3]);require(max(a,b)<=4096 and abs(a-b)<=256,'pin bus bound')
            for bit in range(a,b+(1 if a<=b else -1),1 if a<=b else -1):expanded[f'{match[1]}[{bit}]']=pin
        else:expanded[pin]=pin
    require(len(expanded)==sum(abs(int(m[1])-int(m[2]))+1 if (m:=re.search(r'\[(\d+):(\d+)\]',p)) else 1 for p in pins),'overlapping bus and scalar declarations')
    references=[];seen=set()
    for index,token in enumerate(pieces[:-1]):
        match=re.fullmatch(r'(@@?)('+PIN+')',token);require(match is not None,'unreviewed format expression')
        prefix,name=match.groups();resolved=(name in expanded if prefix=='@@' else name in defaults)
        kind='pin' if prefix=='@@' else 'attribute'
        references.append(dict(kind=kind,name=name,source_sequence=index,resolved=resolved,declared_pin=expanded.get(name) if kind=='pin' else None))
        if kind=='pin':seen.add(name)
    rows.insert(0,dict(kind='xschem-symbol-view',name='(no explicit symbol name)',type=attrs['type'],format='headerless-xschem',pins=pins,electrical_order_inferred=False))
    rows.append(dict(kind='xschem-netlist-template',name='format',**hashed(attrs['format']),references=references,model_identifier=model,model_binding_inferred=False,unreferenced_declared_pin_bits=sorted(set(expanded)-seen)))
    rows.append(dict(kind='xschem-model-reference',name=model,model_binding_inferred=False))
    for ref in references:
        if not ref['resolved']:rows.append(dict(kind='xschem-source-diagnostic',name=ref['name'],diagnostic='unresolved-template-'+ref['kind'],correction_inferred=False))
    if set(expanded)-seen:rows.append(dict(kind='xschem-source-diagnostic',name='format',diagnostic='unreferenced-declared-pin-bits',identifiers=sorted(set(expanded)-seen),correction_inferred=False))
    rows.append(dict(kind='xschem-graphic-accounting',name='graphics',records=graphics,geometry_evaluated=False))
    return rows

def qucs_component(text):
    require(len(text)<=100000 and '<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(),'unreviewed XML declaration')
    root=ET.fromstring(text);schema='{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation'
    require(root.tag=='Component' and set(root.attrib)=={schema,'library','names','schematic_id'},'unreviewed Qucs root')
    require(root.get(schema)=='Component.xsd','unreviewed component schema')
    names=[literal(n.strip()) for n in root.get('names').split(',')];require(len(names)==len(set(names)),'duplicate alias')
    children=list(root);require([n.tag for n in children]==['Description','Models','Netlists','Symbols','Parameters'],'unreviewed component sections')
    require(not (root.text or '').strip() and all(not (n.tail or '').strip() for n in root.iter()),'unparsed XML mixed content')
    rows=[dict(kind='qucs-component',name=n,aliases=names,library=root.get('library'),schematic_id=literal(root.get('schematic_id')),source_suffix_role='retained-legacy-source-view; applicability-not-inferred-from-old-suffix') for n in names]
    def plain(node,attrs):
        require(not len(node) and set(node.attrib)==set(attrs),'unreviewed '+node.tag+' shape')
        require(not (node.text or '').strip(),'unexpected '+node.tag+' text')
    desc,models,netlists,symbols,params=children
    require(not desc.attrib and not len(desc),'unreviewed description');rows.append(dict(kind='qucs-description-identity',name='Description',**hashed(desc.text or '')))
    for group in (models,netlists,symbols,params):require(not group.attrib and not (group.text or '').strip(),'unreviewed section content')
    require([n.tag for n in models]==['DefaultModel','SpiceModel'],'unreviewed models')
    for node in models:
        plain(node,{'value'});rows.append(dict(kind='qucs-model',name=literal(node.get('value')),model_type=node.tag,model_binding_inferred=False))
    require([n.tag for n in netlists]==['NgspiceNetlist','CDLNetlist'],'unreviewed netlist variants')
    for node in netlists:
        plain(node,{'value'});value=node.get('value');require(value,'empty netlist')
        refs=list(dict.fromkeys(re.findall(r'\{+('+IDENT+r')\}+',value)))
        rows.append(dict(kind='qucs-netlist-template',name=node.tag,**hashed(value),placeholder_identifiers=refs,template_evaluated=False,electrical_order_inferred=False))
    require(len(symbols)>0,'missing symbol references')
    ids=set()
    for node in symbols:
        require(node.tag=='Symbol' and set(node.attrib)=={'id'} and not (node.text or '').strip(),'unreviewed symbol')
        identity=literal(node.get('id'));require(identity not in ids,'duplicate symbol');ids.add(identity);refs=[]
        require(len(node)>0,'missing symbol files')
        for child in node:
            require(child.tag=='File' and not child.attrib and not len(child),'unreviewed symbol reference')
            ref=(child.text or '').strip();require(re.fullmatch(r'\{'+IDENT+r'\}/[A-Za-z_][A-Za-z_0-9.-]*\.sym',ref),'unreviewed symbol path');refs.append(ref)
        rows.append(dict(kind='qucs-symbol-reference',name=identity,references=refs,reference_resolution='external-variable-qualified; no installed binding inferred',electrical_order_inferred=False))
    declared=set()
    for node in params:
        require(node.tag=='Parameter' and set(node.attrib) in ({'name','unit','default_value','show'},{'name','unit','equation','show'}),'unreviewed parameter attributes')
        name=literal(node.get('name'));require(name not in declared,'duplicate parameter');declared.add(name)
    for node in params:
        require(node.get('show') in ('true','false') and len(node)==1 and node[0].tag=='Description' and not node[0].attrib and not len(node[0]) and not (node.text or '').strip(),'unreviewed parameter shape')
        name=node.get('name');value=dict(kind='qucs-parameter',name=name,unit=node.get('unit'),shown=node.get('show')=='true',description_sha256=sha(node[0].text or ''))
        require(re.fullmatch(r'[A-Za-z]*',value['unit']),'unreviewed unit')
        if 'default_value' in node.attrib:
            default=node.get('default_value');require(default=='' or re.fullmatch(IDENT+'|'+NUMBER,default),'unreviewed parameter default');value['default_literal']=default
        else:
            expression=node.get('equation');require(len(expression)<=2048,'equation bound');tree=ast.parse(expression,mode='eval')
            require(all(isinstance(n,(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Name,ast.Load,ast.Constant,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.UAdd,ast.USub)) for n in ast.walk(tree)),'unreviewed parameter equation')
            require(all(type(n.value) in (int,float) for n in ast.walk(tree) if isinstance(n,ast.Constant)),'nonnumeric equation')
            refs=list(dict.fromkeys(n.id for n in ast.walk(tree) if isinstance(n,ast.Name)));require(set(refs)<=declared,'unknown equation parameter')
            numeric=[token.string for token in tokenize.generate_tokens(io.StringIO(expression).readline) if token.type==tokenize.NUMBER]
            value['equation']=dict(**hashed(expression),referenced_parameters=refs,numeric_literals=numeric)
        rows.append(value)
    return rows


SKY_REPOSITORY='chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392'
IHP_REPOSITORY='IHP-GmbH/IHP-Open-PDK@5e6d592e4002946a4616f798c357f0f3c06cf3b6'
IHP_PATH='ihp-sg13g2/libs.tech/qucs-s/symbols/cparasitic.xml.old'
REVIEWED_SOURCES={('ihp-sg13g2',IHP_REPOSITORY,IHP_PATH):(None,qucs_component)}
for _process in ('sky130A','sky130B'):
    for _symbol in ('spm','audiodac','sky130_fd_sc_hvl__lsbuflv2hv_1','counter'):
        _path=_process+'/libs.tech/xschem/xschem_verilog_import/'+_symbol+'.sym'
        REVIEWED_SOURCES[(_process,SKY_REPOSITORY,_path)]=('common.tar.zst',headerless_xschem)


def legacy_symbol_views(row,text):
    """Route only nine reviewed pinned views; caller authenticates raw source bytes."""
    key=(row.get('family'),row.get('repository'),row.get('repository_path'))
    selected=REVIEWED_SOURCES.get(key)
    if selected is None or row.get('path')!=key[2] or row.get('archive')!=selected[0]:return None
    return selected[1](text)
