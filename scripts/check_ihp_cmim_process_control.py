"""Replay the finite IHP cap_cmim process-control comparison from raw evidence."""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.engines import parse_raw
from scripts.verify_frozen_ihp_cmim import (
    FIELDS, circuit, completed_stages, confined, load, project_stream, require,
    same_stream, safe, sha, stream, strict_lvs,
)

DOC = 'docs/qualification/ihp-cmim-applicability-v1'
PDK = 'icstudio/assets/pdks/ihp-sg13g2'
FIXTURE = 'icstudio/assets/qualification/ihp-cmim-reference'
DECK = 'icstudio/assets/physical/ihp_klayout_lvs'
ARCHIVE_SHA = '495ee8b7771c8df0f00c8b4b994e48d4dbcf18a8734a1b25cb9c8b423136e6a7'
PACKAGE_SHA = 'da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0'
LEDGER_SHA = '9dd59dddde12f86f2b818ffe7eb721c25fd6b0faed2969f3a9a2940403f5aba7'
MODEL = 'libs.tech/ngspice/models'
MODEL_NAMES = ('cornerCAP.lib', 'capacitors_mod.lib', 'capacitors_mod_mismatch.lib', 'capacitors_stat.lib',
               'cap_cmomi.lib', 'cap_cmomf.lib')
SYMBOL = 'libs.tech/xschem/sg13g2_pr/cap_cmim.sym'
GENERATOR = 'libs.tech/magic/ihp-sg13g2-cap.tcl'
PLATE_RULES = ('cap_derivations.lvs', 'cap_extraction.lvs', 'custom_mim_extractor.lvs')
SOURCE_MODULES = ('scripts/check_ihp_cmim_process_control.py', 'scripts/qualify_ihp_cmim_process_control.py',
                  'scripts/verify_frozen_ihp_cmim.py', 'scripts/verify_frozen_ihp_resistors.py',
                  'scripts/verify_frozen_mim.py', 'icstudio/engines.py')
PORTS = {'C1': 'TopMetal1.drawing', 'C2': 'Metal5.drawing'}
COMMAND = ('-n', '-b', 'input.cir')
MANAGED_WRAPPER_SHA = 'de0028325297f6c2171e04d7d1204b0f711b1d521e7183f9bcf9abf9121d50b7'
CASES = {
    **{f'voltage-{i}': (bias, 26.85, 1_000_000, 7, 7) for i, bias in enumerate((-10, -5, 0, 5, 10))},
    **{f'temperature-{i}': (0, temp, 1_000_000, 7, 7)
       for i, temp in enumerate((-40, 0, 26.85, 27, 75, 125))},
    **{f'geometry-{i}': (0, 27, 100_000, w, l) for i, (w, l) in enumerate(((7, 7), (10, 10), (7, 14)))},
}
CONTROLS = {'swapped-electrodes': (CASES['voltage-4'], 'upper', 'electrode differs'),
            'wrong-frequency': ((10, 26.85, 100_000, 7, 7), 'lower', 'frequency differs'),
            'wrong-temperature': ((10, 27, 1_000_000, 7, 7), 'lower', 'temperature differs'),
            'wrong-geometry': ((10, 26.85, 1_000_000, 8, 7), 'lower', 'geometry differs')}


