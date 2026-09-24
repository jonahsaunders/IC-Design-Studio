"""Source-name inventory for the analysis selector, independent of netlisting.

The editor already validates committed circuits. Refreshing a source selector
only needs instance names and hierarchy; it must not rebuild connectivity or
resolve/copy every device and model in the design. Simulation still uses the
normal validating netlister.
"""
from .layout_limits import MAX_FLAT_DEVICES


def source_names(project, cell_id=None):
    cells = {cell['id']: cell for cell in project['cells']}
    names = []
    count = 0

    def walk(cid, prefix, ancestors):
        nonlocal count
        if cid in ancestors or len(ancestors) > 12:
            raise ValueError('Recursive or excessively deep cell hierarchy.')
        if cid not in cells:
            raise ValueError('Instance references a missing cell.')
        for device in cells[cid]['devices']:
            name = prefix + device['name']
            if device['kind'] == 'X':
                walk(device['cell'], name + '/', ancestors + (cid,))
            else:
                count += 1
                if count > MAX_FLAT_DEVICES:
                    raise ValueError('Flattened circuit exceeds the 50,000-device capacity. Work on a smaller hierarchy.')
                if device['kind'] in ('V', 'I'):
                    names.append(name)

    walk(cell_id or project['top'], '', ())
    return names
