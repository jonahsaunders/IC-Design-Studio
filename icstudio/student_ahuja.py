"""Classroom small-signal return ratio for direct and buffered compensation."""

import cmath
import math

from .student_filters import gain_db

LABELS = ('Direct Miller', 'Ideal Ahuja', 'Finite buffer')
TARGET_PM = 60
GM1, GM2 = .15e-3, 1e-3
R1, R2, C1, CC = 500e3, 100e3, .2e-12, 2e-12
MILLER_ZERO_HZ = GM2 / (2 * math.pi * CC)
FREQUENCIES = tuple(10**(1 + 8*i/800) for i in range(801))


def miller_loop(y1, y2, bridge):
    """Positive DC return ratio with an admittance between the two stages."""
    return GM1*(GM2 - bridge) / (y1*y2 + bridge*(y1 + y2 + GM2))


def response(frequency, load_pf, buffer_mhz):
    """The positive DC return ratio T for unity negative feedback.

    The ideal Ahuja branch follows the two-node current-buffer equivalent.
    The finite-bandwidth exercise keeps the ideal AC-ground input and adds
    one pole to the copied feedback current. Device parasitics, supply
    coupling and nonlinear settling are outside this model.
    """
    s = 2j * math.pi * frequency
    cl = load_pf * 1e-12
    y2 = 1/R2 + s*cl
    y1 = 1/R1 + s*C1
    copy = 1 / (1 + s/(2*math.pi*buffer_mhz*1e6))
    cc = s*CC
    direct = miller_loop(y1, y2, cc)
    ideal = GM1*GM2 / (y1*(y2 + cc) + cc*GM2)
    finite = GM1*GM2 / (y1*(y2 + cc) + cc*GM2*copy)
    return direct, ideal, finite


def unwrap(values):
    phases = []
    for value in values:
        phase = math.degrees(cmath.phase(value))
        if phases:
            phase = phases[-1] + (phase - phases[-1] + 180) % 360 - 180
        phases.append(phase)
    return phases


def unity(xs, gains, phases):
    for i, (a, b) in enumerate(zip(gains, gains[1:])):
        if a >= 0 > b:
            weight = a/(a-b)
            frequency = xs[i] * (xs[i+1]/xs[i])**weight
            return frequency, 180 + phases[i] + weight*(phases[i+1] - phases[i])
    raise ValueError('The swept frequency range does not include a falling 0 dB crossing.')


def loop_readout(values):
    dbs = [gain_db(value) for value in values]
    phases = unwrap(values)
    freq, margin = unity(FREQUENCIES, dbs, phases)
    return dict(gain=dbs, phase=phases, unity_Hz=freq, phase_margin_deg=margin)


def study(load_pf, buffer_mhz):
    if not 1 <= load_pf <= 100 or not 5 <= buffer_mhz <= 500:
        raise ValueError('Choose a load of 1–100 pF and a buffer pole of 5–500 MHz.')
    responses = zip(*(response(freq, load_pf, buffer_mhz) for freq in FREQUENCIES))
    return list(FREQUENCIES), {name: loop_readout(values) for name, values in zip(LABELS, responses, strict=True)}
