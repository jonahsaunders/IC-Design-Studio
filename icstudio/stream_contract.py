"""Independent stream geometry, hierarchy and electrical-label checks."""
import math
from pathlib import Path
from .model import file_digest


def compare(first, second, *, text_presentation=True):
    import klayout.db as db
    layouts = []
    for path in (first, second):
        layout = db.Layout(); layout.read(str(path)); layouts.append(layout)
    a, b = layouts
    if not math.isclose(a.dbu, b.dbu, rel_tol=1e-12, abs_tol=0):
        raise ValueError('Layout database units changed.')
    if {c.name for c in a.each_cell()} != {c.name for c in b.each_cell()}:
        raise ValueError('Layout cell set changed.')
    pairs = {(ly.get_info(i).layer, ly.get_info(i).datatype) for ly in layouts for i in ly.layer_indexes()}
    checked = changes = 0
    def instances(cell, layout):
        return sorted((layout.cell(i.cell_index).name, str(i.cplx_trans), i.na, i.nb, str(i.a), str(i.b)) for i in cell.each_inst())
    def labels(cell, index, presentation):
        texts = [s.text for s in cell.shapes(index).each() if s.is_text()] if index is not None else []
        return sorted((t.string, t.x, t.y, t.trans.angle, t.trans.is_mirror(), t.size, t.font, int(t.halign), int(t.valign))
                      if presentation else (t.string, t.x, t.y) for t in texts)
    for cell in a.each_cell():
        other = b.cell(cell.name)
        if instances(cell, a) != instances(other, b): raise ValueError('Placements changed in ' + cell.name)
        for pair in pairs:
            ia, ib = a.find_layer(*pair), b.find_layer(*pair)
            ra = db.Region(cell.shapes(ia)) if ia is not None else db.Region()
            rb = db.Region(other.shapes(ib)) if ib is not None else db.Region()
            if not (ra ^ rb).is_empty(): raise ValueError('Geometry changed: ' + cell.name + ' / ' + str(pair))
            if labels(cell, ia, text_presentation) != labels(other, ib, text_presentation):
                raise ValueError('Layout text changed: ' + cell.name)
            changes += labels(cell, ia, True) != labels(other, ib, True)
            checked += 1
    return dict(status='passed', cells=a.cells(), cell_layers=checked,
                text_presentation_compared=text_presentation, presentation_changed_cell_layers=changes,
                checks=['region XOR', 'label strings and anchor positions', 'hierarchy and array transforms', 'database units'])


def canonicalize(source, target):
    """Re-encode a stream without flattening, moving geometry or using metadata."""
    import klayout.db as db
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or target.exists(): raise ValueError('Choose a new canonical stream output.')
    layout = db.Layout(); layout.read(str(source)); layout.write(str(target))
    checked = compare(source, target)
    return dict(algorithm='klayout-stream-reencode-v1', input_sha256=file_digest(source),
                output_sha256=file_digest(target), comparison=checked, hierarchy='preserved')
