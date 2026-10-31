"""Generate a complete GF180 reference from an authenticated final OpenDB.

Bulk pins absent from LEF are resolved only from the database's stored global
connection rules. Other missing terminals, unknown cells and unintended opens
fail. A successfully generated reference is not a native LVS acceptance result.
"""
from collections import Counter
import json
from pathlib import Path
import re
import shutil

from .gf180_cdl import normalize
from .gf180_connectivity import PREFIX
from .model import atomic_write, file_digest

UNCONNECTED = re.compile(r'_unconnected_\d+')
BULK = {'VNW': 'VDD', 'VPW': 'VSS'}
RECIPE = 'gf180-9t-opendb-reference-v1'


def lines(text):
    result = []
    for line in text.splitlines():
        if line.lstrip().startswith('+'):
            if not result or not result[-1].strip() or result[-1].lstrip().startswith('*'):
                raise ValueError('Orphan reference continuation.')
            result[-1] += ' ' + line.lstrip()[1:].strip()
        else:
            result.append(line)
    return result


def cell_definition(text, name):
    """Inspect the supported flat M/D CDL library while retaining its bytes."""
    pins, devices, counts, active, ended = None, set(), Counter(), False, False
    for line in lines(text):
        fields = line.split()
        if not fields or fields[0].startswith('*'):
            continue
        word = fields[0].lower()
        if word == '.subckt':
            if active or ended or len(fields) < 3 or fields[1] != name:
                raise ValueError('Require exactly the selected library subcircuit.')
            pins = fields[2:]
            if len(set(p.lower() for p in pins)) != len(pins):
                raise ValueError('Duplicate library terminal.')
            active = True
        elif word == '.ends':
            if not active or len(fields) > 2 or len(fields) == 2 and fields[1] != name:
                raise ValueError('Mismatched library subcircuit end.')
            active, ended = False, True
        else:
            if not active or word[0] not in ('m', 'd') or len(word) < 2:
                raise ValueError('Require flat MOS/diode standard-cell CDL; unsupported statement: ' + fields[0])
            if word in devices:
                raise ValueError('Duplicate library device.')
            devices.add(word); counts[word[0]] += 1
            if word[0] == 'm' and (len(fields) < 8 or not {'W', 'L'} <= {f.split('=')[0].upper() for f in fields[6:]}):
                raise ValueError('A MOS reference must retain four terminals, model, width and length.')
    if active or not ended:
        raise ValueError('Unterminated library subcircuit.')
    # The existing exact adapter validates diode nodes, model, A/P and M.
    normalize(text)
    return dict(pins=pins, devices=dict(counts))


def bulk_bindings(rules):
    """Resolve the recorded literal global rules; never execute supplied Tcl."""
    if not isinstance(rules, list) or not rules:
        raise ValueError('The checkpoint has no recorded global connection rules.')
    by_pin = {}
    for row in rules:
        pin = re.fullmatch(r'\^([A-Za-z_][A-Za-z0-9_]*)\$', row['pin_pattern'])
        if row['inst_pattern'] != '.*' or row['region'] is not None or not pin:
            raise ValueError('Scoped or nonliteral global rules require separate reference support.')
        if pin[1] in by_pin:
            raise ValueError('Ambiguous duplicate global connection rule.')
        by_pin[pin[1]] = row['net']
    if any(by_pin.get(pin) != net for pin, net in BULK.items()):
        raise ValueError('Require explicit stored VNW-to-VDD and VPW-to-VSS connections.')
    return dict(BULK)


