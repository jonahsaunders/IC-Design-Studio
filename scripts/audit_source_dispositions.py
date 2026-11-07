"""Audit complete source-view accounting without asserting device qualification.

The original source-completeness criterion permits explicitly unimplemented
items. This reader verifies their source identities and reasons; it never turns
an unresolved implementation, malformed source or missing model into a pass.
"""
import ast
import argparse
import csv
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import sys
import tarfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
VALID={'supported','unimplemented','inapplicable'}
REPORTS={
 'semantic':('docs/qualification/upstream-semantics-inventory-2026-11-07-v2.json.gz','89e5822520560af880e267bbf44e0d6ae4cfa556c204a8fe33ebf7b998dddcfe'),
 'sky':('docs/qualification/sky130-release-inventory-2026-11-07.json.gz','49f83a308acda1ccdc5c2320ab34ef896b02bcf78c7823190057c822c9fb3848'),
}
COMPANION_ROOTS={
    'gf180-open-pdks':'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9',
    'gf180-fd-pv':'efabless/globalfoundries-pdk-libs-gf180mcu_fd_pv@05e7b6adf19edf942969c1c9625f02fd87874f06',
}
COMPANION_PINS={
    'fossi-foundation/open-pdks':('aa3fc215a80d32437b8cca1cb3fdee819d18c4c9','3cf9b37e21c21cf3f97a9660cb67cb8d3cc39d11'),
    'efabless/globalfoundries-pdk-libs-gf180mcu_fd_pv':('05e7b6adf19edf942969c1c9625f02fd87874f06','4493f4081aba3538729ced167dc39b5d48bd353a'),
    'SymbiFlow/make-env':('33b80bd32c30fb8affd0fd5cda544d1bca075593','8b659aa9f3f50a0ef12dc65460171f54a4ccec08'),
}
SKY_REASONS={
    'catalog_bound_source_declared_not_qualified':('unimplemented','Catalog binding and upstream declarations are recorded; this inventory does not establish complete implementation equivalence.'),
    'catalog_bound_no_exact_release_declaration_review_required':('unimplemented','The catalog binding has no exact declaration in this release; its adapter/source mapping remains unresolved.'),
    'non_electrical_pdk_control_metadata':('inapplicable','This catalog item is non-electrical PDK control metadata, not a physical device model.'),
    'catalog_unavailable_still_blocks':('unimplemented','The required catalog binding is unavailable and remains a release blocker.'),
    'technology_support_or_other_identifier_requires_context':('unimplemented','The declared identifier is retained; its device or technology-support role is unresolved.'),
    'analog_catalog_model_identifier_not_qualified':('unimplemented','The identifier has a catalog association; complete implementation equivalence is not established.'),
    'library_without_selected_application_platform':('unimplemented','This source library is not selected by an application digital platform.'),
    'primitive_or_internal_model_without_exact_catalog_binding':('unimplemented','The primitive or internal declaration has no exact catalog binding.'),
    'hd_auxiliary_or_other_corner_identifier_not_qualified':('unimplemented','The HD auxiliary or other-corner declaration has no established complete application mapping.'),
    'selected_hd_timing_cell_not_qualified':('unimplemented','The selected HD timing declaration is identified; declared-view agreement is not runtime or behavioral equivalence.'),
    'outside_selected_process_sky130B':('inapplicable','This declaration belongs to SKY130B; the selected target is SKY130A.'),
    'upstream_unknown_not_in_release':('unimplemented','Upstream explicitly marks this option unknown and supplies no corresponding release library.'),
    'available_source_no_selected_digital_profile':('unimplemented','The release contains this library but no selected application digital profile uses it.'),
    'technology_integration_metadata_not_library_archive':('unimplemented','The option identifies technology integration metadata, not a corresponding cell-library archive.'),
    'selected_hd_profile_not_qualified':('unimplemented','The HD profile is selected; exact runtime artifact equivalence remains a separate requirement.'),
    'primitive_catalog_reconciled_separately':('unimplemented','Primitive declarations and catalog associations are enumerated separately; this option is not a complete implementation claim.'),
    'outside_selected_process':('inapplicable','This process option belongs to SKY130B; the selected target is SKY130A.'),
}


def require(ok,message):
    if not ok:raise ValueError('Source dispositions: '+message)


def sha(data):return hashlib.sha256(data).hexdigest()


def unique(rows,key,description):
    result={}
    for row in rows:
        identity=key(row)
        require(identity not in result,'duplicate '+description+': '+str(identity));result[identity]=row
    return result


def source_id(row):return row['path'] if 'archive' in row else row['family']+':'+row['path']


def targets(family):
    if family in ('sky130A','sky130B'):return ('sky130A',)
    if family in ('gf180mcu','gf180-ecosystem','gf180-open-pdks','gf180-fd-pv'):return ('gf180mcuC','gf180mcuD')
    require(family=='ihp-sg13g2','unknown source family: '+family)
    return ('ihp-sg13g2',)


def disposition(value,*,qualification='qualified'):
    require(value.get('disposition') in VALID,'unknown/missing disposition')
    require(isinstance(value.get('reason'),str) and bool(value['reason'].strip()),'missing disposition reason')
    require(value.get(qualification) is False,'inventory cannot qualify a device')
    return {k:value[k] for k in ('disposition','reason')}|{'qualified':False}


def graph_ledger(report,files):
    expected=unique(files,source_id,'authenticated graph file')
    actual=unique(report['files'],source_id,'report file')
    require(set(actual)==set(expected),'file ledger omits or adds authenticated graph entries')
    fields=('family','path','repository','repository_path','git_blob_sha1','mode','bytes')
    for key,row in actual.items():
        require(all(row.get(k)==expected[key].get(k) for k in fields),'changed source ledger identity: '+key)
        require(bool(row.get('reason')) and bool(row.get('role')),'missing file role/reason: '+key)
    return expected


