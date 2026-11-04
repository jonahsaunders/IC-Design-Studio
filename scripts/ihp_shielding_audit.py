"""Audit native local-ground invariance under remote same-net connections.

The capture driver must independently verify identical masks within the halo.
This checks the complete three-stack, four-orientation diagnostic matrix; it
does not establish field calibration, waveform convergence or tapeout status.
"""
import math
import re

ABSOLUTE_LIMIT_AF = 1e-10
STATES = ('separate', 'upper-pair', 'all')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _matrix(record):
    result = {}
    for group in record['groups']:
        key = (group['lower_metal'], group['rotation_degrees'])
        _require(key not in result and group['upper_metal'] == key[0] + 2,
                 'Duplicate or invalid metal-stack control.')
        rows = {}
        for row in group['cases']:
            state = row['state']
            _require(state in STATES and state not in rows,
                     'Duplicate or unknown connectivity state.')
            _require(row['local_geometry_unchanged'] is True and
                     row['connected_regions'] == 3 - STATES.index(state),
                     'Local geometry or intended connectivity was not verified.')
            _require(re.fullmatch('[0-9a-f]{64}', row['gds_sha256']) is not None,
                     'A captured geometry digest is required.')
            terms = row['terms_af']
            _require(terms.keys() <= {'initial-edge', 'ground-side-halo', 'ground-blocked-fringe'}
                     and terms.get('initial-edge', 0) > 0 and
                     'ground-side-halo' in terms and
                     all(math.isfinite(v) for v in terms.values()),
                     'Missing or invalid native ground terms.')
            value = math.fsum(terms.values())
            _require(math.isfinite(row['local_fringe_ground_af']) and
                     abs(row['local_fringe_ground_af'] - value) <= ABSOLUTE_LIMIT_AF,
                     'Reported ground value differs from its signed native terms.')
            rows[state] = (value, row['gds_sha256'], terms['initial-edge'])
        _require(set(rows) == set(STATES), 'Incomplete connectivity control.')
        result[key] = rows
    _require(set(result) == {(metal, rotation) for metal in (1, 2, 3)
                            for rotation in (0, 90, 180, 270)},
             'Incomplete metal-stack/orientation coverage.')
    for metal in (1, 2, 3):
        for state in STATES:
            values = [result[metal, rotation][state][0] for rotation in (0, 90, 180, 270)]
            _require(max(values) - min(values) <= ABSOLUTE_LIMIT_AF,
                     'Rotation changes local substrate shielding.')
    return result


def compare(original, corrected):
    """Require detected original failures and invariant corrected native terms."""
    before, after = map(_matrix, (original, corrected))
    rows = []
    for key in sorted(before):
        a, b = before[key], after[key]
        _require(all(a[s][1:] == b[s][1:] for s in STATES),
                 'Correction changed geometry or initial native edge capacitance.')
        _require(abs(a['separate'][0] - b['separate'][0]) <= ABSOLUTE_LIMIT_AF,
                 'Correction changed the separate-net reference.')
        old_spread = max(v[0] for v in a.values()) - min(v[0] for v in a.values())
        new_spread = max(v[0] for v in b.values()) - min(v[0] for v in b.values())
        _require(old_spread > 1., 'The original same-net shielding defect was not exercised.')
        _require(new_spread <= ABSOLUTE_LIMIT_AF and all(v[0] > 0 for v in b.values()),
                 'Corrected local ground is negative or depends on remote connectivity.')
        rows.append(dict(lower_metal=key[0], rotation_degrees=key[1],
                         original_spread_af=old_spread, corrected_spread_af=new_spread))
    return dict(schema=1, status='same-net-shielding-regression-pass', qualified=False,
                native_captures=72, local_controls=12, absolute_limit_af=ABSOLUTE_LIMIT_AF,
                maximum_corrected_spread_af=max(r['corrected_spread_af'] for r in rows),
                controls=rows,
                scope='Local native substrate shielding only. Independent mask capture, '
                      'full graph identity, field calibration and timing remain required.')
