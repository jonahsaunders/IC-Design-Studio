"""Connection names follow the device family, not just a pin's first letter."""
from .catalog import binding_for


def connection_label(technology, device, pin):
    binding = binding_for(technology, device)
    if device['kind'] in ('NMOS', 'PMOS'):
        return {'d': 'Drain', 'g': 'Gate', 's': 'Source', 'b': 'Bulk'}.get(pin, pin)
    if binding and binding.get('category') == 'Bipolar':
        labels = {'c': 'Collector', 'b': 'Base', 'e': 'Emitter', 's': 'Substrate',
                  'collector': 'Collector', 'base': 'Base', 'emitter': 'Emitter'}
        if (device.get('model_ref', {}).get('pdk') == 'ihp-sg13g2'
                and binding['model'] in ('npn13G2_5t', 'npn13G2l_5t', 'npn13G2v_5t')):
            labels['t'] = 'Temperature rise'
        return labels.get(pin, pin)
    if device['kind'] in ('R', 'C', 'L', 'V', 'I'):
        return {'p': 'Positive (+)', 'n': 'Negative (−)'}.get(pin, pin)
    # Arbitrary hierarchy, native and PDK terminals retain their own names.
    return pin