def semantic_items(report,files):
    """Check links in both directions; source counts alone cannot pass."""
    ledger=graph_ledger(report,files)
    sources=unique(report['sources'],lambda r:r['id'],'parsed source')
    interfaces=unique(report['interfaces'],lambda r:r['id'],'interface')
    require(report.get('qualified') is False and report.get('chunk_complete') is False,'qualification promotion')
    by_source=defaultdict(set)
    for key,row in interfaces.items():
        require(row['source'] in sources,'interface references absent source')
        require(row['family']==sources[row['source']]['family'],'interface changed source family')
        by_source[row['source']].add(key)
    for key,row in sources.items():
        require(key in ledger and key==source_id(row),'unbound parsed source')
        for field in ('repository','repository_path','git_blob_sha1','mode','bytes'):
            require(row[field]==ledger[key][field],'parsed source differs from authenticated tree')
        require(len(set(row['interfaces']))==len(row['interfaces']),'duplicate source/interface link')
        require(set(row['interfaces'])==by_source[key],'incomplete source/interface links')
    items=[]
    for key,row in interfaces.items():
        require(row['source'] in sources,'interface references absent source')
        require(set(row['dispositions'])==set(targets(row['family'])),'incomplete target dispositions')
        choices={t:disposition(v,qualification='qualification') for t,v in row['dispositions'].items()}
        for t,v in row['dispositions'].items():
            if v['disposition']=='supported':
                require(bool(v.get('identical_bundled_paths')) and any(not c.get('unavailable') for c in v.get('catalog_candidates',[])),
                        'supported interface lacks exact bytes/available binding')
        items.append(dict(id=key,kind=row['kind'],name=row.get('name'),sources=[row['source']],dispositions=choices))
    for key,row in ledger.items():
        if row['path'].lower().endswith('.slib'):
            require(key in sources and sources[key]['parser']=='slib-symbol' and any(
                interfaces[i]['kind']=='slib-symbol' for i in sources[key]['interfaces']),
                'candidate symbol format silently classified as context: '+key)
    for category in ('libraries','process_options'):
        seen=set()
        for row in report[category]:
            if category=='libraries':
                key=(row['family'],row['library'],row['name'])
                refs=[i for values in row['views'].values() for i in values]
                choices={t:disposition(row) for t in targets(row['family'])}
                require(all(i in interfaces and interfaces[i]['family']==row['family'] for i in refs),'library changed source family')
            else:
                key=(row['kind'],row['source_interface'],row['name']);refs=[row['source_interface']]
                require(row['source_interface'] in interfaces,'missing process-option interface')
                choices={t:disposition(v) for t,v in row['dispositions'].items()} if 'dispositions' in row else {
                    t:disposition(row) for t in targets(interfaces[row['source_interface']]['family'])}
                require(set(choices)==set(targets(interfaces[row['source_interface']]['family'])),'incomplete process-option targets')
            require(key not in seen,'duplicate '+category+' identity');seen.add(key)
            require(refs and all(i in interfaces for i in refs),'missing '+category+' source links')
            items.append(dict(id=category+':'+':'.join(key),kind=category,name=row['name'],
                              sources=sorted({interfaces[i]['source'] for i in refs}),dispositions=choices))
    return items,sources,ledger


def sky_choice(code):
    require(code in SKY_REASONS,'unreviewed SKY disposition code: '+str(code))
    value,reason=SKY_REASONS[code]
    return dict(disposition=value,reason=reason,qualified=False)


def sky_items(report):
    require(report.get('qualified') is False and report.get('chunk_complete') is False,'SKY qualification promotion')
    files=unique(report['files'],lambda r:r['path'],'SKY source path');items=[];seen=set()
    semantic=report['semantic_reconciliation']
    from scripts.inventory_sky130_release import index_rows
    _,declarations=index_rows(list(files.values()))
    expected_identifiers=set(declarations)
    actual_identifiers={(r['process'],r['library'],r['name']) for r in semantic['identifiers']}
    require(actual_identifiers==expected_identifiers,'SKY declaration identifiers omitted or substituted')
    for category in ('analog_catalog','identifiers'):
        for row in semantic[category]:
            name=row['catalog_key'] if category=='analog_catalog' else row['name']
            require(row.get('qualified',False) is False,'SKY item qualification promotion')
            key=category+':'+(':'.join((row['process'],str(row['library']),name)) if category=='identifiers' else name)
            require(key not in seen,'duplicate SKY item');seen.add(key)
            refs=sorted({d['path'] for d in row['declarations']})
            if category=='identifiers':
                expected=Counter((r['path'],d['kind']) for r,d in declarations[(row['process'],row['library'],row['name'])])
                require(Counter((d['path'],d['kind']) for d in row['declarations'])==expected,'SKY identifier source declaration mismatch')
            else:
                for declaration in row['declarations']:
                    source=files.get(declaration['path'],{})
                    require(source.get('process')=='sky130A','catalog declaration has wrong process')
                    require(any(all(declaration.get(k)==value for k,value in d.items() if k in declaration)
                                and d.get('name','').lower()==row['model'].lower() and d.get('prefix')==row['prefix']
                                for d in source.get('semantic',{}).get('declarations',[])), 'catalog declaration identity mismatch')
            if not refs and category=='analog_catalog':
                symbol='sky130A/libs.tech/xschem/'+row['catalog_key']
                refs=[symbol] if symbol in files else ['application-package:sky130A']
            require(refs and all(p in files or category=='analog_catalog' and p=='application-package:sky130A' for p in refs),'missing SKY declaration/catalog source')
            items.append(dict(id=key,kind=category,name=name,sources=refs,
                              dispositions={'sky130A':sky_choice(row['disposition'])}))
    processes=unique(semantic['process_options'],lambda r:r['process'],'SKY process-option scope')
    require(set(processes)=={r['nodeinfo']['node'] for r in files.values() if 'nodeinfo' in r},'missing SKY process-option scope')
    for process in processes.values():
        require(process['path'] in files,'missing SKY process-option source')
        node=files[process['path']].get('nodeinfo',{})
        require(node.get('node')==process['process'],'wrong SKY option process identity')
        require(process['declared_options']==node.get('options'),'incomplete SKY declared process options')
        options=unique(process['options'],lambda r:(r['category'],r['name']),'SKY process option')
        expected={(category,name):value for category in ('stdcells','iocells','primitive','memory','other') for name,value in node.get(category,{}).items()}
        require(set(options)==set(expected),'missing SKY option declaration')
        for key,row in options.items():
            require(row['upstream_value']==expected[key],'changed SKY option source value')
            present=any(r['process']==process['process'] and r['library']==row['name'] for r in files.values())
            require(row['release_library_present']==present,'changed SKY option library presence')
            if row['disposition']=='upstream_unknown_not_in_release':
                require(row['upstream_value']=='unknown' and row['release_library_present'] is False,'unsupported unknown-library claim')
            items.append(dict(id='option:'+process['process']+':'+':'.join(key),kind='process-option',name=row['name'],
                              sources=[process['path']],dispositions={'sky130A':sky_choice(row['disposition'])}))
    return items,files


def strict_json(text):
    def pairs(rows):
        result={}
        for key,value in rows:
            require(key not in result,'duplicate JSON member: '+key);result[key]=value
        return result
    def finite(value):
        result=float(value);require(math.isfinite(result),'nonfinite JSON number');return result
    def invalid(value):raise ValueError('Source dispositions: invalid JSON constant '+value)
    return json.loads(text,object_pairs_hook=pairs,parse_constant=invalid,parse_float=finite)


def factual(value):
    """Retain numeric/token facts, never arbitrary strings or copied expressions."""
    if isinstance(value,float):require(math.isfinite(value),'nonfinite factual value')
    if value is None or isinstance(value,(bool,int,float)):return value
    if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:+/-]{0,64}',value):return value
    if isinstance(value,list):return [factual(v) for v in value]
    if isinstance(value,dict):return {str(k):factual(v) for k,v in value.items()}
    return dict(value_type=type(value).__name__,value_sha256=sha(json.dumps(value,sort_keys=True,ensure_ascii=True).encode()))


