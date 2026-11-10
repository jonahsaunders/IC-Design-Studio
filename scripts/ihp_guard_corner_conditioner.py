"""Explicit finite corner-safe routing profile, never native-mask equivalence."""
import hashlib,json
from icstudio.model import clone
from icstudio.layout import kdb,polygon,rect,shape_from_polygon
from scripts.qualification_geometry import regions

CUT=190
GAP=220
PITCH=CUT+GAP

def mask_identity(p):
    payload={str(k):sorted(str(x) for x in r.each()) for k,r in sorted(regions(p).items())}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def condition(p,model,coverage,contract):
    if coverage!={k:'100' for k in ('viagb','viagt','viagl','viagr')}:
        if coverage not in contract['unchanged_coverage_cases']:raise ValueError('Unreviewed coverage.')
        return clone(p),{'applied':False,'raw_mask_sha256':mask_identity(p),'conditioned_mask_sha256':mask_identity(p)}
    raw=mask_identity(p)
    if model not in contract['raw_mask_sha256'] or raw!=contract['raw_mask_sha256'][model]:raise ValueError('Unreviewed raw all100 geometry.')
    db=kdb();before=regions(p);upper=list(before[(10,0)].each())
    if len(upper)!=1 or upper[0].holes()!=1:raise ValueError('Expected one finite ring with one hole.')
    poly=upper[0];hole=db.Polygon(list(poly.each_point_hole(0)))
    if not (db.Region(hole)^db.Region(hole.bbox())).is_empty():raise ValueError('Unreviewed nonrectangular hole.')
    ring=db.Region(poly.bbox())-db.Region(hole)
    if (ring-before[(10,0)]).area()!=250000 or not (before[(10,0)]-ring).is_empty():raise ValueError('Unreviewed corner fill delta.')
    cuts=list(before[(19,0)].each());vertical={-1:[],1:[]};horizontal=[]
    inner=hole.bbox()
    for cut in cuts:
        b=cut.bbox()
        if b.width()!=CUT or b.height()!=CUT or not (db.Region(cut)^db.Region(b)).is_empty():raise ValueError('Expected190nm square cuts.')
        if b.center().x<inner.left:vertical[-1].append(b)
        elif b.center().x>inner.right:vertical[1].append(b)
        else:horizontal.append(b)
    if len(horizontal)!=14 or any(len(v)!=21 for v in vertical.values()):raise ValueError('Unreviewed single-row topology.')
    low=max(b.top for b in horizontal if b.center().y<0)+GAP
    high=min(b.bottom for b in horizontal if b.center().y>0)-GAP
    n=(high-low+GAP)//PITCH
    if n!=20 or low!=-high:raise ValueError('Unreviewed corner-excluded span.')
    q=clone(p);c=q['cells'][0]
    c['shapes']=[s for s in c['shapes'] if s['layer'] not in ('Metal2.drawing','Via1.drawing')]
    c['shapes'] += [shape_from_polygon(x,'Metal2.drawing') for x in ring.each()]
    newcuts=list(horizontal)
    for side,boxes in vertical.items():
        xs={b.left for b in boxes}
        if len(xs)!=1:raise ValueError('Unreviewed multirow cuts.')
        x=xs.pop();start=-(n*CUT+(n-1)*GAP)//2
        for i in range(n):newcuts.append(db.Box(x,start+i*PITCH,x+CUT,start+i*PITCH+CUT))
    c['shapes'] += [rect('Via1.drawing',b.left,b.bottom,b.width(),b.height()) for b in newcuts]
    after=regions(q)
    for key in before:
        if key not in ((10,0),(19,0)) and not (before[key]^after[key]).is_empty():raise ValueError('Unapproved device-mask change.')
    if after[(19,0)].count()!=54:raise ValueError('Incorrect final cut count.')
    # Rectangle distance audit is independent of native DRC: require at least
    # 220nm separation on one axis for every pair, including adjacent corners.
    for i,a in enumerate(newcuts):
        for b in newcuts[i+1:]:
            dx=max(a.left-b.right,b.left-a.right,0);dy=max(a.bottom-b.top,b.bottom-a.top,0)
            if max(dx,dy)<GAP:raise ValueError('Corner/array cut clearance failed.')
    for b in newcuts:
        if not (db.Region(b)-before[(8,0)]).is_empty() or not (db.Region(b)-ring).is_empty():raise ValueError('Cut outside originalM1/correctedM2.')
    return q,dict(applied=True,raw_mask_sha256=raw,conditioned_mask_sha256=mask_identity(q),m2_added_nm2=250000,m2_removed_nm2=0,via1_before=56,via1_after=54,vertical_count_per_side=n,safe_y_nm=[low,high],cut_nm=CUT,gap_nm=GAP,pitch_nm=PITCH,horizontal_cuts_unchanged=True,other_layers_unchanged=True)
