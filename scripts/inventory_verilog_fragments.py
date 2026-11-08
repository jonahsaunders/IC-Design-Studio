"""Bounded Verilog-fragment syntax inventory; never evaluate, elaborate or simulate."""
import hashlib
import re
from dataclasses import dataclass

def require(ok,message):
    if not ok:raise ValueError(message)
sha=lambda text:hashlib.sha256(text.encode()).hexdigest()
IDENT=r'[A-Za-z_$][A-Za-z_0-9$]*'
BASED=r"(?:[0-9][0-9_]*\s*)?'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+"
DECIMAL=r'(?:[0-9][0-9_]*(?:\.[0-9_]+)?)(?:[eE][+-]?[0-9_]+)?'
KEYWORDS={'wire','reg','integer','parameter','localparam','always','initial','begin','end','if','else','case','casex','casez','endcase','default','assign','posedge','negedge','or','module','endmodule','function','endfunction','task','endtask','generate','endgenerate','for','while','repeat','forever','input','output','inout'}

@dataclass(frozen=True)
class Token:
    kind:str
    value:str
    line:int
    start:int
    end:int

def tokenize(text):
    require(len(text)<=100000,'fragment size bound');tokens=[];i=0;line=1
    while i<len(text):
        ch=text[i]
        if ch.isspace():line+=ch=='\n';i+=1;continue
        if text.startswith('//',i):
            end=text.find('\n',i);i=len(text) if end<0 else end;continue
        if text.startswith('/*',i):
            end=text.find('*/',i+2);require(end>=0,'unterminated Verilog comment');line+=text[i:end+2].count('\n');i=end+2;continue
        begin=i;start_line=line
        if ch=='"':
            i+=1
            while i<len(text) and text[i]!='"':
                require(text[i]!='\n','unreviewed multiline Verilog string')
                if text[i]=='\\':require(i+1<len(text) and text[i+1] not in '\r\n','unreviewed string escape/newline');i+=2
                else:i+=1
            require(i<len(text),'unterminated Verilog string');i+=1;kind='string';value=text[begin:i]
        elif ch=='`':
            m=re.match(IDENT,text[i+1:]);require(m is not None,'unreviewed macro token');i+=1+len(m[0]);kind='macro';value=m[0]
        else:
            match=re.match(BASED,text[i:]) or re.match(DECIMAL,text[i:])
            if match:
                value=match[0];i+=len(value);kind='number'
                require('\n' not in value and '\r' not in value,'unreviewed multiline number token')
                if "'" in value:
                    digits=value.split("'",1)[1];digits=digits[1:] if digits[0] in 'sS' else digits;base=digits[0].lower();allowed={'b':'01xXzZ?_','o':'01234567xXzZ?_','d':'0123456789xXzZ?_','h':'0123456789abcdefABCDEFxXzZ?_'}[base]
                    require(all(c in allowed for c in digits[1:]),'invalid based-number digit')
            else:
                match=re.match(IDENT,text[i:])
                if match:value=match[0];i+=len(value);kind='keyword' if value in KEYWORDS else 'name'
                else:
                    match=re.match(r'===|!==|<<<|>>>|==|!=|<=|>=|&&|\|\||<<|>>|~\||~&|~\^|\^~|[()\[\]{},;:?@#=+*/%&|^~!<>-]',text[i:]);require(match is not None,'unreviewed Verilog character at line '+str(line));value=match[0];i+=len(value);kind='operator'
        require(i-begin<=2048,'token size bound');tokens.append(Token(kind,value,start_line,begin,i));require(len(tokens)<=20000,'token count bound')
    tokens.append(Token('eof','<eof>',line,len(text),len(text)));return tokens

