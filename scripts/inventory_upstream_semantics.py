"""Reconcile authenticated GF180/IHP source interfaces without claiming qualification.

Read-only, offline by default. Every parsed byte must match its reconstructed Git
tree. No upstream Python, Ruby, Tcl, Verilog or model code is executed. Source
interfaces, implementation disposition and electrical qualification are separate.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import posixpath
import re
import shlex
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest
from scripts.inventory_device_models import inventory, parse as spice_parse, logical_lines
from scripts.inventory_upstream_views import canonical, compressed, safe_path, verified_closure
from scripts.inventory_veriloga_models import declarations as va_declarations
from scripts.reconcile_primitive_inventory import git_hash

GF_ROOTS = {'gf180-ecosystem': 'fossi-foundation/gf180mcu-pdk@25ed9c64b64b8e1b93cc4d2d5cade4cd82383a9a'}
GF_PINS = {
    'fossi-foundation/gf180mcu-pdk': ('25ed9c64b64b8e1b93cc4d2d5cade4cd82383a9a', '5d528aae1f078d24712ee1e2cd7d72d697b32a2e'),
    'google/globalfoundries-pdk-libs-gf180mcu_fd_bd_sram': ('6a03b4584ffd90905f8a3bdc0327da173d3c8f69', '2b53ffeb66744b31734ae7b7f18f819590b99a6b'),
    'google/globalfoundries-pdk-libs-gf180mcu_fd_io': ('2aeec51ea2824b6cc0b396acfc39f4535f40b23a', '88fce52620dbef7cdb522726fd674d92af492cdb'),
    'google/globalfoundries-pdk-libs-gf180mcu_fd_pr': ('9f992d5a9186d1f7820c58f039c484ad35b2edea', 'a08a946e935297b1958800d6074fd38935969d4f'),
    'google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0': ('43beb45e4d323a76239de436db2df6732e9a689b', '10f32f9e7b153cc5388c7ba585874ffc7c6cb682'),
    'google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu9t5v0': ('3781fd2951da6e3dc4600e52d997398a9463caeb', '16a30cfc064eb9b804be7ce951668480353e288c'),
    'google/globalfoundries-pdk-ip-gf180mcu_fd_ip_sram': ('9c411928870ce15226228fa52ddb6ecc0ea4ffbe', 'ff88f597aca4a20f32f044a276cfe21e98252c5e'),
    'google/open-source-pdks': ('6658edd208f5b566be504f016477a7cb04a78cb8', '12c7c7febdfa72f4af2ac759420240946f20a44d'),
}


def source_kind(row):
    """Deterministic source selection; all other files retain an explicit role."""
    p = row['path'].lower()
    name = PurePosixPath(p).name
    if name.startswith(('license', 'copying', 'notice')):
        return 'notice'
    if name == 'definition.json':
        return 'cell-definition'
    if any(part in PurePosixPath(p).parts for part in ('testing', 'tests', 'testcases', 'examples', 'testbenches')):
        return None
    if p.endswith('.cdl'):
        return 'cdl'
    if p.endswith('.lef'):
        return 'lef'
    if p.endswith('.gds'):
        return 'gds'
    if p.endswith('.sym'):
        return 'symbol'
    if p.endswith(('.va', '.vams')) or ('verilog-a/' in p and p.endswith(('.include', '.inc', '.h'))):
        return 'veriloga'
    if p.endswith(('.spice', '.ngspice', '.xyce', '.sp', '.spi', '.gc')):
        return 'spice'
    if '/models/' in '/' + p and p.endswith(('.lib', '.include', '.inc')):
        return 'spice'
    if p.endswith('.lib'):
        return 'liberty'
    if p.endswith('.v'):
        return 'verilog'
    if ('pymacros/' in p or 'sg13g2_pycell_lib/' in p) and p.endswith('.py'):
        return 'pcell'
    if ('/lvs/' in p or '/macros/' in p) and p.endswith(('.lvs', '.lylvs', '.yml', '.rb')):
        return 'extraction'
    if ('magic/' in p or 'netgen/' in p) and p.endswith(('.tech', '.tcl')):
        return 'physical-tool'
    if 'klayout/' in p and p.endswith('.json'):
        return 'process-metadata'
    return None


def source_role(row):
    kind = source_kind(row)
    if kind:
        return kind, 'Authenticated content interpreted by the named parser; exceptions remain explicit gaps.'
    p = row['path'].lower()
    if any(part in PurePosixPath(p).parts for part in ('testing', 'tests', 'testcases', 'examples', 'testbenches')):
        return 'validation-or-example', 'Test/example assets are evidence inputs, not production interface declarations.'
    if PurePosixPath(p).suffix in ('.gds', '.oas', '.png', '.pdf', '.xlsx', '.mdm', '.csv', '.svg', '.out', '.htm', '.gif'):
        return 'physical-or-reference-asset', 'Binary geometry, measurement, result or documentation retained in the complete file ledger; no electrical interface inferred.'
    return 'other-source-context', 'Retained source/configuration/documentation outside the declared interface grammars; not declared inapplicable to qualification.'


def gds_interfaces(data):
    """Accept GDSII 2048-byte zero block padding, then use the shared parser."""
    from scripts.inventory_sky130_release import gds
    position = 0
    while position + 4 <= len(data):
        length, kind, dtype = struct.unpack_from('>HBB',data,position)
        if length < 4 or length % 2 or position+length > len(data):
            raise ValueError('Invalid GDS record length.')
        position += length
        if kind == 4:
            padding = data[position:]
            if padding and (len(padding) != (-position)%2048 or any(padding)):
                raise ValueError('Unreviewed data after GDS ENDLIB.')
            parsed = gds(data[:position])
            return parsed['declarations'],len(padding)
    raise ValueError('Unterminated GDS library.')


def authenticated_bytes(row, cache):
    if row['mode'] not in ('100644', '100755'):
        raise ValueError('A semantic source is not a regular file: ' + row['path'])
    sha = row['git_blob_sha1']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Invalid source blob identity.')
    path = Path(cache) / sha
    data = path.read_bytes()
    if git_hash('blob', data) != sha or row['bytes'] is not None and len(data) != row['bytes']:
        raise ValueError('Changed semantic source: ' + row['path'])
    return data


def strip_c_comments(text):
    # Strings remain intact; comment removal preserves source line references.
    return re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*',
                  lambda m: m[0] if m[0].startswith('"') else re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)


def string_mask(text, single=False):
    pattern = r'"(?:\\.|[^"\\])*"' + (r'|\'(?:\\.|[^\'\\])*\'' if single else '')
    masked = re.sub(pattern,lambda m:re.sub(r'[^\n]', ' ', m[0]),text,flags=re.S)
    if '"' in masked or single and "'" in masked:
        raise ValueError('Unterminated quoted string.')
    return masked


def liberty_attributes(body, keys):
    pattern = re.compile(r'"(?:\\.|[^"\\])*"|\b(' + '|'.join(keys) + r')\s*:\s*("(?:\\.|[^"\\])*"|[^;]+);',re.S)
    result = {}
    for m in pattern.finditer(body):
        if m[1] is not None:
            if m[1] in result:
                raise ValueError('Duplicate Liberty interface attribute: ' + m[1])
            result[m[1]] = m[2].strip().strip('"')
    return result


def liberty(text):
    """Balanced groups, cell/pin identities and declared PVT; no timing inference."""
    clean = strip_c_comments(text)
    string_mask(clean)
    token = re.compile(r'"(?:\\.|[^"\\])*"|[{}]|\b(?:library|cell|operating_conditions|pin|pg_pin|bus)\s*\(\s*("(?:\\.|[^"\\])*"|[^()]*)\s*\)\s*\{', re.S)
    stack, rows, depth = [], [], 0
    for m in token.finditer(clean):
        value = m[0]
        if value.startswith('"'):
            continue
        if value == '}':
            if depth <= 0:
                raise ValueError('Unbalanced Liberty group.')
            if stack and stack[-1][0] == depth:
                _, row, start = stack.pop()
                body = clean[start:m.start()]
                if row['kind'] in ('library', 'operating_conditions'):
                    keys = ('nom_process', 'nom_voltage', 'nom_temperature') if row['kind'] == 'library' else ('process', 'voltage', 'temperature')
                    row['pvt'] = liberty_attributes(body, keys)
                elif row['kind'] in ('pin', 'pg_pin', 'bus'):
                    row['attributes'] = liberty_attributes(body, ('direction', 'pg_type', 'voltage_name', 'bus_type'))
            depth -= 1
        elif value == '{':
            depth += 1
        else:
            kind = value.split('(', 1)[0].strip()
            row = dict(kind=kind, name=m[1].strip().strip('"'), line=clean.count('\n', 0, m.start()) + 1)
            if not row['name']:
                raise ValueError('Empty Liberty identity.')
            row['context'] = [{'kind': item[1]['kind'], 'name': item[1]['name']} for item in stack]
            rows.append(row)
            depth += 1
            stack.append((depth, row, m.end()))
    if depth or stack:
        raise ValueError('Unterminated Liberty group.')
    return rows


def lef(text):
    clean = re.sub(r'"(?:\\.|[^"\\])*"|#[^\n]*', lambda m:m[0] if m[0].startswith('"') else ' ' * len(m[0]), text)
    tokens = list(re.finditer(r'"(?:\\.|[^"\\])*"|[^\s;]+|;', clean))
    macros, current, pin, properties_block = [], None, None, False
    for i, tok in enumerate(tokens):
        token = tok[0]
        following = tokens[i+1][0] if i+1 < len(tokens) else ''
        if token == 'PROPERTYDEFINITIONS':
            properties_block = not (i > 0 and tokens[i-1][0] == 'END')
            continue
        if properties_block:
            continue
        if token == 'MACRO':
            if current is not None or not following or following == ';':
                raise ValueError('Nested or unnamed LEF macro.')
            current = dict(kind='lef-macro', name=following, line=clean.count('\n',0,tok.start())+1, pins=[])
            macros.append(current)
        elif token == 'PIN' and current is not None:
            if pin is not None or not following or following == ';':
                raise ValueError('Unterminated or unnamed LEF pin.')
            pin = following
            current['pins'].append(pin)
        elif token == 'END' and current is not None:
            if following == pin:
                pin = None
            elif following == current['name']:
                if pin is not None:
                    raise ValueError('Unterminated LEF pin.')
                current = None
    if current is not None or pin is not None:
        raise ValueError('Unterminated LEF macro or pin.')
    return macros


def expression(node):
    def facts(value):
        if isinstance(value,str) and not re.fullmatch(r'[A-Za-z0-9_.:/^+%@\-]*',value):
            return {'literal_type':'str','value_sha256':hashlib.sha256(value.encode()).hexdigest()}
        if isinstance(value,(list,tuple)):
            return [facts(v) for v in value]
        if isinstance(value,dict):
            return {'literal_type':'dict','entries':[[facts(k),facts(v)] for k,v in value.items()]}
        return value
    try:
        value = ast.literal_eval(node)
        if isinstance(value,str) and not re.fullmatch(r'[A-Za-z0-9_.:/^+%@\-]*',value):
            return {'literal_type':'str','value_sha256':hashlib.sha256(value.encode()).hexdigest()}
        return {'literal': facts(value)}
    except (ValueError, TypeError):
        return {'expression_kind':type(node).__name__,
                'expression_sha256':hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest(),
                'referenced_names':sorted({n.id for n in ast.walk(node) if isinstance(n,ast.Name)}),
                'literal_tokens':sorted({n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str) and re.fullmatch(r'[A-Za-z0-9_.:/^+%@\-]*',n.value)})}


def pcells(text):
    """Parse declarations without importing or executing upstream generators."""
    tree = ast.parse(text)
    rows = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'moduleNames' for t in node.targets):
            names = ast.literal_eval(node.value)
            if not isinstance(names, list) or not all(isinstance(n, str) and n.endswith('_code') for n in names):
                raise ValueError('Unknown IHP registration list.')
            # This list feeds the registerPCells loop. Retain the construction
            # rule instead of treating the dynamic registration call as literal.
            rows.extend(dict(kind='pcell-registration', name=n[:-5], module=n, line=node.lineno,
                             registration='IHP moduleNames/_code loop; execution not asserted') for n in names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'register_pcell':
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                rows.append(dict(kind='pcell-registration', name=node.args[0].value, line=node.lineno,
                                 implementation=expression(node.args[1]) if len(node.args) > 1 else None))
            else:
                rows.append(dict(kind='dynamic-registration', name='nonliteral-registration', line=node.lineno,
                                 expression=expression(node)))
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        parameters = []
        choices = []
        handles = {}
        assignments = {id(n.value):n.targets[0] for n in ast.walk(cls) if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.value,ast.Call)}
        def reference(node):
            if isinstance(node,ast.Name):return node.id
            if isinstance(node,ast.Attribute):return reference(node.value)+'.'+node.attr
            return '<dynamic>'
        for node in sorted(ast.walk(cls),key=lambda n:(getattr(n,'lineno',0),getattr(n,'col_offset',0))):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'param' and node.args:
                if id(node) in assignments and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                    handles[reference(assignments[id(node)])] = node.args[0].value
                parameters.append(dict(name=expression(node.args[0]), line=node.lineno,
                                       arguments=[expression(n) for n in node.args[1:]],
                                       keywords={k.arg: expression(k.value) for k in node.keywords if k.arg is not None}))
            elif isinstance(node.func, ast.Attribute) and node.func.attr == 'add_choice':
                choices.append(dict(line=node.lineno, receiver=expression(node.func.value), parameter=handles.get(reference(node.func.value)), values=[expression(n) for n in node.args]))
            elif isinstance(node.func, ast.Name) and node.func.id == 'specs' and node.args:
                parameters.append(dict(name=expression(node.args[0]), line=node.lineno,
                                       arguments=[expression(n) for n in node.args[1:]],
                                       keywords={k.arg: expression(k.value) for k in node.keywords if k.arg is not None}))
        if parameters or choices:
            rows.append(dict(kind='pcell-parameters', name=cls.name, line=cls.lineno,
                             parameters=sorted(parameters, key=lambda r:r['line']), choices=sorted(choices, key=lambda r:r['line'])))
    return sorted(rows, key=lambda r:(r['line'], r['kind'], r['name']))


def extraction(text):
    if text.lstrip().startswith('<?xml'):
        text = ET.fromstring(text).findtext('text') or ''
    # Ruby comments disappear, but quoted names and interpolation are retained.
    clean = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|#[^\n]*',
                   lambda m:m[0] if m[0][0] in ('"', "'") else ' ' * len(m[0]), text)
    rows = []
    code = string_mask(clean,single=True)
    for match in list(re.finditer(r'%([wWiI])([^\w\s])',code)):
        if code[match.start()] != '%':
            continue
        opener = match[2]
        closer = {'(':')','[':']','{':'}','<':'>'}.get(opener,opener)
        position, depth = match.end(), 1
        while position < len(code) and depth:
            if code[position] == '\\':
                position += 2
                continue
            if code[position] == closer:
                depth -= 1
            elif opener != closer and code[position] == opener:
                depth += 1
            position += 1
        if depth:
            raise ValueError('Unterminated Ruby word/symbol array.')
        value = clean[match.end():position-1]
        rows.append(dict(kind='extraction-literal',name='%'+match[1],line=clean.count('\n',0,match.start())+1,
                         values=value.split() if match[1] in ('w','i') and '\\' not in value else None,
                         expression_sha256=hashlib.sha256(value.encode()).hexdigest() if match[1] in ('W','I') or '\\' in value else None))
        code = code[:match.start()] + re.sub(r'[^\n]',' ',code[match.start():position]) + code[position:]
    if re.search(r'%[qQwWiIxrs][^\w\s]|<<[-~]?[A-Za-z_]\w*',code):
        raise ValueError('Unreviewed Ruby percent/heredoc literal.')
    calls = list(re.finditer(r'\bextract_devices\s*\(', code))
    for start in calls:
        tail = clean[start.end():]
        m = re.match(r'\s*([A-Za-z_][\w.:]*)\s*\(\s*([\'"])(.*?)\2', tail, re.S)
        row = dict(kind='extracted-device', line=clean.count('\n', 0, start.start()) + 1)
        if m:
            row.update(name=m[3], extractor=m[1], dynamic='#{' in m[3])
            end = tail.find('})')
            fragment = tail[:end + 2] if end >= 0 else tail[:2000]
            row['layer_roles'] = re.findall(r'[\'"]([\w]+)[\'"]\s*=>', fragment)
        else:
            row.update(name='unresolved-expression', dynamic=True, expression_sha256=hashlib.sha256(tail.splitlines()[0].encode()).hexdigest())
        rows.append(row)
    for m in re.finditer(r'(?m)^\s*#%include\s+([^\n]+)', text):
        rows.append(dict(kind='extraction-include', name=m[1].strip(), line=text.count('\n', 0, m.start()) + 1))
    # The selected GF launcher declares the variant->physical-stack relation.
    for m in re.finditer(r'(?:if|elsif)\s+options\["variant"\]\s*==\s*"([ABCD])"(.*?)(?=elsif|\bend\b)', clean, re.S):
        if not re.match(r'(?:if|elsif)\b',code[m.start():]):
            continue
        values = dict(re.findall(r'\$(metal_top|metal_level|mim_option)\s*=\s*"([^"]+)"', m[2]))
        rows.append(dict(kind='process-variant', name=m[1], line=clean.count('\n', 0, m.start()) + 1, options=values))
    return rows


def symbol(text):
    from icstudio.xschem_io import records, properties
    if re.search(r'(?m)^\s*v\s+\{xschem\b', text):
        pins, attributes, numbers = [], {}, {}
        for record in records(text):
            if record[0] == 'K':
                attributes = properties(record[1])
            elif record[0] == 'B' and record[1] == '5':
                props = properties(record[-1])
                if not props.get('name') or props['name'] in pins:
                    raise ValueError('Missing or duplicate Xschem terminal.')
                pins.append(props['name'])
                if 'sim_pinnumber' in props:
                    numbers[props['name']] = int(props['sim_pinnumber'])
        if numbers:
            if set(numbers) != set(pins) or len(set(numbers.values())) != len(numbers):
                raise ValueError('Incomplete or duplicate Xschem terminal ordering.')
            pins.sort(key=numbers.get)
        facts = {key:value for key,value in attributes.items() if key in ('type','model','spiceprefix','available_models','extra') and re.fullmatch(r'[\w\s.+-]*',value)}
        return [dict(kind='symbol', name='', line=1, format='xschem', pins=pins, attributes=facts,
                     attribute_keys=sorted(attributes),
                     nonliteral_attribute_sha256={key:hashlib.sha256(value.encode()).hexdigest() for key,value in attributes.items() if key not in facts},
                     dynamic_attribute_keys=sorted(key for key,value in attributes.items() if 'tcleval' in value))]
    if re.match(r'\s*v\s+\d+', text):
        # gEDA pinseq and pinnumber are distinct from Xschem pin ordering.
        pins = []
        for match in re.finditer(r'(?m)^P\s+[^\n]+\n\{(.*?)^\}', text, re.S|re.M):
            props = dict(re.findall(r'(?m)^(pinlabel|pinnumber|pinseq|pintype)=(.*)$', match[1]))
            pins.append(dict(line=text.count('\n',0,match.start())+1, **props))
        return [dict(kind='symbol', name='', line=1, format='geda', pin_declarations=pins,
                     attributes=dict(re.findall(r'(?m)^(device|model-name|model|refdes|footprint)=(.*)$', text)))]
    if text.lstrip().startswith('<'):
        root = ET.fromstring('<symbol>'+text+'</symbol>')
        ports = [dict(node.attrib) for node in root.findall('PortSym')]
        return [dict(kind='symbol', name='', line=1, format='qucs-s-xml', port_coordinates=ports,
                     labels=[dict(node.attrib) for node in root.findall('Text')],
                     terminal_mapping='Port coordinates and text labels are distinct; no electrical order inferred from proximity.')]
    raise ValueError('Unknown symbol language; no terminal identity inferred.')


def verilog(text):
    clean = strip_c_comments(text)
    code = string_mask(clean)
    rows = []
    for m in re.finditer(r'\b(module|primitive)\s+(\\\S+|[\w$]+)\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;', code, re.S):
        terminals, port_declarations = [], []
        inherited = {}
        for value in m[3].split(','):
            value=value.strip()
            if not value:
                continue
            port = re.fullmatch(r'(?:(input|output|inout)\s+)?(?:(wire|reg|logic)\s+)?(?:(signed|unsigned)\s+)?(?:\[([^\]]+)\]\s*)?([A-Za-z_$][\w$]*|\\\S+)',value)
            if not port:
                raise ValueError('Unreviewed Verilog terminal declaration.')
            if port[1]:
                inherited = dict(direction=port[1], data_type=port[2], signedness=port[3],
                                 packed_range_sha256=hashlib.sha256(port[4].encode()).hexdigest() if port[4] else None)
            terminals.append(port[5])
            port_declarations.append(dict(name=port[5],**inherited))
        rows.append(dict(kind='verilog-' + m[1], name=m[2], line=clean.count('\n', 0, m.start()) + 1,
                         terminals=terminals,port_declarations=port_declarations))
    declarations = len(re.findall(r'\b(?:module|primitive)\s+', code))
    if len(rows) != declarations:
        raise ValueError('Unparsed Verilog interface declaration.')
    return rows


def parse_spice_interfaces(text, path):
    """Use the strict parser with explicit zero-port and .endl-name diagnostics."""
    sentinel = '__ICSTUDIO_ZERO_PORT_SENTINEL__'
    if sentinel in text:
        raise ValueError('Reserved parser marker occurs in upstream source.')
    lines = text.splitlines(keepends=True)
    section = None
    diagnostics = []
    for number, statement in logical_lines(text):
        tokens = shlex.split(statement,comments=True)
        if not tokens:
            continue
        op = tokens[0].casefold()
        if op == '.subckt' and len(tokens) == 2:
            lines[number-1] = lines[number-1].rstrip('\r\n') + ' ' + sentinel + '\n'
        elif op == '.lib' and len(tokens) == 2:
            section = tokens[1].casefold()
        elif op == '.endl' and len(tokens) == 2 and section and tokens[1].casefold() != section:
            diagnostics.append(dict(kind='source-diagnostic', name='endl-name-mismatch', line=number,
                                    declared_section=section, ending_name=tokens[1], blocks_semantic_completion=True))
            lines[number-1] = re.sub(r'(?i)\.endl\s+\S+', '.endl', lines[number-1])
            section = None
        elif op == '.endl':
            section = None
    parsed = spice_parse(''.join(lines),path)
    for row in parsed['definitions']:
        if row.get('pins') == [sentinel]:
            row['pins'] = []
    return parsed, diagnostics


def interpret(kind, text, path):
    if kind in ('spice', 'cdl'):
        parsed, diagnostics = parse_spice_interfaces(text, path)
        rows = parsed['definitions'] + diagnostics
        rows += [dict(kind='model-section', name=name, line=1) for name in parsed['sections']]
        rows += [dict(kind='model-include', name=i['path'], **i) for i in parsed['includes']]
        # Empty subcircuits (including IHP bondpad) are never model support.
        logical = text.splitlines()
        for row in rows:
            if row['kind'] == 'subckt':
                end = next((i for i in range(row['line'], len(logical)) if re.match(r'\s*\.ends\b', logical[i], re.I)), len(logical))
                row['element_count'] = sum(bool(s.strip()) and not s.lstrip().startswith(('*', '.', '+')) for s in logical[row['line']:end])
                body = '\n'.join(logical[row['line']:end])
                declared = re.findall(r'(?im)^\s*\.params?\s+(.+)', body)
                row['local_parameters'] = sorted(set(re.findall(r'\b([A-Za-z_]\w*)\s*=', '\n'.join(declared))))
        return rows
    if kind == 'liberty':
        return liberty(text)
    if kind == 'lef':
        return lef(text)
    if kind == 'pcell':
        return pcells(text)
    if kind == 'extraction':
        return extraction(text)
    if kind == 'symbol':
        rows = symbol(text)
        rows[0]['name'] = PurePosixPath(path).stem
        return rows
    if kind == 'verilog':
        return verilog(text)
    if kind == 'veriloga':
        sentinel = '__ICSTUDIO_ZERO_PORT_SENTINEL__'
        if sentinel in text:
            raise ValueError('Reserved parser marker occurs in upstream source.')
        expanded = re.sub(r'(?m)^(\s*module\s+[A-Za-z_]\w*\s*\()\s*(\)\s*;)',r'\1'+sentinel+r'\2',text)
        rows = [dict(kind='veriloga-module', name=r['module'], **r) for r in va_declarations(expanded, path)]
        for row in rows:
            if row['terminals'] == [sentinel]:
                row['terminals'] = []
        return rows
    if kind in ('cell-definition', 'process-metadata'):
        obj = json.loads(text)
        if kind == 'cell-definition':
            return [dict(kind=kind, name=obj['file_prefix'], line=1,
                         library=obj['library'], ports=obj['ports'], parameters=obj.get('parameters', []))]
        facts = []
        def walk(value, keys):
            if isinstance(value,dict):
                for key,child in sorted(value.items()):
                    walk(child,keys+[key])
            elif isinstance(value,list):
                for index,child in enumerate(value):
                    walk(child,keys+[index])
            elif value is None or isinstance(value,(bool,int,float)) or isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:/+\-]*',value):
                facts.append(dict(key=keys,value=value))
            else:
                facts.append(dict(key=keys,value_type=type(value).__name__,value_sha256=hashlib.sha256(canonical(value)).hexdigest()))
        walk(obj,[])
        return [dict(kind=kind, name=PurePosixPath(path).name, line=1, facts=facts)]
    if kind == 'physical-tool':
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith('#'):
                continue
            if m := re.match(r'(device|fet|fetresist|resist|capacitor|variant|style|proc)\s+([^\s{]+)', s):
                rows.append(dict(kind='physical-declaration', name=m[2], line=number, directive=m[1], declaration_sha256=hashlib.sha256(s.encode()).hexdigest()))
        return rows
    return []


def load_sources(original, gf):
    rows, roots = verified_closure(json.loads(gzip.decompress(Path(original).read_bytes())))
    extra, parents = verified_closure(json.loads(gzip.decompress(Path(gf).read_bytes())), roots=GF_ROOTS, repositories=GF_PINS)
    return sorted(rows + extra, key=lambda r:(r['family'], r['path'])), {'selected_sources': roots, 'gf_parent_graph': parents}


def fetch_missing_sources(files, cache):
    """Stream pinned public archives; retain original files/notices by blob ID."""
    import concurrent.futures
    import tarfile
    import tempfile
    import urllib.request
    cache = Path(cache)
    cache.mkdir(parents=True,exist_ok=True)
    groups = defaultdict(dict)
    for row in files:
        if source_kind(row):
            groups[row['repository']][row['repository_path']] = row
    def fetch(key, wanted):
        if all((cache/r['git_blob_sha1']).is_file() for r in wanted.values()):
            for row in wanted.values():
                authenticated_bytes(row,cache)
            return
        repository,commit = key.rsplit('@',1)
        seen = set()
        url = 'https://codeload.github.com/'+repository+'/tar.gz/'+commit
        with urllib.request.urlopen(url,timeout=180) as response, tarfile.open(fileobj=response,mode='r|gz') as archive:
            for member in archive:
                parts = member.name.split('/',1)
                if len(parts) != 2 or parts[1] not in wanted:
                    continue
                name=parts[1]
                if name in seen or not member.isfile():
                    raise ValueError('Duplicate or nonregular semantic archive member: '+name)
                seen.add(name)
                row=wanted[name]
                data=archive.extractfile(member).read()
                if git_hash('blob',data) != row['git_blob_sha1']:
                    raise ValueError('Changed pinned archive source: '+name)
                destination=cache/row['git_blob_sha1']
                if not destination.exists():
                    with tempfile.NamedTemporaryFile(dir=cache,prefix=row['git_blob_sha1']+'-',suffix='.part',delete=False) as handle:
                        handle.write(data)
                        temporary=Path(handle.name)
                    temporary.replace(destination)
                authenticated_bytes(row,cache)
        if set(wanted) != seen:
            raise ValueError('Missing semantic source in pinned archive: '+key)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(fetch,key,wanted) for key,wanted in sorted(groups.items())]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def packages(folder):
    result = {}
    for target in ('gf180mcuC', 'gf180mcuD', 'ihp-sg13g2'):
        root = Path(folder) / target
        manifest = json.loads((root / 'package.json').read_bytes())
        actual = inventory(root)
        by_blob = defaultdict(list)
        for name in manifest['files']:
            by_blob[git_hash('blob', (root / name).read_bytes())].append(name)
        active_ids = {d['id'] for values in actual['active_definitions'].values() for d in values if not d['scope']}
        active_index = defaultdict(list)
        for d in actual['definitions']:
            if d['id'] in active_ids:
                active_index[(d['source'], d['name'], d['kind'], d['line'])].append(d)
        catalog_names, catalog_sources = defaultdict(dict), defaultdict(dict)
        for device, entry in manifest['technology']['simulation']['catalog'].items():
            catalog_names[entry.get('model','').casefold()][device] = entry
            catalog_names[device.casefold()][device] = entry
            catalog_sources[entry['source']][device] = entry
        result[target] = dict(root=root, manifest=manifest, inventory=actual, by_blob=by_blob,
                              active_index=active_index, catalog_names=catalog_names, catalog_sources=catalog_sources)
    return result


def dispositions(row, interface, bundled):
    targets = ['ihp-sg13g2'] if row['family'] == 'ihp-sg13g2' else ['gf180mcuC', 'gf180mcuD']
    out = {}
    for target in targets:
        package = bundled[target]
        exact = package['by_blob'].get(row['git_blob_sha1'], [])
        name = interface['name'].casefold()
        matches = []
        candidates = dict(package['catalog_names'].get(name, {}))
        if interface['kind'] == 'symbol':
            for path in exact:
                candidates.update(package['catalog_sources'].get(path, {}))
        for device, entry in sorted(candidates.items()):
                checks = dict(prefix_compatible=interface.get('prefix') == entry.get('prefix'),
                              terminal_order_compatible=[p.casefold() for p in interface.get('pins', [])] == [p.casefold() for p in entry.get('pin_order', [])],
                              emitted_parameters_declared=set(entry.get('emit_parameters', {}).values()) <= {p for p in interface.get('parameters', []) + interface.get('local_parameters', []) if isinstance(p,str)})
                if interface['kind'] == 'symbol':
                    checks['prefix_compatible'] = None
                    checks['emitted_parameters_declared'] = None
                matches.append(dict(device=device, model=entry.get('model'), unavailable=entry.get('unavailable', ''), prefix=entry.get('prefix'), binding_checks=checks))
        active = [m for m in matches if not m['unavailable']]
        reachable = [d for path in exact for d in package['active_index'].get((path, name, interface['kind'], interface['line']), [])]
        compatible = [m for m in active if (interface['kind'] == 'symbol' and m['binding_checks']['terminal_order_compatible'])
                      or (interface['kind'] == 'subckt' and all(m['binding_checks'].values()))]
        supported = bool(exact and compatible and (interface['kind'] == 'symbol' or reachable)
                         and interface.get('element_count', 1) > 0 and not interface.get('parent') and not interface.get('conditions'))
        if supported:
            reason = 'Exact upstream bytes are bundled and the interface has an available catalog binding; behavioral qualification remains separate.'
        elif matches and not active:
            reason = 'Catalog explicitly declares this interface unavailable: ' + '; '.join(sorted({m['unavailable'] for m in matches}))
        elif interface.get('element_count') == 0:
            reason = 'Empty subcircuit declares an interface without electrical behavior.'
        elif interface['kind'].startswith('pcell') or interface['kind'] == 'dynamic-registration':
            reason = 'Upstream generator interface is inventoried; no complete application mapping/parameter-domain qualification is established by source presence.'
        elif interface['kind'] in ('extracted-device', 'physical-declaration'):
            reason = 'Extraction declaration is inventoried; source naming/layer roles alone do not establish the complete application terminal mapping.'
        else:
            reason = 'No complete implementation equivalence is established for this source interface; catalog name or file presence alone is insufficient.'
        out[target] = dict(disposition='supported' if supported else 'unimplemented', reason=reason,
                           qualification=False, identical_bundled_paths=exact, catalog_candidates=matches,
                           active_bundled_definitions=[d['id'] for d in reachable])
    return out


def library_name(path):
    parts = PurePosixPath(path).parts
    if 'libraries' in parts or 'macros' in parts:
        for key in ('libraries', 'macros'):
            if key in parts:
                return parts[parts.index(key)+1]
    if 'libs.ref' in parts:
        return parts[parts.index('libs.ref')+1]
    return None


def selected_profiles():
    from icstudio.digital_platform import ORFS_PROFILES, BUNDLED_PLATFORMS
    mapping = {'gf180':'gf180mcuC', 'gf180d':'gf180mcuD', 'ihp-sg13g2':'ihp-sg13g2'}
    return dict(source='icstudio/digital_platform.py', sha256=file_digest(ROOT/'icstudio/digital_platform.py'),
                profiles={name:dict(target=mapping[name], **ORFS_PROFILES[name]) for name in mapping if name in BUNDLED_PLATFORMS})


def reconcile_libraries(interfaces, profiles=None):
    profiles = selected_profiles() if profiles is None else profiles
    cells = defaultdict(lambda: defaultdict(list))
    by_id = {r['id']:r for r in interfaces}
    liberty_pins = defaultdict(list)
    for r in interfaces:
        parents = [c['name'] for c in r.get('context', []) if c['kind'] == 'cell']
        if r['kind'] in ('pin', 'pg_pin', 'bus') and parents:
            liberty_pins[(r['source'], parents[-1])].append(dict(name=r['name'], kind=r['kind'], attributes=r.get('attributes', {}), id=r['id']))
    for r in interfaces:
        library = r.get('library_scope')
        if not library:
            continue
        kind = r['kind']
        if kind in ('subckt', 'cell', 'lef-macro', 'verilog-module', 'gds-structure'):
            cells[(r['family'], library, r['name'])][kind].append(r['id'])
    rows = []
    case_candidates = defaultdict(list)
    for family, library, name in cells:
        case_candidates[(family,library,name.casefold())].append(name)
    for (family, library, name), views in sorted(cells.items()):
        declarations = {i:by_id[i] for values in views.values() for i in values}
        pins = {kind:sorted({tuple(r.get('pins', r.get('terminals', []))) for r in declarations.values() if r['kind'] == kind})
                for kind in ('subckt', 'lef-macro', 'verilog-module') if kind in views}
        # CDL preserves terminal order; LEF only defines the named pin set.
        mismatches = []
        if pins.get('subckt') and pins.get('lef-macro'):
            for a in pins['subckt']:
                for b in pins['lef-macro']:
                    if {p.casefold() for p in a} != {p.casefold() for p in b}:
                        mismatches.append(dict(cdl=list(a), lef=list(b)))
        selected_by = [key for key,profile in profiles['profiles'].items()
                       if (family == 'ihp-sg13g2') == (profile['target'] == 'ihp-sg13g2') and
                       any(PurePosixPath(p).name.startswith(library + '__') or PurePosixPath(p).name.startswith(library + '_')
                              for paths in profile['corners'].values() for p in paths)]
        selected = bool(selected_by)
        liberty_terminals = [dict(source=r['source'], pins=liberty_pins[(r['source'],r['name'])])
                            for r in declarations.values() if r['kind'] == 'cell']
        rows.append(dict(family=family, library=library, name=name, views=dict(views), terminal_declarations=pins,
                         liberty_terminal_declarations=liberty_terminals,
                         missing_views=[kind for kind in ('subckt', 'cell', 'lef-macro', 'verilog-module', 'gds-structure') if kind not in views],
                         case_distinct_candidates=sorted(n for n in case_candidates[(family,library,name.casefold())] if n != name),
                         cdl_lef_terminal_set_mismatches=mismatches, selected_digital_library=selected,
                         selected_by_profiles=selected_by,
                         disposition='unimplemented', reason='Selected library identity requires per-cell physical/electrical qualification.' if selected else 'This library is outside the currently selected digital profile; no general macro/library adapter is qualified.',
                         qualified=False))
    return rows


def dependency_edges(interfaces, files):
    known = {(r['family'], r['path']):r for r in files}
    sources = {r['family'] + ':' + r['path']:r for r in files}
    edges = []
    for item in interfaces:
        if item['kind'] not in ('model-include', 'extraction-include'):
            continue
        source = sources[item['source']]
        path = posixpath.normpath(posixpath.join(posixpath.dirname(source['path']),item['name']))
        resolved = known.get((item['family'],path))
        edges.append(dict(interface=item['id'], source=item['source'], declared=item['name'], resolved_path=path,
                          resolved_repository=resolved['repository'] if resolved else None,
                          disposition='supported' if resolved else 'unimplemented',
                          reason='Literal source reference exists in the authenticated graph; runtime selection is not asserted.' if resolved else 'Literal source reference is absent from this pinned graph; explicit companion provenance is separate.'))
    return edges


def process_options(interfaces, profiles):
    rows = []
    for item in interfaces:
        if item['kind'] == 'process-variant':
            dispositions_by_target = {}
            for name, profile in profiles['profiles'].items():
                target = profile['target']
                if not target.startswith('gf180'):
                    continue
                chosen = target[-1] == item['name']
                variables = profile['orfs']['variables']
                expected = dict(metal_top=variables['KVALUE']+'K', metal_level=variables['METAL_OPTION'].split('_')[0], mim_option='B')
                matches = chosen and item['options'] == expected
                dispositions_by_target[target] = dict(disposition='supported' if matches else 'inapplicable' if not chosen else 'unimplemented',
                    reason='The target selects this exact upstream metal-stack/MIM variant and current application profile agrees.' if matches else
                           'This source explicitly declares variant '+item['name']+'; the target is variant '+target[-1]+'.' if not chosen else 'Selected target/profile options differ from the upstream declaration.',
                    application_options=variables, qualified=False)
            rows.append(dict(kind='physical-process-variant', name=item['name'], source_interface=item['id'], values=item['options'], dispositions=dispositions_by_target))
        elif item['kind'] in ('library','operating_conditions') and item.get('pvt'):
            filename = PurePosixPath(item['source'].split(':',1)[1]).name
            selected_by = []
            for key,profile in profiles['profiles'].items():
                if (item['family'] == 'ihp-sg13g2') != (profile['target'] == 'ihp-sg13g2') or not item.get('library_scope'):
                    continue
                for corner,paths in profile['corners'].items():
                    if not any(PurePosixPath(p).name.removesuffix('.gz') == filename and PurePosixPath(p).name.startswith(item['library_scope']+'_') for p in paths):
                        continue
                    expected_voltage = profile['orfs']['corners'][corner]['PWR_NETS_VOLTAGES'].split()[-1]
                    actual_voltage = item['pvt'].get('voltage',item['pvt'].get('nom_voltage'))
                    temp = re.search(r'_([nm]?)(\d+)C(?:\.|_)',filename)
                    actual_temp = item['pvt'].get('temperature',item['pvt'].get('nom_temperature'))
                    compatible = actual_voltage is not None and float(actual_voltage) == float(expected_voltage)
                    compatible = compatible and temp is not None and actual_temp is not None and float(actual_temp) == int(temp[2])*(-1 if temp[1] else 1)
                    selected_by.append(dict(profile=key,corner=corner,target=profile['target'],declared_pvt_compatible=compatible))
            rows.append(dict(kind='library-pvt', name=item['name'], source_interface=item['id'], values=item['pvt'], selected_by_profiles=selected_by,
                             disposition='unimplemented',
                             reason='Source family/library/corner/PVT checked against configured profile; exact installed-library equivalence and behavior remain separate.' if selected_by else 'Upstream timing corner is not selected by an application profile; no qualification inferred.', qualified=False))
    return rows


def companion_sources(files):
    records = []
    by_repo_blob = defaultdict(list)
    for row in files:
        by_repo_blob[(row['repository'], row['git_blob_sha1'])].append(row['path'])
    paths = [*sorted((ROOT/'icstudio/assets/physical').glob('ihp_*/SOURCE.json')),
             ROOT/'icstudio/assets/physical/gf180_hv/SOURCE.json',
             ROOT/'icstudio/assets/physical/gf180_resistors/upstream-lock.json',
             ROOT/'examples/gf180-lvs-source-lock.json']
    for path in paths:
        obj = json.loads(path.read_bytes())
        commit = obj.get('commit', obj.get('revision'))
        if 'repository' in obj:
            repository = obj['repository'].removeprefix('https://github.com/')
        else:
            urls = [info['url'] for info in obj['files'].values() if isinstance(info,dict) and info.get('url')]
            matches = [re.match(r'https://raw.githubusercontent.com/([^/]+/[^/]+)/'+re.escape(commit)+'/',url) for url in urls]
            if not matches or not all(matches) or len({m[1] for m in matches}) != 1:
                raise ValueError('Ambiguous companion repository provenance.')
            repository = matches[0][1]
        entries = []
        for rel, info in sorted(obj['files'].items()):
            safe_path(rel)
            expected = info['sha256'] if isinstance(info,dict) else info
            local = path.parent/rel
            actual = None
            if local.is_file():
                data = local.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    raise ValueError('Changed companion asset: ' + local.relative_to(ROOT).as_posix())
                blob = git_hash('blob',data)
            else:
                blob = info.get('git_blob_sha1',info.get('git_blob')) if isinstance(info,dict) else None
            entries.append(dict(path=rel, sha256=expected, local_bytes_verified=actual is not None,
                                authenticated_graph_matches=by_repo_blob.get((repository+'@'+commit,blob), [])))
        records.append(dict(source=path.relative_to(ROOT).as_posix(), sha256=file_digest(path), repository=repository, commit=commit,
                            files=entries, flags=obj.get('flags'),
                            full_repository_in_graph=any(r['repository']==repository+'@'+commit for r in files),
                            reason='Explicit application companion source; this record does not silently replace the selected primitive source or assert full device qualification.'))
    return records


def run(original, gf, cache, package_root=ROOT/'icstudio/assets/pdks'):
    dependency_paths = [Path(__file__), ROOT/'scripts/inventory_upstream_views.py', ROOT/'scripts/inventory_device_models.py',
                        ROOT/'scripts/inventory_veriloga_models.py', ROOT/'scripts/reconcile_primitive_inventory.py',
                        ROOT/'scripts/inventory_sky130_release.py', ROOT/'icstudio/digital_platform.py']
    identity_before = {path.relative_to(ROOT).as_posix():file_digest(path) for path in dependency_paths}
    input_before = {'selected_graph':file_digest(original), 'gf_parent_graph':file_digest(gf)}
    files, closure = load_sources(original, gf)
    bundled = packages(package_root)
    interfaces, sources, errors, ledger = [], [], [], []
    for index, row in enumerate(files):
        role, reason = source_role(row)
        ledger.append(dict(**row, role=role, reason=reason))
        kind = source_kind(row)
        if not kind:
            continue
        raw = authenticated_bytes(row, cache)
        ident = row['family'] + ':' + row['path']
        source = dict(**row, id=ident, sha256=hashlib.sha256(raw).hexdigest(), parser=kind, interfaces=[])
        sources.append(source)
        try:
            if kind == 'gds':
                declarations, padding = gds_interfaces(raw)
                parsed = [dict(kind='gds-structure',name=r['name'],line=1) for r in declarations]
                source['encoding'] = 'GDSII-binary'
                source['zero_block_padding_bytes'] = padding
            else:
                try:
                    decoded = raw.decode('utf-8-sig')
                    source['encoding'] = 'utf-8-sig'
                except UnicodeDecodeError:
                    if kind not in ('spice','cdl') or any(any(ord(c)>127 for c in line) and not line.lstrip().startswith('*') for line in raw.decode('latin1').splitlines()):
                        raise
                    decoded = raw.decode('latin1')
                    source['encoding'] = 'latin1-comments/ascii-code'
                parsed = interpret(kind, decoded, row['path'])
        except (ValueError, SyntaxError, UnicodeDecodeError, ET.ParseError) as exc:
            # An explicit blocking gap preserves the complete source ledger.
            # Parser errors never become "inapplicable" or successful coverage.
            errors.append(dict(source=ident, parser=kind, error=str(exc), disposition='unimplemented', blocks_semantic_completion=True))
            continue
        for sequence, item in enumerate(parsed):
            item.pop('id', None)
            item.setdefault('line', 1)
            if item.get('conditions'):
                item['conditions'] = [[dict(directive=statement.split()[0],
                                           expression_sha256=hashlib.sha256(statement.encode()).hexdigest())
                                       for statement in branch] for branch in item['conditions']]
            item.update(id=ident + ':' + str(sequence), source=ident, family=row['family'], library_scope=library_name(row['path']))
            item['dispositions'] = dispositions(row, item, bundled)
            interfaces.append(item)
            source['interfaces'].append(item['id'])
    profiles = selected_profiles()
    library_rows = reconcile_libraries(interfaces, profiles)
    package_records = {target:dict(manifest_sha256=p['inventory']['manifest_sha256'], revision=p['inventory']['revision'],
                                   catalog_entries=len(p['inventory']['catalog'])) for target,p in bundled.items()}
    # Recheck package manifests and every parsed cache blob after interpretation.
    for target,p in bundled.items():
        if file_digest(p['root']/'package.json') != package_records[target]['manifest_sha256']:
            raise ValueError('Package changed during semantic inventory.')
        for rel, expected in p['manifest']['files'].items():
            if file_digest(p['root']/rel) != expected:
                raise ValueError('Bundled package changed during semantic inventory.')
    for source in sources:
        authenticated_bytes(source, cache)
    if identity_before != {path.relative_to(ROOT).as_posix():file_digest(path) for path in dependency_paths}:
        raise ValueError('Inventory implementation changed during execution.')
    if input_before != {'selected_graph':file_digest(original), 'gf_parent_graph':file_digest(gf)}:
        raise ValueError('Source metadata changed during execution.')
    diagnostics = [dict(interface=r['id'], **{k:v for k,v in r.items() if k not in ('id','dispositions')}) for r in interfaces if r.get('blocks_semantic_completion')]
    return dict(schema=1, chunk=7, chunk_complete=False, qualified=False,
                status='GAPS' if errors or diagnostics else 'PASS', semantic_qualification_complete=False,
                scope=__doc__, closure=closure, packages=package_records,
                runner_sha256=identity_before['scripts/inventory_upstream_semantics.py'], implementation_sha256=identity_before,
                input_files_sha256=input_before, files=ledger, sources=sources, interfaces=interfaces,
                libraries=library_rows, digital_profiles=profiles, process_options=process_options(interfaces, profiles),
                source_dependencies=dependency_edges(interfaces, files), companion_sources=companion_sources(files), parse_gaps=errors,
                blocking_source_diagnostics=diagnostics,
                unparsed_physical_formats=[dict(source=r['family']+':'+r['path'],format=PurePosixPath(r['path']).suffix,
                                                disposition='unimplemented',reason='OASIS fixture is retained in the source ledger; this runner does not interpret OASIS structures.')
                                           for r in files if r['path'].lower().endswith(('.oas','.oasis'))],
                notice_sources=[dict(source=r['id'],repository=r['repository'],path=r['repository_path'],git_blob_sha1=r['git_blob_sha1'],sha256=r['sha256']) for r in sources if r['parser']=='notice'],
                counts=dict(files=len(files), parsed_sources=len(sources), interfaces=len(interfaces),
                            by_kind=dict(Counter(r['kind'] for r in interfaces)), libraries=len(library_rows), parse_gaps=len(errors), blocking_source_diagnostics=len(diagnostics)),
                disposition_scope='Supported means an exact-byte available catalog interface, not full device qualification. Unimplemented includes unproven equivalence. No unknown is relabeled inapplicable.',
                limitations=['No operating envelope is inferred from PCell dimensions or Liberty PVT.',
                             'Conditional definitions and dynamic registrations are retained without execution.',
                             'Other-source-context and physical/reference files remain explicit; source interface parsing is not complete tool behavior interpretation.',
                             'SPICE terminal order and LEF pin sets are compared without assuming their aliases or bus syntax are interchangeable.',
                             'Liberty pin/pg_pin/bus contexts are attached to cells; bus expansion and timing arc semantics remain unqualified.',
                             'GF parent-linked primitive 9f992d5 and currently selected primitive 4d0b4ce remain separate source identities.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree-inputs', type=Path, default=ROOT/'docs/qualification/upstream-view-inputs-2026-10-20.json.gz')
    parser.add_argument('--gf-inputs', type=Path, default=ROOT/'docs/qualification/upstream-semantics-gf-inputs-2026-11-07.json.gz')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--fetch-missing', action='store_true',help='Stream exact-commit public archives into the original-source cache before the offline audit.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Choose a new report path.')
    if args.fetch_missing:
        files,_ = load_sources(args.tree_inputs,args.gf_inputs)
        fetch_missing_sources(files,args.cache)
    report = run(args.tree_inputs, args.gf_inputs, args.cache)
    args.output.write_bytes(compressed(report))
    print(json.dumps(dict(status=report['status'], **report['counts']), sort_keys=True))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
