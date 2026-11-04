"""Independent finite CMIM multiplicity electrical replay; no model calibration."""
import argparse
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.engines import parse_raw
from scripts.verify_frozen_ihp_cmim import confined, load, require, safe, sha
from scripts.check_ihp_cmim_process_control import (
    MANAGED_WRAPPER_SHA, MODEL, MODEL_NAMES, PDK, source_contract,
)

SECTIONS = {'cap_typ': 1.0, 'cap_bcs': 0.9, 'cap_wcs': 1.1}
ROUTES = ('catalog', 'pair', 'extracted', 'literal', 'count1', 'count3', 'areaonly', 'series', 'wrongr')
POSITIVES = ROUTES[:4]
CONTROLS = ROUTES[4:]
CODE = ('scripts/qualify_ihp_cmim_multiplicity_electrical.py',
        'scripts/check_ihp_cmim_multiplicity_electrical.py', 'icstudio/engines.py',
        'scripts/check_ihp_cmim_process_control.py', 'scripts/verify_frozen_ihp_cmim.py',
        'scripts/verify_frozen_ihp_resistors.py', 'scripts/verify_frozen_mim.py',
        'scripts/check_ihp_cmim_multiplicity.py', 'scripts/check_ihp_cmim_enclosures.py')


def constants(section):
    # Exact pinned deterministic model: the corner multiplies area, not perimeter.
    value = Decimal(49) * Decimal('1.5e-15') * Decimal(str(SECTIONS[section])) + Decimal(28) * Decimal('40e-18')
    return float(value), 0.055


def frequencies(section):
    cap, resistance = constants(section)
    # This third point is dimensionless numerical sensitivity, NOT a physical band.
    return (100_000.0, 1_000_000.0, float(format(1 / (2 * math.pi * resistance * cap), '.17g')))


def relative_error(actual, expected):
    """Deterministic report arithmetic across differing host hypot libraries.

    Preserve the actual binary components, calculate their magnitudes with
    decimal guard digits, then round once to the serialized binary float.
    """
    require(all(math.isfinite(value) for value in (actual.real, actual.imag, expected.real, expected.imag))
            and expected != 0, 'Nonfinite or zero error-reference component.')
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        def norm(value):
            real, imag = Decimal.from_float(value.real), Decimal.from_float(value.imag)
            return (real * real + imag * imag).sqrt()
        return float(norm(actual - expected) / norm(expected))


def device_lines(text, *, physical=False):
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(lines) >= 3 and lines[0].lower() in ('.subckt coupon c1 c2', '.subckt coupon c2 c1')
            and lines[-1].lower() == '.ends coupon', 'Unexpected captured circuit boundary.')
    records = []
    for line in lines[1:-1]:
        fields = line.split()
        require(len(fields) >= 5 and fields[0][0].upper() == ('C' if physical else 'X') and
                fields[1:4] == ['C1', 'C2', 'cap_cmim'], 'Unexpected captured capacitor topology.')
        values = {}
        for field in fields[4:]:
            require(field.count('=') == 1, 'Malformed captured device parameter.')
            key, value = field.split('=')
            require(key.lower() not in values, 'Duplicate captured device parameter.')
            exponent = {'u': -6, 'p': -12}.get(value[-1:].lower(), 0)
            number = Decimal(value[:-1] if exponent else value)
            require(number.is_finite(), 'Nonfinite captured device parameter.')
            parts = number.as_tuple()
            number = Decimal((parts.sign, parts.digits, parts.exponent + exponent))
            values[key.lower()] = number
        require(set(values) == ({'w', 'l', 'a', 'p', 'm'} if physical else {'w', 'l', 'm', 'mm_ok'}) and
                values['w'] == values['l'] == Decimal('7e-6'), 'Unexpected captured unit geometry.')
        if physical:
            require(values['a'] == Decimal('49e-12') and values['p'] == Decimal('28e-6') and values['m'] == 1,
                    'Unexpected raw pre-reduction physical capacitor.')
        else:
            require(values['mm_ok'] == 1, 'Unexpected statistical selector.')
        records.append(dict(line=line, name=fields[0], values={key: str(value) for key, value in values.items()}))
    require(len({row['name'].lower() for row in records}) == len(records), 'Duplicate captured device name.')
    return records


