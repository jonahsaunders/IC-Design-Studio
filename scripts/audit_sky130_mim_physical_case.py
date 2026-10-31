"""Independent physical readback for the fixed 2 x 10 um MiM corner coupon.

Only retained masks, native records and logs are read. No application extractor,
generator, qualification producer or executable EDA tool is imported or run.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shlex
import xml.etree.ElementTree as ET

import klayout.db as db
from scripts.audit_sky130_mim_orientation import normalization, regions

STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')
FAULTS = ('dielectric-missing', 'top-open', 'bottom-open', 'reference-width', 'reference-count', 'reference-swapped')
SIZE = (2, 10, 1)
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
load = lambda path: json.loads(Path(path).read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stage_map(report):
    stages = report['stages']
    require(tuple(s['name'] for s in stages) == STAGES, 'Physical stages are incomplete, duplicated or reordered.')
    return {s['name']: s for s in stages}


def circuit(text, plate, size=SIZE, top_open=False):
    text = re.sub(r'\n\s*\+\s*', ' ', text)
    rows = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows) == 3 and rows[0] == ['.subckt', 'device_coupon', 'P', 'N'] and
            rows[-1] in (['.ends'], ['.ends', 'device_coupon']), 'Physical circuit interface or element count differs.')
    fields = rows[1]
    require(len(fields) in (6, 7) and fields[0].startswith('X') and
            fields[3] == f'sky130_fd_pr__cap_mim_m3_{plate}', 'Physical circuit model or parameters differ.')
    if top_open:
        require(fields[1] not in ('P', 'N', '0') and fields[2] == 'N', 'Top-open native terminal is not disconnected.')
    else:
        require(fields[1:3] == ['P', 'N'], 'Physical circuit terminal binding differs.')
    pairs = [v.split('=') for v in fields[4:]]
    require(all(len(v) == 2 for v in pairs), 'Malformed physical circuit parameter.')
    values = {k: float(v) for k, v in pairs}
    require(len(values) == len(pairs) and {'w', 'l'} <= values.keys() and not set(values) - {'w', 'l', 'm'}, 'Ambiguous physical circuit parameters.')
    require(all(math.isfinite(v) for v in values.values()) and
            (values['w'], values['l'], values.get('m', 1)) == tuple(size), 'Physical circuit dimensions or multiplicity differ.')


def equal_masks(first, second):
    return all((first.get(k, db.Region()) ^ second.get(k, db.Region())).is_empty() for k in first.keys() | second.keys())


def fault_masks(before, after, plate, name):
    require(plate in (1, 2) and name in FAULTS, 'Unknown physical mutation.')
    cap, cut = ((89, 44), (70, 44)) if plate == 1 else ((97, 44), (71, 44))
    require(cap in before and not before[cap].is_empty() and cut in before, 'Missing baseline capacitor/contact masks.')
    inside, outside = before[cut] & before[cap], before[cut] - before[cap]
    require(not inside.is_empty() and not outside.is_empty(), 'Baseline needs both top and bottom contacts.')
    expected = {k: v.dup() for k, v in before.items()}
    if name == 'dielectric-missing': expected[cap] = db.Region()
    elif name == 'top-open': expected[cut] = outside
    elif name == 'bottom-open': expected[cut] = inside
    require(equal_masks(expected, after), 'Physical fault masks do not match the declared mutation: ' + name)


def native_completion(path):
    text = path.read_text()
    require(re.findall(r'^(STUDIO_MAGIC_COMPLETE)[ \t]*$', text, re.M) == ['STUDIO_MAGIC_COMPLETE'], 'Native Magic completion marker missing or duplicated.')


def execution_scripts(origin, technology, fault=None):
    """Independent literal contract for the fixed coupon's three Magic paths."""
    for value in (origin, technology):
        require(value.startswith('/') and not any(c in value for c in '\\$[]{}"\n\r'), 'Unsupported recorded native execution path.')
    startup = f'tech load "{technology}"\ndrc euclidean on\n'
    prefix = ('if {[catch {\n' + f'gds read "{origin}/layout.gds"\n' +
              'load "device_coupon"\nselect top cell\nbox values 0 0 0 0\n' +
              'if {![port "P" exists]} {error "Missing layout port P"}\nport "P" index 1\n' +
              'if {![port "N" exists]} {error "Missing layout port N"}\nport "N" index 2\n')
    suffix = 'puts STUDIO_MAGIC_COMPLETE\n} err]} {puts stderr "STUDIO_MAGIC_ERROR $err"}\nquit -noprompt\n'
    drc = ('snap internal\nselect top cell\nbox values {*}[select bbox]\nbox grow c 10um\n'
           'drc style "drc(full)"\ndrc ignore none\ndrc check\ndrc catchup\n'
           'puts "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\n'
           'puts "STUDIO_MAGIC_SCALE [cif scale out]"\nset f [open findings.tsv w]\n'
           'foreach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\n\n')
    ext2spice = ('ext2spice lvs\next2spice subcircuit top on\next2spice renumber off\n'
                 'ext2spice global off\next2spice hierarchy on\next2spice blackbox off\n'
                 'ext2spice scale off\next2spice merge none\next2spice cthresh infinite\n'
                 'ext2spice rthresh infinite\next2spice extresist off\next2spice -o extracted.spice\n')
    scripts = {'drc/startup.tcl': startup, 'drc/run.tcl': prefix + drc + suffix,
               'lvs-extraction/startup.tcl': startup}
    if fault == 'dielectric-missing':
        scripts['lvs-extraction/run.tcl'] = prefix + 'extract all\n' + ext2spice + suffix
    else:
        scripts['lvs-extraction/native-extraction.tcl'] = prefix + 'extract all\n\nputs "STUDIO_MIM_SCALE [cif scale out]"\n\n' + suffix
        if fault != 'bottom-open':
            scripts['lvs-extraction/run.tcl'] = prefix + '\n' + ext2spice + suffix
    return scripts


