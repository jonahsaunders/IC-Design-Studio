"""Three-port reference arithmetic with explicit terminal and return conventions.

This reader retains every S-parameter. It does not turn a common return into a
separately characterized substrate terminal or bind an application catalog model.
"""
import cmath
import math

MAX_SAMPLES = 10000
MAX_BYTES = 8_000_000


def touchstone3(text):
    """Read full, row-major Touchstone 1.x S3P with an explicit option line."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Three-port reference exceeds the input limit.')
    units = {'hz': 1., 'khz': 1e3, 'mhz': 1e6, 'ghz': 1e9}
    options = None
    tokens = []
    for raw in text.splitlines():
        line = raw.split('!', 1)[0].strip()
        if not line:
            continue
        if line.startswith('#'):
            words = line[1:].lower().split()
            if options is not None or tokens or len(words) != 5 or words[0] not in units or words[1] != 's' or words[2] not in ('ri', 'ma', 'db') or words[3] != 'r':
                raise ValueError('Use one explicit Touchstone 1.x S/RI, S/MA or S/DB option line.')
            try:
                reference = float(words[4])
            except ValueError as exc:
                raise ValueError('Invalid reference impedance.') from exc
            if not math.isfinite(reference) or reference <= 0:
                raise ValueError('Reference impedance must be finite and positive.')
            options = (units[words[0]], words[2], reference)
        else:
            if options is None or line.startswith('['):
                raise ValueError('An explicit Touchstone 1.x option line must precede all samples.')
            try:
                tokens.extend(float(value) for value in line.split())
            except ValueError as exc:
                raise ValueError('Three-port samples must be numeric.') from exc
    if not tokens or len(tokens) % 19 or len(tokens) // 19 > MAX_SAMPLES or not all(math.isfinite(x) for x in tokens):
        raise ValueError('Provide complete finite three-port samples.')
    scale, mode, reference = options
    frequency, scattering = [], []
    for offset in range(0, len(tokens), 19):
        row = tokens[offset:offset+19]
        f = row[0] * scale
        if not math.isfinite(f) or f <= 0 or frequency and f <= frequency[-1]:
            raise ValueError('Frequencies must be finite, positive and strictly increasing.')
        values = []
        for a, b in zip(row[1::2], row[2::2]):
            if mode == 'ma' and a < 0:
                raise ValueError('Touchstone magnitudes must be nonnegative.')
            try:
                value = complex(a, b) if mode == 'ri' else cmath.rect(10**(a/20) if mode == 'db' else a, math.radians(b))
            except (OverflowError, ValueError) as exc:
                raise ValueError('Invalid complex three-port sample.') from exc
            if not math.isfinite(value.real) or not math.isfinite(value.imag):
                raise ValueError('Nonfinite complex three-port sample.')
            values.append(value)
        # S3P uses row order S11,S12,S13,S21,..., unlike the S2P special case.
        scattering.append([values[0:3], values[3:6], values[6:9]])
        frequency.append(f)
    return dict(frequency_hz=frequency, reference_ohm=reference, scattering=scattering,
                ports=3, convention='V1.x full S3P, row-major, all ports to the same reference.')


def _inverse(matrix):
    n = len(matrix)
    if not n or any(len(row) != n for row in matrix):
        raise ValueError('Expected a square matrix.')
    data = [[complex(v) for v in row] + [complex(i == j) for j in range(n)] for i, row in enumerate(matrix)]
    scale = max(abs(v) for row in matrix for v in row)
    if not math.isfinite(scale) or not scale:
        raise ValueError('Singular or nonfinite reference conversion.')
    for column in range(n):
        pivot = max(range(column, n), key=lambda r: abs(data[r][column]))
        if abs(data[pivot][column]) <= scale * 1e-14:
            raise ValueError('Ill-conditioned reference conversion.')
        data[column], data[pivot] = data[pivot], data[column]
        factor = data[column][column]
        data[column] = [v/factor for v in data[column]]
        for row in range(n):
            if row != column:
                factor = data[row][column]
                data[row] = [v-factor*w for v, w in zip(data[row], data[column])]
    out = [row[n:] for row in data]
    if not all(math.isfinite(v.real) and math.isfinite(v.imag) for row in out for v in row):
        raise ValueError('Nonfinite reference conversion.')
    return out


def _multiply(a, b):
    return [[sum(x*y for x, y in zip(row, col)) for col in zip(*b)] for row in a]


def _validate_network(network):
    try:
        if not isinstance(network, dict) or type(network['ports']) is not int or network['ports'] != 3:
            raise ValueError('Expected a complete three-port network.')
        frequency, samples, reference = network['frequency_hz'], network['scattering'], network['reference_ohm']
        if not 0 < len(frequency) == len(samples) <= MAX_SAMPLES:
            raise ValueError('Every frequency requires exactly one three-port matrix.')
        if type(reference) not in (int, float) or not math.isfinite(reference) or reference <= 0:
            raise ValueError('Reference impedance must be finite and positive.')
        previous = 0
        for f, matrix in zip(frequency, samples):
            if type(f) not in (int, float) or not math.isfinite(f) or f <= previous:
                raise ValueError('Frequencies must be finite, positive and strictly increasing.')
            previous = f
            if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
                raise ValueError('Every frequency requires exactly nine complex entries.')
            if not all(type(v) in (int, float, complex) and math.isfinite(v.real) and math.isfinite(v.imag)
                       for row in matrix for v in row):
                raise ValueError('Three-port entries must be finite numbers.')
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('Malformed three-port network.') from exc


def matrices(network, kind):
    """Return all three-port Y or Z entries; reject singular conversions."""
    if kind not in ('y', 'z'):
        raise ValueError('Select three-port Y or Z.')
    _validate_network(network)
    reference = network['reference_ohm']
    out = []
    for s in network['scattering']:
        plus = [[complex(i == j)+s[i][j] for j in range(3)] for i in range(3)]
        minus = [[complex(i == j)-s[i][j] for j in range(3)] for i in range(3)]
        matrix = _multiply(minus, _inverse(plus)) if kind == 'y' else _multiply(plus, _inverse(minus))
        try:
            scaled = [[value/reference if kind == 'y' else value*reference for value in row] for row in matrix]
        except OverflowError as exc:
            raise ValueError('Nonfinite reference conversion.') from exc
        if not all(math.isfinite(value.real) and math.isfinite(value.imag) for row in scaled for value in row):
            raise ValueError('Nonfinite reference conversion.')
        out.append(scaled)
    return out


def center_tap_impedances(network, *, coil_ports, center_tap):
    """Use explicit 0-based port roles; distinguish floating and voltage-clamped CT.

    Differential-current quantities inject +1 A and -1 A at the two coil ends.
    The balanced-voltage quantity clamps them to +0.5 V and -0.5 V. These are
    distinct experiments for asymmetric networks.
    """
    if not isinstance(coil_ports, (tuple, list)) or len(coil_ports) != 2:
        raise ValueError('Specify both coil-end port indices.')
    roles = [*coil_ports, center_tap]
    if any(type(x) is not int for x in roles) or set(roles) != {0, 1, 2}:
        raise ValueError('Use each of the three port indices exactly once.')
    a, b, ct = roles
    ys, zs = matrices(network, 'y'), matrices(network, 'z')
    out = dict(frequency_hz=list(network['frequency_hz']), coil_ports=list(coil_ports), center_tap=center_tap,
               differential_current_ct_open=[], differential_current_ct_grounded=[],
               differential_voltage_ct_grounded=[], center_tap_ends_grounded=[],
               first_end_others_grounded=[], second_end_others_grounded=[])
    for y, z in zip(ys, zs):
        closed = _inverse([[y[a][a], y[a][b]], [y[b][a], y[b][b]]])
        try:
            values = dict(
                differential_current_ct_open=z[a][a]+z[b][b]-z[a][b]-z[b][a],
                differential_current_ct_grounded=closed[0][0]+closed[1][1]-closed[0][1]-closed[1][0],
                differential_voltage_ct_grounded=4/(y[a][a]+y[b][b]-y[a][b]-y[b][a]),
                center_tap_ends_grounded=1/y[ct][ct],
                first_end_others_grounded=1/y[a][a], second_end_others_grounded=1/y[b][b])
        except ZeroDivisionError as exc:
            raise ValueError('Singular terminated response.') from exc
        for key, value in values.items():
            if not math.isfinite(value.real) or not math.isfinite(value.imag):
                raise ValueError('Nonfinite terminated response.')
            out[key].append(value)
    return out

