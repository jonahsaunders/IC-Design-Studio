"""Nonexecuting bounded declaration readers for six pinned layer/stack views.

These record source facts. They do not evaluate geometry, reconstruct a process,
certify dimensions/electrical properties or resolve runtime tool behavior.
"""
import ast
from collections import Counter
import hashlib
import re
import xml.etree.ElementTree as ET

ID=r'[A-Za-z_][A-Za-z0-9_]*'
NUM=r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
def require(ok,message):
    if not ok:raise ValueError('Physical declarations: '+message)
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def integer(text):
    require(re.fullmatch(r'[0-9]{1,6}',text),'unsupported layer/datatype literal');return int(text)
def number(text):
    require(len(text)<=128 and re.fullmatch(NUM,text),'unsupported decimal literal');return text
def line_identity(text):return dict(expression_sha256=digest(text),expression_bytes=len(text.encode()),evaluated=False)
def uncomment(text,marker='#'):
    quote=None
    for i,c in enumerate(text):
        if c=='\\':raise ValueError('Physical declarations: unsupported escaped/dynamic string')
        if c in ('"',"'"):
            if quote==c:quote=None
            elif quote is None:quote=c
        elif c==marker and quote is None:return text[:i].strip()
    require(quote is None,'unterminated quoted source field');return text.strip()
def lines(text,marker='#'):
    require(len(text)<=100_000,'source too large for bounded grammar')
    for line,raw in enumerate(text.splitlines(),1):
        if not raw.strip() or raw.lstrip().startswith(marker):continue
        value=uncomment(raw,marker)
        if value:yield line,value


def python_layers(text):
    require(len(text)<=100_000,'source too large for bounded grammar');tree=ast.parse(text);rows=[];declared={}
    for node in tree.body:
        if isinstance(node,ast.Assign):
            require(len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and isinstance(node.value,ast.Dict),'nonliteral Python layer mapping')
            owner=node.targets[0].id;require(owner not in declared,'redefined Python layer dictionary');declared[owner]=set()
            rows.append(dict(kind='python-layer-map-declaration',name=owner,line=node.lineno,entries=len(node.value.keys)))
            for key,value in zip(node.value.keys,node.value.values):
                require(isinstance(key,ast.Constant) and isinstance(key.value,str) and re.fullmatch(ID,key.value),'nonliteral Python layer name')
                require(key.value not in declared[owner],'duplicate Python layer key');declared[owner].add(key.value)
                require(isinstance(value,ast.Tuple) and len(value.elts)==2 and all(isinstance(v,ast.Constant) and type(v.value) is int and 0<=v.value<=999999 for v in value.elts),'nonliteral Python layer pair')
                rows.append(dict(kind='python-layer-mapping',name=key.value,owner=owner,layer=value.elts[0].value,datatype=value.elts[1].value,line=key.lineno))
        elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            call=node.value
            require(isinstance(call.func,ast.Name) and call.func.id=='print' and len(call.args)==1 and not call.keywords,'unreviewed Python statement')
            sub=call.args[0]
            require(isinstance(sub,ast.Subscript) and isinstance(sub.value,ast.Name) and isinstance(sub.slice,ast.Constant) and isinstance(sub.slice.value,str),'unreviewed Python reference')
            owner=sub.value.id;key=sub.slice.value;require(key in declared.get(owner,set()),'missing Python mapping reference')
            rows.append(dict(kind='python-layer-lookup-reference',name=key,owner=owner,operation='print',line=node.lineno,executed=False))
        else:raise ValueError('Physical declarations: unsupported Python source statement')
    require(bool(declared),'no literal Python layer mappings');return rows


def layer_map(text):
    rows=[];purposes={'VIA','NET','SPNET','PIN','LEFPIN','FILL','LEFOBS','ALL'}
    for line,value in lines(text):
        parts=value.split();require(len(parts)==4,'invalid layer map field count');name,purpose,layer,datatype=parts
        require(re.fullmatch(ID,name),'nonliteral map name')
        if name=='NAME':
            require(re.fullmatch(ID+r'(?:/(?:PIN|LABEL))?',purpose),'unsupported label map target')
            target=purpose.split('/');row=dict(kind='layer-label-mapping',name=target[0],purpose=target[1] if len(target)==2 else None)
        else:
            selected=purpose.split(',');require(all(p in purposes for p in selected) and len(set(selected))==len(selected),'unsupported layer purpose')
            row=dict(kind='layer-purpose-mapping',name=name,purposes=selected)
        rows.append(dict(**row,record_type=name,layer=integer(layer),datatype=integer(datatype),line=line))
    require(bool(rows),'empty layer map');return rows