def linked_inputs(evidence):
    """Audit copied actual simulation references and unfiltered physical records.

    The separate full physical reader establishes their DRC/LVS acceptance.
    This reader never substitutes a reported merged device for the raw two units.
    """
    result = {}
    for rotation in (0, 90):
        row = {}
        for kind in ('m2', 'pair', 'native'):
            name = f'inputs/{kind}-{rotation}.spice'
            path = confined(evidence, name)
            records = device_lines(path.read_text(encoding='utf-8'), physical=kind == 'native')
            require(len(records) == (1 if kind == 'm2' else 2), 'Captured unit count differs.')
            require(all(Decimal(r['values']['m']) == (2 if kind == 'm2' else 1) for r in records),
                    'Captured multiplicity differs.')
            row[kind] = dict(sha256=sha(path), records=records)
        result[str(rotation)] = row
    receipt = load(confined(evidence, 'physical-inputs.json'))
    require(receipt['inputs'] == result and receipt['scope'] == 'audited full physical multiplicity output',
            'Physical input copy receipt differs.')
    require(re.fullmatch('[0-9a-f]{64}', receipt['physical_reader_report_sha256']) is not None,
            'Missing independently replayed physical report identity.')
    require(sha(confined(evidence, 'physical-reader-report.json')) == receipt['physical_reader_report_sha256'],
            'Physical reader report bytes changed.')
    report = load(confined(evidence, 'physical-reader-report.json'))
    names = ['m2-0', 'pair-0', 'm2-90', 'pair-90', 'm1-0', 'm3-0', 'wrong-wire-0',
             'missing-contact-0', 'wrong-width-0', 'physical-width-0']
    require(report['status'] == 'PASS_FINITE_MULTIPLICITY_READBACK' and
            [row['name'] for row in report['cases']] == names and
            all(row['raw_units'] == 2 and row['strict_lvs'] == ('passed' if row['name'] in names[:4] else 'failed')
                for row in report['cases']) and report['qualified'] is False and report['installed_acceptance'] is False,
            'Physical reader report selection or outcomes differ.')
    expected_sources = {}
    cases = {row['name']: row for row in report['cases']}
    for rotation, row in result.items():
        for kind, entry in row.items():
            case = f'{"m2" if kind == "native" else kind}-{rotation}'
            relative = f'{case}/job/physical-flow/' + (
                'lvs-extraction/native.cir' if kind == 'native' else 'schematic.spice')
            expected_sources[relative] = entry['sha256']
            require(cases[case]['native_sha256' if kind == 'native' else 'schematic_sha256'] == entry['sha256'],
                    'Copied electrical input differs from the independently accepted physical record.')
    require(receipt['original_input_hashes'] == expected_sources, 'Captured physical source/copy binding differs.')
    return result


def expected_devices(route, inputs, section):
    cap, resistance = constants(section)
    if route in ('catalog', 'pair'):
        return [r['line'] for r in inputs['m2' if route == 'catalog' else 'pair']['records']]
    if route == 'extracted':
        return [f'Xraw{i} C1 C2 cap_cmim w={r["values"]["w"]} l={r["values"]["l"]} m={r["values"]["m"]} mm_ok=1'
                for i, r in enumerate(inputs['native']['records'])]
    if route in ('literal', 'wrongr'):
        r = resistance if route == 'literal' else 2 * resistance
        return [f'R{i} C1 mid{i} {r:.17g}\nC{i} mid{i} C2 {cap:.17g}' for i in (1, 2)]
    if route in ('count1', 'count3'):
        return [f'Xfault C1 C2 cap_cmim w=7u l=7u m={route[-1]} mm_ok=1']
    if route == 'areaonly':
        return ['Xfault C1 C2 cap_cmim w=7u l=14u m=1 mm_ok=1']
    require(route == 'series', 'Unknown electrical route.')
    return ['Xfault1 C1 junction cap_cmim w=7u l=7u m=1 mm_ok=1',
            'Xfault2 junction C2 cap_cmim w=7u l=7u m=1 mm_ok=1', 'Rbias junction C2 1e12']


