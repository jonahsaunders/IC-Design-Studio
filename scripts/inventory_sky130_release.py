"""Inventory the complete pinned SKY130 release and explicit cell/option dispositions.

Streams all seven archives; executes no upstream content. Declaration and pin
comparisons are evidence for review, not simulation, layout, LVS, operating-range
or installed-release qualification. Historical two-archive reports stay intact.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital_platform import BUNDLED_PLATFORMS, ORFS_PROFILES
from icstudio.model import file_digest
from scripts.inventory_upstream_views import compressed, package_index, safe_path
from scripts.inventory_device_models import logical_lines, parse as parse_spice

RELEASE = 'sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392'
RELEASE_ID = 76339333
REPOSITORY = 'chipfoundry/volare'
# Three historical repository pins plus four retrieved-byte pins. The GitHub
# release API supplies no independent digest/signature for these 2023 assets.
ASSETS = {
    'common.tar.zst': (123929774, 16569606, 'c7c155596a1fd1fcf6d5414dfcffcbbcf4e35b2b33160af97f4340e763c97406'),
    'sky130_fd_io.tar.zst': (123929776, 50685688, 'feaa2d40837ff272e6f3b9512b11b8c61c4356ccb939e2fd75443a50af66cb47'),
    'sky130_fd_pr.tar.zst': (123929779, 14015443, '41dc9098541ed3329eba4ec7f5dfd1422eb09e94b623ea1f6dc3895f9ccebf63'),
    'sky130_fd_sc_hd.tar.zst': (123929788, 166744319, 'd4081b3c0fbfa2afe31dba789c03157ad137ea08b11910e2c8b3ec81b2a61bf6'),
    'sky130_fd_sc_hvl.tar.zst': (123929780, 54171210, '2df7826900912a7986017604c16c0ab1caa1996a3c5e267bc0c6be695c0dcc11'),
    'sky130_ml_xx_hd.tar.zst': (123929786, 9225, '3b27c44c9de9f3e4ba8477b5f42c2bb9bc5bb21aa387b564091b744b2b0b07c7'),
    'sky130_sram_macros.tar.zst': (123929775, 30345017, '465c05a0626de37f0e87f7b0ed0fc36bbf69746327641fcf240902d940f29298'),
}
SEMANTIC_SUFFIXES = {'.lib', '.lef', '.tlef', '.spice', '.cdl', '.v', '.gds', '.mag'}
MAX_MEMBER = 512 * 1024 * 1024
COMMENT = re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*', re.S)
BRACE = re.compile(r'"(?:\\.|[^"\\])*"|[{}]')
QUOTED = r'"(?:\\.|[^"\\])*"'


def verified_metadata(data):
    if (data.get('repository'), data.get('tag'), data.get('release_id')) != (REPOSITORY, RELEASE, RELEASE_ID):
        raise ValueError('Wrong SKY130 release identity.')
    rows = data['archives']
    if len(rows) != len(ASSETS) or {r['name'] for r in rows} != set(ASSETS):
        raise ValueError('Missing, duplicate or extra SKY130 release asset.')
    for row in rows:
        if (row['id'], row['bytes'], row['sha256']) != ASSETS[row['name']]:
            raise ValueError('Changed release asset identity: ' + row['name'])
        if row['url'] != f'https://github.com/{REPOSITORY}/releases/download/{RELEASE}/{row["name"]}':
            raise ValueError('Changed release asset URL.')
        if row['api_url'] != f'https://api.github.com/repos/{REPOSITORY}/releases/assets/{row["id"]}':
            raise ValueError('Changed release asset API identity.')
        if row.get('upstream_digest') is not None:
            raise ValueError('Unexpected independent upstream digest claim.')
    return {k: v for k, v in data.items() if k != 'archives'} | {
        'archives': [{k: v for k, v in r.items() if k != 'local_path'} for r in sorted(rows, key=lambda r: r['name'])]}


def uncomment(text):
    return COMMENT.sub(lambda m: m[0] if m[0].startswith('"') else '\n' * m[0].count('\n') + ' ', text)


def mask_strings(text):
    masked = re.sub(QUOTED, lambda m: ' ' * len(m[0]), text)
    if '"' in masked:
        raise ValueError('Unterminated quoted string in semantic source.')
    return masked


def source_text_identity(text):
    """Retain the identity of a source fragment without redistributing its text."""
    data = text.encode('utf-8')
    return dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))


def condition_metadata(conditions):
    return [[dict(operator=branch.split(None, 1)[0].lower(), **source_text_identity(branch))
             for branch in level] for level in conditions]


def node_metadata(data):
    """Keep process/revision facts; replace descriptive source prose with a hash."""
    node = dict(data)
    if 'description' in node:
        node['description_identity'] = source_text_identity(node.pop('description'))
    return node


def groups(text, name):
    """Read named Liberty groups, with balanced braces and quoted-string handling."""
    pattern = re.compile(QUOTED + r'|\b' + re.escape(name) + r'\s*\(\s*("(?:\\.|[^"\\])*"|[^()]*)\s*\)\s*\{')
    position = 0
    while match := pattern.search(text, position):
        if match[1] is None:
            position = match.end()
            continue
        depth = 1
        for token in BRACE.finditer(text, match.end()):
            if token[0] == '{':
                depth += 1
            elif token[0] == '}':
                depth -= 1
            if depth == 0:
                yield match[1].strip().strip('"'), text[match.end():token.start()]
                position = token.end()
                break
        else:
            raise ValueError('Unclosed Liberty group: ' + name)


def attributes(text, names):
    # Attributes belong to this group, not its nested timing/power tables.
    # Removing nested bodies once also avoids repeatedly scanning large tables.
    segments, start, depth = [], 0, 0
    for token in BRACE.finditer(text):
        if token[0] == '{':
            if depth == 0:
                segments.append(text[start:token.start()])
            depth += 1
        elif token[0] == '}':
            depth -= 1
            if depth == 0:
                start = token.end()
    segments.append(text[start:])
    text = ' '.join(segments)
    result = {}
    for name in names:
        found = next((m for m in re.finditer(QUOTED + r'|\b' + name + r'\s*:\s*("(?:\\.|[^"\\])*"|[^;]+);', text)
                      if m[1] is not None), None)
        if found:
            result[name] = found[1].strip().strip('"')
    return result


def liberty(text):
    text = uncomment(text)
    mask_strings(text)
    libraries = list(groups(text, 'library'))
    if not libraries:
        raise ValueError('No Liberty library declaration.')
    declarations, conditions = [], []
    for name, body in libraries:
        cells = list(groups(body, 'cell'))
        for condition, settings in groups(body, 'operating_conditions'):
            conditions.append(dict(library=name, name=condition,
                                   **attributes(settings, ('process', 'voltage', 'temperature'))))
        for cell, content in cells:
            pins = []
            for group in ('pin', 'pg_pin', 'bus'):
                for pin, detail in groups(content, group):
                    fields = attributes(detail, ('direction', 'pg_type', 'function', 'bus_type'))
                    if 'function' in fields:
                        fields['function_identity'] = source_text_identity(fields.pop('function'))
                    pins.append(dict(name=pin, kind=group,
                                     **fields))
            declarations.append(dict(kind='liberty_cell', name=cell, library=name, pins=pins))
    return dict(declarations=declarations, operating_conditions=conditions)


def spice(text, extension):
    parsed = parse_spice(text, '(archive member)')
    statements = dict(logical_lines(text))
    declarations = []
    for definition in parsed['definitions']:
        statement = statements[definition['line']]
        name = statement.split()[1]
        declaration = dict(name=name, line=definition['line'], prefix=definition['prefix'],
                           parent=definition['parent'], section=definition['section'],
                           conditions=condition_metadata(definition['conditions']))
        if definition['kind'] == 'model':
            declaration.update(kind='spice_model', model_type=definition['model_type'],
                               parameters=sorted(set(re.findall(r'\b([A-Za-z_]\w*)\s*=', statement))))
        else:
            declaration.update(kind='cdl_subcircuit' if extension == '.cdl' else 'spice_subcircuit',
                               terminals=definition['pins'], parameters=sorted(set(definition['parameters'])))
        declarations.append(declaration)
    return dict(declarations=declarations, sections=parsed['sections'],
                includes=parsed['includes'], diagnostics=parsed['diagnostics'])


def lef(text):
    text = re.sub(QUOTED + r'|#[^\n]*', lambda m: m[0] if m[0].startswith('"') else ' ' * len(m[0]), text)
    searchable = mask_strings(text)
    declarations = []
    for match in re.finditer(r'\bMACRO\s+(\S+)', searchable):
        name = match[1]
        end = re.search(r'\bEND\s+' + re.escape(name) + r'(?=\s|;|$)', searchable[match.end():])
        if not end:
            raise ValueError('Unclosed LEF macro: ' + name)
        body = searchable[match.end():match.end() + end.start()]
        pins = []
        for pin in re.finditer(r'\bPIN\s+(\S+)', body):
            pin_end = re.search(r'\bEND\s+' + re.escape(pin[1]) + r'(?=\s|;|$)', body[pin.end():])
            if not pin_end:
                raise ValueError('Unclosed LEF pin: ' + pin[1])
            detail = body[pin.end():pin.end() + pin_end.start()]
            fields = {k.lower(): v.lower() for k, v in re.findall(r'\b(DIRECTION|USE)\s+(\S+)\s*;', detail)}
            pins.append(dict(name=pin[1], **fields))
        declarations.append(dict(kind='lef_macro', name=name, pins=pins))
    return dict(declarations=declarations,
                layers=re.findall(r'(?m)^LAYER\s+(\S+)\s*$', text),
                sites=re.findall(r'(?m)^SITE\s+(\S+)\s*$', text))


def verilog(text):
    text = uncomment(text)
    searchable = mask_strings(text)
    declarations = []
    for match in re.finditer(r'\b(module|primitive)\s+(?:(automatic|static)\s+)?([A-Za-z_][\w$]*|\\\S+)', searchable):
        end = re.search(r'\bend' + match[1] + r'\b', searchable[match.end():])
        if not end:
            raise ValueError('Unclosed Verilog declaration: ' + match[3])
        body = text[match.end():match.end() + end.start()]
        # The audit needs declaration identity and conditional-presence facts,
        # not copied source headers. Keep the hash of the unelaborated header.
        header = body.split(';', 1)[0].strip()
        declarations.append(dict(kind='verilog_' + match[1], name=match[3].removeprefix('\\'),
                                 literal_identifier=match[3], lifetime=match[2],
                                 interface_identity=source_text_identity(header),
                                 conditional_macros=sorted(set(re.findall(r'`(?:ifdef|ifndef)\s+([A-Za-z_]\w*)', header))),
                                 elaborated=False))
    return dict(declarations=declarations)


def gds(data):
    position = 0
    declarations = []
    library = False
    structure = False
    named = False
    library_named = False
    ended = False
    if not data:
        raise ValueError('Empty GDS library.')
    while position < len(data):
        if position + 4 > len(data):
            raise ValueError('Truncated GDS record.')
        length, kind, dtype = struct.unpack_from('>HBB', data, position)
        if length < 4 or length % 2 or position + length > len(data):
            raise ValueError('Invalid GDS record length.')
        if position == 0 and kind != 0 or ended:
            raise ValueError('Invalid GDS library framing.')
        if kind == 1:
            if library or position == 0:
                raise ValueError('Duplicate GDS library.')
            library = True
        elif kind == 2:
            if not library or library_named or structure:
                raise ValueError('Invalid GDS library name.')
            library_named = True
        elif kind == 5:
            if not library_named or structure:
                raise ValueError('Invalid GDS structure framing.')
            structure, named = True, False
        if kind == 6:  # STRNAME is an explicit structure declaration.
            if dtype != 6 or not structure or named:
                raise ValueError('Invalid GDS structure-name type.')
            name = data[position+4:position+length].rstrip(b'\0').decode('ascii')
            if not name:
                raise ValueError('Empty GDS structure name.')
            declarations.append(dict(kind='gds_structure', name=name))
            named = True
        elif kind == 7:
            if not structure or not named:
                raise ValueError('Unmatched GDS structure ending.')
            structure = False
        elif kind == 4:
            if not library_named or structure:
                raise ValueError('Unmatched GDS library ending.')
            ended = True
        position += length
    if not ended:
        raise ValueError('Unterminated GDS library.')
    return dict(declarations=declarations)


def semantic(path, data):
    ext = PurePosixPath(path).suffix
    if ext == '.gds':
        return gds(data)
    text = data.decode('utf-8')
    if ext == '.lib':
        return liberty(text)
    if ext in ('.spice', '.cdl'):
        return spice(text, ext)
    if ext in ('.lef', '.tlef'):
        return lef(text)
    if ext == '.v':
        return verilog(text)
    if ext == '.mag':
        if not text.startswith('magic\n'):
            raise ValueError('Invalid Magic layout header.')
        return dict(declarations=[], layout_file_identifier=PurePosixPath(path).stem,
                    identifier_basis='Magic filename, not an electrical declaration',
                    technology=re.findall(r'(?m)^tech\s+(\S+)', text),
                    referenced_cells=sorted(set(re.findall(r'(?m)^use\s+(\S+)', text))),
                    ports=re.findall(r'(?m)^[rf]label\s+.*\s+(\S+)\nport\s+([^\n]+)', text))
    raise ValueError('Unexpected semantic input.')


def archive_rows(path, expected_hash, expected_bytes):
    import zstandard
    path = Path(path)
    if path.stat().st_size != expected_bytes or file_digest(path) != expected_hash:
        raise ValueError('Changed SKY130 archive: ' + path.name)
    rows, seen = [], set()
    with path.open('rb') as raw, zstandard.ZstdDecompressor().stream_reader(raw) as decoded:
        with tarfile.open(fileobj=decoded, mode='r|') as archive:
            for member in archive:
                name = safe_path(member.name)
                if name in seen or not member.isfile():
                    raise ValueError('Duplicate or nonregular archive member: ' + name)
                seen.add(name)
                parts = PurePosixPath(name).parts
                if parts[0] not in ('sky130A', 'sky130B') or len(parts) < 2:
                    raise ValueError('Unexpected SKY130 process path.')
                if member.size > MAX_MEMBER:
                    raise ValueError('Archive member exceeds audit limit.')
                parse = PurePosixPath(name).suffix in SEMANTIC_SUFFIXES
                node = parts[-2:] == ('.config', 'nodeinfo.json')
                sha, total, blocks = hashlib.sha256(), 0, []
                with archive.extractfile(member) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        total += len(block)
                        sha.update(block)
                        if parse or node:
                            blocks.append(block)
                if total != member.size:
                    raise ValueError('Truncated archive member.')
                row = dict(path=name, process=parts[0], archive=path.name,
                           bytes=total, sha256=sha.hexdigest(), mode=member.mode,
                           library=parts[2] if len(parts) > 3 and parts[1] == 'libs.ref' else '(technology/support)')
                if parse:
                    try:
                        row['semantic'] = semantic(name, b''.join(blocks))
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise ValueError('Semantic scan failed for ' + name + ': ' + str(exc)) from exc
                elif node:
                    row['nodeinfo'] = node_metadata(json.loads(b''.join(blocks)))
                rows.append(row)
    if not rows or file_digest(path) != expected_hash or path.stat().st_size != expected_bytes:
        raise ValueError('Empty or changed SKY130 archive after scan.')
    return rows


def index_rows(rows):
    files, index = {}, defaultdict(list)
    for row in rows:
        if row['path'] in files:
            raise ValueError('Duplicate effective release path: ' + row['path'])
        files[row['path']] = row
        for declaration in row.get('semantic', {}).get('declarations', []):
            index[(row['process'], row['library'], declaration['name'])].append((row, declaration))
    return files, index


def selected_cells(files, index, profile):
    selected = []
    for corner, paths in sorted(profile['corners'].items()):
        for path in paths:
            source = 'sky130A/libs.ref/sky130_fd_sc_hd/' + safe_path(path)
            if source not in files:
                raise ValueError('Selected application corner is absent from release: ' + source)
            cells = files[source].get('semantic', {}).get('declarations', [])
            if not cells:
                raise ValueError('Selected corner has no declared cells.')
            for cell in cells:
                views = index[('sky130A', 'sky130_fd_sc_hd', cell['name'])]
                comparisons = []
                timing_pins = {p['name'] for p in cell['pins'] if p['kind'] == 'pin' and p.get('direction') != 'internal'}
                internal_pins = [p['name'] for p in cell['pins'] if p['kind'] == 'pin' and p.get('direction') == 'internal']
                power_pins = {p['name'] for p in cell['pins'] if p['kind'] == 'pg_pin'}
                buses = [p['name'] for p in cell['pins'] if p['kind'] == 'bus']
                for kind in ('lef_macro', 'spice_subcircuit', 'cdl_subcircuit', 'gds_structure', 'verilog_module'):
                    matches = [(r, d) for r, d in views if d['kind'] == kind and not d.get('parent')]
                    if not matches:
                        comparisons.append(dict(kind=kind, status='missing_same_identifier'))
                    for row, declared in matches:
                        check = dict(kind=kind, path=row['path'], status='identifier_present')
                        if kind in ('spice_subcircuit', 'cdl_subcircuit', 'lef_macro'):
                            fold = (lambda s: s) if kind == 'lef_macro' else str.casefold
                            pins = ({p['name'] for p in declared['pins']} if kind == 'lef_macro' else
                                    {fold(p) for p in declared['terminals']})
                            timing, power = {fold(p) for p in timing_pins}, {fold(p) for p in power_pins}
                            check.update(missing_timing_pins=sorted(timing-pins),
                                         additional_pins=sorted(pins-timing-power),
                                         absent_power_pins=sorted(power-pins),
                                         pin_case_comparison='exact' if kind == 'lef_macro' else 'case_insensitive')
                            check['status'] = 'pin_sets_agree' if pins == timing | power else 'pin_set_difference_review_required'
                        if kind == 'lef_macro':
                            directions = {p['name']: p.get('direction') for p in declared['pins']}
                            check['direction_mismatches'] = [p['name'] for p in cell['pins']
                                if p['kind'] == 'pin' and p.get('direction') != 'internal' and p.get('direction') != directions.get(p['name'])]
                            if check['direction_mismatches']:
                                check['status'] = 'pin_direction_difference_review_required'
                        if buses and kind in ('lef_macro', 'spice_subcircuit', 'cdl_subcircuit'):
                            check['status'] = 'bus_interface_requires_expansion_review'
                            check['unresolved_buses'] = buses
                        comparisons.append(check)
                selected.append(dict(corner=corner, source=source, name=cell['name'], comparisons=comparisons,
                                     declared_internal_pins=internal_pins,
                                     qualified=False))
    return selected


def catalog_reconciliation(catalog, index):
    # SPICE model/subcircuit identifiers are case-insensitive. No suffix removal,
    # size inference or model substitution is allowed.
    by_name = defaultdict(list)
    for (process, library, name), declarations in index.items():
        if process != 'sky130A':
            continue
        for row, declaration in declarations:
            if declaration['kind'] in ('spice_subcircuit', 'spice_model'):
                by_name[(name.lower(), declaration['prefix'])].append((row, declaration))
    result = []
    for key, entry in sorted(catalog.items()):
        model = entry.get('model', '')
        control = entry.get('kind') == 'PDK' and not entry.get('pin_order') and not entry.get('prefix')
        all_matches = by_name.get((model.lower(), entry.get('prefix')), [])
        matches = [(r, d) for r, d in all_matches if d['parent'] is None]
        declarations = [dict(path=r['path'], kind=d['kind'], name=d['name'],
                             **{k: d[k] for k in ('terminals', 'parameters', 'model_type', 'parent', 'section', 'conditions', 'prefix', 'line') if k in d}) for r, d in matches]
        terminal_sets = sorted({tuple(d.get('terminals', [])) for _, d in matches if d['kind'] == 'spice_subcircuit'})
        result.append(dict(catalog_key=key, model=model, prefix=entry.get('prefix'), application_pin_order=entry.get('pin_order', []),
                           application_parameters=sorted(entry.get('emit_parameters', {})),
                           unavailable=entry.get('unavailable', ''),
                           disposition=('non_electrical_pdk_control_metadata' if control else
                                        'catalog_unavailable_still_blocks' if entry.get('unavailable') else
                                        'catalog_bound_source_declared_not_qualified' if matches else
                                        'catalog_bound_no_exact_release_declaration_review_required'),
                           declarations=declarations, source_terminal_orders=[list(p) for p in terminal_sets],
                           matching_terminal_order_present=tuple(p.casefold() for p in entry.get('pin_order', [])) in
                               {tuple(p.casefold() for p in terminals) for terminals in terminal_sets},
                           activation='Global lexical declarations with compatible instance prefix; include/section/condition activation not proven here.',
                           qualified=False))
    return result


def reconcile(rows, catalog, profile):
    files, index = index_rows(rows)
    selected = selected_cells(files, index, profile)
    selected_names = {row['name'] for row in selected}
    corner_coverage = [dict(name=name, corners={corner: ('declared' if any(
        r['name'] == name and r['corner'] == corner for r in selected) else 'missing_from_selected_corner')
        for corner in sorted(profile['corners'])}) for name in sorted(selected_names)]
    bound_models = {row.get('model', '').lower() for row in catalog.values()}
    identifiers = []
    for (process, library, name), declarations in sorted(index.items()):
        if process != 'sky130A':
            disposition = 'outside_selected_process_sky130B'
        elif library == 'sky130_fd_sc_hd':
            disposition = ('selected_hd_timing_cell_not_qualified' if name in selected_names else
                           'hd_auxiliary_or_other_corner_identifier_not_qualified')
        elif name.lower() in bound_models:
            disposition = 'analog_catalog_model_identifier_not_qualified'
        elif library == 'sky130_fd_pr':
            disposition = 'primitive_or_internal_model_without_exact_catalog_binding'
        elif library in ('sky130_fd_io', 'sky130_fd_sc_hvl', 'sky130_sram_macros'):
            disposition = 'library_without_selected_application_platform'
        else:
            disposition = 'technology_support_or_other_identifier_requires_context'
        identifiers.append(dict(process=process, library=library, name=name, disposition=disposition,
                                declarations=[dict(path=r['path'], kind=d['kind']) for r, d in declarations],
                                qualified=False))
    nodes = []
    for process in ('sky130A', 'sky130B'):
        path = process + '/.config/nodeinfo.json'
        if path not in files or 'nodeinfo' not in files[path]:
            raise ValueError('Missing process-option declarations: ' + path)
        node = files[path]['nodeinfo']
        if node['node'] != process or node['commit']['open_pdks'] != RELEASE.removeprefix('sky130-'):
            raise ValueError('Wrong process metadata identity.')
        options = []
        for category in ('stdcells', 'iocells', 'primitive', 'memory', 'other'):
            for name, version in sorted(node.get(category, {}).items()):
                present = any(r['process'] == process and r['library'] == name for r in rows)
                options.append(dict(category=category, name=name, upstream_value=version,
                                    release_library_present=present,
                                    disposition=('upstream_unknown_but_library_present_review_required' if version == 'unknown' and present else
                                                 'upstream_unknown_not_in_release' if version == 'unknown' else
                                                 'selected_hd_profile_not_qualified' if name == 'sky130_fd_sc_hd' and process == 'sky130A' else
                                                 'primitive_catalog_reconciled_separately' if name == 'sky130_fd_pr' and process == 'sky130A' else
                                                 'outside_selected_process' if process == 'sky130B' else
                                                 'available_source_no_selected_digital_profile' if present else
                                                 'technology_integration_metadata_not_library_archive')))
        nodes.append(dict(process=process, path=path, declared_options=node['options'],
                          description_identity=node.get('description_identity', source_text_identity(node.get('description', ''))), options=options,
                          qualified=False, operating_envelope_qualified=False))
    return dict(identifiers=identifiers, selected_hd_cells=selected,
                selected_cell_corner_coverage=corner_coverage,
                analog_catalog=catalog_reconciliation(catalog, index), process_options=nodes)


def main():
    evidence_sources = {'runner_sha256': Path(__file__),
                        'inventory_helper_sha256': ROOT / 'scripts/inventory_upstream_views.py',
                        'model_parser_sha256': ROOT / 'scripts/inventory_device_models.py',
                        'digital_platform_sha256': ROOT / 'icstudio/digital_platform.py'}
    source_hashes = {name: file_digest(path) for name, path in evidence_sources.items()}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--cache', type=Path, action='append', required=True,
                        help='One or more retained archive directories. No extraction or download occurs.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.suffixes[-2:] != ['.json', '.gz']:
        raise ValueError('Choose a new .json.gz output path.')
    inputs = verified_metadata(json.loads(args.inputs.read_bytes()))
    rows = []
    for name, (_, size, digest) in sorted(ASSETS.items()):
        print('Scanning ' + name, file=sys.stderr, flush=True)
        candidates = [folder / name for folder in args.cache if (folder / name).is_file()]
        if len(candidates) != 1:
            raise ValueError('Missing or ambiguous cached release asset: ' + name)
        rows.extend(archive_rows(candidates[0], digest, size))
    package_root = ROOT / 'icstudio/assets/pdks/sky130A'
    package_identity, _ = package_index(package_root)
    package = json.loads((package_root / 'package.json').read_bytes())
    profile = ORFS_PROFILES['sky130hd']
    semantics = reconcile(rows, package['technology']['simulation']['catalog'], profile)
    if package_index(package_root)[0] != package_identity:
        raise ValueError('Package changed during release reconciliation.')
    report = dict(schema=1, chunk=7, status='PASS', inventory_complete_for_pinned_release=True,
                  qualified=False, chunk_complete=False, sources=inputs,
                  source_authentication='Release/asset metadata and retrieved SHA-256 pins; no signature or independent upstream digest.',
                  application=dict(package=package_identity, bundled_platforms=list(BUNDLED_PLATFORMS),
                                   selected_sky130_profile=profile,
                                   digital_platform_sha256=source_hashes['digital_platform_sha256']),
                  scope=__doc__, files=sorted(rows, key=lambda r: r['path']),
                  file_counts=dict(Counter(r['process'] for r in rows)),
                  archive_file_counts=dict(Counter(r['archive'] for r in rows)),
                  declaration_counts=dict(Counter(d['kind'] for r in rows for d in r.get('semantic', {}).get('declarations', []))),
                  source_notice_files=[{k: r[k] for k in ('archive', 'path', 'sha256', 'bytes')}
                      for r in sorted(rows, key=lambda r: r['path']) if re.fullmatch(
                          r'(?:license|notice|copying|copyright)(?:[._-].*)?', PurePosixPath(r['path']).name, re.I)],
                  retained_content='Generated declaration/option facts and content identities. Source prose, Verilog headers, '
                                   'Boolean-function expressions and conditional-source expressions are represented by hashes. '
                                   'This report does not grant reuse rights to underlying archives. The notice-file list identifies '
                                   'named files in the release, not a complete license determination for all source content.',
                  semantic_reconciliation=semantics,
                  limitations=['Declared identifiers/pin sets are not extracted connectivity or a working implementation.',
                               'Liberty operating conditions are characterization points, not complete device ratings.',
                               'Verilog header identities and conditional macro names are retained without source text or preprocessing/elaboration.',
                               'Primitive model-bin, helper, layout and catalog identities are not silently aliased.',
                               'Unavailable or unselected libraries are explicit dispositions, not acceptance waivers.',
                               'Tool scripts and generators are inventoried but not executed or semantically qualified.',
                               'Full terminal/parameter/model, operating-envelope, layout, extracted-connectivity and installed-release gates remain.'],
                  **{name: value for name, value in source_hashes.items() if name != 'digital_platform_sha256'})
    if any(file_digest(path) != source_hashes[name] for name, path in evidence_sources.items()):
        raise ValueError('Audit implementation changed during inventory; rerun the frozen source.')
    args.output.write_bytes(compressed(report))
    print(json.dumps(dict(status=report['status'], file_counts=report['file_counts'],
                          declaration_counts=report['declaration_counts'],
                          identifiers=len(semantics['identifiers']), selected_hd_cells=len(semantics['selected_hd_cells']),
                          report_sha256=file_digest(args.output), bytes=args.output.stat().st_size), indent=2))


if __name__ == '__main__':
    main()