def source_contract(root):
    paths = {f'{DOC}/source-ledger.json': LEDGER_SHA, f'{PDK}/package.json': PACKAGE_SHA}
    for relative, digest in paths.items():
        require(sha(confined(root, relative)) == digest, 'Source lock differs: '+relative)
    ledger = load(root/f'{DOC}/source-ledger.json')
    package = load(root/f'{PDK}/package.json')
    for name in ('LICENSE', 'mimcap_params.csv', 'meas_cond.csv', '04_06_cap.rst'):
        paths[f'{DOC}/{name}'] = ledger['files'][name]['sha256']
    for name in (*(f'{MODEL}/{name}' for name in MODEL_NAMES), SYMBOL, GENERATOR, 'LICENSE'):
        paths[f'{PDK}/{name}'] = package['files'][name]
    fixture = load(confined(root, f'{FIXTURE}/SOURCE.json'))
    paths.update({f'{FIXTURE}/SOURCE.json': 'b8eee6f5c73fb3e700967095b89c2ce9cbce60343fa1ce6a4aec4de639c51982',
                  f'{FIXTURE}/mask-only.json': fixture['mask_only_sha256'],
                  f'{FIXTURE}/LICENSE': fixture['license_sha256']})
    for relative, digest in paths.items():
        require(sha(confined(root, relative)) == digest, 'Source differs: '+relative)
    require(ledger['license'] == 'Apache-2.0' and package['revision'] == 'cfb96b74cf33877e' and
            fixture['pdk_manifest_sha256'] == PACKAGE_SHA and fixture['public_magic_generator_sha256'] == paths[f'{PDK}/{GENERATOR}'],
            'Package/fixture identity differs.')

    def table(name):
        return csv.reader(io.StringIO((root/DOC/name).read_text(encoding='utf-8')), skipinitialspace=True)

    condition = {row[0].strip(): row[2] for row in table('meas_cond.csv') if len(row) >= 3}
    required_terms = {'A.k': ('V=0V', '100kHz', 'Cmeasure / Area'),
                      'A.l': ('V=0V', '100kHz', 'Cmeasure / Perimeter'),
                      'A.ad': ('VMIM = 0V', 'f = 1MHz', '-40°C to 125°C', 'T0 = 300K', '(T - T0)²'),
                      'A.ah': ('T = 300K', 'f = 1MHz', '-10V to +10V', 'lower electrode',
                               'top electrode is grounded', '(VMIM)²')}
    for key, terms in required_terms.items():
        require(all(term in condition[key] for term in terms), 'Measurement condition differs: '+key)
    target = {}
    for row in table('mimcap_params.csv'):
        key, unit, low, nominal, high, setup = row[1:7]
        if setup in required_terms:
            values = [float(re.fullmatch(r':[a-z]+:`(-?[0-9.]+)`', item)[1]) if item else None
                      for item in (low, nominal, high)]
            target[key] = dict(unit=unit, min=values[0], target=values[1], max=values[2], condition=setup)
    require(set(target) == {'CMIMA', 'CMIMP', 'VCMIM1', 'VCMIM2', 'TCMIM1', 'TCMIM2'}, 'Missing process targets.')
    require(all(target[key]['min'] is target[key]['max'] is None for key in target if key != 'CMIMA'),
            'Unexpected source tolerance.')
    return dict(document_commit=ledger['commit'], package_revision=package['revision'], files=paths,
                targets=target, conditions={key: condition[key] for key in required_terms})


