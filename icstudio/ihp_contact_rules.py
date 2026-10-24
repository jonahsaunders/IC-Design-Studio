"""Check the public IHP Cnt.a minimum width on the written contact mask.

The bundled Magic deck specifies 160 nm for ordinary diffusion/poly contacts.
Its distinct extracted tap contact types can miss that check. Keep full Magic
DRC and inspect the original mask too; never repair or resize the user's cuts.
This is one supplemental rule, not a replacement public or foundry deck.
"""
from fractions import Fraction
from pathlib import Path
from .model import file_digest

RULE_PATH='libs.tech/magic/ihp-sg13g2-drc.tech'
RULE_SHA256='bec75c6c8aeb9720edcdfdcf1e2c132d9be4af42801dd61b45715d6c6ec68402'
MINIMUM_NM=160


def check(source,top,technology):
    import klayout.db as db
    if technology.get('package_lock',{}).get('id')!='ihp-sg13g2':raise ValueError('IHP contact width requires the IHP package.')
    root=Path(technology['package_root']).resolve();rule=(root/RULE_PATH).resolve()
    if not rule.is_relative_to(root) or technology['package_lock']['files'].get(RULE_PATH)!=RULE_SHA256 or file_digest(rule)!=RULE_SHA256:
        raise ValueError('IHP contact-width rule source is missing or changed.')
    ly=db.Layout();ly.read(str(source));cell=ly.cell(top)
    if cell is None or any(cell.each_inst()):raise ValueError('Contact width needs the checked flattened layout.')
    unit=Fraction(str(ly.dbu))*1000;distance=Fraction(MINIMUM_NM)/unit
    if unit<=0 or distance.denominator!=1:raise ValueError('Layout grid cannot represent the exact IHP contact-width limit.')
    index=ly.find_layer(6,0);region=db.Region() if index is None else db.Region(cell.shapes(index))
    region.merge();errors=region.width_check(int(distance));boxes=[]
    for pair in errors.each():
        b=pair.bbox();coords=[Fraction(v)*unit for v in (b.left,b.bottom,b.right,b.top)]
        if any(v.denominator!=1 for v in coords):raise ValueError('Contact finding cannot be represented exactly in nanometres.')
        boxes.append([int(v) for v in coords])
    return dict(schema=1,status='FAIL' if boxes else 'PASS',rule='Cnt.a',minimum_width_nm=MINIMUM_NM,
                layer=[6,0],violations=len(boxes),boxes_nm=boxes,layout_sha256=file_digest(source),
                rule_source=dict(path=RULE_PATH,sha256=RULE_SHA256),
                scope='Minimum contact-mask width only; full native DRC and LVS remain separate requirements.')