def json_views(text,path):
    """Enumerate named Liberty-JSON groups, not merely their filename suffix."""
    obj=strict_json(text);rows=[]
    def walk(value,context):
        if isinstance(value,dict):
            for key,child in value.items():
                match=re.fullmatch(r'(library|cell|pin|pg_pin|bus|operating_conditions)\s+(.+)',key)
                if match:
                    kind,name=match.groups();require(bool(name.strip()),'empty JSON declaration')
                    require(isinstance(child,dict),'non-object JSON declaration')
                    attrs={k:factual(child[k]) for k in ('direction','pg_type','voltage_name','voltage','temperature','process','nom_voltage','nom_temperature','nom_process') if k in child}
                    rows.append(dict(kind='json-'+kind,name=name,context=context,attributes=attrs))
                walk(child,context+[key])
        elif isinstance(value,list):
            for number,child in enumerate(value):walk(child,context+[number])
    walk(obj,[])
    if path.endswith('.lib.json'):require(bool(rows),'Liberty JSON view lacks any declaration')
    if not rows:
        # Configuration facts remain explicit, including unknown option values.
        def leaves(value,keys):
            if isinstance(value,dict):
                for key,child in value.items():leaves(child,keys+[key])
            elif isinstance(value,list):
                for index,child in enumerate(value):leaves(child,keys+[index])
            else:rows.append(dict(kind='json-configuration',name='/'.join(map(str,keys)),value=factual(value)))
        leaves(obj,[])
    return rows


def template_views(text):
    tree=ast.parse(text);assignments=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='templates' for t in n.targets)]
    require(len(assignments)==1 and isinstance(assignments[0].value,(ast.List,ast.Tuple)),'missing or dynamic PCell template list')
    rows=[]
    for number,node in enumerate(assignments[0].value.elts):
        require(isinstance(node,ast.Dict),'dynamic PCell mapping')
        pairs={ast.literal_eval(k):v for k,v in zip(node.keys,node.values)}
        require(len(pairs)==len(node.keys),'duplicate PCell mapping member')
        require({'regex','pcell_library','pcell_name','params'}<=set(pairs),'incomplete PCell mapping')
        name=ast.literal_eval(pairs['pcell_name']);library=ast.literal_eval(pairs['pcell_library'])
        require(isinstance(name,str) and isinstance(library,str),'nonliteral PCell identity')
        params=ast.literal_eval(pairs['params'])
        require(isinstance(params,list) and all(isinstance(p,dict) and isinstance(p.get('name'),str) and isinstance(p.get('type'),str) for p in params),'unrecognized PCell parameters')
        unique(params,lambda p:p['name'],'PCell parameter')
        rows.append(dict(kind='netlist-pcell-mapping',name=name,library=library,line=node.lineno,index=number,
                         parameters=[dict(name=p['name'],type=p['type']) for p in params],
                         default_parameters=factual(ast.literal_eval(pairs['default_params'])) if 'default_params' in pairs else {},
                         pattern_ast_sha256=sha(ast.dump(pairs['regex'],include_attributes=False).encode()),
                         branch_expression_sha256=sha(ast.dump(node,include_attributes=False).encode())))
    require(bool(rows),'empty PCell template list');return rows


def python_views(text):
    tree=ast.parse(text);rows=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            rows.append(dict(kind='python-declaration',name=node.name,line=node.lineno,
                             declaration_type=type(node).__name__,ast_sha256=sha(ast.dump(node,include_attributes=False).encode())))
        elif isinstance(node,ast.ImportFrom):
            rows.append(dict(kind='python-import',name=node.module or '.',line=node.lineno,identifiers=[a.name for a in node.names]))
        elif isinstance(node,ast.Import):
            rows.append(dict(kind='python-import',name='import',line=node.lineno,identifiers=[a.name for a in node.names]))
    return rows


def ruby_views(text):
    """Static option references only; no Ruby execution or inferred defaults."""
    from scripts.inventory_upstream_semantics import string_mask
    text,commands=ruby_source_mask(text)
    clean=re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|#[^\n]*',lambda m:m[0] if m[0][0] in ('"',"'") else ' '*len(m[0]),text)
    code=string_mask(clean,single=True)
    require(not re.search(r'%[qQxrs][^\w\s]|<<[-~]?[A-Za-z_]\w*',code),'unsupported Ruby literal; view requires explicit unresolved disposition')
    for match in list(re.finditer(r'%[wWiI]([^\w\s])',code)):
        if code[match.start()]!='%':continue
        opener=match[1];closer={'[':']','{':'}','(':')','<':'>'}.get(opener,opener);position=match.end();depth=1
        while position<len(code) and depth:
            if code[position]=='\\':position+=2;continue
            if code[position]==closer:depth-=1
            elif opener!=closer and code[position]==opener:depth+=1
            position+=1
        require(depth==0,'unterminated Ruby array literal')
        code=code[:match.start()]+re.sub(r'[^\n]',' ',code[match.start():position])+code[position:]
    rows=commands
    for match in re.finditer(r'(?m)^\s*(class|module|def)\s+([A-Za-z_][\w.:!?=]*)',code):
        rows.append(dict(kind='ruby-'+match[1],name=match[2],line=code.count('\n',0,match.start())+1))
    for match in re.finditer(r'(?m)^\s*((?:\$|@{1,2})?[A-Za-z_]\w*)\s*=(?!=)([^\n]*)',code):
        rows.append(dict(kind='macro-assignment',name=match[1],line=code.count('\n',0,match.start())+1,
                         expression_sha256=sha(clean[match.start():match.end()].encode())))
    for match in re.finditer(r'\bfill_pattern\s*\(\s*([\'"])([^\'"\n]+)\1',clean):
        if code[match.start():match.start()+len('fill_pattern')]!='fill_pattern':continue
        rows.append(dict(kind='generated-fill-cell',name=match[2],line=code.count('\n',0,match.start())+1))
    for match in re.finditer(r'(?m)^\s*(connect(?:_global|_implicit|_explicit)?|soft_connect|equivalent_pins|same_nets|same_circuits|require|load|source|include)\b([^\n]*)',code):
        rows.append(dict(kind='ruby-mapping-or-dependency',name=match[1],line=code.count('\n',0,match.start())+1,
                         argument_identifiers=sorted(set(re.findall(r'\b[A-Za-z_]\w*\b',match[2]))),
                         expression_sha256=sha(clean[match.start():match.end()].encode())))
    for m in re.finditer(r'\b(options|defaults|opts|drc_initial|lvs_initial)\s*\[\s*([\'"])([A-Za-z_]\w*)\2\s*\]',clean):
        if code[m.start():m.start()+len(m[1])]!=m[1]:continue
        rows.append(dict(kind='macro-option-reference',name=m[3],scope=m[1],line=clean.count('\n',0,m.start())+1))
    for m in re.finditer(r'\b([A-Za-z_]\w*)\.(add_selection|add_checkbox|add_string)\s*\(\s*([\'"])([A-Za-z_]\w*)\3',clean):
        if code[m.start():m.start()+len(m[1])]!=m[1]:continue
        tail=clean[m.end():clean.find('\n',m.end()) if '\n' in clean[m.end():] else len(clean)]
        choices=re.search(r'%w\[([^\]]*)\]',tail)
        rows.append(dict(kind='macro-option-declaration',name=m[4],scope=m[1],widget=m[2],
                         line=clean.count('\n',0,m.start())+1,choices=choices[1].split() if choices else None))
    # Retain all literal hash keys (including defaults) as candidates, not selections.
    for m in re.finditer(r'([\'"])([A-Za-z_]\w*)\1\s*=>',clean):
        if not code[m.end()-2:m.end()]==' =>'.strip():continue
        rows.append(dict(kind='macro-option-key',name=m[2],line=clean.count('\n',0,m.start())+1))
    return rows