def execution_context(folder, plate):
    """Use retained identities only, so archived evidence needs no live tool/PDK."""
    root = folder.parent.parent
    aggregate = load(root / 'qualification.json'); contract = load(root / 'contract.json')
    pdk = load(folder / 'input.icproj')['pdk']; lock = pdk['package_lock']
    physical = pdk['physical']; pdk_root = pdk['package_root']
    require(lock['id'] == aggregate['physical_package']['target'] == 'sky130A' and
            lock['revision'] == aggregate['physical_package']['revision'], 'Physical package revision differs from execution.')
    require(physical['magic_technology'] == 'libs.tech/magic/sky130A.tech' and
            physical['netgen_setup'] == 'libs.tech/netgen/sky130A_setup.tcl', 'Physical engine asset selection differs.')
    release_path = root / 'contract-sources/physical_release_lock'
    require(sha(release_path) == contract['sources']['physical_release_lock']['sha256'],
            'Public physical release source binding differs.')
    release = load(release_path)
    physical_release = {key: release[key] for key in ('release', 'repository')}
    physical_release['files'] = {name: release['files'][name] for name in ('common.tar.zst', 'sky130_fd_pr.tar.zst')}
    release_bytes = (json.dumps(physical_release, indent=2, sort_keys=True) + '\n').encode()
    require(lock['files']['UPSTREAM-LOCK.json'] == hashlib.sha256(release_bytes).hexdigest(),
            'Physical package upstream release differs from captured public release.')
    for name, relative in (('physical_technology', physical['magic_technology']),
                           ('physical_pcell', 'libs.tech/magic/sky130A.tcl')):
        expected = contract['sources'][name]['sha256']
        require(lock['files'][relative] == expected and sha(root / 'contract-sources' / name) == expected,
                'Public physical source binding differs: ' + name)
    assets = {}
    for name, digest in lock['files'].items():
        if name.startswith('libs.tech/magic/') or name in (physical['netgen_setup'], 'libs.tech/netgen/setup.tcl'):
            require('..' not in PurePosixPath(name).parts and not PurePosixPath(name).is_absolute(), 'Physical asset escaped package root.')
            assets[str(PurePosixPath(pdk_root) / name)] = digest
    require(assets and str(PurePosixPath(pdk_root) / physical['netgen_setup']) in assets, 'Missing physical setup asset.')
    return dict(pdk=pdk, assets=assets,
                tools={name: aggregate['tools'][name] for name in ('magic', 'netgen')},
                origin=str(PurePosixPath(aggregate['execution_root']) / 'physical' / str(plate)),
                technology=str(PurePosixPath(pdk_root) / physical['magic_technology']),
                setup=str(PurePosixPath(pdk_root) / physical['netgen_setup']))


