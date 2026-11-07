"""Finite nonexecuting schematic declarations and lossless version-header handling."""
import hashlib
import re

NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
IDENT=r'[A-Za-z_][A-Za-z_0-9.$:#\[\]-]*'
REF=r'[A-Za-z_][A-Za-z_0-9./-]*'
sha=lambda text:hashlib.sha256(text.encode()).hexdigest()
def require(ok,msg):
    if not ok:raise ValueError(msg)

def preserve_version_header(text):
    """Keep valid multi-line headers intact; retain the known orphan-comment diagnostic.

    This only prepares records. It does not declare embedded source fully inventoried.
    """
    lines=text.splitlines(keepends=True);rows=[]
    require(lines and re.match(r'^v\s+\{xschem\b',lines[0]),'expected Xschem version header')
    # The old cleanup ran even when this line opened a valid multi-line header.
    # Only the separately closed one-line header permits the known orphan repair.
    if re.fullmatch(r'v\s+\{xschem\s+[^{}]*\}\s*',lines[0].strip()) is None:return text,rows
    preamble=True;comment=False
    for index,line in enumerate(lines):
        stripped=line.strip()
        if index==0 or not stripped:continue
        if preamble and stripped.startswith('*'):comment=True;lines[index]='\n';continue
        if preamble and stripped=='}' and comment:
            rows.append(dict(kind='source-diagnostic',name='unmatched-header-comment-close',line=index+1,
                             reason='An orphan brace follows the initial star-comment preamble. It is retained as a source defect; subsequent typed declarations are inventoried without asserting importability.',blocks_device_qualification=True))
            lines[index]='\n';preamble=False;continue
        preamble=False
    return ''.join(lines),rows

def headerless_generated(text):
    """Parse every record of the eight reviewed generated, code-free .sch views."""
    require(len(text)<=2_000_000,'source size bound');lines=text.splitlines();require(len(lines)<=20000,'record bound')
    rows=[];header=[];names=set();records=0
    for number,line in enumerate(lines,1):
        if not line.strip():continue
        records+=1
        if len(header)<3:
            match=re.fullmatch(r'\s*([VGS])\s+\{\s*\}\s*',line)
            require(match is not None and match[1]==('V','G','S')[len(header)],'unreviewed headerless source header or embedded code')
            header.append(match[1]);rows.append(dict(kind='xschem-empty-source-block',name=match[1],line=number));continue
        match=re.fullmatch(r'\s*C\s+\{('+REF+r')\}\s+('+NUMBER+r')\s+('+NUMBER+r')\s+([0-3])\s+([01])\s+\{([^{}]*)\}\s*',line)
        require(match is not None,'unreviewed generated schematic record at line '+str(number))
        require(all(len(match[i])<=32 for i in (2,3)),'coordinate literal bound');reference=match[1]
        require(len(reference)<=256 and not reference.startswith('/') and '..' not in reference.split('/'),'unreviewed symbol reference')
        props={}
        for token in match[6].split():
            entry=re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)',token);require(entry is not None,'unparsed instance property')
            key,value=entry.groups();require(key not in props,'duplicate instance property');require(key in ('name','lab','w','l','VGND','VNB','VPB','VPWR'),'unreviewed instance property '+key)
            require(len(value)<=256 and re.fullmatch(NUMBER+r'[munpf]?' if key in ('w','l') else IDENT,value),'nonliteral instance property '+key)
            props[key]=value
        require('name' in props,'missing instance identity');name=props.pop('name');require(name not in names,'duplicate instance name');names.add(name)
        require(('w' in props)==('l' in props),'incomplete dimension declaration')
        rows.append(dict(kind='xschem-instance',name=name,line=number,symbol_reference=reference,literal_properties=props,
                         placement_literals=dict(x=match[2],y=match[3],rotation_code=match[4],mirror_code=match[5]),
                         terminal_order='Defined by referenced symbol; not inferred here.',model_binding_inferred=False,geometry_evaluated=False))
    require(len(header)==3 and names,'incomplete or empty generated schematic')
    rows.insert(0,dict(kind='xschem-schematic-view',name='(no explicit schematic model name)',format='headerless-generated-xschem',records=records,instances=len(names),embedded_code_present=False,netlist_equivalence_inferred=False))
    return rows