def ruby_source_mask(text):
    chars=list(text);index=0;commands=[]
    while index<len(text):
        if (index==0 or text[index-1]=='\n') and re.match(r'=begin\b',text[index:]):
            end=re.search(r'(?m)^=end\b[^\n]*',text[index:]);require(end is not None,'unterminated Ruby block comment')
            stop=index+end.end()
            for n in range(index,stop):
                if chars[n]!='\n':chars[n]=' '
            index=stop;continue
        if text[index]=='#':
            newline=text.find('\n',index);index=newline if newline>=0 else len(text);continue
        if text[index]=='`':
            start=index;index+=1
            while index<len(text):
                if text[index]=='\\':index+=2;continue
                if text[index]=='`':index+=1;break
                index+=1
            else:raise ValueError('Unterminated Ruby command literal')
            commands.append(dict(kind='ruby-command-literal',name='(unevaluated-command)',line=text.count('\n',0,start)+1,expression_sha256=sha(text[start:index].encode())))
            for n in range(start,index):
                if chars[n]!='\n':chars[n]=' '
            continue
        if text[index] in ('"',"'"):
            quote=text[index];index+=1
            while index<len(text):
                if text[index]=='\\':index+=2;continue
                if text[index]==quote:index+=1;break
                index+=1
            else:raise ValueError('Unterminated Ruby quoted string')
            continue
        index+=1
    return ''.join(chars),commands


def ruby_without_block_comments(text):return ruby_source_mask(text)[0]


def macro_views(text):
    root=ET.fromstring(text);require(root.tag=='klayout-macro','unexpected macro XML root')
    require(not (root.findtext('prolog') or '').strip() and not (root.findtext('epilog') or '').strip(),'unreviewed macro prolog/epilog code')
    language=root.findtext('interpreter');body=root.findtext('text') or ''
    rows=[dict(kind='klayout-macro',name=root.findtext('category') or '(uncategorized)',interpreter=language,
               body_sha256=sha(body.encode()),autorun=root.findtext('autorun'))]
    if language=='python':children=python_views(body)
    elif language=='ruby' or language=='dsl' and root.findtext('dsl-interpreter-name')=='drc-dsl-xml':children=ruby_views(body)
    else:raise ValueError('Unimplemented macro interpreter: '+str(language))
    rows += [dict(**r,line_scope='embedded-text') for r in children]
    return rows


def preprocessor_views(text):
    rows=[]
    for number,line in enumerate(text.splitlines(),1):
        match=re.match(r'\s*#\s*(if|ifdef|ifndef|elif|elseif|define|undef)\b(.*)',line)
        if not match:continue
        tokens=re.findall(r'\b[A-Z][A-Z0-9_]*\b',match[2])
        rows.append(dict(kind='build-process-option',name=tokens[0] if tokens else '(expression)',line=number,
                         directive=match[1],identifiers=sorted(set(tokens)),expression_sha256=sha(match[2].encode())))
    return rows


def conditional_json_views(text):
    """Read the pinned flat-map JSON template without choosing any #if branch."""
    rows=preprocessor_views(text);stack=[]
    for number,line in enumerate(text.splitlines(),1):
        value=line.strip()
        if not value or value.startswith('#'):continue
        if value in ('{','}', '},',']','],'):
            if value[0] in '}]' and stack:stack.pop()
            continue
        if match:=re.fullmatch(r'("(?:\\.|[^"\\])*")\s*:\s*(.*)',value):
            key=strict_json(match[1]);tail=match[2].rstrip(',').strip()
            if tail in ('{','['):stack.append(key);continue
            literal=strict_json(tail)
            rows.append(dict(kind='conditional-json-setting',name=key,context=list(stack),line=number,value=factual(literal),
                             activation='All lexical branches retained; no preprocessor selection inferred.'))
            continue
        token=value.rstrip(',').strip()
        require(bool(stack) and token.startswith('"'),'unreviewed conditional JSON template syntax')
        literal=strict_json(token)
        rows.append(dict(kind='conditional-json-option',name=literal,context=list(stack),line=number,
                         activation='All lexical branches retained; no preprocessor selection inferred.'))
    require(any(r['kind'].startswith('conditional-json') for r in rows),'no conditional JSON names enumerated')
    return rows


def xml_views(text):
    root=ET.fromstring(text);rows=[]
    if root.tag=='Component':
        require(bool(root.get('names')),'Qucs-S component has no declared identity')
        names=[n.strip() for n in root.get('names').split(',')]
        require(all(names) and len(set(names))==len(names),'empty or duplicate Qucs-S alias')
        rows.extend(dict(kind='qucs-component',name=name,aliases=names,library=root.get('library'),schematic_id=root.get('schematic_id')) for name in names)
        for node in root.findall('./Models/*'):
            require(node.get('value') is not None,'Qucs-S model has no identity')
            rows.append(dict(kind='qucs-model',name=node.get('value'),model_type=node.tag))
        for node in root.findall('./Symbols/Symbol'):
            require(bool(node.get('id')),'Qucs-S symbol has no identity')
            refs=[(n.text or '').strip() for n in node.findall('File')]
            rows.append(dict(kind='qucs-symbol-reference',name=node.get('id'),references=refs,
                             reference_resolution='External variable-qualified paths retained; no installed symbol equivalence inferred.'))
        for node in root.findall('./Netlists/*'):
            rows.append(dict(kind='qucs-netlist-template',name=node.tag,expression_sha256=sha((node.get('value') or '').encode())))
        params=root.findall('./Parameters/Parameter');unique(params,lambda n:n.get('name'),'Qucs-S parameter')
        for node in params:
            require(bool(node.get('name')),'unnamed Qucs-S parameter')
            rows.append(dict(kind='qucs-parameter',name=node.get('name'),default=factual(node.get('default_value')),unit=factual(node.get('unit'))))
        return rows
    if root.tag=='circuit':
        require(root.findtext('version')=='2','unreviewed Digital circuit version')
        rows.append(dict(kind='digital-circuit-view',name='(no declared circuit model name)',version=2,wire_count=len(root.findall('./wires/wire'))))
        for index,node in enumerate(root.findall('./visualElements/visualElement')):
            name=node.findtext('elementName');require(bool(name),'unnamed Digital element')
            attrs={};label=None
            for entry in node.findall('./elementAttributes/entry'):
                require(len(entry)==2 and entry[0].tag=='string','unreviewed Digital attribute')
                key=entry[0].text;require(key not in attrs,'duplicate Digital attribute')
                if key=='Label':require(entry[1].tag=='string' and not len(entry[1]),'nonliteral Digital label');label=entry[1].text
                attrs[key]=factual(entry[1].text) if not len(entry[1]) else dict(value_sha256=sha(ET.tostring(entry[1])))
            pos=node.find('pos');require(pos is not None,'missing Digital element position')
            rows.append(dict(kind='digital-element',name=name,index=index,label=label,attributes=attrs,
                             position={k:int(pos.attrib[k]) for k in ('x','y')},terminal_order='not-inferred-from-position-or-declaration-order'))
        require(len(rows)>1,'empty Digital circuit');return rows
    if root.tag=='Stackup':
        for index,node in enumerate(root.iter()):
            if node is root:continue
            if node.attrib:
                rows.append(dict(kind='em-stackup-'+node.tag,name=node.get('Name',node.tag),index=index,attributes=factual(node.attrib)))
        require(bool(rows),'empty EM stackup');return rows
    if root.tag in ('layer-properties','technology'):
        for index,node in enumerate(root.iter()):
            if len(node):continue
            rows.append(dict(kind='technology-xml-setting',name=node.tag,index=index,value=factual(node.text)))
        return rows
    raise ValueError('Unreviewed production XML root: '+root.tag)


