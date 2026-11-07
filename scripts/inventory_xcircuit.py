"""Bounded nonexecuting XCircuit library declaration inventory.

Only reviewed literal library forms are enumerated. Unsupported structure is an
explicit error, including under optimized Python. Pin-label source order is not
electrical terminal order; templates are identified but never evaluated.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
import re

def require(condition, message):
    if not condition:
        raise ValueError("XCircuit declarations: " + message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

@dataclass
class Token:
    kind: str
    value: object
    start: int
    end: int
    line: int

def lex(text):
    require(len(text) < 1000000, 'invalid XCircuit len(text) < 1000000')
    i = 0
    line = 1
    tokens = 0

    def sequence(close=None, depth=0):
        nonlocal i, line, tokens
        require(depth < 32, 'excessive nesting')
        out = []
        while i < len(text):
            if text[i].isspace():
                line += text[i] == '\n'
                i += 1
                continue
            if text[i] == '%':
                end = text.find('\n', i)
                i = len(text) if end < 0 else end
                continue
            if close and text.startswith(close, i):
                i += len(close)
                return out
            start = i
            firstline = line
            c = text[i]
            if c == '(':
                i += 1
                level = 1
                value = []
                while i < len(text) and level:
                    c = text[i]
                    i += 1
                    if c == '\\':
                        require(i < len(text), 'trailing string escape')
                        c = text[i]
                        i += 1
                        if c in '01234567':
                            digits = c
                            while len(digits) < 3 and i < len(text) and (text[i] in '01234567'):
                                digits += text[i]
                                i += 1
                            value.append(chr(int(digits, 8)))
                            continue
                        if c in '\r\n':
                            if c == '\r' and i < len(text) and (text[i] == '\n'):
                                i += 1
                            line += 1
                            continue
                        value.append({'n': '\n', 'r': '\r', 't': '\t', 'b': '\x08', 'f': '\x0c'}.get(c, c))
                        continue
                    if c == '(':
                        level += 1
                    elif c == ')':
                        level -= 1
                    if level:
                        value.append(c)
                    line += c == '\n'
                require(level == 0, 'unterminated PS string')
                kind = 'string'
                value = ''.join(value)
            elif text.startswith('<<', i):
                i += 2
                kind = 'dictionary'
                value = sequence('>>', depth + 1)
            elif c in '{[':
                i += 1
                kind = 'procedure' if c == '{' else 'array'
                value = sequence('}' if c == '{' else ']', depth + 1)
            else:
                require(c not in ')}]<>', 'unexpected PS delimiter')
                i += 1
                while i < len(text) and (not text[i].isspace()) and (text[i] not in '(){}[]<>%/'):
                    i += 1
                value = text[start:i]
                kind = 'literal-name' if c == '/' else 'number' if re.fullmatch('[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?', value) else 'word'
                if c == '/':
                    value = value[1:]
                    require(value, 'empty literal name')
            out.append(Token(kind, value, start, i, firstline))
            tokens += 1
            require(tokens < 200000, 'too many tokens')
        require(close is None, 'unterminated PS container')
        return out
    return sequence()

def parameter_facts(dictionary, text):
    rows = []
    values = dictionary.value
    keys = [i for i, t in enumerate(values) if t.kind == 'literal-name']
    require(not values or (keys and keys[0] == 0), 'unnamed parameter prefix')
    for index, pos in enumerate(keys):
        end = keys[index + 1] if index + 1 < len(keys) else len(values)
        parts = values[pos + 1:end]
        require(parts, 'missing parameter value')
        require(parts[0].kind in ('number', 'string'), 'unsupported parameter default')
        require(len(parts) == 1 or (len(parts) == 3 and parts[1].kind == 'string' and (parts[2].kind == 'word') and (parts[2].value == 'pop')), 'unsupported parameter expression')
        row = dict(name=values[pos].value, line=values[pos].line, expression_sha256=sha(text[parts[0].start:parts[-1].end].encode()))
        if parts[0].kind in ('number', 'string'):
            row['literal_default'] = parts[0].value if re.fullmatch('[A-Za-z0-9_.:+/?-]{0,128}', parts[0].value) else None
        if len(parts) == 3 and parts[1].kind == 'string' and (parts[2].kind == 'word') and (parts[2].value == 'pop'):
            match = re.fullmatch('lindex\\s+\\{([^{}]*)\\}\\s+(\\d+)', parts[1].value)
            if match and all((re.fullmatch('[A-Za-z0-9_.:+/?-]+', s) for s in match[1].split())):
                row['literal_option_candidates'] = match[1].split()
                row['literal_default_index'] = int(match[2])
                row['options_evaluated'] = False
            else:
                row['dynamic_value_identity'] = sha(parts[1].value.encode())
        rows.append(row)
    require(len({r['name'] for r in rows}) == len(rows), 'duplicate parameter names')
    return rows

def label_parts(body, index):
    require(index >= 6, 'short label operands')
    count = body[index - 6]
    if count.kind == 'number':
        require(re.fullmatch('\\d+', count.value), "invalid XCircuit re.fullmatch('\\\\d+', count.value)")
        n = int(count.value)
        require(1 <= n <= 100, 'invalid XCircuit 1 <= n <= 100')
        start = index - 6 - n
        require(start >= 0, 'invalid XCircuit start >= 0')
        parts = body[start:index - 6]
    else:
        require(count.kind == 'word' and count.value == 'ctmk', 'unsupported label part count')
        start = index - 7
        while start >= 0 and (not (body[start].kind == 'word' and body[start].value == 'mark')):
            start -= 1
        require(start >= 0, 'no label mark')
        parts = body[start + 1:index - 6]
    require(bool(parts), 'empty label parts')
    return (list(reversed(parts)), body[index - 5:index])

def styled_label(token):
    """Only the literal style procedures seen in pinned label operands."""
    require(token.kind == 'procedure', "invalid XCircuit token.kind == 'procedure'")
    parts = token.value
    return len(parts) == 2 and parts[0].kind == 'literal-name' and (parts[1].kind == 'word') and (parts[1].value == 'cf') or (len(parts) == 1 and parts[0].kind == 'word' and (parts[0].value in {'hS', 'CR', 'ss', 'Tf', 'Ts', 'qS', 'ol'})) or (len(parts) == 4 and all((p.kind == 'number' for p in parts[:3])) and (parts[3].kind == 'word') and (parts[3].value == 'scb'))

def library(text):
    require(text.startswith('%! PostScript set of library objects for XCircuit'), "invalid XCircuit text.startswith('%! PostScript set of library objects for XCircuit')")
    names = re.findall('(?m)^%\\s*Library name is:\\s*(\\S+)\\s*$', text)
    require(len(names) == 1, 'invalid XCircuit len(names) == 1')
    require(re.search('(?m)^%\\s*XCircuitLib\\b', text), "invalid XCircuit re.search('(?m)^%\\\\s*XCircuitLib\\\\b', text)")
    ends = list(re.finditer('(?m)^%\\s*EndLib\\s*$', text))
    require(len(ends) == 1 and (not text[ends[0].end():].strip()), 'invalid XCircuit len(ends) == 1 and (not text[ends[0].end():].strip())')
    tokens = lex(text[:ends[0].start()])
    require(bool(tokens), 'empty library has no declared objects')
    objects = []
    instances = []
    cursor = 0
    body_ops = Counter()
    while cursor < len(tokens):
        token = tokens[cursor]
        if token.kind == 'literal-name' and cursor + 2 < len(tokens) and (tokens[cursor + 1].kind == 'procedure') and (tokens[cursor + 2].kind == 'word') and (tokens[cursor + 2].value == 'def'):
            body = tokens[cursor + 1].value
            name = token.value
            require(re.fullmatch('[A-Za-z_][A-Za-z0-9_:.-]*', name), "invalid XCircuit re.fullmatch('[A-Za-z_][A-Za-z0-9_:.-]*', name)")
            require(sum((t.kind == 'word' and t.value == 'begingate' for t in body)) == 1, "invalid XCircuit sum((t.kind == 'word' and t.value == 'begingate' for t in body)) == 1")
            require(sum((t.kind == 'word' and t.value == 'endgate' for t in body)) == 1 and body[-1].kind == 'word' and (body[-1].value == 'endgate'), "invalid XCircuit sum((t.kind == 'word' and t.value == 'endgate' for t in body)) == 1 and body[-1].kind == 'word' and (body[-1].value == 'endgate')")
            gate = next((i for i, t in enumerate(body) if t.kind == 'word' and t.value == 'begingate'))
            require(gate in (0, 1) and (gate == 0 or body[0].kind == 'dictionary'), 'nonliteral object preamble')
            params = parameter_facts(body[0], text) if gate else []
            ports = []
            templates = []
            references = []
            known_words = {'begingate', 'beginpath', 'ctmk', 'curveto', 'ellipse', 'endgate', 'endpath', 'infolabel', 'label', 'mark', 'pinlabel', 'polyc', 'polygon', 'scb', 'sce', 'spline', 'xcarc'}
            parameter_names = {p['name'] for p in params}
            label_containers = set()
            for index, part in enumerate(body):
                if part.kind == 'word' and part.value in ('pinlabel', 'infolabel', 'label'):
                    label, position = label_parts(body, index)
                    require(all((p.kind == 'number' or (p.kind == 'word' and p.value in parameter_names) for p in position)), 'unsupported label position')
                    for operand in label:
                        require(operand.kind in ('string', 'word', 'procedure'), 'unsupported label operand')
                        if operand.kind == 'word':
                            require(operand.value in parameter_names, 'undeclared label parameter')
                        if operand.kind == 'procedure':
                            require(styled_label(operand), 'unsupported nested label procedure')
                            label_containers.add(operand.start)
            for index, part in enumerate(body):
                if part.kind in ('procedure', 'dictionary', 'array'):
                    require(index == 0 and gate == 1 and (part.kind == 'dictionary') or part.start in label_containers, 'unexpected nested body container')
            for i, t in enumerate(body):
                if t.kind != 'word':
                    continue
                body_ops[t.value] += 1
                require(t.value not in ('def', 'exec', 'run', 'if', 'ifelse', 'for', 'forall', 'repeat', 'loop', 'stopped', 'cvx'), 'dynamic PS construct')
                require(t.value in known_words or t.value in parameter_names or re.fullmatch('[A-Za-z_][A-Za-z0-9_.-]*::[A-Za-z_][A-Za-z0-9_.-]*', t.value), 'unknown body operator or undeclared parameter')
                if t.value == 'pinlabel':
                    parts, position = label_parts(body, i)
                    require(all((p.kind == 'string' or (p.kind == 'procedure' and len(p.value) == 2 and (p.value[0].kind == 'literal-name') and (p.value[1].kind == 'word') and (p.value[1].value == 'cf')) for p in parts)), 'dynamic or styled pin label')
                    label = ''.join((p.value for p in parts if p.kind == 'string'))
                    require(label, 'invalid XCircuit label')
                    ports.append(dict(name=label, declaration_index=len(ports), line=t.line, position_tokens=[v.value for v in position[-2:]], electrical_port_order_inferred=False))
                elif t.value == 'infolabel':
                    parts, _ = label_parts(body, i)
                    strings = [p.value for p in parts if p.kind == 'string']
                    prefix = next((re.match('([A-Za-z][A-Za-z0-9_]*)(?:@\\d+)?:', s) for s in strings if re.match('([A-Za-z][A-Za-z0-9_]*)(?:@\\d+)?:', s)), None)
                    refs = [v for s in strings for v in re.findall('%p([^\\s%]+)', s)]
                    templates.append(dict(format=prefix[1] if prefix else None, line=t.line, literal_pin_references=refs, parameter_references=[p.value for p in parts if p.kind == 'word' and p.value.startswith('@')], literal_model_tokens=[v for s in strings for v in re.findall('\\bsky130_[A-Za-z0-9_]+__[A-Za-z0-9_]*', s)], external_file_reference_tokens=[v for s in strings for v in re.findall('%F([^\\s]+)', s)], model_binding_inferred=False, expression_sha256=sha(text[parts[-1].start:body[i].end].encode()), evaluated=False))
                elif '::' in t.value:
                    references.append(t.value)
            objects.append(dict(name=name, line=token.line, parameters=params, ports=ports, netlist_templates=templates, referenced_objects=sorted(set(references)), raw_body_sha256=sha(text[tokens[cursor + 1].start:tokens[cursor + 1].end].encode())))
            cursor += 3
        else:
            start = cursor
            while cursor < len(tokens) and (not (tokens[cursor].kind == 'word' and tokens[cursor].value == 'libinst')):
                cursor += 1
            require(cursor < len(tokens), 'unknown top-level PS records')
            parts = tokens[start:cursor]
            require(len(parts) in (3, 4) and all((p.kind == 'number' for p in parts[:2])) and (parts[-1].kind == 'literal-name'), "invalid XCircuit len(parts) in (3, 4) and all((p.kind == 'number' for p in parts[:2])) and (parts[-1].kind == 'literal-name')")
            require(len(parts) == 3 or parts[2].kind == 'dictionary', "invalid XCircuit len(parts) == 3 or parts[2].kind == 'dictionary'")
            instances.append(dict(name=parts[-1].value, line=parts[-1].line, scale=parts[0].value, rotation=parts[1].value, parameters=parameter_facts(parts[2], text) if len(parts) == 4 else []))
            cursor += 1
    require(len({o['name'] for o in objects}) == len(objects), 'duplicate object declaration')
    require(all((i['name'] in {o['name'] for o in objects} for i in instances)), 'unresolved palette instance')
    dependencies = []
    for owner, parents in re.findall('(?m)^%\\s*Depend\\s+(\\S+)\\s+([^\\n]+)$', text[:tokens[0].start]):
        dependencies.append(dict(name=owner, referenced_objects=parents.split()))
    return dict(name=names[0], objects=objects, palette_instances=instances, dependency_declarations=dependencies, top_level_coverage='All noncomment tokens consumed as object definitions or libinst records.', body_word_counts=dict(body_ops))


def xcircuit_views(text):
    """Flatten every named declaration into source-bound inventory facts.

    The caller supplies the authenticated source identity and conservative
    disposition. Diagnostics are retained as facts, never repaired or treated
    as proof of a usable template/model binding.
    """
    parsed = library(text)
    rows = [dict(kind='xcircuit-library', name=parsed['name'],
                 object_count=len(parsed['objects']),
                 top_level_coverage=parsed['top_level_coverage'])]

    def parameters(values, owner, context):
        for value in values:
            rows.append(dict(kind='xcircuit-parameter', owner=owner,
                             declaration_context=context, **value))
            for index, option in enumerate(value.get('literal_option_candidates', [])):
                rows.append(dict(kind='xcircuit-parameter-option', name=option,
                                 owner=owner, parameter=value['name'],
                                 declaration_context=context, option_index=index,
                                 expression_sha256=value['expression_sha256'],
                                 line=value['line'], selection_evaluated=False))

    for symbol in parsed['objects']:
        owner = symbol['name']
        rows.append(dict(kind='xcircuit-symbol', name=owner, line=symbol['line'],
                         library=parsed['name'], raw_body_sha256=symbol['raw_body_sha256'],
                         electrical_port_order_inferred=False))
        parameters(symbol['parameters'], owner, 'symbol')
        for pin in symbol['ports']:
            rows.append(dict(kind='xcircuit-pin-label', owner=owner, **pin))
        for name in symbol['referenced_objects']:
            rows.append(dict(kind='xcircuit-object-reference', name=name, owner=owner,
                             line=symbol['line'], binding_inferred=False))
        declared_pins = {pin['name'] for pin in symbol['ports']}
        for index, template in enumerate(symbol['netlist_templates']):
            rows.append(dict(kind='xcircuit-netlist-template', name=owner,
                             template_index=index, **template))
            for token in template['literal_model_tokens']:
                rows.append(dict(kind='xcircuit-model-token-reference', name=token,
                                 owner=owner, template_index=index, line=template['line'],
                                 expression_sha256=template['expression_sha256'],
                                 token_may_be_partial=True, model_binding_inferred=False))
            missing = sorted(set(template['literal_pin_references']) - declared_pins)
            if missing:
                rows.append(dict(kind='xcircuit-template-pin-diagnostic', name=owner,
                                 diagnostic='literal-template-reference-without-declared-pin-label',
                                 template_index=index, format=template['format'],
                                 line=template['line'], identifiers=missing,
                                 expression_sha256=template['expression_sha256'],
                                 correction_inferred=False))
    for index, instance in enumerate(parsed['palette_instances']):
        rows.append(dict(kind='xcircuit-palette-instance', name=instance['name'],
                         declaration_index=index, line=instance['line'],
                         scale=instance['scale'], rotation=instance['rotation'],
                         binding_inferred=False))
        parameters(instance['parameters'], instance['name'], 'palette:' + str(index))
    for dependency in parsed['dependency_declarations']:
        rows.append(dict(kind='xcircuit-dependency-declaration', **dependency,
                         binding_inferred=False))
    return rows