def check_execution(folder, native, context, fault=None):
    origin = str(PurePosixPath(context['origin']) / folder.name)
    expected = execution_scripts(origin, context['technology'], fault)
    actual = {p.relative_to(folder).as_posix() for stage in ('drc', 'lvs-extraction') for p in (folder / stage).glob('*.tcl')}
    require(actual == set(expected), 'Native script coverage differs.')
    for name, text in expected.items():
        require((folder / name).read_text() == text, 'Executed native Tcl differs: ' + name)
    # Valid orientations are reimported streams linked to the package; only the
    # original application fixture carries these routing/connectivity helpers.
    expected_pdk = context['pdk'] if fault else {k: v for k, v in context['pdk'].items()
                                               if k not in ('connectivity', 'routing_conductors')}
    require(load(folder / 'input.icproj')['pdk'] == expected_pdk, 'Saved native PDK differs from physical case input.')
    require(native['drc_engine'] == native['lvs_extractor'] == 'magic', 'Native engine selection differs.')
    for stage in native['stages']:
        if stage['name'] in ('preflight', 'integrity') and stage['status'] == 'passed':
            evidence = stage['evidence']
            require(evidence['assets'] == context['assets'] and evidence['tools'] == context['tools'],
                    'Native asset/tool receipt differs from captured execution identity.')
    if fault not in ('bottom-open', 'dielectric-missing'):
        console = (folder / 'lvs/console.log').read_text()
        require(re.findall(r'^Reading netlist file (.+)$', console, re.M) ==
                [origin + '/schematic-lvs.spice', origin + '/lvs-extraction/extracted.spice'], 'Netgen compared different native input paths.')
        require(re.findall(r'^Reading setup file (.+)$', console, re.M) == [context['setup']], 'Netgen used a different setup path.')
        proof = load(folder / 'lvs-extraction/mim-orientation.json')
        require(native['mim_orientation'] == proof and proof['technology_sha256'] == context['assets'][context['technology']] and
                proof['pcell_sha256'] == context['pdk']['package_lock']['files']['libs.tech/magic/sky130A.tcl'],
                'Native orientation source identity differs.')