def make_views(text):
    rows=[];continued=[];start=0
    for number,line in enumerate(text.splitlines(),1):
        # Recipes are implementation bodies; their enclosing target is retained.
        if not continued and (not line.strip() or line.startswith('\t') or line.lstrip().startswith('#')):continue
        if not continued:start=number
        continued.append(line.rstrip('\\').strip())
        if line.endswith('\\'):continue
        value=' '.join(continued);continued=[]
        if m:=re.match(r'(?:export\s+|override\s+)?([A-Za-z_]\w*)\s*([:+?]?=)(.*)',value):
            body=m[3].strip();literal=body.split() if re.fullmatch(r'[A-Za-z0-9_./+\-\s]*',body) else None
            rows.append(dict(kind='build-variable',name=m[1],operator=m[2],line=start,literal_tokens=literal,expression_sha256=sha(body.encode())))
        elif m:=re.match(r'(-?include|sinclude)\s+(.+)',value):
            rows.append(dict(kind='build-include',name=m[1],line=start,references=factual(m[2].split())))
        elif re.match(r'(ifn?def|ifeq|ifneq|else|endif)\b',value):
            rows.append(dict(kind='build-condition',name=value.split()[0],line=start,expression_sha256=sha(value.encode())))
        elif m:=re.fullmatch(r'(export|unexport)\s+([A-Za-z_][\w\s]*)',value):
            rows.extend(dict(kind='build-export',name=name,line=start,operation=m[1]) for name in m[2].split())
        elif ':' in value:
            name,body=value.split(':',1)
            # Macro-qualified target expressions remain named templates, not expanded cells.
            rows.append(dict(kind='build-target-template',name=factual(name.strip()),line=start,expression_sha256=sha(value.encode())))
        elif re.match(r'(define|endef)\b',value):
            rows.append(dict(kind='build-macro',name=value.split()[1] if len(value.split())>1 else 'endef',line=start,expression_sha256=sha(value.encode())))
        else:raise ValueError('Unreviewed Make declaration at line '+str(start))
    require(not continued,'unterminated Make continuation');return rows


def yaml_views(text):
    rows=[];contexts=[]
    for number,line in enumerate(text.splitlines(),1):
        value=line.strip()
        if not value or value.startswith('#') or value in ('---','...'):continue
        indent=len(line)-len(line.lstrip())
        require('\t' not in line[:indent],'tab-indented YAML')
        while contexts and contexts[-1][0]>=indent:contexts.pop()
        if m:=re.match(r'([A-Za-z_][\w.-]*)\s*:\s*(.*)$',value):
            tail=m[2];require(not tail.startswith(('|','>','&','*','!')),'unreviewed YAML scalar/template')
            rows.append(dict(kind='yaml-setting',name=m[1],context=[v for _,v in contexts],line=number,value=factual(tail)))
            if not tail:contexts.append((indent,m[1]))
        elif value.startswith('- '):
            rows.append(dict(kind='yaml-list-entry',name=str(number),context=[v for _,v in contexts],line=number,value=factual(value[2:])))
        else:raise ValueError('Unreviewed YAML declaration at line '+str(number))
    return rows


def veriloga_extra(text):
    from scripts.inventory_upstream_semantics import strip_c_comments,string_mask
    clean=strip_c_comments(text);code=string_mask(clean);rows=[]
    starts=list(re.finditer(r'\bparamset\s+([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\b',code));ends=list(re.finditer(r'\bendparamset\b',code))
    require(len(starts)==len(ends),'unmatched Verilog-A paramset')
    for index,(start,end) in enumerate(zip(starts,ends)):
        require(start.end()<end.start() and (index+1==len(starts) or end.end()<starts[index+1].start()),'nested or mismatched paramset')
        body=clean[start.end():end.start()];masked=code[start.end():end.start()]
        parameters=[]
        for match in re.finditer(r'\bparameter\s+(?:(real|integer|string)\s+)?([A-Za-z_]\w*)\s*=([^;]+);',masked):
            parameters.append(dict(name=match[2],type=match[1],expression_sha256=sha(body[match.start():match.end()].encode())))
        overrides=[dict(name=m[1],expression_sha256=sha(body[m.start():m.end()].encode())) for m in re.finditer(r'(?m)^\s*\.([A-Za-z_]\w*)\s*=([^;]+);',masked)]
        rows.append(dict(kind='veriloga-paramset',name=start[1],base_model=start[2],line=code.count('\n',0,start.start())+1,parameters=parameters,overrides=overrides))
    for match in re.finditer(r'(?m)^\s*`(define|ifdef|ifndef|elsif|include)\b(.*)',clean):
        if code[match.start():match.end()].lstrip().startswith('`'+match[1]):
            tokens=re.findall(r'\b[A-Za-z_]\w*\b',match[2]);rows.append(dict(kind='veriloga-preprocessor',name=tokens[0] if tokens else '(expression)',directive=match[1],line=code.count('\n',0,match.start())+1,expression_sha256=sha(match[2].encode())))
    return rows