def expression(value,known,mode):
    allowed='|&-' if mode=='d25' else '+-';tokens=[];at=0;refs=[];numbers=[];inputs=[];operators=[]
    token_re=re.compile(r'\s*(input\s*\(\s*[0-9]+\s*,\s*[0-9]+\s*\)|'+ID+r'|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)|[|&+\-])')
    while at<len(value):
        match=token_re.match(value,at);require(match is not None,'unsupported expression token');tokens.append(match[1]);at=match.end()
    require(0<len(tokens)<=128 and len(tokens)%2==1,'incomplete bounded expression')
    for i,token in enumerate(tokens):
        if i%2:require(token in allowed,'unsupported expression operator');operators.append(token);continue
        if token.startswith('input') and re.fullmatch(r'input\s*\(.*\)',token):
            require(mode=='d25','unexpected input call');match=re.fullmatch(r'input\s*\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)',token)
            inputs.append(dict(layer=integer(match[1]),datatype=integer(match[2])))
        elif re.fullmatch(ID,token):require(token in known,'unknown named expression input '+token);refs.append(token)
        else:require(mode=='xs','unexpected number in layer expression');numbers.append(number(token))
    return dict(**line_identity(value),references=refs,numeric_literals=numbers,operators=operators,input_layers=inputs)


def d25(text):
    require(len(text)<=100_000 and not re.search(r'<!DOCTYPE|<!ENTITY',text,re.I),'unsupported XML entities')
    try:root=ET.fromstring(text)
    except ET.ParseError as error:raise ValueError('Physical declarations: malformed d25 XML') from error
    require(root.tag=='klayout-macro' and not root.attrib and not (root.text or '').strip(),'unknown d25 XML root')
    allowed={'description','version','category','prolog','epilog','doc','autorun','autorun-early','priority','shortcut','show-in-menu','group-name','menu-path','interpreter','dsl-interpreter-name','text'}
    children={};rows=[]
    for child in root:
        require(child.tag in allowed and child.tag not in children and not child.attrib and len(child)==0 and not (child.tail or '').strip(),'unsupported macro metadata structure');children[child.tag]=child.text or ''
        if child.tag!='text':rows.append(dict(kind='d25-macro-setting',name=child.tag,**line_identity(child.text or '')))
    require(children.get('interpreter')=='dsl' and children.get('dsl-interpreter-name')=='d25-dsl-xml','unknown macro interpreter')
    require('text' in children and all(not children.get(name,'').strip() for name in ('prolog','epilog')),'unparsed macro execution body')
    known=set();displays=set()
    for line,value in lines(children['text']):
        if match:=re.fullmatch('('+ID+r')\s*=\s*(.+)',value):
            name,expr=match.groups();require(name not in known,'duplicate layer definition');facts=expression(expr,known,'d25');known.add(name)
            rows.append(dict(kind='d25-layer-declaration',name=name,text_line=line,**facts))
        else:
            match=re.fullmatch(r'z\(\s*('+ID+r')\s*,\s*name:\s*"([A-Za-z_][A-Za-z0-9_>\-]*)"\s*,\s*zstart:\s*('+NUM+r')\s*,\s*height:\s*('+NUM+r')\s*,\s*color:\s*(0x[0-9A-Fa-f]{6})\s*\)',value)
            require(match is not None,'unknown d25 declaration');source,name,zstart,height,color=match.groups();require(source in known,'missing d25 layer input');require(name not in displays,'duplicate d25 display name');displays.add(name)
            rows.append(dict(kind='d25-display-layer',name=name,source_layer=source,zstart_literal=number(zstart),height_literal=number(height),color_literal=color,text_line=line,**line_identity(value),geometry_evaluated=False))
    require(bool(known) and bool(displays),'empty d25 declarations');return rows


def xsection(text):
    rows=[];known=set();occurrences=Counter()
    for line,value in lines(text):
        if match:=re.fullmatch('('+ID+r')\s*=\s*(.+)',value):
            name,expr=match.groups();facts=line_identity(expr);kind='xsection-variable-declaration'
            if match:=re.fullmatch(r'layer\("([0-9]+)/([0-9]+)"\)',expr):
                facts.update(layer=integer(match[1]),datatype=integer(match[2]));kind='xsection-input-layer'
            elif expr=='bulk':facts.update(operation='bulk',references=[])
            elif match:=re.fullmatch(r'mask\(('+ID+r')\)\.grow\(('+ID+r')\)',expr):
                refs=list(match.groups());require(all(ref in known for ref in refs),'missing xsection grow input');facts.update(operation='grow',references=refs)
            elif match:=re.fullmatch(r'deposit\(([^(),]+)(?:,\s*('+NUM+r'))?\)',expr):
                facts.update(expression(match[1].strip(),known,'xs'));facts.update(operation='deposit',lateral_literal=number(match[2]) if match[2] else None)
                # The whole declaration identity also covers the lateral argument.
                facts.update(line_identity(expr))
            else:facts.update(expression(expr,known,'xs'))
            rows.append(dict(kind=kind,name=name,line=line,assignment_index=occurrences[name],**facts,geometry_evaluated=False));occurrences[name]+=1;known.add(name)
        elif match:=re.fullmatch(r'height\(('+NUM+r')\)',value):
            rows.append(dict(kind='xsection-setting',name='height',literal=number(match[1]),line=line,**line_identity(value)))
        elif match:=re.fullmatch(r'planarize\(\s*:to\s*=>\s*('+ID+r')\s*,\s*:into\s*=>\s*('+ID+r')\s*\)',value):
            require(all(ref in known for ref in match.groups()),'missing planarize reference')
            rows.append(dict(kind='xsection-operation',name='planarize',references=list(match.groups()),line=line,**line_identity(value),geometry_evaluated=False))
        elif match:=re.fullmatch(r'output\("([0-9]+)/([0-9]+)"\s*,\s*('+ID+r')\)',value):
            require(match[3] in known,'missing output material')
            rows.append(dict(kind='xsection-output-layer',name=match[3],layer=integer(match[1]),datatype=integer(match[2]),line=line,**line_identity(value),geometry_evaluated=False))
        else:raise ValueError('Physical declarations: unknown xsection statement')
    require(bool(rows),'empty xsection source');return rows