def measurement(folder, inputs, section):
    deck = confined(folder, 'input.cir').read_text(encoding='ascii').splitlines()
    required = ['CMIM multiplicity integration', f'.lib ../models/cornerCAP.lib {section}', '.temp 27']
    for route in ROUTES:
        required += [f'.subckt {route} C1 C2']
        required += '\n'.join(expected_devices(route, inputs, section)).splitlines()
        required += [f'.ends {route}', f'V{route} {route} 0 DC 0 AC 1', f'X{route} {route} 0 {route}']
    probes = ' '.join(f'v({name}) i(v{name})' for name in ROUTES)
    required += ['.control', 'set filetype=ascii', 'set numdgt=17']
    for i, frequency in enumerate(frequencies(section)):
        required += [f'ac lin 1 {frequency:.17g} {frequency:.17g}', f'write ac-{i}.raw {probes}']
    required += ['quit', '.endc', '.end']
    require(deck == required, 'Native deck, model selection, topology or analysis changed.')
    log = confined(folder, 'engine.log').read_text(encoding='utf-8')
    temps = re.findall(r'Doing analysis at TEMP\s*=\s*([-0-9.]+) and TNOM\s*=\s*([-0-9.]+)', log)
    require(temps == [('27.000000', '27.000000')] * 3 and
            not re.search(r'^\s*(?:error|fatal|warning)(?:\s|:)', log, re.I | re.M), 'Native analysis failed or temperature differs.')
    cap, resistance = constants(section)
    rows = []
    for i, frequency in enumerate(frequencies(section)):
        path = confined(folder, f'ac-{i}.raw')
        header, sep, values = path.read_bytes().partition(b'Values:')
        require(sep and header.splitlines().count(b'Plotname: AC Analysis') == 1, 'Wrong raw plot type.')
        raw_lines = [line.split() for line in values.splitlines() if line.strip()]
        require(len(raw_lines) == 1 + 2 * len(ROUTES) and raw_lines[0][0] == b'0' and
                len(raw_lines[0]) == 2 and all(len(line) == 1 for line in raw_lines[1:]), 'Wrong raw sample shape.')
        variables, samples, is_complex = parse_raw(path)
        expected_vars = ['frequency'] + [v for name in ROUTES for v in (f'v({name})', f'i(v{name})')]
        require(is_complex and len(samples) == 1 and variables == expected_vars, 'Wrong native electrical probe set.')
        sample = dict(zip(variables, samples[0]))
        require(math.isclose(sample['frequency'].real, frequency, rel_tol=1e-14), 'Wrong native frequency.')
        wanted = 2 / complex(resistance, -1 / (2 * math.pi * frequency * cap))
        omega = 2 * math.pi * frequency
        area_cap = 98 * 1.5e-15 * SECTIONS[section] + 42 * 40e-18
        fault_expected = {
            'count1': 1 / complex(resistance, -1 / (omega * cap)),
            'count3': 3 / complex(resistance, -1 / (omega * cap)),
            'areaonly': 1 / complex(resistance, -1 / (omega * area_cap)),
            'series': 1 / (complex(resistance, -1 / (omega * cap)) +
                           1 / (1 / complex(resistance, -1 / (omega * cap)) + 1e-12)),
            'wrongr': 2 / complex(2 * resistance, -1 / (omega * cap)),
        }
        observed, errors = {}, {}
        for route in ROUTES:
            voltage, current = sample[f'v({route})'], sample[f'i(v{route})']
            require(voltage == 1 and math.isfinite(abs(current)), 'Wrong stimulus or nonfinite current.')
            admittance = -current / voltage
            require(admittance.real >= 0 and admittance.imag > 0, 'Nonpassive electrical result.')
            error = relative_error(admittance, wanted)
            if route in POSITIVES:
                require(error < 1e-8, 'Parallel electrical equivalence differs: ' + route)
                if i == 2:
                    require(abs((1 / admittance).real / (resistance / 2) - 1) < 1e-8,
                            'Parallel series resistance differs: ' + route)
            else:
                own = fault_expected[route]
                # At low frequency the source current subtracts conductance
                # terms of order 1/R. Bound only that real-component roundoff;
                # the reactive component and RC-sensitivity test remain tight.
                accurate = (abs(admittance - own) / abs(own) < 1e-8 if i == 2 else
                            abs(admittance.imag / own.imag - 1) < 1e-8 and
                            abs(admittance.real - own.real) <= 8 * math.ulp(1 / resistance) + 1e-8 * abs(own.real))
                require(accurate,
                        'Fault output does not match the intended altered network: ' + route)
                # wrong-R is deliberately indistinguishable at low frequency.
                if route != 'wrongr' or i == 2:
                    require(error > 1e-4, 'Undetected actual electrical fault: ' + route)
            observed[route] = [admittance.real, admittance.imag]
            errors[route] = error
        rows.append(dict(frequency_hz=frequency, numerical_rc_sensitivity=i == 2,
                         expected_y_s=[wanted.real, wanted.imag], observed_y_s=observed, relative_errors=errors,
                         fault_expected_y_s={key: [value.real, value.imag] for key, value in fault_expected.items()},
                         raw_sha256=sha(path)))
    return dict(rows=rows, input_sha256=sha(folder/'input.cir'), log_sha256=sha(folder/'engine.log'))