class Parser:
    PRECEDENCE={'||':1,'&&':2,'|':3,'^':4,'^~':4,'~^':4,'&':5,'==':6,'!=':6,'===':6,'!==':6,'<':7,'<=':7,'>':7,'>=':7,'<<':8,'>>':8,'<<<':8,'>>>':8,'+':9,'-':9,'*':10,'/':10,'%':10}
    UNARY={'+','-','!','~','&','|','^','~&','~|','~^','^~'}
    def __init__(self,text):self.text=text;self.tokens=tokenize(text);self.i=0;self.rows=[];self.scope=[];self.context=[];self.serial=0
    def peek(self,value=None):
        token=self.tokens[self.i]
        return token if value is None else token.value==value and token.kind==('keyword' if value in KEYWORDS else 'operator')
    def take(self,value=None):
        token=self.peek();require(token.kind!='eof','unexpected end of Verilog fragment')
        require(value is None or self.peek(value),'expected '+str(value)+' at line '+str(token.line));self.i+=1;return token
    def accept(self,value):
        if self.peek(value):return self.take()
        return None
    def name(self):
        token=self.take();require(token.kind=='name' and not token.value.startswith('$'),'expected literal declared name');return token
    def fact(self,kind,name,start,**fields):
        begin=self.tokens[start];end=self.tokens[self.i-1] if self.i>start else begin;body=self.text[begin.start:end.end]
        row=dict(kind=kind,name=name,line=begin.line,scope=list(self.scope),control_context=list(self.context),expression_sha256=sha(body),expression_bytes=len(body.encode()),evaluated=False,**fields);self.rows.append(row);return row
    def expression(self,minimum=0,depth=0):
        require(depth<=64,'expression nesting bound');start=self.i;token=self.take()
        if token.value in self.UNARY:left=('unary',token.value,self.expression(11,depth+1))
        elif token.value=='(':
            left=self.expression(0,depth+1);self.take(')')
        elif token.value=='{':
            first=self.expression(0,depth+1)
            if self.accept('{'):
                values=[self.expression(0,depth+1)]
                while self.accept(','):values.append(self.expression(0,depth+1))
                self.take('}');self.take('}');left=('repeat',first,values)
            else:
                values=[first]
                while self.accept(','):values.append(self.expression(0,depth+1))
                self.take('}');left=('concat',values)
        elif token.kind in ('name','macro','number','string'):
            require(token.kind!='name' or not token.value.startswith('$') or token.value=='$time','unreviewed system expression');left=(token.kind,token.value)
        else:raise ValueError('unreviewed expression token '+token.value+' at line '+str(token.line))
        while True:
            if self.accept('['):
                first=self.expression(0,depth+1);last=self.expression(0,depth+1) if self.accept(':') else None;self.take(']');left=('select',left,first,last);continue
            if self.accept('('):
                raise ValueError('unreviewed expression function call')
            if self.peek('?') and minimum==0:
                self.take();yes=self.expression(0,depth+1);self.take(':');no=self.expression(0,depth+1);left=('conditional',left,yes,no);continue
            op=self.peek().value;precedence=self.PRECEDENCE.get(op)
            if precedence is None or precedence<minimum:break
            self.take();right=self.expression(precedence+1,depth+1);left=('binary',op,left,right)
        return left
    def exprfacts(self,node):
        names=[];macros=[];numbers=[];strings=[];operators=[];calls=[]
        pending=[node]
        while pending:
            value=pending.pop()
            if value is None:continue
            if isinstance(value,list):
                pending.extend(reversed(value));continue
            kind=value[0]
            if kind=='name':names.append(value[1])
            elif kind=='macro':macros.append(value[1])
            elif kind=='number':numbers.append(value[1])
            elif kind=='string':strings.append(dict(sha256=sha(value[1]),bytes=len(value[1].encode())))
            elif kind in ('unary','binary'):
                operators.append(value[1])
                pending.extend(reversed(value[2:]))
            elif kind=='call':calls.append(value[1]);pending.append(value[2])
            else:pending.extend(reversed(value[1:]))
        return dict(identifier_references=list(dict.fromkeys(names)),macro_references=list(dict.fromkeys(macros)),numeric_literals=numbers,string_identities=strings,operators=operators,call_references=calls)
    def lvalue(self,depth=0):
        require(depth<=64,'lvalue nesting bound')
        if self.accept('{'):
            values=[self.lvalue(depth+1)]
            while self.accept(','):values.append(self.lvalue(depth+1))
            self.take('}');return ('concat',values)
        name=self.name();node=('name',name.value)
        while self.accept('['):
            first=self.expression();last=self.expression() if self.accept(':') else None;self.take(']');node=('select',node,first,last)
        return node
    def targets(self,node):
        if node[0]=='name':return [node[1]]
        if node[0]=='select':return self.targets(node[1])
        require(node[0]=='concat','unreviewed target structure');return [name for child in node[1] for name in self.targets(child)]
    def range(self):
        if not self.accept('['):return None
        first=self.expression();self.take(':');last=self.expression();self.take(']');return ('range',first,last)
    def declaration(self):
        start=self.i;kind=self.take().value;require(kind in ('wire','reg'),'unreviewed data declaration');packed=self.range()
        while True:
            name=self.name();unpacked=self.range();initial=self.expression() if self.accept('=') else None
            self.fact('verilog-data-declaration',name.value,start,data_type=kind,packed_range=self.exprfacts(packed) if packed else None,unpacked_range=self.exprfacts(unpacked) if unpacked else None,initializer=self.exprfacts(initial) if initial else None)
            if not self.accept(','):break
        self.take(';')
    def event(self):
        self.take('@');self.take('(');parts=[]
        while True:
            edge=self.take().value if self.peek().kind=='keyword' and self.peek().value in ('posedge','negedge') else None;value=self.expression();parts.append(dict(edge=edge,**self.exprfacts(value)))
            if not self.accept('or') and not self.accept(','):break
        self.take(')');return parts
    def statement(self,depth=0):
        require(depth<=64,'statement nesting bound');start=self.i;token=self.peek();op=token.value
        require(token.kind!='macro','unreviewed macro in statement position')
        if self.accept(';'):self.fact('verilog-empty-statement',';',start);return
        if op in ('wire','reg'):self.declaration();return
        if op=='begin':
            self.take();label=self.name().value if self.accept(':') else None;self.serial+=1;scope=label if label else '(block '+str(self.serial)+')';self.fact('verilog-block',scope,start,named=label is not None);self.scope.append(scope)
            while not self.peek('end'):self.statement(depth+1)
            self.take('end');self.scope.pop();return
        if op=='if':
            self.take();self.take('(');condition=self.expression();self.take(')');self.fact('verilog-if','if',start,condition=self.exprfacts(condition));self.context.append(dict(construct='if',token=start,branch='then'));self.statement(depth+1);self.context.pop()
            if self.accept('else'):self.context.append(dict(construct='if',token=start,branch='else'));self.statement(depth+1);self.context.pop()
            return
        if op in ('case','casex'):
            self.take();self.take('(');selector=self.expression();self.take(')');self.fact('verilog-case',op,start,selector=self.exprfacts(selector));branches=0
            while not self.peek('endcase'):
                branch_start=self.i;default=bool(self.accept('default'));values=[]
                if not default:
                    values.append(self.expression())
                    while self.accept(','):values.append(self.expression())
                self.take(':');self.fact('verilog-case-branch','default' if default else str(branches),branch_start,labels=[self.exprfacts(v) for v in values]);self.context.append(dict(construct=op,token=start,branch='default' if default else branches));self.statement(depth+1);self.context.pop();branches+=1;require(branches<=1024,'case branch bound')
            self.take('endcase');require(branches>0,'empty case');return
        if op=='@':
            events=self.event();self.fact('verilog-event-control','@',start,events=events);self.statement(depth+1);return
        if op=='#':
            self.take();delay=self.expression(11);self.fact('verilog-delay-control','#',start,delay=self.exprfacts(delay));self.statement(depth+1);return
        if token.kind=='name' and op.startswith('$'):
            call=self.take().value;require(call in ('$dumpfile','$dumpvars','$finish','$display'),'unreviewed system task');args=[]
            if self.accept('('):
                if not self.peek(')'):
                    args.append(self.expression())
                    while self.accept(','):args.append(self.expression())
                self.take(')')
            self.take(';');self.fact('verilog-system-task-reference',call,start,arguments=[self.exprfacts(v) for v in args],executed=False);return
        target=self.lvalue();operator=self.take().value;require(operator in ('=','<='),'unreviewed assignment operator');value=self.expression();self.take(';');self.fact('verilog-procedural-assignment',','.join(self.targets(target)),start,assignment_operator=operator,target_names=self.targets(target),target=self.exprfacts(target),value=self.exprfacts(value))
    def parse(self):
        while self.peek().kind!='eof':
            start=self.i;op=self.peek().value
            require(self.peek().kind=='keyword','unreviewed top-level token kind '+self.peek().kind)
            if op in ('wire','reg'):self.declaration()
            elif op=='assign':
                self.take();target=self.lvalue();self.take('=');value=self.expression();self.take(';');self.fact('verilog-continuous-assignment',','.join(self.targets(target)),start,target_names=self.targets(target),target=self.exprfacts(target),value=self.exprfacts(value))
            elif op in ('always','initial'):
                self.take();events=self.event() if self.peek('@') else [];self.serial+=1;name=op+' '+str(self.serial);self.fact('verilog-process',name,start,process_type=op,events=events);self.scope.append(name);self.statement();self.scope.pop()
            else:raise ValueError('unreviewed top-level Verilog token '+op+' at line '+str(self.peek().line))
        require(self.rows,'empty Verilog fragment');return self.rows

