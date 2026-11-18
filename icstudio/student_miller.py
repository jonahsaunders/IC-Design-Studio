"""Two-stage teaching model for the Miller capacitor and its nulling resistor."""

import math

from .student_ahuja import C1, CC, FREQUENCIES, GM2, R1, R2, loop_readout, miller_loop

NULL_OHM = 1 / GM2
LABELS = ('Uncompensated', 'Capacitor only', 'Series RC')


def zero(cc, resistor):
    """Return the finite zero's half plane and frequency magnitude, if any."""
    if cc == 0:
        return 'No branch', None
    distance = NULL_OHM - resistor
    if distance == 0:
        return 'At infinity', None
    return ('Right half plane' if distance > 0 else 'Left half plane',
            1 / (2*math.pi*cc*abs(distance)))


def response(frequency, load_pf, cc, resistor):
    s = 2j * math.pi * frequency
    y1 = 1/R1 + s*C1
    y2 = 1/R2 + s*load_pf*1e-12
    bridge = s*cc / (1 + s*resistor*cc)
    return miller_loop(y1, y2, bridge)


def study(load_pf=20, cc_pf=CC*1e12, resistor=NULL_OHM):
    if not 1 <= load_pf <= 100 or not .5 <= cc_pf <= 10 or not 0 <= resistor <= 8_000:
        raise ValueError('Use a 1–100 pF load, 0.5–10 pF compensation capacitor, and 0–8 kΩ series resistor.')
    cc = cc_pf * 1e-12
    cases = ((0, 0), (cc, 0), (cc, resistor))
    return list(FREQUENCIES), {
        name: dict(loop_readout([response(f, load_pf, cap, ohms) for f in FREQUENCIES]),
                   zero=zero(cap, ohms))
        for name, (cap, ohms) in zip(LABELS, cases, strict=True)
    }


def equivalent_input_capacitance(cc_pf):
    """Low-frequency Miller approximation for the compensation branch alone."""
    return cc_pf * (1 + GM2*R2)
