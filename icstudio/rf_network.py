"""Small-signal multiport network characterization using ngspice's .sp solver."""

import cmath
import math
import re
from pathlib import Path

from . import interchange, native_analysis
from .engines import execute, ngspice_command, parse_raw
from .model import NET, atomic_write, clone, design_digest, digest, file_digest, now, scalar
from .spice_program import find_ngspice, runtime_environment


def port_lines(text):
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) not in (2, 3):
            raise ValueError('Enter signal net, return net and optional DC voltage on each port line.')
        signal, reference = fields[:2]
        rows.append([signal, reference, scalar(fields[2]) if len(fields) == 3 else 0.0])
    return rows


def validate_settings(project, cell_id, settings):
    cell = next((c for c in project['cells'] if c['id'] == cell_id), None)
    if cell is None:
        raise ValueError('Select a fixture schematic before running the RF analysis.')
    ports = settings['ports']
    if not isinstance(ports, list) or not 1 <= len(ports) <= 8:
        raise ValueError('Define one to eight RF ports in the order they should appear in the result.')
    from .native_vectors import devices
    nets = {'0', *(net.casefold() for d in devices(cell, project) for net in d['nets'].values())}
    used = set()
    for signal, reference, dc in ports:
        pair = {signal.casefold(), reference.casefold()}
        if not all(NET.fullmatch(name) for name in (signal, reference)) or not pair <= nets or len(pair) != 2:
            raise ValueError(f'Port {signal} / {reference} needs two distinct nets in the fixture.')
        if frozenset(pair) in used or not math.isfinite(dc):
            raise ValueError('Use distinct terminal pairs and finite port bias voltages.')
        used.add(frozenset(pair))
    start, stop, impedance = (scalar(settings[field]) for field in ('start', 'stop', 'impedance'))
    if not 0 < start < stop or not 0 < impedance <= 1e9:
        raise ValueError('Choose increasing positive frequencies and a positive reference impedance.')
    if type(settings['points']) is not int or not 2 <= settings['points'] <= 5000:
        raise ValueError('Use 2–5,000 frequency points.')
    if scalar(settings['temperature']) <= -273.15:
        raise ValueError('Temperature must exceed absolute zero.')


def prepare(project, cell_id, settings, configured=''):
    settings = {**settings, 'type': 'rf_network'}
    validate_settings(project, cell_id, settings)
    return ngspice_job(project, cell_id, settings, configured)


def ngspice_job(project, cell_id, settings, configured):
    executable = find_ngspice(configured)
    if not executable:
        raise ValueError('Configure ngspice in Analysis → Engine setup to run this analysis.')
    from .osdi import verified
    verified(project)
    job = dict(project=clone(project), cell=cell_id, engine='ngspice',
               executable=str(Path(executable).resolve()), settings=settings)
    from .run_environment import stamp
    job['environment'] = stamp(job)
    return job


def fixture_text(project, cell_id, settings, directory):
    from .native_spice import native
    analysis = {'type': 'op', 'temperature': settings['temperature'], 'corner': settings['corner']}
    if native(project):
        text, _ = native_analysis.deck(project, cell_id, analysis, directory)
    else:
        text = interchange.spice(project, cell_id, analysis, hierarchical=False)
    return native_analysis.circuit_text(text) + f'.temp {scalar(settings["temperature"]):.16g}\n'


def deck(project, cell_id, settings, directory):
    text = fixture_text(project, cell_id, settings, directory)
    if re.search(r'^\s*v\S+\s+[^\n]*\bportnum\b', text, re.I | re.M):
        raise ValueError('Remove existing SPICE RF port declarations from the fixture before defining ports here.')
    if re.search(r'^\s*v__icstudio_rf\d+\s', text, re.I | re.M):
        raise ValueError('Rename fixture sources beginning with v__icstudio_rf followed by a number.')
    z0 = scalar(settings['impedance'])
    lines = [f'V__icstudio_rf{i} {signal} {reference} DC {dc:.16g} AC 1 portnum {i} z0 {z0:.16g}'
             for i, (signal, reference, dc) in enumerate(settings['ports'], 1)]
    if len(lines) == 1:
        # ngspice .sp needs two ports. An isolated matched termination provides
        # the second port and leaves the device under test's S11 unchanged.
        if re.search(r'\b__icstudio_rf_term\b|^\s*r__icstudio_rf_term\s', text, re.I | re.M):
            raise ValueError('Rename the fixture net or resistor reserved for the isolated RF termination.')
        lines.extend((f'V__icstudio_rf2 __icstudio_rf_term 0 DC 0 AC 1 portnum 2 z0 {z0:.16g}',
                      f'R__icstudio_rf_term __icstudio_rf_term 0 {z0:.16g}'))
    lines.extend((f'.sp lin {settings["points"]} {scalar(settings["start"]):.16g} {scalar(settings["stop"]):.16g}',
                  '.end'))
    return text + '\n'.join(lines) + '\n'


def parameter_names(size):
    return [f'S{i}{j}' for i in range(1, size + 1) for j in range(1, size + 1)]