def assemble(raw, observed, database, library, *, top):
    """Cross-check every exported instance, port and terminal before conversion.

    library maps each used master to its independently hash-checked CDL text.
    observed comes from digital_lvs_engine on the captured checkpoint.
    """
    if (observed.get('schema') != 1 or observed.get('top') != top or
            observed.get('database') != database or database.get('version') != 1):
        raise ValueError('Fresh OpenDB readback differs from the captured placement.')
    captured = database.get('instances', [])
    if not captured or len({i['name'] for i in captured}) != len(captured):
        raise ValueError('Require nonempty, unique captured instances.')
    by_name = {i['name']: i for i in captured}
    masters = {i['master'] for i in captured}
    if set(library) != masters or any(not n.startswith(PREFIX) for n in masters):
        raise ValueError('Independent 9-track CDL coverage must match every used master.')
    definitions = {name: cell_definition(library[name], name) for name in sorted(masters)}
    bulk = bulk_bindings(observed['global_connections'])
    ports = observed['ports']
    if (not ports or len({p['name'] for p in ports}) != len(ports) or
            len({p['net'] for p in ports}) != len(ports) or
            any(not p['name'] or not p['net'] for p in ports) or
            any(p['name'] in ('VDD', 'VSS') and p['name'] != p['net'] for p in ports) or
            not {'VDD', 'VSS'} <= {p['name'] for p in ports}):
        raise ValueError('Require distinct captured top ports and nets, with matching supplies.')
    canonical = {p['net']: p['name'] for p in ports}
    defined_nets = {p['net'] for i in captured for p in i['pins'] if p['net']} | {p['net'] for p in ports}
    if len({canonical.get(n, n) for n in defined_nets}) != len(defined_nets):
        raise ValueError('Captured top ports alias another internal net.')
    if any(UNCONNECTED.fullmatch(n) for n in defined_nets):
        raise ValueError('A circuit net collides with OpenROAD generated open-terminal names.')
    corrected, instances, changes, unused, placeholders = [], [], [], [], set()
    active = ended = False
    for line in lines(raw):
        fields = line.split()
        if not fields or fields[0].startswith('*'):
            corrected.append(line); continue
        word = fields[0].lower()
        if word == '.subckt':
            if active or ended or len(fields) < 3 or fields[1] != top or Counter(fields[2:]) != Counter(p['name'] for p in ports):
                raise ValueError('Exported top port coverage differs from OpenDB.')
            active = True
        elif word == '.ends':
            if not active or len(fields) > 2 or len(fields) == 2 and fields[1] != top:
                raise ValueError('Mismatched reference subcircuit end.')
            active, ended = False, True
        elif word.startswith('x') and active and len(fields) >= 3:
            name, master, nodes = fields[0][1:], fields[-1], fields[1:-1]
            item = by_name.get(name)
            if item is None or item['master'] != master:
                raise ValueError('Exported instance differs from the captured database: ' + name)
            pins = definitions[master]['pins']
            captured_pins = {p['name']: p for p in item['pins']}
            if (len(captured_pins) != len(item['pins']) or len(nodes) != len(pins) or
                    set(pins) - set(captured_pins) - bulk.keys() or set(captured_pins) - set(pins)):
                raise ValueError('Incomplete reference terminal coverage: ' + name)
            for index, pin in enumerate(pins):
                node = nodes[index]
                actual = captured_pins.get(pin)
                if UNCONNECTED.fullmatch(node):
                    if node in placeholders:
                        raise ValueError('Generated open terminals share a net.')
                    placeholders.add(node)
                if actual is None:
                    if pin not in bulk or not UNCONNECTED.fullmatch(node):
                        raise ValueError('An absent LEF terminal has no explicit bulk binding.')
                    changes.append(dict(instance=name, pin=pin, before=node, after=bulk[pin]))
                    nodes[index] = bulk[pin]
                elif node != canonical.get(actual['net'], actual['net']):
                    if actual['net'] or actual['direction'] != 'OUTPUT' or not UNCONNECTED.fullmatch(node):
                        raise ValueError('Exported terminal differs from OpenDB: ' + name + '/' + pin)
                    unused.append(dict(instance=name, pin=pin, node=node, direction=actual['direction']))
                elif not node:
                    raise ValueError('Empty reference terminal.')
            instances.append(dict(instance=name, cell=master, pins=dict(zip(pins, nodes))))
            line = ' '.join([fields[0], *nodes, master])
        else:
            raise ValueError('Unsupported top-level reference statement: ' + fields[0])
        corrected.append(line)
    if active or not ended or Counter(i['instance'] for i in instances) != Counter(by_name.keys()):
        raise ValueError('Exported reference omits or duplicates captured instances.')
    reference = '\n'.join(corrected) + '\n\n' + '\n'.join(library[n] for n in sorted(library))
    reference, diodes = normalize(reference)
    counts = Counter()
    for item in instances:
        counts.update(definitions[item['cell']]['devices'])
    return reference, dict(schema=1, status='reference_generated', qualified=False,
        top=top, top_ports=len(ports), top_port_net_mapping=[dict(port=p['name'], net=p['net']) for p in ports],
        instances=instances, explicit_bulk_bindings=changes,
        intentional_unused_outputs=unused, diode_changes=diodes, device_counts=dict(counts),
        scope='Complete captured OpenDB to independent standard-cell CDL reference; native LVS and written-metal continuity remain required.')