def plate_evidence(root, archive_path):
    require(sha(safe(archive_path)) == ARCHIVE_SHA, 'Original audited native archive differs.')
    prefix = 'default-7-0/'
    flow = 'job/physical-flow/'
    extract = flow+'lvs-extraction/'
    with zipfile.ZipFile(archive_path) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'Duplicate native member.')

        def member(name):
            return archive.read(prefix+name)

        native = circuit(member(extract+'native.cir').decode(), 'public', raw_top_order=True)
        original = circuit(member('captured-reference.spice').decode(), 'original')
        strict_lvs(member(flow+'lvs/lvs.log').decode())
        completed_stages(json.loads(member(flow+'report.json')), 'ihp-klayout')
        require(b'Extracting cap_cmim device' in member(extract+'console.log') and
                b'LVS Total Run time' in member(extract+'console.log'), 'Incomplete native extraction.')
        project = json.loads(member('catalog.icproj'))
        cell, = project['cells']
        device, = cell['devices']
        lock = load(root/f'{PDK}/package.json')
        fixture = load(root/f'{FIXTURE}/mask-only.json')
        require(all(project['pdk'].get(k) == v for k, v in lock['technology'].items()) and
                all(cell[key] == fixture[key] for key in FIELDS), 'Physical fixture/package does not match archived input.')
        require(device['nets'] == {'c0': 'C1', 'c1': 'C2'} and
                device['model_ref'] == dict(pdk=lock['id'], revision=lock['revision'], device='sg13g2_pr/cap_cmim.sym'),
                'Archived ordinary catalog terminal mapping differs.')
        require({p['name']: p['layer'] for p in cell['layout_ports']} == PORTS and len(cell['layout_ports']) == 2,
                'Physical label layer mapping differs.')
        command = json.loads(member(extract+'command.json'))
        require(any(value.startswith('input=') and value.endswith('/'+prefix+extract+'labels.gds') for value in command) and
                {'topcell=coupon', 'net_only=true', 'top_lvl_pins=true', 'no_simplify=true'} <= set(command),
                'Raw extraction mask/command binding differs.')
        with tempfile.TemporaryDirectory(prefix='cmim-plates-') as directory:
            gds = Path(directory)/'layout.gds'
            expected = project_stream(project)
            gds.write_bytes(member(flow+'layout.gds'))
            same_stream(stream(gds, 'coupon'), expected, text_presentation=False)
            gds.write_bytes(member(extract+'labels.gds'))
            # The native adapter adds matching extractor text on datatype 25.
            duplicates = [((layer, 25), name, x, y, angle) for (layer, _), name, x, y, angle in expected[1]]
            same_stream(stream(gds, 'coupon'), (expected[0], sorted(expected[1]+duplicates)), text_presentation=False)
        rule_text = {}
        for name in PLATE_RULES:
            actual = member(extract+'deck/rule_decks/'+name)
            require(actual == (root/DECK/'rule_decks'/name).read_bytes(), 'Physical extractor rule differs: '+name)
            rule_text[name] = actual.decode()
        require('mim_top = mim_drw.overlapping(topmetal1_con)' in rule_text['cap_derivations.lvs'] and
                'mim_btm = mim_drw.and(metal5_con)' in rule_text['cap_derivations.lvs'] and
                "'top_mim' => cmim_top" in rule_text['cap_extraction.lvs'] and
                "'btm_mim' => cmim_btm" in rule_text['cap_extraction.lvs'] and
                re.findall(r'ter[12] = add_terminal\(RBA::DeviceTerminalDefinition\.new\("(mim_(?:top|btm))"\)\)',
                           rule_text['custom_mim_extractor.lvs']) == ['mim_top', 'mim_btm'],
                'Native ordered top/bottom definitions differ.')
        evidence = {name: hashlib.sha256(member(name)).hexdigest() for name in (
            'catalog.icproj', 'captured-reference.spice', flow+'layout.gds', flow+'report.json', flow+'lvs/lvs.log',
            extract+'native.cir', extract+'console.log', extract+'labels.gds', extract+'command.json',
            *(extract+'deck/rule_decks/'+name for name in PLATE_RULES))}
    symbol = (root/PDK/SYMBOL).read_text(encoding='utf-8')
    model = (root/PDK/MODEL/'capacitors_mod.lib').read_text(encoding='utf-8')
    lvs_doc = (root/DOC/'04_06_cap.rst').read_text(encoding='utf-8')
    require(re.findall(r'^B\s+5\s+[^\n]+\{name=(\w+) dir=inout\}', symbol, re.M) == ['c0', 'c1'] and
            re.search(r'^\.subckt cap_cmim PLUS MINUS\s*$', model, re.M) and
            'Metal5 - insulator - TopMetal1 capacitor' in lvs_doc and 'C0 PLUS MINUS cap_cmim' in lvs_doc,
            'Public physical/model/symbol order differs.')
    return dict(archive_sha256=ARCHIVE_SHA, selected_member_prefix=prefix, files=evidence, raw_native=native,
                captured_reference=original, top=['c0', 'PLUS', 'C1', 'TopMetal1'],
                lower=['c1', 'MINUS', 'C2', 'Metal5'],
                model_comment_conflict='The pinned model comment names Metal3; the selected actual layout and ordered extractor establish TopMetal1.')


