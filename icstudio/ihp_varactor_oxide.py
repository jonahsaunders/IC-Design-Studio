"""Require written thick oxide over the marked high-voltage varactor gates.

The public SVaricap generator always draws ThickGateOx over those gates. The
public DRC decks alone miss a removed oxide on its large fixture. This checks
that device construction requirement; it introduces no guessed enclosure or
process spacing and cannot replace the native decks or strict extraction/LVS.
"""
from pathlib import Path
from .model import file_digest


def check(source,top):
    import klayout.db as k
    from .ihp_klayout_drc import assets,COMMIT
    generator=assets()['SVaricap_code.py'];source=Path(source);sha=file_digest(source)
    ly=k.Layout();ly.read(str(source));cell=ly.cell(top)
    if cell is None or any(cell.each_inst()) or ly.dbu!=.001:
        raise ValueError('IHP varactor oxide checking requires a flat 1 nm verification stream.')
    def region(layer):
        index=ly.find_layer(layer,0)
        return k.Region() if index is None else k.Region(cell.shapes(index)).merged()
    active,poly,well,buried,oxide=(region(n) for n in (1,5,31,32,44))
    index=ly.find_layer(63,0);marked=k.Region();labels=0
    if index is not None:
        for shape in cell.shapes(index).each():
            if shape.is_text() and shape.text.string.casefold()=='svaricap':
                text=shape.text;marked.insert(k.Box(text.x,text.y,text.x+1,text.y+1));labels+=1
    gates=(active&poly&well&buried).merged()
    # Match the public main deck's active/text/well recognition operands.
    selected_wells=well.interacting(active.interacting(gates).interacting(marked))
    selected=gates&selected_wells;missing=(selected-oxide).merged();boxes=[]
    for polygon in missing.each():
        b=polygon.bbox();boxes.append([b.left,b.bottom,b.right,b.top])
    if labels and selected.is_empty():raise ValueError('Marked IHP varactor has no recognized gate geometry.')
    if file_digest(source)!=sha:raise ValueError('Layout changed during IHP varactor oxide checking.')
    return dict(schema=1,status='FAIL' if boxes else 'PASS',violations=len(boxes),boxes_nm=boxes,
                recognized_labels=labels,gate_components=selected.count(),gate_area_nm2=selected.area(),
                missing_area_nm2=missing.area(),layout_sha256=sha,source_commit=COMMIT,
                generator_sha256=file_digest(generator),rule='IHP.SVaricap.ThickGateOx',
                scope='Written thick oxide covers the marked varactor gates as constructed by the pinned public generator. No additional enclosure limit is inferred.')