def schematic_views(text):
    if re.match(r'\s*v\s+\{xschem\b',text):
        from icstudio.xschem_io import records,properties
        rows=[];lines=text.splitlines(keepends=True);preamble=True;comment=False
        for index,line in enumerate(lines):
            stripped=line.strip()
            if index==0 or not stripped:continue
            if preamble and stripped.startswith('*'):comment=True;lines[index]='\n';continue
            if preamble and stripped=='}' and comment:
                rows.append(dict(kind='source-diagnostic',name='unmatched-header-comment-close',line=index+1,
                                 reason='An orphan brace follows the initial star-comment preamble. It is retained as a source defect; subsequent typed declarations are inventoried without asserting importability.',
                                 blocks_device_qualification=True));lines[index]='\n';preamble=False;continue
            preamble=False
        for index,record in enumerate(records(''.join(lines))):
            if record[0]=='C':
                props=properties(record[-1])
                rows.append(dict(kind='xschem-instance',name=props.get('name','(unnamed)'),symbol_reference=record[1],record=index,
                                 properties=factual(props),terminal_order='Defined by referenced symbol; not inferred here.'))
            elif record[0] in ('K','G','V','S','F','E') and record[1].strip():
                rows.append(dict(kind='xschem-code-or-property-block',name=record[0],record=index,expression_sha256=sha(record[1].encode())))
        require(bool(rows),'no Xschem instances or source blocks');return rows
    require(re.match(r'\s*<Qucs Schematic [^>]+>',text) is not None,'unknown schematic format')
    rows=[]
    for section in ('Symbol','Components'):
        blocks=re.findall(r'<'+section+r'>\s*(.*?)\s*</'+section+r'>',text,re.S)
        require(len(blocks)==1,'missing/duplicate Qucs '+section+' block')
        for index,line in enumerate(blocks[0].splitlines()):
            line=line.strip()
            if not line:continue
            require(line.startswith('<') and line.endswith('>'),'malformed Qucs record')
            tokens=shlex.split(line[1:-1],posix=True)
            if section=='Components':
                require(len(tokens)>=2,'incomplete Qucs component')
                rows.append(dict(kind='qucs-schematic-instance',name=tokens[1],component=tokens[0],record=index,
                                 attribute_tokens=factual(tokens[2:]),terminal_order='Declared symbol/Port fields retained; no graph equivalence inferred.'))
            elif tokens[0] in ('.PortSym','.ID'):
                rows.append(dict(kind='qucs-schematic-symbol-declaration',name=tokens[-1],declaration=tokens[0],record=index,fields=factual(tokens[1:])))
    require(bool(rows),'empty Qucs schematic');return rows


def supplemental_views(row,raw):
    """A recognized but unsupported format is an explicit view, never context."""
    from scripts.inventory_upstream_semantics import source_kind,interpret,gds_interfaces
    path=row['path'];kind=source_kind(row);suffix=PurePosixPath(path).suffix.lower()
    if row['mode']=='120000':
        target=raw.decode('utf-8');require(target and not target.startswith('/') and '\\' not in target,'unreviewed source symlink target')
        resolved=posixpath.normpath(posixpath.join(posixpath.dirname(path),target));require(not resolved.startswith('../'),'source symlink escapes family root')
        return [dict(kind='source-symlink',name=path,target=target,resolved_path=resolved)]
    if kind=='gds':return [dict(kind='gds-structure',name=r['name']) for r in gds_interfaces(raw)[0]]
    text=raw.decode('utf-8-sig')
    if suffix=='.lps':
        from scripts.inventory_xcircuit import xcircuit_views
        return xcircuit_views(text)
    from scripts.inventory_source_configs import config_views,openrcx
    if suffix=='.rules' and text.lstrip().startswith('Extraction Rules for OpenRCX'):return openrcx(text)
    configured=config_views(path,text)
    if configured is not None:return configured
    if PurePosixPath(path).name.lower() in ('makefile','makefile.in') or suffix=='.mk':return make_views(text)
    if path.endswith('ihp130_pcell_templates.py'):return template_views(text)
    if suffix in ('.lym','.lydrc'):return macro_views(text)
    if suffix in ('.yml','.yaml'):return yaml_views(text)
    if suffix in ('.lvs','.lylvs','.rb','.drc'):
        if text.lstrip().startswith('<?xml'):return macro_views(text)
        return interpret('extraction',ruby_without_block_comments(text),path)+ruby_views(text)
    if suffix=='.json':
        if re.search(r'(?m)^\s*#(?:if|define)',text):return conditional_json_views(text)
        return json_views(text,path)
    if suffix=='.py':
        declarations=python_views(text)
        if kind=='pcell':declarations+=interpret('pcell',text,path)
        if not declarations and all(isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str) for n in ast.parse(text).body):
            declarations=[dict(kind='empty-or-documentation-python-module',name=PurePosixPath(path).name)]
        return declarations
    if suffix=='.sch':return schematic_views(text)
    if suffix in ('.xml','.dig','.lyt','.lyp'):return xml_views(text)
    if suffix in ('.cells','.celllist'):
        rows=[dict(kind='cell-list-entry',name=line.strip(),line=i) for i,line in enumerate(text.splitlines(),1) if line.strip() and not line.lstrip().startswith('#')]
        return [dict(kind='cell-list-view',name=PurePosixPath(path).name,entries=len(rows))]+rows
    if suffix=='.csv':
        reader=csv.reader(io.StringIO(text));header=next(reader,[])
        require(bool(header) and len(set(header))==len(header),'missing/duplicate CSV field declarations')
        rows=[dict(kind='csv-field-declarations',name=PurePosixPath(path).name,fields=factual(header))]
        for number,values in enumerate(reader,2):
            require(len(values)==len(header),'CSV schema width mismatch')
            rows.append(dict(kind='csv-data-record',name=str(number),line=number,values={h:factual(v) for h,v in zip(header,values)}))
        return rows
    if kind=='veriloga':return interpret(kind,text,path)+veriloga_extra(text)
    if kind and kind!='notice':return interpret(kind,text,path)
    raise ValueError('No complete declaration grammar for production format '+(suffix or '(extensionless)'))


def checked_report(path,expected):
    raw=Path(path).read_bytes();require(sha(raw)==expected,'changed reviewed report: '+str(path))
    return json.loads(gzip.decompress(raw))


def blob(row,cache):
    from scripts.reconcile_primitive_inventory import git_hash
    raw=(Path(cache)/row['git_blob_sha1']).read_bytes()
    require(git_hash('blob',raw)==row['git_blob_sha1'] and (row['bytes'] is None or len(raw)==row['bytes']),'changed source blob: '+row['path'])
    return raw


