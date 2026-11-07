"""Nonexecuting declaration readers for pinned PDK configuration formats.

These enumerate names and source expressions, never certify numerical values,
evaluate templates, or infer runtime behavior from configuration presence.
"""
import hashlib
import math
from pathlib import PurePosixPath
import re
import shlex


def require(condition, message):
    if not condition:
        raise ValueError('Source configuration: ' + message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def number(value):
    result = float(value)
    require(math.isfinite(result), 'nonfinite number')
    return result


def fact(value):
    return value if re.fullmatch(r'[A-Za-z0-9_.:/+*?,@%-]+', value) else {'expression_sha256':digest(value)}


def directives(text):
    rows=[]
    for line, value in enumerate(text.splitlines(), 1):
        match=re.match(r'\s*#\s*(if|ifdef|ifndef|elif|elseif|define|undef)\b(.*)', value)
        if match:
            names=re.findall(r'\b[A-Za-z_]\w*\b', match[2])
            rows.append(dict(kind='configuration-condition', name=names[0] if names else '(expression)',
                             identifiers=names, line=line, expression_sha256=digest(match[2])))
    return rows


def tracks(text):
    rows=[];seen=set()
    for line, value in enumerate(text.splitlines(), 1):
        value=value.split('#', 1)[0].strip()
        if not value:continue
        words=value.split()
        require(len(words)==4 and words[1] in ('X','Y'), 'unrecognized track declaration')
        key=(words[0],words[1]);require(key not in seen,'duplicate layer/direction track');seen.add(key)
        rows.append(dict(kind='routing-track',name=words[0],axis=words[1],offset=number(words[2]),pitch=number(words[3]),line=line))
    return rows


def magic_cell(text, path):
    lines=[(n,v.strip()) for n,v in enumerate(text.splitlines(),1) if v.strip() and not v.lstrip().startswith('#')]
    require(lines and lines[0][1]=='magic' and lines[-1][1]=='<< end >>','incomplete Magic cell')
    rows=[dict(kind='magic-cell',name=PurePosixPath(path).stem)]
    section=None;label=None
    for line,value in lines[1:-1]:
        words=shlex.split(value)
        if match:=re.fullmatch(r'<<\s*([^<>]+?)\s*>>',value):
            section=match[1];label=None
            rows.append(dict(kind='magic-layer-section',name=section,line=line));continue
        head=words[0]
        if head=='tech':
            require(len(words)==2,'invalid Magic technology')
            rows.append(dict(kind='magic-technology',name=words[1],line=line))
        elif head=='use':
            require(len(words) in (3,4),'invalid Magic cell use')
            rows.append(dict(kind='magic-cell-reference',name=words[1],instance=words[2],
                             path=fact(words[3]) if len(words)==4 else None,line=line))
        elif head in ('rlabel','flabel'):
            require(section=='labels' and len(words)>=8,'invalid Magic label')
            label=words[-1]
            rows.append(dict(kind='magic-label',name=label,layer=words[1],line=line))
        elif head=='port':
            require(label is not None and len(words)>=3 and words[1].isdigit(),'orphan/invalid Magic port')
            rows.append(dict(kind='magic-port',name=label,index=int(words[1]),attributes=words[2:],line=line))
            label=None
        elif head=='string':
            require(section=='properties' and len(words)>=3,'invalid Magic property')
            rows.append(dict(kind='magic-property',name=words[1],value=fact(' '.join(words[2:])),line=line))
        elif head in ('magscale','timestamp','transform','box','rect','array'):
            counts={'magscale':2,'timestamp':1,'transform':6,'box':4,'rect':4,'array':6}
            require(len(words)==counts[head]+1 and all(re.fullmatch(r'-?\d+',w) for w in words[1:]),'invalid Magic '+head)
        else:raise ValueError('Source configuration: unknown Magic record '+head)
    return rows


def parameter_file(text):
    rows=[]
    for line,value in enumerate(text.splitlines(),1):
        value=value.split(';',1)[0].strip()
        if not value or value.startswith('#'):continue
        words=value.split()
        if words[0]=='resistance':
            require(len(words)==6,'invalid resistance configuration')
            rows.append(dict(kind='simulator-resistance-setting',name=words[1],mode=words[2],
                             values=[number(w) for w in words[3:]],line=line))
        else:
            require(len(words)==2 and re.fullmatch(r'[A-Za-z_]\w*',words[0]),'invalid simulator parameter')
            rows.append(dict(kind='simulator-parameter',name=words[0],value=number(words[1]),line=line))
    return rows


def qflow_parameters(text):
    rows=directives(text);rules=False
    for line,value in enumerate(text.splitlines(),1):
        value=value.strip()
        if not value or value.startswith('#'):continue
        if value=='RULES':require(not rules,'nested placement rules');rules=True;continue
        if value=='ENDRULES':require(rules,'orphan placement end');rules=False;continue
        if rules:
            words=value.split();head=words[0]
            require(head in ('layer','via','width','spacing','overhang'),'unknown placement rule')
            arity={'layer':5,'via':4,'width':3,'spacing':4,'overhang':4}
            require(len(words)==arity[head],'invalid placement rule')
            rows.append(dict(kind='placement-'+head,name=words[1],fields=[fact(w) for w in words[2:]],line=line))
        else:
            match=re.fullmatch(r'([A-Za-z0-9_.*]+)\s*:\s*(\S.*)',value)
            require(match is not None,'unknown placement parameter')
            rows.append(dict(kind='placement-parameter',name=match[1],value=fact(match[2]),line=line))
    require(not rules,'unterminated placement rules')
    return rows


def qflow_shell(text):
    rows=directives(text)
    for line,value in enumerate(text.splitlines(),1):
        value=value.strip()
        if not value or value.startswith('#'):continue
        # This format is a static tcsh variable template, not arbitrary shell.
        value=re.sub(r'\s*;#.*$', '',value)
        match=re.fullmatch(r'set\s+([A-Za-z_]\w*)\s*=\s*(.*)',value)
        require(match is not None,'nonassignment qflow shell command')
        words=shlex.split(match[2]);require(len(words)<=1,'unreviewed qflow shell value')
        rows.append(dict(kind='qflow-setting',name=match[1],value=fact(words[0] if words else ''),line=line))
    return rows


def openrcx(text):
    lines=[(n,v.strip()) for n,v in enumerate(text.splitlines(),1) if v.strip() and not v.lstrip().startswith('#')]
    require(lines and lines[0][1]=='Extraction Rules for OpenRCX','unknown RC table header')
    rows=[];table=None;numeric_rows=0
    for line,value in lines[1:]:
        words=value.split();head=words[0]
        if re.fullmatch(r'[+\-\d.].*',head):
            require(table is not None and len(words)==4,'unbound/invalid RC sample')
            [number(w) for w in words];numeric_rows+=1;continue
        if head=='Metal':
            require(len(words) in (3,4,6) and words[1].isdigit(),'invalid RC metal declaration')
            rows.append(dict(kind='rc-metal-table',name=words[1],relation=words[2],neighbors=words[3:],line=line))
        elif head in ('DIAGMODEL','LayerCount','DensityRate','DensityModel'):
            require(len(words)>=2,'invalid RC configuration')
            rows.append(dict(kind='rc-configuration',name=head,values=[fact(w) for w in words[1:]],line=line))
        elif head=='WIDTH':
            require(len(words)>=4 and words[1]=='Table' and words[2].isdigit() and words[3]=='entries:','invalid RC width table')
            values=[number(w) for w in words[4:]]
            require(len(values)==int(words[2]),'RC width count mismatch')
            rows.append(dict(kind='rc-widths',name='WIDTH',values=values,line=line))
        elif head=='DIST':
            require(table is None and len(words)==5 and words[1]=='count' and words[2].isdigit() and words[3]=='width','invalid RC distance table')
            table=dict(kind='rc-distance-table',name='DIST',declared_count=int(words[2]),width=number(words[4]),line=line)
            numeric_rows=0
        elif words==['END','DIST']:
            require(table is not None,'orphan RC distance end')
            table['observed_rows']=numeric_rows;rows.append(table);table=None
        elif len(words)==3 and words[:2]==['END','DensityModel']:
            rows.append(dict(kind='rc-density-end',name=words[2],line=line))
        else:raise ValueError('Source configuration: unknown RC record '+head)
    require(table is None,'unterminated RC distance table')
    return rows


def tcl_commands(text, list_mode=False):
    """Yield lexical commands/words with quoting preserved; never invoke Tcl."""
    n=len(text)
    def parse(i,line,stop=False,as_list=False):
        commands=[];words=[];command_line=line
        spaces=' \t\r\n' if as_list else ' \t\r\n;'
        while i<n:
            c=text[i]
            if stop and c==']':
                if words:commands.append((command_line,words))
                return commands,i+1,line
            if text.startswith('\\\n',i):line+=1;i+=2;continue
            if c in ' \t\r' or as_list and c=='\n':line+=c=='\n';i+=1;continue
            if not as_list and c in '\n;':
                if words:commands.append((command_line,words));words=[]
                line+=c=='\n';i+=1;continue
            if not as_list and c=='#' and not words:
                end=text.find('\n',i);i=n if end<0 else end;continue
            if not words:command_line=line
            start=i;expanded=not as_list and text.startswith('{*}',i) and i+3<n and text[i+3] not in spaces
            if expanded:i+=3;c=text[i]
            quoted=c in '{"';brace=c=='{';kind='brace' if brace else 'quote' if quoted else 'bare'
            if quoted:i+=1
            begin=i;depth=1 if brace else 0;substitutions=[]
            while i<n:
                c=text[i]
                if c=='\\':
                    require(i+1<n,'trailing Tcl escape');line+=text[i+1]=='\n';i+=2;continue
                if brace:
                    depth+=(c=='{')-(c=='}')
                    if depth==0:break
                else:
                    if quoted and c=='"':break
                    if not quoted and (c in spaces or stop and c==']'):break
                    if not as_list and c=='[':
                        substart=i+1;subline=line
                        _,i,line=parse(substart,line,stop=True)
                        substitutions.append(dict(body=text[substart:i-1],line=subline))
                        continue
                    require(as_list or c!=']' or quoted,'unmatched Tcl bracket')
                line+=c=='\n';i+=1
            end=i
            require(not quoted or i<n,'unterminated Tcl word')
            if brace:require(depth==0,'unterminated Tcl brace')
            if quoted:
                i+=1
                require(i==n or text[i] in spaces or stop and text[i]==']',
                        'characters after quoted Tcl word at line '+str(line))
            value=('{*}' if expanded else '')+text[begin:end]
            words.append(dict(value=value,kind=kind,line=command_line,raw=text[start:i],substitutions=substitutions))
        require(not stop,'unterminated Tcl command substitution')
        if words:commands.append((command_line,words))
        return commands,i,line
    return parse(0,1,as_list=list_mode)[0]


def tcl_views(text):
    rows=directives(text)
    def expression_substitutions(value,scope,base):
        for _,group in tcl_commands(value):
            for word in group:
                for substitution in word['substitutions']:
                    script(substitution['body'],scope,base+substitution['line']-1)
    def script(body,scope,base=0):
        for line,words in tcl_commands(body):
            values=[w['value'] for w in words];head=values[0];line+=base
            for word in words:
                for substitution in word['substitutions']:
                    script(substitution['body'],scope,base+substitution['line']-1)
            widget=re.fullmatch(r'\$\{[A-Za-z_]\w*\}(?:\.[A-Za-z_]\w*)+',head) is not None
            require(widget or bool(head) and not re.search(r'[$\[\]\\{}"\s]',head),'dynamic Tcl command')
            if widget:
                require(len(values)>=3 and (values[1]=='add' and values[2] in ('command','cascade','separator')
                        or len(values)>=4 and values[1]=='insert' and values[2].isdigit() and values[3] in ('command','separator')),
                        'unreviewed dynamic widget operation')
                rows.append(dict(kind='tcl-menu-command',name='(dynamic widget path)',widget_sha256=digest(head),
                                 arguments=[fact(v) for v in values[1:]],scope=scope,line=line))
                if '-command' in values:
                    pos=values.index('-command')+1
                    require(pos<len(words) and words[pos]['kind'] in ('quote','brace') and not re.search(r'[$\[\\]',values[pos]),'dynamic widget callback')
                    script(values[pos],scope,line-1)
                continue
            if head in ('eval','uplevel','apply','tailcall','interp','coroutine','yieldto','after','fileevent','trace','bind'):
                raise ValueError('Source configuration: dynamic Tcl script '+head)
            if head in ('global','variable'):
                require(len(values)>=2,'unnamed Tcl variable')
                names=values[1:] if head=='global' else values[1::2]
                for name in names:
                    dynamic=bool(re.search(r'[$\[\\]',name))
                    rows.append(dict(kind='tcl-dynamic-variable' if dynamic else 'tcl-variable',
                                     name='(expression)' if dynamic else name,name_sha256=digest(name),operation=head,scope=scope,line=line))
            elif head in ('set','lappend','append'):
                require(len(values)>=2,'unnamed Tcl variable')
                dynamic=bool(re.search(r'[$\[\\]',values[1]))
                rows.append(dict(kind='tcl-dynamic-variable' if dynamic else 'tcl-variable',
                                 name='(expression)' if dynamic else values[1],name_sha256=digest(values[1]),operation=head,scope=scope,
                                 values=[fact(v) for v in values[2:]],line=line))
            elif head=='proc':
                require(len(words)==4 and words[3]['kind']=='brace' and re.fullmatch(r'[A-Za-z_:][\w:.-]*',values[1]),'nonliteral Tcl procedure identity/body')
                arguments=[w for _,group in tcl_commands(values[2],list_mode=True) for w in group]
                rows.append(dict(kind='tcl-procedure',name=values[1],scope=scope,
                                 arguments=[fact(w['value']) for w in arguments],arguments_sha256=digest(values[2]),line=line))
                script(values[3],scope+[values[1]],line-1);continue
            elif head in ('source','addpath'):
                require(len(values)>=2,'missing Tcl source path')
                rows.append(dict(kind='tcl-source-reference',name=fact(values[-1]),operation=head,scope=scope,line=line))
            else:
                rows.append(dict(kind='tcl-command-reference',name=head,scope=scope,line=line,
                                 arguments=[fact(v) for v in values[1:]]))
            if head=='return' and scope and scope[-1].endswith('_defaults') and len(words)==2 and words[1]['kind']=='brace':
                parts=[w['value'] for _,group in tcl_commands(values[1],list_mode=True) for w in group]
                require(len(parts)%2==0,'incomplete literal PCell defaults')
                for key,value in zip(parts[::2],parts[1::2]):
                    rows.append(dict(kind='tcl-pcell-default',name=key,value=fact(value),scope=scope,line=line))
            if head=='expr':
                for word in words[1:]:
                    if word['kind']=='brace':expression_substitutions(word['value'],scope,line-1)
            bodies=[]
            if head=='namespace' and len(values)>=4 and values[1]=='eval':
                require(len(words)==4 and words[3]['kind']=='brace' and re.fullmatch(r'[A-Za-z_:][\w:.-]*',values[2]),'dynamic Tcl namespace body')
                script(values[3],scope+[values[2]],line-1)
            elif head=='dict' and len(values)>=3 and values[1] in ('for','filter','map','update','with'):
                # Only the script forms of dict filter execute the final word.
                if values[1]!='filter' or len(values)>=4 and values[3]=='script':bodies=[len(words)-1]
            elif head in ('foreach','lmap','while'):bodies=[len(words)-1]
            elif head=='for':
                require(len(words)==5,'invalid Tcl for');bodies=[1,3,4]
                if words[2]['kind']=='brace':expression_substitutions(values[2],scope,line-1)
            elif head=='catch':bodies=[1]
            elif head=='try':
                bodies=[1];pos=2
                while pos<len(words):
                    if values[pos]=='finally':bodies.append(pos+1);pos+=2
                    else:
                        require(values[pos] in ('on','trap'),'unknown Tcl try handler')
                        bodies.append(pos+3);pos+=4
                require(pos==len(words),'incomplete Tcl try handler')
            elif head=='if':
                pos=1
                while pos<len(words):
                    if values[pos] in ('elseif','else'):
                        if values[pos]=='else':bodies.append(pos+1);pos+=2;break
                        pos+=1
                    elif bodies:
                        # Tcl permits the final else keyword to be omitted.
                        require(pos==len(words)-1,'ambiguous Tcl conditional tail');bodies.append(pos);pos+=1;break
                    if words[pos]['kind']=='brace':expression_substitutions(values[pos],scope,line-1)
                    pos+=1
                    if pos<len(words) and values[pos]=='then':pos+=1
                    require(pos<len(words),'missing Tcl conditional body');bodies.append(pos);pos+=1
                require(pos==len(words),'invalid Tcl conditional')
            elif head=='switch':
                pos=1
                while pos<len(words) and values[pos] in ('-exact','-glob','-regexp','-nocase','--'):
                    end=values[pos]=='--';pos+=1
                    if end:break
                require(pos<len(words) and (values[pos]=='-' or not values[pos].startswith('-')),'unreviewed Tcl switch option')
                pos+=1
                pairs=words[pos:]
                if len(pairs)==1:
                    require(pairs[0]['kind']=='brace','dynamic Tcl switch alternatives')
                    pairs=[w for _,group in tcl_commands(pairs[0]['value'],list_mode=True) for w in group]
                require(bool(pairs) and len(pairs)%2==0,'incomplete Tcl switch alternatives')
                for pattern,child in zip(pairs[::2],pairs[1::2]):
                    rows.append(dict(kind='tcl-switch-option',name=fact(pattern['value']),scope=scope,line=line))
                    if child['value']=='-':continue
                    require(child['kind']=='brace','dynamic Tcl switch body')
                    script(child['value'],scope,line-1)
            for pos in bodies:
                require(pos<len(words) and words[pos]['kind']=='brace','nonliteral Tcl nested script')
                script(values[pos],scope,line-1)
            if head=='while' and len(words)>1 and words[1]['kind']=='brace':
                expression_substitutions(values[1],scope,line-1)
    script(text,[])
    return rows


def config_views(path,text):
    """Return declarations for a recognized format; None leaves it unresolved."""
    name=PurePosixPath(path).name;suffix=PurePosixPath(path).suffix.lower()
    if suffix=='.mag':return magic_cell(text,path)
    if name=='tracks.info':return tracks(text)
    if name.startswith('rules.openrcx.'):return openrcx(text)
    if suffix=='.prm':return parameter_file(text)
    if suffix=='.par':return qflow_parameters(text)
    if suffix=='.sh' and '/qflow/' in '/'+path:return qflow_shell(text)
    if suffix in ('.tcl','.magicrc','.bindkeys'):return tcl_views(text)
    return None