def itf(text):
    rows=[];declarations={};references=[];technology=False
    attrs={'DIELECTRIC':{'THICKNESS','ER'},'CONDUCTOR':{'THICKNESS','WMIN','SMIN','RPSQ','LAYER_TYPE'},'VIA':{'FROM','TO','AREA','RPV'}}
    for line,value in lines(text,'$'):
        if match:=re.fullmatch(r'TECHNOLOGY\s*=\s*('+ID+r')',value):
            require(not technology,'duplicate ITF technology');technology=True;rows.append(dict(kind='itf-technology',name=match[1],line=line));continue
        match=re.fullmatch(r'(DIELECTRIC|CONDUCTOR|VIA)\s+('+ID+r')\s*\{([^{}]*)\}',value)
        require(match is not None,'unsupported ITF statement');kind,name,body=match.groups();settings=[];keys=set();at=0
        for field in re.finditer('('+ID+r')\s*=\s*('+ID+'|'+NUM+r')',body):
            require(not body[at:field.start()].strip(),'unparsed ITF attribute');at=field.end();key,val=field.groups();require(key in attrs[kind] and key not in keys,'unsupported/duplicate ITF attribute');keys.add(key)
            if key=='LAYER_TYPE':require(val in ('GATE','DIFFUSION'),'unsupported ITF layer type')
            elif key in ('FROM','TO'):require(re.fullmatch(ID,val),'nonliteral ITF reference');references.append((name,key,val,line))
            else:number(val)
            settings.append(dict(name=key,literal=val,**line_identity(val)))
        require(not body[at:].strip() and bool(settings),'missing/unparsed ITF fields')
        required={'DIELECTRIC':{'THICKNESS','ER'},'CONDUCTOR':{'THICKNESS','WMIN','SMIN','RPSQ'},'VIA':{'FROM','TO','AREA','RPV'}}
        require(required[kind]<=keys,'missing required bounded ITF fields')
        indices=declarations.setdefault((kind,name),[]);index=len(indices);indices.append(line)
        rows.append(dict(kind='itf-stack-declaration',name=name,stack_type=kind,occurrence_index=index,line=line,attributes=settings,**line_identity(body),geometry_or_electrical_value_qualified=False))
        if index:rows.append(dict(kind='itf-source-diagnostic',name=name,diagnostic='repeated-stack-name',stack_type=kind,lines=list(indices),correction_inferred=False))
    require(technology and bool(declarations),'missing ITF technology/stack')
    for owner,key,target,line in references:
        rows.append(dict(kind='itf-layer-reference',name=target,owner=owner,attribute=key,line=line,target_lines=declarations.get(('CONDUCTOR',target),[]),runtime_binding_inferred=False))
    return rows


GF_REPOSITORY='fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr@4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c'
IHP_REPOSITORY='IHP-GmbH/IHP-Open-PDK@5e6d592e4002946a4616f798c357f0f3c06cf3b6'
REVIEWED_SOURCES={
    ('gf180mcu',GF_REPOSITORY,'cells/klayout/pymacros/cells/layers_def.py'):python_layers,
    ('gf180mcu',GF_REPOSITORY,'tech/klayout/gf180mcu.map'):layer_map,
    ('ihp-sg13g2',IHP_REPOSITORY,'ihp-sg13g2/libs.tech/klayout/tech/sg13g2.map'):layer_map,
    ('ihp-sg13g2',IHP_REPOSITORY,'ihp-sg13g2/libs.tech/klayout/tech/d25/sg13g2_beol.lyd25'):d25,
    ('ihp-sg13g2',IHP_REPOSITORY,'ihp-sg13g2/libs.tech/klayout/tech/xsect/sg13g2_for_EM.xs'):xsection,
    ('ihp-sg13g2',IHP_REPOSITORY,'ihp-sg13g2/libs.tech/parasitics/itf/sg13g2_typ.itf'):itf,
}


def physical_views(row,text):
    """Dispatch only the six reviewed repository paths and pinned families.

    Authentication of the original Git graph/blob remains the caller's job.
    Other paths and revisions remain unresolved for the existing audit routing.
    """
    key=(row.get('family'),row.get('repository'),row.get('repository_path'))
    parser=REVIEWED_SOURCES.get(key)
    if parser is None or row.get('path')!=key[2]:return None
    return parser(text)