def noninterface_role(row):
    """Only positively identified nonproduction roles bypass declaration parsing."""
    path=PurePosixPath(row['path']);lower=row['path'].lower();parts=tuple(p.lower() for p in path.parts)
    if re.match(r'(license|notice|copying|copyright|authors)(?:[._-].*)?$',path.name,re.I):
        return 'notice','Copyright, license or authorship notice; no production device interface is declared by this notice view.'
    if row['family']=='gf180-open-pdks' and parts[0] in ('sky130',):
        return 'outside-gf-companion-route','This subtree configures SKY130 in the GF companion repository; the selected GF source route does not consume it. It does not replace the separately locked SKY130 release.'
    if row['repository'].startswith('SymbiFlow/make-env@'):
        return 'build-environment','Pinned build-environment gitlink, not a production device/model library.'
    if row['family']=='gf180mcu' and '/models/180mcu_spice_data_clean/' in '/'+lower and path.suffix.lower()=='.csv':
        return 'measurement-and-sweep-data','Published GF characterization measurement/sweep tables under the explicitly named SPICE_DATA source directory; these are validation data, not model/symbol/PCell/extractor declarations.'
    if any(p in ('sg13g2_tests','sg13g2_tests_xyce') for p in parts):
        return 'validation-or-ci','Explicit upstream SG13G2 test/test-XYCE directory; the source is a validation fixture rather than a production library view.'
    if any(p in ('testing','tests','testcases','testcase','examples','more_examples','testbenches','libs.qa','sky130_tests','.github','.gitlab') for p in parts):
        return 'validation-or-ci','Explicit test/example/CI path; this evidence asset is not a production interface supplied to the selected PDK.'
    if '/workflow/output/' in '/'+lower:
        return 'published-workflow-output','Published electromagnetic workflow output, retained as a result asset rather than a production device/library declaration.'
    if any(p in ('docs','doc','libs.doc','.vscode') for p in parts) or path.suffix.lower() in ('.rst','.md','.html','.htm','.pdf','.png','.svg','.gif','.jpg','.bmp','.odt','.xlsx','.mdm') or path.name.lower() in ('readme','changelog','changes','dockerfile','.gitignore','.gitmodules','.gitattributes','.gitkeep','.flake8','.pylintrc','.rubocop.yml','.readthedocs.yaml','manifest.in','requirements.txt','requirements.test.txt','versions.txt','docs.txt'):
        return 'documentation-or-reference','Documentation, measurement, image or repository/build metadata; the named source view is retained without treating prose or measured results as a device implementation.'
    return None


def source_view(row,reason,choice='unimplemented',kind='source-view'):
    if row['family']=='sky130B':choice='inapplicable';reason='This enumerated view belongs to SKY130B, outside target SKY130A. '+reason
    return dict(id='file:'+source_id(row),kind=kind,name=row['path'],sources=[source_id(row)],
                dispositions={t:dict(disposition=choice,reason=reason,qualified=False) for t in targets(row['family'])})


def supplemental(files,parsed,cache,reader=None):
    """Enumerate additional known grammars; keep opaque production inputs blocking."""
    from scripts.inventory_upstream_semantics import source_kind
    items=[];records=[];gaps=[];notices=[]
    read=reader if reader is not None else lambda r:blob(r,cache)
    rescan={'.py','.tcl','.yml','.yaml','.rb','.lvs','.lylvs','.va','.vams','.include','.h'}
    for row in files:
        key=source_id(row);role=noninterface_role(row)
        record=None;raw=None
        if key in parsed:
            raw=read(row);require(sha(raw)==parsed[key]['sha256'],'changed parsed source SHA256')
            items.append(source_view(row,'Every parsed declaration is linked to its own item disposition; exact view bytes alone do not qualify the contained devices.'))
            record=dict(**row,sha256=sha(raw),accounting='reviewed-semantic-report',item_ids=['file:'+key]+list(parsed[key]['interfaces']));records.append(record)
            if parsed[key]['parser']=='notice':notices.append(dict(source=key,git_blob_sha1=row['git_blob_sha1'],sha256=sha(raw)))
            if PurePosixPath(row['path']).suffix.lower() not in rescan:continue
        if role and record is None:
            kind,reason=role;items.append(source_view(row,reason,'inapplicable',kind))
            records.append(dict(**row,accounting=kind,item_ids=['file:'+key]))
            if kind=='notice':
                raw=read(row);records[-1]['sha256']=sha(raw);notices.append(dict(source=key,git_blob_sha1=row.get('git_blob_sha1'),sha256=sha(raw)))
            continue
        suffix=PurePosixPath(row['path']).suffix.lower();kind=source_kind(row)
        reason='This additional source view has no established complete application mapping; all declared interfaces remain unimplemented.'
        if record is None:
            items.append(source_view(row,reason));record=dict(**row,accounting='supplemental-declarations',item_ids=['file:'+key]);records.append(record)
        try:
            if raw is None:raw=read(row)
            record['sha256']=sha(raw)
            declarations=supplemental_views(row,raw)
            if not declarations and not kind=='notice':
                if key in parsed and parsed[key]['interfaces']:continue
                raise ValueError('No declared interface identified; production-view role requires review')
            for number,decl in enumerate(declarations):
                ident='supplement:'+key+':'+str(number)
                # Never redistribute raw conditions or arbitrary source snippets.
                if decl.get('conditions'):decl['conditions_identity']=sha(json.dumps(decl.pop('conditions'),sort_keys=True).encode())
                if decl['kind']=='source-symlink':
                    linked=[source_id(f) for f in files if f['family']==row['family'] and (f['path']==decl['resolved_path'] or f['path'].startswith(decl['resolved_path']+'/'))]
                    require(bool(linked),'source symlink target absent from authenticated family graph');decl['target_sources']=linked
                selected= row['family']!='sky130B'
                item=dict(id=ident,kind=decl['kind'],name=decl.get('name'),sources=[key],facts=decl,
                          dispositions={t:dict(disposition='unimplemented' if selected else 'inapplicable',reason=reason if selected else 'This named declaration belongs to SKY130B; the selected application target is SKY130A.',qualified=False) for t in targets(row['family'])})
                items.append(item);record['item_ids'].append(ident)
        except (ValueError,SyntaxError,UnicodeDecodeError,ET.ParseError,FileNotFoundError) as exc:
            record['accounting']='inventory-gap'
            error='Missing authenticated source blob: '+row.get('git_blob_sha1',row.get('sha256','(unknown)')) if isinstance(exc,FileNotFoundError) else str(exc)
            gaps.append(dict(source=key,format=suffix,error=error,disposition='unimplemented',
                             reason='The file is accounted for, but its contained production declarations have not been completely enumerated.',blocks_inventory_completion=True))
    return items,records,gaps,notices