def fragment(text):
    """Parse already decoded Verilog source; return facts and explicit reference identities."""
    rows=Parser(text).parse();return [dict(kind='verilog-fragment',name='V',source_sha256=sha(text),elaborated=False,simulated=False)]+rows


def macro_declarations(text):
    """Only literal object-like macro definitions seen in the reviewed fragments."""
    rows=[];names=set()
    for line,raw in enumerate(text.splitlines(),1):
        code=raw.split('//',1)[0].strip()
        if not code:continue
        match=re.fullmatch(r'`define\s+('+IDENT+r')\s+('+BASED+'|'+DECIMAL+r')',code)
        require(match is not None,'unreviewed embedded preprocessor declaration');name,value=match.groups();require(name not in names,'duplicate embedded macro');names.add(name)
        tokens=tokenize(value);require(len(tokens)==2 and tokens[0].kind=='number','nonliteral macro value')
        rows.append(dict(kind='verilog-macro-declaration',name=name,line=line,value_literal=value,expression_sha256=sha(raw),evaluated=False))
    require(rows,'empty embedded preprocessor');return rows


def _references(value,key):
    result=[]
    if isinstance(value,dict):
        for name,child in value.items():
            if name==key:result.extend(child)
            else:result.extend(_references(child,key))
    elif isinstance(value,list):
        for child in value:result.extend(_references(child,key))
    return result


