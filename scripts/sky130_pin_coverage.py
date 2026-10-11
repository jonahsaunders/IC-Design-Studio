"""Execute SKY130 x.5 on pin polygons throughout the complete GDS hierarchy.

Layer pairs follow the captured sky130hd.lyt. P-well is the default substrate
(NOT nwell), as defined by the published table C3; it is not a drawn mask.
Isolated P-well is (NOT nwell) AND dnwell. The layout extent only bounds the
complement operation and cannot turn an out-of-well pin into a passing pin.
"""
import argparse
import hashlib
import json
from pathlib import Path

PIN_LAYERS = {
    'diff': ((65,16),(65,20)), 'tap': ((65,48),(65,44)),
    'poly': ((66,16),(66,20)), 'licon1': ((66,58),(66,44)),
    'li1': ((67,16),(67,20)), 'mcon': ((67,48),(67,44)),
    'met1': ((68,16),(68,20)), 'via': ((68,58),(68,44)),
    'met2': ((69,16),(69,20)), 'via2': ((69,58),(69,44)),
    'met3': ((70,16),(70,20)), 'via3': ((70,48),(70,44)),
    'met4': ((71,16),(71,20)), 'via4': ((71,48),(71,44)),
    'met5': ((72,16),(72,20)), 'rdl': ((74,16),(74,20)),
    'nwell': ((64,16),(64,20)), 'pad': ((76,16),(76,20)),
}


def audit(path):
    import klayout.db as k
    path=Path(path);ly=k.Layout();ly.read(str(path))
    if len(ly.top_cells())!=1:raise ValueError('The x.5 check requires one layout top.')
    top=ly.top_cell()
    def region(pair):return k.Region(top.begin_shapes_rec(ly.layer(*pair))).merged()
    rows=[]
    def check(name,pair,material):
        pins=region(pair);missing=pins-material
        rows.append(dict(layer=name,pin_layer=list(pair),pin_polygons=pins.count(),
                         violations=missing.count(),missing_area_um2=missing.area()*ly.dbu**2))
    for name,(pins,drawing) in PIN_LAYERS.items():check(name,pins,region(drawing))
    pwell=k.Region(top.bbox())-region((64,20))
    check('pwell',(122,16),pwell)
    check('pwelliso',(44,16),pwell & region((64,18)))
    count=sum(row['violations'] for row in rows)
    return dict(schema=1,rule='x.5',status='PASS' if count==0 else 'FAIL',top=top.name,
                gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),violations=count,layers=rows,
                scope='Pin containment only; no other rule or process acceptance is implied.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('gds',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report=audit(a.gds);a.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(report['status'],report['violations']);raise SystemExit(report['status']!='PASS')
