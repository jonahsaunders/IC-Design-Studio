"""Preserve the public IHP isolation-box terminals and outer area/perimeter.

The public writer uses a three-terminal D record (IS/NW/bulk), not an ordinary
SPICE diode. The symbol and model express outer W/L; the public LVS reader uses
A=W*L and P=2*(W+L). This conversion supplies no new electrical model.
"""
import math
from pathlib import Path
import re

from .model import file_digest, scalar
from .ihp_isolation import MODEL_SHA256

SYMBOL_SHA256 = 'dc0022e383a72e138f5c3708589b5da78573b98800d2c140515fc39b5327cb09'
CONNECTION_SHA256 = 'a55896d567a14240ae33faa8799daed545b06bd777245c3731fa4c632e9833f3'


def recognition_label(layer, datatype, text):
    return (layer, datatype) == (63, 0) and text.casefold() == 'isolbox'


def recognition_inventory(source, top):
    import klayout.db as k
    ly = k.Layout(); ly.read(str(source)); cell = ly.cell(top)
    if cell is None or any(cell.each_inst()):
        raise ValueError('IHP isolation checking needs the flattened physical stream.')
    index = ly.find_layer(63, 0)
    return [dict(text=s.text.string, x=s.text.x, y=s.text.y)
            for s in cell.shapes(index).each() if s.is_text() and recognition_label(63, 0, s.text.string)] if index is not None else []


def extractor_connections(destination):
    """Connect the buried n-region to its overlapping contacted NWell ring.

    The pinned PCell places its I terminal on the n-active/NWell ring. The
    public extractor's isolbox_i is nBuLay minus isolated p-well, but the public
    connectivity deck never connects that buried region to NWell. Generic
    ntap also excludes Recog/diode, removing this ring's contact path. Retain
    both overlaps explicitly; contact-to-metal joins and labels stay unchanged.
    """
    relative = 'rule_decks/diode_connections.lvs'; path = Path(destination)/relative
    original = b'connect(isolbox_i, nbulay_drw)'
    content = path.read_bytes()
    if file_digest(path) != CONNECTION_SHA256 or content.count(original) != 1:
        raise ValueError('Unexpected public IHP isolation connection source.')
    replacement = original + b'''\n# IC Design Studio: retain the physical isolation NWell and its n-active contacts.
connect(isolbox_i, nwell_drw)
isolbox_n_tie = nact_nwell.and(isolbox_recog)
connect(isolbox_i, isolbox_n_tie)
connect(isolbox_n_tie, cont_drw)'''
    path.write_bytes(content.replace(original, replacement))
    return dict(path=relative, source_sha256=CONNECTION_SHA256, sha256=file_digest(path),
                change='Retain the physical isolbox_i/NWell overlap and n-active ring contact path excluded by generic ntap. Preserve metal joins, labels and original source files.')


def _proof(technology):
    entry = technology.get('simulation', {}).get('catalog', {}).get('sg13g2_pr/isolbox.sym', {})
    if entry.get('unavailable') or entry.get('model') != 'isolbox' or entry.get('pin_order') != ['isosub', 'nwell', 'sub!']:
        raise ValueError('A reviewed three-terminal IHP isolation binding is required for LVS.')
    root = Path(technology['package_root']).resolve(); files = technology['package_lock']['files']
    expected = {entry['source']: SYMBOL_SHA256, entry['model_source']: MODEL_SHA256}
    for relative, sha in expected.items():
        path = (root/relative).resolve()
        if not path.is_relative_to(root) or files.get(relative) != sha or file_digest(path) != sha:
            raise ValueError('Changed IHP isolation LVS source: ' + relative)
    return expected


def geometry(text, technology=None, *, extracted=False):
    if technology is not None and technology.get('package_lock', {}).get('id') != 'ihp-sg13g2':
        return text, []
    lines = re.sub(r'\n[ \t]*\+[ \t]*', ' ', text).splitlines(); changes = []; proof = None
    for index, line in enumerate(lines):
        tokens = line.split()
        if not tokens or tokens[0].startswith(('*', '.')): continue
        model_index = next((i for i, token in enumerate(tokens) if '=' in token), len(tokens)) - 1
        if tokens[model_index].casefold() != 'isolbox': continue
        if model_index != 4 or tokens[0][0].upper() not in ('X', 'D'):
            raise ValueError('IHP isolation LVS must retain IS, NWell and bulk terminals.')
        if technology is not None and proof is None: proof = _proof(technology)
        params = {}
        for token in tokens[5:]:
            pair = token.split('=', 1)
            if len(pair) != 2 or pair[0].lower() in params:
                raise ValueError('Duplicate or unresolved IHP isolation LVS parameter.')
            key, raw = pair[0].lower(), pair[1]; value = scalar(raw)
            if not math.isfinite(value) or value <= 0:
                raise ValueError('IHP isolation LVS geometry must be positive and finite.')
            params[key] = (value, raw)
        if set(params) == {'w', 'l'} and not extracted:
            w, l = (params[k][0] for k in ('w', 'l'))
            if min(w, l) <= 2.1e-6:
                raise ValueError('IHP isolation W/L must exceed the model inner-dimension offset of 2.1 um.')
            area, perimeter = w*l, 2*(w+l)
            if not math.isfinite(area+perimeter) or area <= 0:
                raise ValueError('Invalid IHP isolation area/perimeter.')
            values = [f'a={area:.15g}', f'p={perimeter:.15g}']
        elif set(params) == {'a', 'p'}:
            values = ['a='+params['a'][1], 'p='+params['p'][1]]
        else:
            raise ValueError('IHP isolation LVS requires resolved W/L or public A/P; extra parameters cannot be discarded.')
        name = tokens[0] if tokens[0][0].upper() == 'X' else 'XICSTUDIO_ISO_'+tokens[0]
        lines[index] = ' '.join([name, *tokens[1:5], *values])
        changes.append(dict(instance=tokens[0], replacement=name, model='isolbox', terminal_count=3,
                            original=line, comparison=lines[index], source=proof,
                            reason='Preserve IS/NWell/bulk roles and public outer area/perimeter; no two-terminal diode reduction.'))
    if not changes: return text, []
    from .ihp_tap_lvs import _names
    _names(lines)
    return '\n'.join(lines)+'\n', changes