def verify(root, evidence):
    sources = source_contract(root)
    inputs = linked_inputs(evidence)
    models = {name: sha(confined(evidence, f'models/{name}')) for name in MODEL_NAMES}
    require(all(models[name] == sources['files'][f'{PDK}/{MODEL}/{name}'] for name in models), 'Staged model closure changed.')
    results = {f'{rotation}-{section}': measurement(confined(evidence, f'{rotation}-{section}'), inputs[str(rotation)], section)
               for rotation in (0, 90) for section in SECTIONS}
    call = load(confined(evidence, 'invocation.json'))
    engine, binary, runtime = call['engine'], call['binary'], call['runtime_before']
    require(call['runtime_after'] == runtime and engine in runtime and binary in runtime and len(runtime) >= 3 and
            all(re.fullmatch('[0-9a-f]{64}', value) for value in runtime.values()) and
            (engine == binary or (engine, binary, runtime[engine]) == ('/opt/icstudio/bin/ngspice', '/usr/bin/ngspice', MANAGED_WRAPPER_SHA)) and
            call['argv'] == [engine, '-n', '-b', 'input.cir'], 'Runtime closure or command changed.')
    require(set(call['returncodes']) == set(results) and all(type(v) is int and v == 0 for v in call['returncodes'].values()),
            'Missing or failed native execution.')
    for name, key in (('runtime-version.log', 'version_sha256'), ('runtime-ldd.log', 'linkage_sha256')):
        require(sha(confined(evidence, name)) == call[key], 'Runtime diagnostic changed.')
    code = {name: sha(confined(root, name)) for name in CODE}
    require(call['source_code'] == code, 'Electrical source changed since execution.')
    return dict(status='MULTIPLICITY_ELECTRICAL_REPLAYED', qualified=False, installed_acceptance=False,
                physical_model_calibrated=False, source=sources, source_code=code, inputs=inputs,
                models=models, results=results, invocation_sha256=sha(evidence/'invocation.json'),
                physical_reader_report_sha256=sha(evidence/'physical-reader-report.json'),
                scope='Two selected parallel 7 um units, two rotations, three deterministic capacitor sections at 27 C; '
                      '100 kHz/1 MHz plus numerical omega*R*C=1 sensitivity only. No PEX, statistical, nested-m, '
                      'physical frequency/operating envelope or installed acceptance.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = verify(safe(ROOT), safe(args.evidence))
    require(load(confined(args.evidence, 'comparison.json')) == result, 'Saved electrical comparison differs from replay.')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
