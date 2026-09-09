"""One-time conversion from Xschem capture to independent native documents."""
import hashlib
import json
import re
import tempfile
from pathlib import Path
from .model import clone, digest, now, validate, atomic_write, save_project, device
from .native_spice import asset_path, render, netlist

INCLUDE = re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)')
TOKEN = re.compile(r'@@?[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*')


def compile_device(device):
    """Compile the supported declarative subset once; never evaluate Tcl."""
    from .xschem_project import properties
    info = device['xschem']; attrs = info['symbol'].get('attributes', {})
    props = {**properties(attrs.get('template', '')), **info['properties']}
    if info.get('missing'): raise ValueError('The symbol is missing.')
    for attribute in ('extra', 'spice_stop'):
        if props.get(attribute, attrs.get(attribute)) not in (None, '', 'false', '0'):
            raise ValueError('Symbol behavior ' + attribute + ' needs a native implementation.')
    if props.get('spice_ignore', attrs.get('spice_ignore')) == 'short':
        raise ValueError('Shorted symbols need an explicit native connection before migration.')
    if info['kind'] == 'netlist_commands':
        return {'version': 1, 'type': 'program', 'text': props.get('value', ''),
                'only_toplevel': props.get('only_toplevel', 'false') in ('true', '1')}
    fmt = props.get('format', attrs.get('format', ''))
    compact = re.sub(r'\s+', '', fmt.replace('\\', ''))
    if attrs.get('type') == 'vsource' and compact == 'tcleval([expr{@savecurrent?"@name@pinlist@value.saveI(?1@name)":"@name@pinlist@value"}])':
        fmt = '@name @pinlist @value'
        if props.get('savecurrent') in ('true', '1'): fmt += '\n.save i(@name)'
    if not fmt.strip(): raise ValueError('No electrical emission format is defined.')
    if 'tcleval' in fmt or '\\@' in fmt:
        raise ValueError('This executable or escaped symbol format needs a native implementation.')
    tokens = []; offset = 0; used = {}
    for match in TOKEN.finditer(fmt):
        if match.start() > offset: tokens.append({'kind': 'literal', 'value': fmt[offset:match.start()]})
        token = match[0]; key = token.lstrip('@%')
        if token.startswith('@@'):
            if key not in device['nets']: raise ValueError('Unknown terminal ' + key)
            entry = {'kind': 'terminal', 'value': key}
        elif key == 'name': entry = {'kind': 'instance'}
        elif key == 'pinlist': entry = {'kind': 'terminals'}
        elif key == 'symname': entry = {'kind': 'cell'}
        elif key in props:
            value = str(props[key])
            if 'tcleval' in value or '\n' in value or '\r' in value:
                raise ValueError('Parameter ' + key + ' needs translation to a native expression.')
            used[key] = value; entry = {'kind': 'parameter', 'value': key}
        elif token.startswith('%'): entry = {'kind': 'literal', 'value': key}
        elif key in ('extra', 'spiceprefix'): entry = {'kind': 'literal', 'value': ''}
        else: raise ValueError('Missing symbol parameter ' + key)
        tokens.append(entry); offset = match.end()
    if offset < len(fmt): tokens.append({'kind': 'literal', 'value': fmt[offset:]})
    return {'version': 1, 'type': 'device', 'label': Path(info['reference']).stem,
            'model_name': Path(info['reference']).stem, 'tokens': tokens,
            'parameters': used, 'definition': attrs.get('spice_sym_def', '')}