def inverse(matrix):
    """Invert a small complex matrix, rejecting unresolved pivots."""
    size = len(matrix)
    scale = max(abs(value) for row in matrix for value in row)
    rows = [list(row) + [complex(i == j) for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        level = rows[pivot][column]
        if abs(level) <= 1e-10 * max(1, scale):
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        normal = [value/level for value in rows[column]]
        rows[column] = normal
        for index, row in enumerate(rows):
            if index != column:
                factor = row[column]
                rows[index] = [value-factor*unit for value, unit in zip(row, normal)]
    return [row[size:] for row in rows]


def converted_parameters(scattering, size, impedance, family):
    # For a common real reference impedance, Z = Z0 (I+S)(I-S)^-1
    # and Y = (I-S)(I+S)^-1 / Z0. A floating network can have singular Z.
    sign, factor = (1, impedance) if family == 'Z' else (-1, 1/impedance)
    names = parameter_names(size)
    result = {family+name[1:]: [] for name in names}
    for samples in zip(*(scattering[name] for name in names)):
        numerator = [[(i == j)+sign*samples[i*size+j] for j in range(size)] for i in range(size)]
        denominator = [[(i == j)-sign*samples[i*size+j] for j in range(size)] for i in range(size)]
        back = inverse(denominator)
        if back is None:
            return {}
        for i, row in enumerate(numerator):
            for j in range(size):
                value = factor*sum(coefficient*vector[j] for coefficient, vector in zip(row, back))
                if not math.isfinite(abs(value)):
                    return {}
                result[f'{family}{i+1}{j+1}'].append(value)
    return result


def run_fixture(job, directory, text, stem):
    from .ngspice_compat import prepare as prepare_compatibility
    from .osdi import preload
    from .pdks import stage_model_deck
    project, executable = job['project'], job['executable']
    source, raw = directory/(stem+'-input.cir'), directory/(stem+'.raw')
    text = stage_model_deck(project['pdk'], text, directory)
    atomic_write(source, prepare_compatibility(preload(project, text, directory), executable, directory))
    try:
        log = execute(ngspice_command(project, executable, raw, source), directory,
                      env=runtime_environment(executable))
    except Exception as exc:
        atomic_write(directory/'engine.log', str(exc))
        raise
    atomic_write(directory/'engine.log', log)
    if not raw.is_file():
        raise ValueError('ngspice produced no raw data. See the run log and verify solver support.')
    return source, raw, log


def run(job, directory, progress):
    project, cell, settings, executable = (job[k] for k in ('project', 'cell', 'settings', 'executable'))
    validate_settings(project, cell, settings)
    directory = Path(directory).resolve()
    progress(.1, 'Running the ngspice scattering-parameter analysis')
    source, raw, log = run_fixture(job, directory, deck(project, cell, settings, directory), 'rf')
    variables, rows, complex_data = parse_raw(raw)
    variables = [v.casefold() for v in variables]
    names = parameter_names(len(settings['ports']))
    columns = [f's_{name[1]}_{name[2]}' for name in names]
    if not complex_data or not variables or variables[0] != 'frequency' or any(v not in variables for v in columns):
        raise ValueError('ngspice did not return the requested full complex scattering matrix.')
    frequencies = [row[0].real for row in rows]
    if (len(frequencies) != settings['points'] or
            not math.isclose(frequencies[0], scalar(settings['start']), rel_tol=1e-9) or
            not math.isclose(frequencies[-1], scalar(settings['stop']), rel_tol=1e-9) or
            any(not math.isfinite(f) or f <= 0 for f in frequencies) or
            any(a >= b for a, b in zip(frequencies, frequencies[1:]))):
        raise ValueError('The RF sweep did not return the requested frequency grid.')
    indices = [variables.index(column) for column in columns]
    values = {name: [row[index] for row in rows] for name, index in zip(names, indices)}
    if any(not math.isfinite(abs(value)) for trace in values.values() for value in trace):
        raise ValueError('The RF result contains non-finite scattering parameters.')
    matrices = {'S': values}
    for family in ('Y', 'Z'):
        converted = converted_parameters(values, len(settings['ports']), scalar(settings['impedance']), family)
        if converted:
            matrices[family] = converted
    result = dict(schema=1, created=now(), engine='ngspice · RF network', engine_hash=file_digest(executable),
                  project_id=project['id'], revision=project['revision'], design_hash=design_digest(project),
                  pdk_hash=digest(project['pdk']), rule_hash=digest(project['pdk']['layers']), cell_id=cell,
                  settings=settings, x=frequencies, x_label='Frequency (Hz)', plot_unit='|S|',
                  traces={name: [abs(v) for v in trace] for name, trace in values.items()},
                  phase={name: [math.degrees(cmath.phase(v)) for v in trace] for name, trace in values.items()},
                  rf_network={'matrices': {family: {name: [[v.real, v.imag] for v in trace] for name, trace in matrix.items()}
                                           for family, matrix in matrices.items()},
                              'deck_sha256': file_digest(source), 'raw_sha256': file_digest(raw)},
                  warnings=[], log=log)
    progress(1, 'RF network analysis completed')
    return result


def touchstone(result):
    settings = result['settings']
    size = len(settings['ports'])
    data = result['rf_network']['matrices']['S']
    names = parameter_names(size)
    lines = [f'# Hz S RI R {scalar(settings["impedance"]):.16g}']
    if size == 2:
        groups = [('S11', 'S21', 'S12', 'S22')]
    else:
        groups = [names[row * size + start:row * size + min(size, start + 4)]
                  for row in range(size) for start in range(0, size, 4)]
    for index, frequency in enumerate(result['x']):
        for group_index, group in enumerate(groups):
            pairs = ' '.join(f'{part:.16g}' for name in group for part in data[name][index])
            lines.append((f'{frequency:.16g} ' if group_index == 0 else '  ') + pairs)
    return '\n'.join(lines) + '\n'