def measurement(directory, spec, driven='lower'):
    bias, temperature, frequency, width, length = spec
    grounded = 'upper' if driven == 'lower' else 'lower'
    for name in ('op.raw', 'ac.raw', 'engine.log', 'input.cir'):
        confined(directory, name)
    log = (directory/'engine.log').read_text(encoding='utf-8')
    found = re.findall(r'Doing analysis at TEMP\s*=\s*([-0-9.]+) and TNOM\s*=\s*([-0-9.]+)', log)
    require(len(found) == 2 and all(float(t) == temperature and float(n) == 27 for t, n in found),
            'Native analysis temperature differs.')
    require(not re.search(r'^\s*(?:error|fatal)(?:\s|:)', log, re.I | re.M), 'Native ngspice error.')

    def raw(name, plot):
        path = directory/name
        header, separator, values = path.read_bytes().partition(b'Values:')
        require(separator and header.splitlines().count(b'Plotname: '+plot) == 1, 'Native raw plot kind differs.')
        lines = [line.split() for line in values.splitlines() if line.strip()]
        require(len(lines) == 4 and len(lines[0]) == 2 and lines[0][0] == b'0' and
                all(len(line) == 1 for line in lines[1:]), 'Native raw row shape differs.')
        return parse_raw(path)

    op_vars, op_rows, op_complex = raw('op.raw', b'Operating Point')
    ac_vars, ac_rows, ac_complex = raw('ac.raw', b'AC Analysis')
    require(len(op_rows) == len(ac_rows) == 1 and not op_complex and ac_complex, 'Expected one OP and one complex AC sample.')
    nodes = ['v(upper)', 'v(lower)', 'i(vdrive)']
    require(op_vars[1:] == nodes and op_vars[0] in nodes[:2] and ac_vars == ['frequency', *nodes], 'Native probe set differs.')
    op = dict(zip(nodes, op_rows[0][1:]))
    ac = dict(zip(ac_vars, ac_rows[0]))
    require(op_rows[0][0] == op[op_vars[0]], 'Native OP scale/duplicate differs.')
    require(all(math.isfinite(v) for v in op.values()) and all(math.isfinite(abs(ac[v])) for v in nodes), 'Nonfinite terminal/current evidence.')
    # The AC scale is a real frequency, even in a complex raw plot.
    require(ac['frequency'].real == frequency, 'Native AC frequency differs.')
    drive, ground = 'v('+driven+')', 'v('+grounded+')'
    require(op[ground] == 0 and op[drive] == bias and ac[ground] == 0 and ac[drive] == 1,
            'Native driven/grounded physical electrode differs.')
    require(op['i(vdrive)'] == 0, 'Unexpected nominal-model DC branch current.')
    admittance = -ac['i(vdrive)']/ac[drive]
    require(admittance.real >= 0 and admittance.imag > 0, 'Native current sign/passivity differs.')
    # Validate the complete deck, independently of the producer's renderer.
    statements = (directory/'input.cir').read_text(encoding='ascii').split('\n')
    require(len(statements) >= 6, 'Incomplete stimulus deck.')
    title, library, ambient, stimulus, reference, device, *analysis = statements
    require(library == '.lib ../models/cornerCAP.lib cap_typ', 'Selected immutable model section differs.')
    require(device == f'Xdut upper lower cap_cmim w={width}u l={length}u m=1 mm_ok=1', 'Ordered DUT or geometry differs.')
    require(title == 'IHP cap_cmim process-control comparison' and ambient == f'.temp {temperature}' and
            stimulus == f'Vdrive {driven} 0 DC {bias} AC 1' and reference == f'Vground {grounded} 0 DC 0 AC 0',
            'Retained source stimulus differs.')
    require(analysis == [
        '.control', 'set filetype=ascii', 'set numdgt=17', 'op',
        'write op.raw v(upper) v(lower) i(vdrive)', f'ac lin 1 {frequency} {frequency}',
        'write ac.raw v(upper) v(lower) i(vdrive)', 'quit', '.endc', '.end', '',
    ], 'Unexpected stimulus deck statement or control sequence.')
    omega = 2*math.pi*frequency
    return dict(bias_v=bias, temperature_c=temperature, temperature_k=temperature+273.15,
                frequency_hz=frequency, w_um=width, l_um=length,
                driven_electrode=driven, grounded_electrode=grounded,
                op=op, ac={key: [ac[key].real, ac[key].imag] for key in sorted(nodes)},
                capacitance_f=admittance.imag/omega, conductance_s=admittance.real,
                series_equivalent_capacitance_f=-1/(omega*(1/admittance).imag),
                files={name: sha(directory/name) for name in ('op.raw','ac.raw','engine.log','input.cir')})