def check_common(folder, native, context, fault=None):
    stages = stage_map(native)
    check_execution(folder, native, context, fault)
    require(all(stages[k]['status'] == 'passed' for k in ('preflight', 'layout_export', 'drc')), 'Physical setup/export/DRC did not pass.')
    reference = stages['preflight']['evidence']['reference']
    require(reference['top'] == 'device_coupon' and reference['ports'] == ['P', 'N'] and
            reference['sha256'] == sha(folder / 'schematic.spice'), 'Physical reference receipt differs.')
    require((folder / 'schematic.spice').read_bytes() == (folder / 'schematic-lvs.spice').read_bytes(), 'Physical comparison reference was substituted.')
    export = stages['layout_export']['evidence']
    require(export['source_sha256'] == sha(folder / 'original.gds') and export['sha256'] == sha(folder / 'layout.gds'), 'Physical stream receipt differs.')
    require(equal_masks(regions(folder / 'original.gds'), regions(folder / 'layout.gds')), 'Private physical stream altered masks.')
    drc = stages['drc']['evidence']; log = (folder / 'drc/console.log').read_text()
    require(native['drc_count'] == native['magic_drc_count'] == drc['violations'] == drc['native_violations'] == 0 and
            native['magic_drc_style'] == drc['style'] == 'drc(full)', 'Physical full DRC result differs.')
    require(re.findall(r'^STUDIO_DRC_COUNT (\d+)\s*$', log, re.M) == ['0'] and
            re.findall(r'^STUDIO_DRC_STYLE (.+)$', log, re.M) == ['drc(full)'], 'Native full DRC log differs.')
    native_completion(folder / 'drc/console.log')
    require(not (folder / 'drc/findings.tsv').read_text().strip(), 'Native DRC findings remain.')
    if stages['integrity']['status'] == 'passed':
        integrity = stages['integrity']['evidence']; files = integrity['files']
        required = {'input.icproj', 'schematic.spice', 'schematic-lvs.spice', 'original.gds', 'layout.gds',
                    'drc/console.log', 'lvs-extraction/native-extraction.log', 'lvs-extraction/console.log',
                    'lvs-extraction/mim-orientation.json', 'lvs-extraction/native-original.ext',
                    'lvs-extraction/device_coupon.ext', 'lvs-extraction/extracted.spice', 'lvs/lvs.log'}
        require(integrity.get('verified') is True and required <= files.keys(), 'Incomplete native integrity receipt.')
        for name, digest in files.items():
            path = folder / name
            require(path.resolve().is_relative_to(folder.resolve()) and not path.is_symlink() and sha(path) == digest, 'Native integrity file differs: ' + name)
    if stages['lvs_extraction']['status'] == 'passed':
        extraction = stages['lvs_extraction']['evidence']
        require(extraction['deck'] == 'lvs-extraction/extracted.spice' and
                extraction['sha256'] == sha(folder / extraction['deck']), 'Native extraction receipt differs.')
        require(extraction['settings'] == dict(hierarchy=True, blackbox=False, merge='none', scale=False,
                capacitance_threshold='infinite', resistance_threshold='infinite', distributed_resistance=False), 'Native extraction class/settings differ.')
        native_completion(folder / 'lvs-extraction/native-extraction.log')
        native_completion(folder / 'lvs-extraction/console.log')
    return stages


def completed_failure(folder, plate, name, native, stages):
    extraction = folder / 'lvs-extraction'
    states = tuple(stages[k]['status'] for k in STAGES)
    model = f'sky130_fd_pr__cap_mim_m3_{plate}'
    if name in ('bottom-open', 'dielectric-missing'):
        require(states == ('passed', 'passed', 'passed', 'failed', 'not_run', 'not_run'), 'Extraction fault has an unrelated stage outcome.')
        require(not (folder / 'lvs/lvs.log').exists() and not (extraction / 'native-original.ext').exists()
                and not (extraction / 'mim-orientation.json').exists(), 'Failed extraction has unexpected downstream evidence.')
        devices = [shlex.split(line) for line in (extraction / 'device_coupon.ext').read_text().splitlines() if line.startswith('device ')]
        if name == 'bottom-open':
            native_completion(extraction / 'native-extraction.log')
            require(len(devices) == 1 and devices[0][:3] == ['device', 'csubckt', model], 'Bottom-open fault lacks the actual native capacitor.')
            require(native.get('error') == 'MiM orientation needs bottom contacts on exactly one axis.' and
                    stages['lvs_extraction'].get('error') == native['error'] and not (extraction / 'extracted.spice').exists(), 'Wrong bottom-contact extraction failure.')
        else:
            native_completion(extraction / 'console.log')
            rows = [line.split() for line in (extraction / 'extracted.spice').read_text().splitlines() if line.strip() and not line.lstrip().startswith('*')]
            require(not devices and rows == [['.subckt', 'device_coupon', 'P'], ['.ends']], 'Dielectric fault retained a capacitor or wrong interface.')
            require(native.get('error', '').startswith('Extracted port order differs from the schematic:') and
                    stages['lvs_extraction'].get('error') == native['error'], 'Wrong dielectric extraction failure.')
    else:
        require(states == ('passed', 'passed', 'passed', 'passed', 'failed', 'passed'), 'Physical mismatch has an unrelated stage outcome.')
        require(normalization(folder, SIZE, plate) == 1, 'Physical fault extraction normalization differs.')
        circuit((extraction / 'extracted.spice').read_text(), plate, top_open=name == 'top-open')
        text = (folder / 'lvs/lvs.log').read_text()
        final = re.findall(r'^Final result: (.+)$', text, re.M)
        if name == 'top-open':
            require(final == ['Top level cell failed pin matching.'], 'Top-open fault lacks completed native pin mismatch.')
        else:
            require(final == ['Circuits match uniquely.'] and 'Property errors were found.' in text,
                    'Reference fault lacks completed native property mismatch.')