def review(project):
    """Return a reviewable candidate without changing the source document."""
    from .xschem_project import properties
    from .xschem_runtime import format_device
    from .electrical_identity import partition, identify_symbol
    from .wiring import rebuild
    p = clone(project); rows = []; blocked = False
    def item(subject, status, detail, cell='', obj=''):
        rows.append({'subject': subject, 'status': status, 'detail': detail, 'cell': cell, 'object': obj})
    exchange = p.get('xschem_exchange', {})
    if not exchange:
        return {'candidate': None, 'status': 'Needs attention', 'items': [{'subject': 'Project', 'status': 'Needs attention', 'detail': 'Open or import an Xschem schematic first.'}]}
    if exchange.get('mode') != 'compatible':
        # Existing simple imports already have native primitives and analysis.
        if p['pdk'].get('package_root') or p['pdk'].get('simulation', {}).get('includes'):
            return {'candidate': None, 'status': 'Needs attention', 'items': [{'subject': 'External technology', 'status': 'Needs attention', 'detail': 'This older native import uses an external technology package. Use Import and migrate Xschem project on the original schematic to collect its model dependencies.'}]}
        archive = clone(exchange); archive['capture_cells'] = clone(p['cells'])
        for c in p['cells']:
            for record in c.get('xschem', {}).get('records', []):
                if record[0] not in ('v', 'G', 'K', 'V', 'S', 'E', 'F', 'N', 'T', 'C'):
                    item(c['name'], 'Needs attention', 'Source graphic ' + record[0] + ' is retained in the recovery archive.', c['id'])
            c['electrical'] = {'version': 1, 'nets': []}; rebuild(c, p)
            c.pop('xschem', None)
            for d in c['devices']:
                d.pop('xschem', None); d.pop('xschem_properties', None)
                if d.get('symbol'): d['symbol']['attributes'] = {}
        p.pop('xschem_exchange', None)
        item('Circuit', 'Migrated', 'Existing native primitives, hierarchy and analysis retained.')
        status = 'Complete' if all(row['status']=='Migrated' for row in rows) else 'Needs attention'
        p['native_migration'] = {'version': 1, 'created': now(), 'status': status, 'items': rows, 'archive': archive}
        validate(p)
        return {'candidate': p, 'status': status, 'items': rows}
    for error in exchange.get('unresolved', []):
        item('Dependency', 'Needs attention', error); blocked = True
    files = exchange['source_files']; mapping = {}
    for path, asset in files.items():
        if hashlib.sha256(asset['text'].encode()).hexdigest() != asset['sha256']:
            item(Path(path).name, 'Needs attention', 'Source checksum changed; review the source files again.'); blocked = True
        if asset['kind'].startswith('Model'):
            mapping[path] = hashlib.sha256((path + '\0' + asset['sha256']).encode()).hexdigest()[:24]
    def rewrite(text, parent):
        def replace(match):
            if match[1].lower() == '.lib' and not match[3].strip(): return match[0]
            reference = match[2].strip('"\'')
            target = next((d['path'] for d in exchange['resolved_dependencies'] if d['parent'] == parent and d['reference'] == reference and d['path'] in mapping), None)
            if target is None: raise ValueError('Unresolved model reference: ' + reference)
            return match[1] + ' ' + asset_path(mapping[target]) + match[3]
        return INCLUDE.sub(replace, text)
    p['spice'] = {'version': 1, 'assets': {}, 'library_lock': clone(exchange.get('library_lock', {}))}
    for path, ident in mapping.items():
        try:
            text = rewrite(files[path]['text'], path)
            p['spice']['assets'][ident] = {'name': Path(path).name, 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
        except ValueError as exc: item(Path(path).name, 'Needs attention', str(exc)); blocked = True
    item('Model library', 'Migrated', f'{len(p["spice"]["assets"])} model files embedded with checksums and portable relative paths.')
    by = {c['id']: c for c in p['cells']}
    for c in p['cells']:
        rebuild(c, p); before = partition(c); meta = c.get('xschem', {})
        # An archived object does not count as migrated functionality.
        for info in meta.get('components', []):
            if info.get('label_id') and info.get('properties', {}).get('global') in ('true', '1'):
                item(info['reference'], 'Needs attention', 'Global label scope needs explicit native conversion.', c['id']); blocked = True
            if not info.get('device_id') and not info.get('label_id'):
                kind = info['kind']
                item(info['reference'], 'Needs attention', f'{kind or "Unsupported object"} remains in the recovery archive; its behavior has no native equivalent yet.', c['id'])
        for record in meta.get('records', []):
            if record[0] not in ('v', 'G', 'K', 'V', 'S', 'E', 'F', 'N', 'T', 'C'):
                item(c['name'], 'Needs attention', 'Schematic record ' + record[0] + ' is retained in the recovery archive.', c['id'])
            if record[0] == 'T' and len(record[1]) > 2000:
                item(c['name'], 'Fixed representation', 'Long annotation is shortened in the native view; its full source remains archived.', c['id'])
            if record[0] == 'N' and properties(record[-1]).get('bus'):
                item(c['name'], 'Needs attention', 'Vector wire semantics require scalar bus conversion.', c['id']); blocked = True
        c['spice_statements'] = []
        for r in meta.get('records', []):
            if r[0] == 'S' and r[1].strip():
                try: c['spice_statements'].append(rewrite(r[1], meta['path']))
                except ValueError as exc: item(c['name'], 'Needs attention', str(exc), c['id']); blocked = True
        if c.get('symbol'):
            identify_symbol(c['symbol'])
            attrs = c['symbol'].get('attributes', {})
            defaults = properties(attrs.get('template', ''))
            c['spice_parameters'] = {k: v for k, v in defaults.items() if k not in ('name', 'spiceprefix')}
            c['symbol']['attributes'] = {}
        for d in c['devices']:
            info = d.get('xschem')
            if not info: continue
            try:
                definition = compile_device(d)
                if definition['type'] == 'program':
                    definition['text'] = rewrite(definition['text'], meta['path'])
                else:
                    d['native_spice'] = definition
                    if render(d, by.get(d.get('cell'))) != format_device(d, by.get(d.get('cell'))):
                        raise ValueError('Native emission differs from the imported device definition.')
                    if definition['definition']:
                        definition['definition'] = rewrite(definition['definition'], info['symbol_path'])
                d['native_spice'] = definition
                if d['kind'] != 'X': d['kind'] = 'SPICE'
                identify_symbol(d['symbol'])
                d['symbol_context'] = {**info['properties'], 'symname': Path(info['reference']).stem}
                d['symbol']['attributes'] = {}
                d.pop('xschem')
                item(d['name'], 'Migrated', 'Editable native simulation program.' if definition['type'] == 'program' else 'Native electrical definition, ordered pins and editable parameters.', c['id'], d['id'])
            except (ValueError, KeyError) as exc:
                item(d['name'], 'Needs attention', str(exc), c['id'], d['id']); blocked = True
        c.pop('xschem', None); c['electrical'] = {'version': 1, 'nets': []}; rebuild(c, p)
        if partition(c) != before:
            item(c['name'], 'Needs attention', 'Migration changed terminal connectivity.', c['id']); blocked = True
    # Keep source documents for recovery; native execution never consults them.
    p.pop('xschem_exchange', None)
    p['analysis'].update(type='program', engine='ngspice')
    top = by[p['top']]
    texts = top.get('spice_statements', []) + [d['native_spice']['text'] for d in top['devices'] if d.get('native_spice', {}).get('type') == 'program']
    if not blocked and not any(re.search(r'(?im)^\s*\.control\b', text) for text in texts):
        analyses = []
        def extract(text):
            def take(match):
                analyses.append(match[1] + match[2]); return ''
            return re.sub(r'(?im)^\s*\.(op|tran|dc|ac|noise)([^\n]*)$', take, text)
        top['spice_statements'] = [extract(text) for text in top.get('spice_statements', [])]
        for d in top['devices']:
            if d.get('native_spice', {}).get('type') == 'program': d['native_spice']['text'] = extract(d['native_spice']['text'])
        name = 'Analysis1'; index = 1; names = {d['name'].casefold() for d in top['devices']}
        while name.casefold() in names: index += 1; name = 'Analysis' + str(index)
        symbol = {'pins': {}, 'pin_order': [], 'pin_meta': {}, 'attributes': {}, 'primitives': [{'kind':'rect','points':[[0,0],[180,45]]},{'kind':'text','points':[[8,8],[170,35]],'text':'@name: simulation program','font_size':9}]}
        program = device('SPICE', name, max([d['x'] for d in top['devices']]+[0])+200, 0, nets={}, symbol=symbol,
                         native_spice={'version':1,'type':'program','text':'.control\n'+'\n'.join(analyses or ['op'])+'\n.endc','only_toplevel':True}, symbol_context={'name':name})
        top['devices'].append(program)
        item(name, 'Migrated', 'Deck analyses converted to a native program.' if analyses else 'No analysis was specified; an editable operating-point setup was created.', top['id'], program['id'])
    for setup in p.get('simulation_setups', []):
        if setup['settings'].get('type') == 'xschem': setup['settings']['type'] = 'program'
    status = 'Complete' if all(r['status'] == 'Migrated' for r in rows) and not blocked else 'Needs attention'
    report = {'version': 1, 'created': now(), 'status': status, 'items': rows,
              'source_digest': digest(project), 'archive': clone(exchange),
              'scope': 'SPICE schematic, native device definitions and ngspice program',
              'validation': {'connectivity': 'passed' if not blocked else 'needs_attention',
                             'independent_reference': 'not_run', 'simulation': 'not_run'}}
    p['native_migration'] = report
    if not blocked:
        try:
            validate(p)
            # Fail during review rather than after the user accepts migration.
            with tempfile.TemporaryDirectory() as tmp:
                text = netlist(p, tmp)
                from .spice_program import prepare_program
                prepare_program(text, tmp, p['analysis'])
        except (ValueError, KeyError, OSError) as exc:
            item('Native simulation', 'Needs attention', str(exc)); blocked = True; status = report['status'] = 'Needs attention'
    return {'candidate': None if blocked else p, 'status': status, 'items': rows}


def review_path(path, libraries=()):
    from .native_exchange import MANIFEST
    if (Path(path).resolve().parent/MANIFEST).is_file():
        from .native_exchange import review_project
        record=review_project(path,libraries);candidate=record['candidate']
        items=[{'subject':'Xschem exchange','status':'Needs attention','detail':text} for text in record['errors']+record['warnings']]
        if candidate:items.append({'subject':'Native project','status':'Migrated','detail':'Reconciled native identities, electrical edits and linked physical views.'})
        return {'candidate':candidate,'status':'Needs attention' if record['errors'] or record['warnings'] else 'Complete','items':items}
    from .xschem_libraries import prepare
    from .xschem_compat import CaptureReader
    roots, locations, lock = prepare(path, libraries, None)
    reader = CaptureReader(path, roots, None, locations)
    try:
        p = reader.capture(); p['xschem_exchange']['library_lock'] = lock
        result = review(p)
        for warning in reader.warnings:
            result['items'].append({'subject': 'Source interpretation', 'status': 'Needs attention', 'detail': warning})
        if reader.warnings:
            result['status'] = 'Needs attention'
            if result['candidate']: result['candidate']['native_migration']['status'] = 'Needs attention'
        return result
    except (ValueError, OSError, KeyError) as exc:
        return {'candidate': None, 'status': 'Needs attention', 'items': [{'subject': str(path), 'status': 'Needs attention', 'detail': str(exc)}]}


def export_report(project, path):
    report = clone(project['native_migration']); report.pop('archive', None)
    atomic_write(path, json.dumps(report, indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Migrate an Xschem project into an independent native project.')
    parser.add_argument('schematic'); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--library', action='append', default=[])
    args = parser.parse_args(); result = review_path(args.schematic, args.library)
    report_path = args.output.with_suffix('.migration.json')
    if args.output.exists(): parser.error('Choose a new output filename; migration never overwrites an existing project.')
    if result['candidate']:
        save_project(result['candidate'], args.output); export_report(result['candidate'], report_path)
    else: atomic_write(report_path, json.dumps({k:v for k,v in result.items() if k != 'candidate'}, indent=2))
    print(json.dumps({'status': result['status'], 'project': str(args.output) if result['candidate'] else None, 'report': str(report_path)}))
    return 0 if result['status'] == 'Complete' else 2


if __name__ == '__main__': raise SystemExit(main())