def prepare(checkpoint, masters, directory, *, top):
    """Create a new engine request with complete, hash-checked master inputs."""
    directory = Path(directory).resolve()
    if directory.exists():
        raise ValueError('Use a new reference directory; prior evidence is preserved.')
    sources = []
    for master, row in sorted(masters.items()):
        path = Path(row['path']).resolve(strict=True)
        if file_digest(path) != row['sha256']:
            raise ValueError('Independent CDL source hash mismatch: ' + master)
        cell_definition(path.read_text(encoding='utf-8'), master)
        sources.append(dict(master=master, path=str(path), sha256=row['sha256']))
    if not sources:
        raise ValueError('No independent CDL masters were captured.')
    checkpoint = Path(checkpoint).resolve(strict=True)
    request = dict(schema=1, top=top, checkpoint=dict(path=str(checkpoint), sha256=file_digest(checkpoint)),
        masters=sources, raw_cdl=str(directory/'raw-reference.cdl'), output=str(directory/'engine-reference.json'))
    directory.mkdir(parents=True)
    worker = directory/'reference_engine.py'
    shutil.copy2(Path(__file__).with_name('digital_lvs_engine.py'), worker)
    atomic_write(directory/'request.json', json.dumps(request, indent=2) + '\n')
    driver = directory/'export.py'
    atomic_write(driver, 'import runpy\nrunpy.run_path(' + repr(str(worker)) +
                 ', init_globals={"REQUEST_PATH": ' + repr(str(directory/'request.json')) + '})\n')
    return driver, request


def finalize(directory, database, *, top):
    """Authenticate fresh engine outputs, then retain the completed reference."""
    directory = Path(directory)
    request = json.loads((directory/'request.json').read_text(encoding='utf-8'))
    observed = json.loads((directory/'engine-reference.json').read_text(encoding='utf-8'))
    if top != request['top'] or observed['checkpoint_sha256'] != request['checkpoint']['sha256']:
        raise ValueError('Reference engine output belongs to another checkpoint.')
    if file_digest(directory/'raw-reference.cdl') != observed['raw_cdl_sha256']:
        raise ValueError('Raw reference changed after engine readback.')
    library = {}
    for row in [request['checkpoint'], *request['masters']]:
        if file_digest(Path(row['path'])) != row['sha256']:
            raise ValueError('Reference source changed after engine readback.')
        if 'master' in row:
            library[row['master']] = Path(row['path']).read_text(encoding='utf-8')
    text, report = assemble((directory/'raw-reference.cdl').read_text(encoding='utf-8'), observed, database, library, top=top)
    for name in ('reference.cdl', 'reference.json'):
        if (directory/name).exists():
            raise ValueError('Completed reference evidence already exists.')
    atomic_write(directory/'reference.cdl', text)
    report.update(checkpoint_sha256=request['checkpoint']['sha256'],
        raw_cdl_sha256=observed['raw_cdl_sha256'], reference_sha256=file_digest(directory/'reference.cdl'),
        request_sha256=file_digest(directory/'request.json'), engine_report_sha256=file_digest(directory/'engine-reference.json'))
    atomic_write(directory/'reference.json', json.dumps(report, indent=2) + '\n')
    return report


def validate(platform):
    """Validate optional, captured library inputs for automatic finish export."""
    spec = platform.get('lvs_reference')
    if spec is None:
        return
    from .digital import relative_path
    if (platform.get('name') not in ('gf180', 'gf180d') or not isinstance(spec, dict) or
            set(spec) != {'recipe', 'library_revision', 'masters'} or spec['recipe'] != RECIPE or
            not isinstance(spec['library_revision'], str) or not spec['library_revision'].strip()):
        raise ValueError('Choose a captured GF180 9-track reference recipe and library revision.')
    masters = spec['masters']
    files = {item['path'] for item in platform['files']}
    if not isinstance(masters, dict) or not masters:
        raise ValueError('Reference generation needs captured standard-cell CDL masters.')
    for name, path in masters.items():
        if (not isinstance(name, str) or not name.startswith(PREFIX) or
                not isinstance(path, str) or relative_path(path) not in files):
            raise ValueError('Reference master is not a captured GF180 CDL file.')
    if len(set(masters.values())) != len(masters):
        raise ValueError('Each reference master needs its own captured CDL definition.')


def summary(report):
    return {**{key: report[key] for key in ('schema', 'status', 'qualified', 'scope', 'top',
            'checkpoint_sha256', 'reference_sha256', 'platform_fingerprint', 'device_counts', 'top_ports')},
        'placed_cells': len(report['instances']), 'bulk_bindings': len(report['explicit_bulk_bindings']),
        'unused_outputs': len(report['intentional_unused_outputs'])}


