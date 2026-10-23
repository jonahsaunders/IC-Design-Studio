"""Process-neutral mask/rotation helpers for flat qualification coupons."""
from icstudio.layout import kdb,polygon
from icstudio.model import clone


def regions(p):
    db=kdb();layers={l['name']:(l['gds'],l['datatype']) for l in p['pdk']['layers']};out={}
    for shape in p['cells'][0]['shapes']:
        key=layers[shape['layer']];out.setdefault(key,db.Region()).insert(polygon(shape))
    return {k:r.merged() for k,r in out.items()}

def same_masks(a,b):
    a,b=regions(a),regions(b)
    if set(a)!=set(b) or any(not (a[k]^b[k]).is_empty() for k in a):
        raise ValueError('A mask changed during import, port assignment or exchange.')

def rotated(p):
    q=clone(p);c=q['cells'][0]
    for s in c['shapes']:
        s['points']=[[-y,x] for x,y in s['points']]
        s['holes']=[[[-y,x] for x,y in hole] for hole in s.get('holes',[])]
    for t in c.get('layout_texts',[]):t['x'],t['y']=-t['y'],t['x'];t['rotation']=(t.get('rotation',0)+90)%360
    for v in c['layout_ports']:v['point']=[-v['point'][1],v['point'][0]]
    return q