def comparison(rows, targets):
    voltage_zero = rows['voltage-2']['capacitance_f']
    temperature_zero = rows['temperature-2']['capacitance_f']
    groups = {'voltage': ('VCMIM1', 'VCMIM2'), 'temperature': ('TCMIM1', 'TCMIM2')}
    results = {}
    for prefix, keys in groups.items():
        values = []
        for name, row in rows.items():
            if not name.startswith(prefix+'-'):
                continue
            delta = row['bias_v'] if prefix == 'voltage' else row['temperature_c']-26.85
            baseline = voltage_zero if prefix == 'voltage' else temperature_zero
            target = 1+1e-6*(targets[keys[0]]['target']*delta+targets[keys[1]]['target']*delta**2)
            ratio = row['capacitance_f']/baseline
            values.append(dict(case=name, delta=delta, target_ratio=target, model_ratio=ratio,
                               model_minus_target_ppm=1e6*(ratio-target)))
        results[prefix] = dict(comparison='target_only_no_acceptance_tolerance', values=values)
    results['temperature']['source_reference_c'] = 26.85
    results['temperature']['pinned_model_tnom_c'] = 27
    normalized = []
    for name, row in rows.items():
        if name.startswith('geometry-'):
            w, l, c = row['w_um'], row['l_um'], row['capacitance_f']
            normalized.append(dict(case=name, area_um2=w*l, perimeter_um=2*(w+l), capacitance_f=c,
                                   direct_fF_per_um2=c*1e15/(w*l), direct_aF_per_um=c*1e18/(2*(w+l))))
    first, second, third = normalized
    a1, p1, c1 = (first[k] for k in ('area_um2','perimeter_um','capacitance_f'))
    a2, p2, c2 = (second[k] for k in ('area_um2','perimeter_um','capacitance_f'))
    determinant = a1*p2-a2*p1
    area, edge = (c1*p2-c2*p1)/determinant, (a1*c2-a2*c1)/determinant
    results['area_perimeter'] = dict(temperature_c=27, temperature_basis='analyst selected model TNOM; source unspecified',
        source_monitor_geometry_or_deembedding_supplied=False, direct_normalizations=normalized,
        normalization_scope='Total-device C/A and C/P include both contributions and do not calibrate either process coefficient.',
        model_only_fit=dict(area_fF_per_um2=area*1e15, perimeter_aF_per_um=edge*1e18,
            third_geometry_residual_f=third['capacitance_f']-area*third['area_um2']-edge*third['perimeter_um']))
    return results


def verify(root, evidence, physical_archive):
    sources = source_contract(root)
    plates = plate_evidence(root, physical_archive)
    models = {name: sha(confined(evidence, f'models/{name}')) for name in MODEL_NAMES}
    require(all(models[name] == sources['files'][f'{PDK}/{MODEL}/{name}'] for name in models), 'Staged nominal model bytes differ.')
    rows = {name: measurement(evidence/name, spec) for name, spec in CASES.items()}
    controls = {}
    for name, (spec, drive, expected) in CONTROLS.items():
        actual = measurement(evidence/name, spec, drive)
        try:
            measurement(evidence/name, CASES['voltage-4'])
        except ValueError as error:
            require(expected in str(error), 'Wrong control failure: '+str(error))
            controls[name] = dict(reason=str(error), observed=actual)
        else:
            raise ValueError('Undetected measurement fault: '+name)
    require(controls['wrong-geometry']['observed']['capacitance_f'] > rows['voltage-4']['capacitance_f'],
            'Wider-device native capacitance control differs.')
    invocation = load(confined(evidence, 'invocation.json'))
    engine, binary = invocation['engine'], invocation['binary']
    runtime = invocation['runtime_before']
    require(invocation['argv'] == [engine, *COMMAND] and invocation['runtime_after'] == runtime and
            engine in runtime and binary in runtime and len(runtime) >= 3 and
            all(re.fullmatch(r'[0-9a-f]{64}', value) for value in runtime.values()) and
            (engine == binary or (engine, binary, runtime[engine]) ==
             ('/opt/icstudio/bin/ngspice', '/usr/bin/ngspice', MANAGED_WRAPPER_SHA)), 'Runtime invocation identity differs.')
    require(set(invocation['returncodes']) == set(CASES)|set(CONTROLS) and
            all(type(code) is int and code == 0 for code in invocation['returncodes'].values()), 'Incomplete native cases.')
    for name, key in (('runtime-version.log','version_sha256'), ('runtime-ldd.log','linkage_sha256')):
        require(sha(confined(evidence, name)) == invocation[key], 'Runtime diagnostic bytes differ: '+name)
    return dict(status='PROCESS_CONTROL_COMPARISON_REPLAYED', qualified=False, installed_acceptance=False,
                full_family=False, safe_operating_limits_established=False, nominal_section='cap_typ',
                observable='Parallel capacitance Im(-I(Vdrive)/V(lower))/(2*pi*f); AC drive is 1 V phasor for small-signal linearization.',
                source=sources, plate_mapping=plates, staged_models=models, native_rows=rows, controls=controls,
                invocation_sha256=sha(evidence/'invocation.json'), runtime_sha256=runtime,
                source_code={name: sha(confined(root, name)) for name in SOURCE_MODULES},
                comparison=comparison(rows, sources['targets']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--physical-archive', type=Path, required=True)
    args = parser.parse_args()
    result = verify(safe(ROOT), safe(args.evidence), args.physical_archive)
    require(load(confined(args.evidence, 'comparison.json')) == result, 'Retained comparison does not match raw replay.')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