def execute(r):
    """Automatic reference export in the application's finished-design job."""
    if r.platform.get('lvs_reference') is None:
        return None
    validate(r.platform)
    for key in ('checkpoint', 'database'):
        if file_digest(r.root/r.artifacts[key]['path']) != r.artifacts[key]['sha256']:
            raise ValueError('Captured implementation changed before reference export.')
    database = json.loads((r.root/r.artifacts['database']['path']).read_text(encoding='utf-8'))
    files = {item['path']: item for item in r.platform['files']}
    definitions = r.platform['lvs_reference']['masters']
    masters = {}
    for name in {i['master'] for i in database['instances']}:
        if name not in definitions:
            raise ValueError('The captured CDL library is missing a placed master: ' + name)
        path = definitions[name]
        masters[name] = dict(path=r.root/'platform'/path, sha256=files[path]['sha256'])
    folder = r.root/'lvs-reference'
    driver, request = prepare(r.root/r.artifacts['checkpoint']['path'], masters, folder, top=r.config['top'])
    r.command([r.tools['openroad'], '-no_init', '-exit', '-python', str(driver)],
              'Reading final-layout reference connections', fraction=.94)
    report = finalize(folder, database, top=r.config['top'])
    for key, name in [('lvs_reference', 'reference.cdl'), ('lvs_reference_raw', 'raw-reference.cdl'),
                      ('lvs_reference_engine', 'engine-reference.json'), ('lvs_reference_request', 'request.json'),
                      ('lvs_reference_worker', 'reference_engine.py'), ('lvs_reference_driver', 'export.py')]:
        r.add_artifact(key, folder/name)
    library_artifacts = {}
    for index, (name, row) in enumerate(sorted(masters.items())):
        key = 'lvs_reference_master_' + str(index)
        r.add_artifact(key, row['path']); library_artifacts[name] = key
    report.update(platform_fingerprint=r.platform['fingerprint'], recipe=RECIPE,
        library_revision=r.platform['lvs_reference']['library_revision'], library_artifacts=library_artifacts)
    r.save_json('lvs_reference_report', report, 'lvs-reference-report.json')
    return summary(report)


def validate_saved(data, root):
    """Reconstruct saved reference semantics, not just a declared pass flag."""
    root = Path(root); artifacts = data['artifacts']
    declared = data.get('physical', {}).get('reference')
    required = {'lvs_reference', 'lvs_reference_raw', 'lvs_reference_engine', 'lvs_reference_report'}
    if declared is None and not required & artifacts.keys():
        return None  # Historical/unconfigured jobs remain readable without this claim.
    if not isinstance(declared, dict) or not required <= artifacts.keys():
        raise ValueError('Saved reference-generation evidence is incomplete.')

    def path(key):
        return root/artifacts[key]['path']

    report = json.loads(path('lvs_reference_report').read_text(encoding='utf-8'))
    observed = json.loads(path('lvs_reference_engine').read_text(encoding='utf-8'))
    policy = data.get('environment', {}).get('lvs_reference', {})
    if (report.get('checkpoint_sha256') != artifacts['checkpoint']['sha256'] or
            observed.get('checkpoint_sha256') != artifacts['checkpoint']['sha256'] or
            report.get('reference_sha256') != artifacts['lvs_reference']['sha256'] or
            observed.get('raw_cdl_sha256') != artifacts['lvs_reference_raw']['sha256'] or
            report.get('platform_fingerprint') != data.get('platform', {}).get('fingerprint') or
            report.get('recipe') != RECIPE or policy.get('recipe') != RECIPE or
            report.get('library_revision') != policy.get('library_revision')):
        raise ValueError('Saved reference evidence belongs to different implementation inputs.')
    for master, key in report['library_artifacts'].items():
        if artifacts[key]['path'] != 'platform/' + policy.get('masters', {}).get(master, ''):
            raise ValueError('Saved reference library differs from its captured policy.')
    library = {name: path(key).read_text(encoding='utf-8') for name, key in report['library_artifacts'].items()}
    database = json.loads(path('database').read_text(encoding='utf-8'))
    text, expected = assemble(path('lvs_reference_raw').read_text(encoding='utf-8'), observed, database,
                              library, top=report['top'])
    if (text != path('lvs_reference').read_text(encoding='utf-8') or
            any(report.get(key) != value for key, value in expected.items()) or summary(report) != declared):
        raise ValueError('Saved reference no longer reproduces its captured device connections.')
    return report
