"""Supported saved-bench extraction choices, shared by jobs and the desktop."""
from .model import clone, scalar


EXTRACTION_MODES = {
    'capacitance': 'Process capacitance',
    'rc': 'Process distributed RC',
    'calibrated_rc': 'Calibrated interconnect RC',
}


def normalize_extraction(options=None):
    """Validate an explicit choice; never silently downgrade the requested model."""
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError('Choose a supported physical extraction configuration.')
    mode = options.get('mode', 'capacitance')
    if not isinstance(mode,str) or mode not in EXTRACTION_MODES:
        raise ValueError('Choose process capacitance, process RC or calibrated interconnect RC.')
    allowed = {'mode'} | ({'section_nm', 'coupling_distance_nm', 'corner'} if mode == 'calibrated_rc' else set())
    if set(options) - allowed:
        raise ValueError('Unsupported option for '+EXTRACTION_MODES[mode]+': '+', '.join(sorted(set(options)-allowed)))
    result = {'mode': mode}
    if mode == 'calibrated_rc':
        for key, default, low in (('section_nm', 5000, 100), ('coupling_distance_nm', 5000, 0)):
            value = scalar(options.get(key, default))
            if not low <= value <= 1000000 or int(value) != value:
                raise ValueError(key+': use integer nanometres between '+str(low)+' and 1000000.')
            result[key] = int(value)
        corner = options.get('corner')
        if corner is not None:
            if not isinstance(corner, str) or not corner.strip() or len(corner) > 100:
                raise ValueError('Choose a named RC calibration corner or omit it to follow the model corner.')
            result['corner'] = corner.strip()
    return clone(result)


def measurement_comparison(before, after):
    """Retain failed and missing measurements as well as numerical deltas."""
    left = {row['name']: row for row in before}
    right = {row['name']: row for row in after}
    result = []
    for name in dict.fromkeys([*left, *right]):
        a, b = left.get(name, {}), right.get(name, {})
        av, bv = a.get('value'), b.get('value')
        compatible = a.get('unit', '') == b.get('unit', '')
        delta = bv-av if compatible and av is not None and bv is not None else None
        result.append({'name': name, 'unit': a.get('unit', b.get('unit', '')),
                       'before': av, 'after': bv, 'delta': delta,
                       'relative_delta': delta/abs(av) if delta is not None and av else None,
                       'before_status': a.get('status', 'not_run'),
                       'after_status': b.get('status', 'not_run'),
                       'regressed': a.get('status') in ('passed', 'PASS') and b.get('status') in ('failed', 'FAIL'),
                       'error': '; '.join(v for v in (a.get('error'), b.get('error'),
                                          'Measurement units changed.' if not compatible else '') if v)})
    return result


def calibrated_network(project, cell_id, options, model_corner='nominal'):
    """Apply a coupon-bound interconnect network to the verified schematic devices."""
    options = normalize_extraction(options)
    if options['mode'] != 'calibrated_rc':
        raise ValueError('Choose calibrated interconnect RC for the coefficient extractor.')
    from .rc_calibration import coefficients
    corner = options.get('corner', model_corner)
    _, calibration = coefficients(project['pdk'], corner)
    if calibration is None:
        raise ValueError('Import coupon calibration evidence for RC corner '+corner+' before choosing calibrated interconnect RC.')
    from .distributed_rc import extract, apply
    extraction = extract(project, cell_id, options['section_nm'], options['coupling_distance_nm'], corner)
    return extraction, apply(project, cell_id, extraction)