def sky_supplement(path,ledger):
    """Authenticate and interpret previously unparsed members; never extract paths."""
    import zstandard
    from scripts.inventory_upstream_views import safe_path
    from scripts.inventory_sky130_release import ASSETS
    from icstudio.model import file_digest
    _,size,digest=ASSETS[path.name]
    require(path.stat().st_size==size and file_digest(path)==digest,'changed archive before supplemental scan')
    items=[];sources=[];gaps=[];notices=[];seen=set()
    with path.open('rb') as stream,zstandard.ZstdDecompressor().stream_reader(stream) as decoded,tarfile.open(fileobj=decoded,mode='r|') as archive:
        for member in archive:
            name=safe_path(member.name);require(name not in seen and name in ledger,'unexpected supplemental archive member');seen.add(name)
            original=ledger[name];require(member.isfile() and member.size==original['bytes'],'changed archive member')
            row=dict(**original,family=original['process'],repository='chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392',repository_path=name)
            if 'semantic' in original or 'nodeinfo' in original:
                items.append(source_view(row,'Every retained declaration or process option has an explicit item disposition; source presence does not qualify devices.'))
                sources.append(dict(path=name,accounting='reviewed-release-declarations',sha256=original['sha256']));continue
            raw=archive.extractfile(member).read();require(sha(raw)==original['sha256'],'changed supplemental archive bytes')
            more,records,errors,notice=supplemental([row],{},None,reader=lambda _:raw)
            items+=more;sources+=records;gaps+=errors;notices+=notice
    require(seen==set(ledger),'missing supplemental archive member')
    require(path.stat().st_size==size and file_digest(path)==digest,'changed archive after supplemental scan')
    return items,sources,gaps,notices


def application_identity(semantic,sky):
    from scripts.inventory_upstream_views import package_index
    from scripts.inventory_upstream_semantics import selected_profiles
    from icstudio.digital_platform import ORFS_PROFILES,BUNDLED_PLATFORMS
    result={}
    for target,wanted in semantic['packages'].items():
        actual,_=package_index(ROOT/'icstudio/assets/pdks'/target)
        require(all(actual[k]==wanted[k] for k in ('revision','manifest_sha256')),'bundled package differs from reviewed dispositions: '+target);result[target]=actual
    actual,_=package_index(ROOT/'icstudio/assets/pdks/sky130A')
    require(actual==sky['application']['package'],'SKY package differs from reviewed dispositions');result['sky130A']=actual
    require(selected_profiles()==semantic['digital_profiles'],'GF/IHP profile differs from reviewed dispositions')
    require(ORFS_PROFILES['sky130hd']==sky['application']['selected_sky130_profile'] and list(BUNDLED_PLATFORMS)==sky['application']['bundled_platforms'],'SKY profile differs from reviewed dispositions')
    return result


def main():
    from icstudio.model import file_digest
    from scripts.inventory_upstream_semantics import load_sources
    from scripts.inventory_upstream_views import verified_closure,compressed
    from scripts.inventory_sky130_release import ASSETS,archive_rows
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True,help='Original Git blob cache; no source code is executed.')
    parser.add_argument('--sky-cache',type=Path,action='append',required=True)
    parser.add_argument('--companion-inputs',type=Path,default=ROOT/'docs/qualification/source-dispositions-companion-inputs-2026-11-07.json.gz')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists(),'choose a new output path')
    paths=[Path(__file__),ROOT/'scripts/inventory_source_configs.py',ROOT/'scripts/inventory_xcircuit.py',ROOT/'scripts/inventory_upstream_semantics.py',ROOT/'scripts/inventory_sky130_release.py',ROOT/'scripts/inventory_upstream_views.py',ROOT/'scripts/inventory_device_models.py',ROOT/'scripts/inventory_veriloga_models.py',ROOT/'scripts/reconcile_primitive_inventory.py',ROOT/'icstudio/model.py',ROOT/'icstudio/xschem_io.py',ROOT/'icstudio/digital_platform.py']
    original=ROOT/'docs/qualification/upstream-view-inputs-2026-10-20.json.gz';gf=ROOT/'docs/qualification/upstream-semantics-gf-inputs-2026-11-07.json.gz'
    paths += [original,gf,args.companion_inputs]+[ROOT/value[0] for value in REPORTS.values()]
    before={str(p):file_digest(p) for p in paths}
    semantic=checked_report(ROOT/REPORTS['semantic'][0],REPORTS['semantic'][1]);sky=checked_report(ROOT/REPORTS['sky'][0],REPORTS['sky'][1])
    application=application_identity(semantic,sky)
    files,closure=load_sources(original,gf)
    companions,companion_closure=verified_closure(json.loads(gzip.decompress(args.companion_inputs.read_bytes())),roots=COMPANION_ROOTS,repositories=COMPANION_PINS)
    items,parsed,_=semantic_items(semantic,files)
    extra,source_records,gaps,notices=supplemental(files+companions,parsed,args.cache);items+=extra
    print(json.dumps(dict(phase='git-sources',files=len(source_records),items=len(items),inventory_gaps=len(gaps))),flush=True)
    archive_records=[];sky_source_records=[]
    for name,(_,size,digest) in sorted(ASSETS.items()):
        matches=[p/name for p in args.sky_cache if (p/name).is_file()]
        require(len(matches)==1,'missing/ambiguous SKY release archive: '+name)
        print('Authenticating '+name,flush=True);rows=archive_rows(matches[0],digest,size);archive_records+=rows
        more,records,errors,notice=sky_supplement(matches[0],{r['path']:r for r in rows})
        items+=more;sky_source_records+=records;gaps+=errors;notices+=notice
    # The archive parser legitimately returns tuples for Magic port pairs;
    # reviewed JSON encodes those same arrays as lists. Compare canonical JSON.
    from scripts.inventory_upstream_views import canonical
    require(canonical(sorted(archive_records,key=lambda r:r['path']))==canonical(sky['files']),'SKY report differs from authenticated archive declarations')
    sky_rows,sky_files=sky_items(sky);items+=sky_rows
    require(len({r['id'] for r in items})==len(items),'duplicate final item identity')
    for row in source_records:
        if 'sha256' in row:require(sha(blob(row,args.cache))==row['sha256'],'Git source changed during complete audit')
    require(application_identity(semantic,sky)==application,'application changed during audit')
    require(before=={str(p):file_digest(p) for p in paths},'auditor/source input changed during execution')
    report=dict(schema=1,chunk=7,status='GAPS' if gaps else 'PASS_INVENTORY_DISPOSITIONS',qualified=False,chunk_complete=False,
                inventory_complete=not gaps,device_qualification_complete=False,scope='Original source-completeness bookkeeping criterion only; unsupported required devices and all implementation/electrical/physical/release gates remain open.',
                implementation_and_inputs_sha256={p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.name:v for p,v in ((Path(k),v) for k,v in before.items())},
                source_closure=closure,companion_closure=companion_closure,reviewed_reports=REPORTS,
                files=source_records,sky_files=sky['files'],sky_source_accounting=sky_source_records,application=application,items=items,inventory_gaps=gaps,notice_sources=notices,
                retained_source_diagnostics=semantic['blocking_source_diagnostics'],
                counts=dict(files=len(source_records)+len(sky_files),items=len(items),inventory_gaps=len(gaps),
                            by_kind=dict(Counter(i['kind'] for i in items)),dispositions=dict(Counter(d['disposition'] for i in items for d in i['dispositions'].values()))))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(compressed(report))
    print(json.dumps(dict(status=report['status'],counts=report['counts'],report_sha256=file_digest(args.output)),sort_keys=True))
    return 1 if gaps else 0


if __name__=='__main__':raise SystemExit(main())