def versioned_literal(text):
    """Account for the six reviewed MIPS views with empty embedded-source blocks."""
    from scripts.inventory_legacy_symbols import records,properties
    prepared,diagnostics=preserve_version_header(text)
    require(not diagnostics,'malformed header remains outside literal-view subset')
    source=records(prepared);require(source and source[0][1][0]==('word','v') and len(source[0][1])==2 and source[0][1][1][0]=='block','unreviewed version header')
    header=source[0][1][1][1];parts=header.splitlines();match=re.fullmatch(r'xschem version=([A-Za-z_0-9.]+) file_version=([0-9.]+)',parts[0])
    require(match is not None and all(not line.strip() or line.lstrip().startswith('*') for line in parts[1:]),'unreviewed header fields')
    rows=[dict(kind='xschem-version-header',name='xschem',version=match[1],file_version=match[2],header_sha256=sha(header))];blocks=[];names=set();instances=0
    for line,tokens in source[1:]:
        op=tokens[0][1]
        if len(blocks)<5:
            require(op==('G','K','V','S','E')[len(blocks)] and len(tokens)==2 and tokens[1][0]=='block','unreviewed source-block order')
            require(not tokens[1][1].strip(),'unenumerated embedded source block '+op+' at line '+str(line))
            blocks.append(op);rows.append(dict(kind='xschem-empty-source-block',name=op,line=line));continue
        if op=='C':
            require(len(tokens)==7 and tokens[1][0]=='block' and tokens[-1][0]=='block' and all(kind=='word' for kind,value in tokens[2:6]),'unreviewed component record')
            reference=tokens[1][1];require(len(reference)<=256 and re.fullmatch(REF,reference) and '..' not in reference.split('/'),'unreviewed component reference')
            require(all(len(tokens[i][1])<=32 and re.fullmatch(NUMBER,tokens[i][1]) for i in (2,3)) and tokens[4][1] in ('0','1','2','3') and tokens[5][1] in ('0','1'),'unreviewed component placement')
            props=properties(tokens[-1][1]);require(set(props)<= {'name','lab','author','verilog_type'},'unenumerated embedded or unreviewed component properties')
            require('name' in props and re.fullmatch(IDENT,props['name']),'missing/nonliteral instance name');name=props.pop('name');require(name not in names,'duplicate instance identity');names.add(name)
            author=props.pop('author',None)
            require(all(len(value)<=256 and re.fullmatch(IDENT,value) for value in props.values()),'nonliteral instance property')
            require('verilog_type' not in props or props['verilog_type'] in ('reg','wire'),'unreviewed Verilog port type')
            rows.append(dict(kind='xschem-instance',name=name,line=line,symbol_reference=reference,literal_properties=props,
                             metadata_sha256={'author':sha(author)} if author is not None else {},placement_literals=dict(zip(('x','y','rotation_code','mirror_code'),(v for k,v in tokens[2:6]))),
                             terminal_order='Defined by referenced symbol; not inferred here.',model_binding_inferred=False,geometry_evaluated=False));instances+=1
        elif op in ('L','P','T'):
            require(tokens[-1][0]=='block','unreviewed graphic property block');props=properties(tokens[-1][1])
            if op=='L':require(len(tokens)==7 and not props,'unreviewed line record');numeric=tokens[1:-1]
            elif op=='P':
                require(len(tokens)>=8 and tokens[2][0]=='word' and re.fullmatch(r'\d{1,3}',tokens[2][1]),'unreviewed polygon count');require(len(tokens)==4+int(tokens[2][1])*2 and props=={'fill':'true'},'unreviewed polygon record');numeric=tokens[1:-1]
            else:
                require(len(tokens)==9 and tokens[1][0]=='block' and set(props)<= {'layer'} and all(re.fullmatch(r'\d{1,3}',v) for v in props.values()),'unreviewed text record');numeric=tokens[2:-1]
            require(all(k=='word' and len(v)<=32 and re.fullmatch(NUMBER,v) for k,v in numeric),'unreviewed graphic numeric fields')
            rows.append(dict(kind='xschem-graphic-record',name=op,line=line,record_sha256=sha(repr(tokens)),geometry_evaluated=False))
        else:raise ValueError('unreviewed schematic operator '+op)
    require(len(blocks)==5 and instances,'incomplete literal schematic')
    rows.insert(0,dict(kind='xschem-schematic-view',name='(no explicit schematic model name)',format='versioned-literal-xschem',records=len(source),instances=instances,embedded_code_present=False,netlist_equivalence_inferred=False))
    return rows


SKY_REPOSITORY='chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392'
IHP_REPOSITORY='IHP-GmbH/IHP-Open-PDK@5e6d592e4002946a4616f798c357f0f3c06cf3b6'
IHP_PATH='ihp-sg13g2/libs.tech/xschem/start_page.sch'


def unenumerated_ihp_embedded(text):
    prepared,diagnostics=preserve_version_header(text)
    require(prepared==text and not diagnostics,'unexpected IHP version-header structure')
    raise ValueError('Unenumerated embedded simulator/Tcl property declarations and malformed value quotation require review; the valid multiline version header is preserved.')


REVIEWED_SOURCES={('ihp-sg13g2',IHP_REPOSITORY,IHP_PATH):(None,unenumerated_ihp_embedded)}
for _process in ('sky130A','sky130B'):
    for _name in ('spm','audiodac','sky130_fd_sc_hvl__lsbuflv2hv_1','counter'):
        _path=_process+'/libs.tech/xschem/xschem_verilog_import/'+_name+'.sch'
        REVIEWED_SOURCES[(_process,SKY_REPOSITORY,_path)]=('common.tar.zst',headerless_generated)
    for _name in ('controller','top','mips','tb','dmem','imem','sign_extend','aludec','maindec','datapath','regfile','alu'):
        _path=_process+'/libs.tech/xschem/mips_cpu/'+_name+'.sch'
        REVIEWED_SOURCES[(_process,SKY_REPOSITORY,_path)]=('common.tar.zst',versioned_literal)


def reviewed_schematic_views(row,text):
    """Inventory14 literal views and retain explicit embedded-source gaps for19 others.

    The immutable caller authenticates source bytes; this dispatcher accepts only
    the33 reviewed family/repository/revision/path/archive identities.
    """
    key=(row.get('family'),row.get('repository'),row.get('repository_path'));selected=REVIEWED_SOURCES.get(key)
    if selected is None or row.get('path')!=key[2] or row.get('archive')!=selected[0]:return None
    return selected[1](text)