def audit_physical(folder, plate, physical):
    folder = Path(folder).resolve()
    require(plate in (1, 2) and physical['plate'] == plate and physical['status'] == 'PASS' and
            physical['size'] == list(SIZE) and load(folder / 'record.json') == physical, 'Physical case identity differs.')
    require(len(physical['layouts']) == 2 and {v['name'] for v in physical['layouts']} == {'0-plain', '90-plain'}, 'Physical orientation coverage differs.')
    require(len(physical['faults']) == len(FAULTS) and {v['name'] for v in physical['faults']} == set(FAULTS), 'Physical fault coverage differs.')
    context = execution_context(folder, plate)
    base = regions(folder / 'original.gds')
    for row in physical['layouts']:
        dest = folder / ('valid-' + row['name']); native = load(dest / 'report.json')
        require(sha(dest / 'report.json') == row['report_sha256'] and native['status'] == 'passed', 'Positive physical report differs.')
        stages = check_common(dest, native, context)
        require(all(s['status'] == 'passed' for s in stages.values()), 'Positive physical stage failed.')
        require(stages['lvs']['evidence'] == dict(unique_match=True, log='lvs/lvs.log'), 'Positive LVS receipt differs.')
        log = (dest / 'lvs/lvs.log').read_text()
        require(re.findall(r'^Final result: (.+)$', log, re.M) == ['Circuits match uniquely.'] and
                'Cell pin lists are equivalent.' in log and not re.search(r'property errors|failed pin matching|do not match', log, re.I), 'Native LVS did not establish a clean match.')
        require(row['public_drc']['violations'] == 0 and not ET.parse(dest / 'public-drc/report.lyrdb').findall('.//items/item'), 'Public physical DRC finding.')
        require(normalization(dest, SIZE, plate) == 1, 'Positive native mask dimensions differ.')
        circuit((dest / 'schematic-lvs.spice').read_text(), plate)
        circuit((dest / 'lvs-extraction/extracted.spice').read_text(), plate)
        angle = int(row['name'].split('-')[0])
        expected = {k: v.transformed(db.Trans(angle // 90, False, 125000, -235000)) for k, v in base.items()}
        require(equal_masks(expected, regions(dest / 'layout.gds')), 'Native orientation/translation differs from original masks.')
        for path in (folder / ('input-' + row['name'] + '.gds'), folder / ('roundtrip-' + row['name'] + '.gds'), folder / ('roundtrip-' + row['name'] + '.oas')):
            require(equal_masks(expected, regions(path)), 'Physical stream roundtrip altered masks.')
    for row in physical['faults']:
        name = row['name']; dest = folder / name; native = load(dest / 'report.json')
        require(row['detected'] is True and sha(dest / 'report.json') == row['report_sha256'] and
                native['status'] == 'failed' and row['error'] == native.get('error'), 'Physical fault report differs.')
        expected_method = 'written-mask orientation guard after native extraction' if name == 'bottom-open' else 'native circuit comparison'
        require(row['method'] == expected_method, 'Physical fault detection method differs.')
        stages = check_common(dest, native, context, name)
        fault_masks(base, regions(dest / 'layout.gds'), plate, name)
        size = {'reference-width': (2.4, 10, 1), 'reference-count': (2, 10, 2), 'reference-swapped': (10, 2, 1)}.get(name, SIZE)
        circuit((dest / 'schematic-lvs.spice').read_text(), plate, size)
        completed_failure(dest, plate, name, native, stages)
    return dict(layouts=2, physical_faults=6)