def schematic(text):
    """Inventory full reviewed MIPS schematic records, including the embedded V body."""
    from collections import Counter
    from scripts.inventory_legacy_symbols import records,properties
    from scripts.inventory_schematic_views import preserve_version_header
    prepared,diagnostics=preserve_version_header(text);require(prepared==text and not diagnostics,'unreviewed malformed MIPS header')
    source=records(text);require(source and source[0][1][0]==('word','v') and len(source[0][1])==2 and source[0][1][1][0]=='block','unreviewed schematic header')
    header=source[0][1][1][1];parts=header.splitlines();version=re.fullmatch(r'xschem version=([A-Za-z_0-9.]+) file_version=([0-9.]+)',parts[0]);require(version is not None and all(not x.strip() or x.lstrip().startswith('*') for x in parts[1:]),'unreviewed header metadata')
    rows=[dict(kind='xschem-version-header',name='xschem',version=version[1],file_version=version[2],header_sha256=sha(header))];blocks=[];seen=set();macros={};references=[];body_rows=[];instances=0
    for line,tokens in source[1:]:
        op=tokens[0][1]
        if len(blocks)<5:
            require(op==('G','K','V','S','E')[len(blocks)] and len(tokens)==2 and tokens[1][0]=='block','unreviewed schematic source-block order');blocks.append(op);body=tokens[1][1]
            if op=='V':
                require(body.strip(),'expected nonempty reviewed V fragment');decoded=re.sub(r'\\([{}])',r'\1',body);parsed=fragment(decoded)
                for fact in parsed:
                    fact['origin']=dict(record_operator='V',record_line=line,raw_expression_sha256=sha(body),decoded_expression_sha256=sha(decoded))
                    if 'line' in fact:fact['source_line']=line+fact['line']-1
                rows.extend(parsed);body_rows=parsed;references.extend(_references(parsed,'macro_references'))
            else:require(not body.strip(),'unreviewed non-Verilog embedded source');rows.append(dict(kind='xschem-empty-source-block',name=op,line=line))
            continue
        if op=='C':
            require(len(tokens)==7 and tokens[1][0]=='block' and tokens[-1][0]=='block' and all(k=='word' for k,v in tokens[2:6]),'unreviewed component record');ref=tokens[1][1]
            require(len(ref)<=256 and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9./-]*',ref) and '..' not in ref.split('/'),'unreviewed component reference')
            require(all(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',tokens[i][1]) and len(tokens[i][1])<=32 for i in (2,3)) and tokens[4][1] in ('0','1','2','3') and tokens[5][1] in ('0','1'),'unreviewed component placement')
            rawprops=tokens[-1][1]
            if ref=='devices/architecture.sym' and rawprops.strip()=='nothing here, use global schematic properties':
                props={};metadata={'annotation':sha(rawprops)}
            else:
                props=properties(rawprops);metadata={};require('name' in props,'missing component identity')
            require(set(props)<= {'name','author','lab','verilog_type','string','descr','url'},'unreviewed component property')
            name=props.pop('name',None)
            if name is not None:require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.$:#\[\]-]*',name) and name not in seen,'invalid/duplicate instance identity');seen.add(name)
            for key in ('author','descr'):
                if key in props:
                    require(ref==('devices/title.sym' if key=='author' else 'devices/launcher.sym'),'metadata on unreviewed component');metadata[key]=sha(props.pop(key))
            if 'url' in props:
                require(ref=='devices/launcher.sym' and re.fullmatch(r'https://[A-Za-z_0-9./-]+',props['url']),'unreviewed external reference')
                rows.append(dict(kind='xschem-external-reference',name=props.pop('url'),instance=name,line=line,opened=False))
            if 'string' in props:
                require(ref=='devices/verilog_preprocessor.sym','embedded string on unreviewed component');definitions=macro_declarations(props.pop('string'))
                for fact in definitions:
                    require(fact['name'] not in macros,'duplicate schematic macro');fact['origin']=dict(component_record_line=line,instance=name,property='string',raw_property_sha256=sha(rawprops));macros[fact['name']]=name;rows.append(fact)
            require(all(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.$:#\[\]-]*',v) and len(v)<=256 for v in props.values()),'nonliteral signal property');require('verilog_type' not in props or props['verilog_type'] in ('reg','wire'),'unreviewed port type')
            rows.append(dict(kind='xschem-instance',name=name if name is not None else ref,declared_instance_name=name,line=line,symbol_reference=ref,literal_properties=props,metadata_sha256=metadata,placement_literals=dict(zip(('x','y','rotation_code','mirror_code'),(v for k,v in tokens[2:6]))),terminal_order='Defined by referenced symbol; not inferred here.',model_binding_inferred=False,geometry_evaluated=False));instances+=1
        elif op=='T':
            require(len(tokens)==9 and tokens[1][0]=='block' and tokens[-1][0]=='block','unreviewed text record');props=properties(tokens[-1][1]);require(set(props)<= {'layer','hcenter','vcenter','font'},'unreviewed text properties')
            require(all((re.fullmatch(r'\d{1,3}',v) if k=='layer' else v.lower()=='monospace' if k=='font' else v in ('true','false')) for k,v in props.items()),'unreviewed text property value')
            require(all(k=='word' and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',v) and len(v)<=32 for k,v in tokens[2:8]),'unreviewed text numeric fields')
            rows.append(dict(kind='xschem-graphic-record',name='T',line=line,record_sha256=sha(repr(tokens)),geometry_evaluated=False))
        else:raise ValueError('unreviewed schematic record '+op)
    require(len(blocks)==5 and instances and body_rows,'incomplete reviewed schematic')
    for name in dict.fromkeys(references):
        require(name in macros,'unresolved embedded macro '+name);rows.append(dict(kind='verilog-macro-reference',name=name,declaration_instance=macros[name],expanded=False))
    assignments=[r for r in body_rows if r['kind']=='verilog-continuous-assignment'];counts=Counter(tuple(r['target_names']) for r in assignments)
    for targets,count in counts.items():
        if count>1:rows.append(dict(kind='verilog-source-diagnostic',name=','.join(targets),diagnostic='repeated-continuous-assignment-target',source_lines=[r['source_line'] for r in assignments if tuple(r['target_names'])==targets],correction_inferred=False,electrical_validity_inferred=False))
    rows.insert(0,dict(kind='xschem-behavioral-schematic-view',name='(no explicit schematic model name)',records=len(source),instances=instances,embedded_verilog_inventoried=True,elaborated=False,simulated=False,netlist_equivalence_inferred=False));return rows


REVIEWED = {('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/tb.sch', 'sky130A/libs.tech/xschem/mips_cpu/tb.sch', 'common.tar.zst'): '9429a0cc27d79957c47197f22b1b6557948791277e57d11903c2aafdd7ffc688', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/dmem.sch', 'sky130A/libs.tech/xschem/mips_cpu/dmem.sch', 'common.tar.zst'): '83ff8bd75429a7e4dc533be97976cee3585cd59b662e22e342d1aa37fe4cb3e5', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/imem.sch', 'sky130A/libs.tech/xschem/mips_cpu/imem.sch', 'common.tar.zst'): 'e36dce3b61806fdfcb0fb38ff99d075c0594740aeaafe21562c239e7632024fb', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/sign_extend.sch', 'sky130A/libs.tech/xschem/mips_cpu/sign_extend.sch', 'common.tar.zst'): '5416a46649306fc48a51b35ffac0a29e1b6d47d4974bf910f31760bbc493e1d9', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/aludec.sch', 'sky130A/libs.tech/xschem/mips_cpu/aludec.sch', 'common.tar.zst'): 'eb0c6528bdfb5f13de62626afad30876af58056aaaf9249e526965fb4bef734b', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/maindec.sch', 'sky130A/libs.tech/xschem/mips_cpu/maindec.sch', 'common.tar.zst'): 'ad54036ef8ae2a2df658fa636835db46ca15b3b7fc791d1683f843267b7d2a32', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/datapath.sch', 'sky130A/libs.tech/xschem/mips_cpu/datapath.sch', 'common.tar.zst'): '7cb54177470f488a55fab00a2165a9ca7e950abb996c2816429a1e3ff665132a', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/regfile.sch', 'sky130A/libs.tech/xschem/mips_cpu/regfile.sch', 'common.tar.zst'): '9239af7f69463ebefef4e5d65caae47d27bd98d69ebe17d2e5a9ebcfe23017ff', ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/xschem/mips_cpu/alu.sch', 'sky130A/libs.tech/xschem/mips_cpu/alu.sch', 'common.tar.zst'): '3bf55178539ebdeee88a377f7db2d0d1185da6c0c437a04689506500dedcd17e', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/tb.sch', 'sky130B/libs.tech/xschem/mips_cpu/tb.sch', 'common.tar.zst'): '9429a0cc27d79957c47197f22b1b6557948791277e57d11903c2aafdd7ffc688', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/dmem.sch', 'sky130B/libs.tech/xschem/mips_cpu/dmem.sch', 'common.tar.zst'): '83ff8bd75429a7e4dc533be97976cee3585cd59b662e22e342d1aa37fe4cb3e5', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/imem.sch', 'sky130B/libs.tech/xschem/mips_cpu/imem.sch', 'common.tar.zst'): 'e36dce3b61806fdfcb0fb38ff99d075c0594740aeaafe21562c239e7632024fb', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/sign_extend.sch', 'sky130B/libs.tech/xschem/mips_cpu/sign_extend.sch', 'common.tar.zst'): '5416a46649306fc48a51b35ffac0a29e1b6d47d4974bf910f31760bbc493e1d9', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/aludec.sch', 'sky130B/libs.tech/xschem/mips_cpu/aludec.sch', 'common.tar.zst'): 'eb0c6528bdfb5f13de62626afad30876af58056aaaf9249e526965fb4bef734b', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/maindec.sch', 'sky130B/libs.tech/xschem/mips_cpu/maindec.sch', 'common.tar.zst'): 'ad54036ef8ae2a2df658fa636835db46ca15b3b7fc791d1683f843267b7d2a32', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/datapath.sch', 'sky130B/libs.tech/xschem/mips_cpu/datapath.sch', 'common.tar.zst'): '7cb54177470f488a55fab00a2165a9ca7e950abb996c2816429a1e3ff665132a', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/regfile.sch', 'sky130B/libs.tech/xschem/mips_cpu/regfile.sch', 'common.tar.zst'): '9239af7f69463ebefef4e5d65caae47d27bd98d69ebe17d2e5a9ebcfe23017ff', ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/xschem/mips_cpu/alu.sch', 'sky130B/libs.tech/xschem/mips_cpu/alu.sch', 'common.tar.zst'): '3bf55178539ebdeee88a377f7db2d0d1185da6c0c437a04689506500dedcd17e'}

def embedded_schematic_views(row,raw):
    """Only the18 exact reviewed schematic identities and authenticated raw bytes."""
    key=tuple(row.get(k) for k in ('family','repository','repository_path','path','archive'))
    digest=REVIEWED.get(key)
    if digest is None:return None
    require(type(raw) is bytes and hashlib.sha256(raw).hexdigest()==digest,'Reviewed embedded schematic source bytes changed')
    return schematic(raw.decode('utf-8'))
