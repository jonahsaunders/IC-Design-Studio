"""Selected SKY130 aluminium interconnect and contact enclosure requirements.

The installed fill purposes are combined with drawn metal for physical width,
space and area checks. Only drawn conductors may enclose electrical contacts;
floating fill cannot repair a missing connection. No frame, resistor, SRAM or
large-via exceptions are silently applied. Dimensions are integer nm.
"""
import hashlib
from pathlib import Path
import klayout.db as k


METALS={
    'li':((67,20),(56,28),170,170,56100,'li.6.-'),
    'm1':((68,20),(36,28),140,140,83000,'m1.6'),
    'm2':((69,20),(41,28),140,140,67600,'m2.6'),
    'm3':((70,20),(34,28),300,300,240000,'m3.6'),
    'm4':((71,20),(51,28),300,300,240000,'m4.4a'),
    'm5':((72,20),(59,28),1600,1600,4000000,'m5.4'),
}
CUTS={'ct':((67,44),170,190),'via':((68,44),150,170),
      'via2':((69,44),200,200),'via3':((70,44),200,200),'via4':((71,44),800,800)}


def adjacent_enclosure(inner,outer,distance):
    """At least one side of every adjacent pair must have enough enclosure.

    Preserve the actual portions with insufficient projected enclosure, as in
    the pinned PDK's li.5/m1.5 algorithm. An error occurs where two such portions
    meet at a cut corner. Promoting a partial failure to a whole side incorrectly
    rejects T-shaped conductors used by the published nor4b_2 cell. The 1 nm
    width check detects coincident adjacent portions on the integer grid; it
    does not change the physical enclosure threshold. Full containment is also
    required, so missing conductors cannot pass through an empty edge result.
"""
    bad=inner.enclosed_check(outer,distance,metrics=k.Region.Projection).first_edges()
    count=(inner-outer).count()+sum(not p.is_box() for p in inner.each())
    count+=bad.width_check(1,ignore_angle=100).count()
    return int(count)


def check(regions):
    get=lambda pair:regions.get(pair,k.Region()).merged()
    rows=[]
    def add(rule,count,description):
        rows.append(dict(rule=rule,violations=int(count),description=description))
    def enclose(rule,outer,inner,distance):
        add(rule,outer.enclosing_check(inner,distance).count()+(inner-outer).count(),
            'Drawn conductor enclosure of every contact is at least '+str(distance)+' nm.')
    for pair in ((81,1),(81,2),(81,10),(81,12),(86,20),(79,20)):
        add('profile.absent.'+str(pair),get(pair).count(),'No seal, SRAM, frame, module or precision-resistor exceptions in this profile.')
    for name,(drawn,fill,width,space,area,area_rule) in METALS.items():
        metal=(get(drawn)|get(fill)).merged()
        add(name+'.1'+('.-' if name=='li' else ''),metal.width_check(width).count(),
            'Physical drawn-plus-fill metal minimum width is '+str(width)+' nm.')
        add(name+('.3.-' if name=='li' else '.2'),metal.space_check(space).count(),
            'Physical drawn-plus-fill metal minimum spacing and notch is '+str(space)+' nm.')
        add(area_rule,sum(p.area()<area for p in metal.each()),'Physical drawn-plus-fill metal minimum area is '+str(area)+' nm2.')
        if name in ('m1','m2'):
            add(name+'.7',sum(k.Polygon(list(p.each_point_hole(h))).area()<140000
                for p in metal.each() for h in range(p.holes())), 'Physical metal-hole minimum area is 0.140 um2.')
    for name,(pair,size,space) in CUTS.items():
        cuts=get(pair)
        add(name+'.size',sum(not p.is_box() or p.bbox().width()!=size or p.bbox().height()!=size
            for p in cuts.each()),'Every selected contact is an exact '+str(size)+' nm square.')
        add(name+'.2',cuts.space_check(space).count(),'Minimum contact spacing is '+str(space)+' nm.')
    li,m1,m2,m3,m4,m5=(get(METALS[n][0]) for n in ('li','m1','m2','m3','m4','m5'))
    ct,via,via2,via3,via4=(get(CUTS[n][0]) for n in ('ct','via','via2','via3','via4'))
    add('ct.4',(ct-li).count(),'Every mcon is fully covered by drawn LI, allowing zero enclosure.')
    for rule,outer,inner,distance in (
        ('m1.4',m1,ct,30),('via.4a',m1,via,55),('m2.4',m2,via,55),
        ('via2.4',m2,via2,40),('m3.4',m3,via2,65),('via3.4',m3,via3,60),
        ('m4.3',m4,via3,65),('via4.4',m4,via4,190),('m5.3',m5,via4,310)):
        enclose(rule,outer,inner,distance)
    add('via2.X.1',(via2-m2).count()+(via2-m3).count(),
        'Every selected via2 lies within both drawn met2 and met3; selected five-metal aluminium connectivity.')
    diff,tap,poly,licon=(get(p) for p in ((65,20),(65,44),(66,20),(66,44)))
    active=diff|tap;pl=licon.not_overlapping(active-poly)
    isolated=tap.not_interacting(diff);tl=licon.overlapping(tap)
    add('licon.5b',(tap.edges()&diff).enclosing_check(tl.edges(),60).count(),
        'Tap licon is at least 0.060 um from the actual coincident diff/tap boundary.')
    for rule,inner,outer,distance in (
        ('licon.5c',licon.overlapping(diff),diff,60),
        ('licon.7',licon.overlapping(isolated),isolated,120),
        ('licon.8a',pl,poly,80),('li.5.-',licon,li,80),
        ('m1.5',ct,m1,60),('via.5a',via,m1,85),('m2.5',via,m2,85),
        ('via2.5',via2,m2,85),('via3.5',via3,m3,90)):
        add(rule,adjacent_enclosure(inner,outer,distance),
            'At least one of every two adjacent contact sides has '+str(distance)+' nm projected enclosure; complete containment is also required.')
    violations=sum(r['violations'] for r in rows)
    return dict(schema=1,status='PASS' if not violations else 'FAIL',qualified=False,
        violations=violations,checks=rows,
        scope='Selected aluminium metal width/spacing/area/holes, square contacts and drawn-conductor enclosure. Huge-metal, density and other unbound requirements remain separate.')


def audit(path):
    path=Path(path);layout=k.Layout();layout.read(str(path))
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:
        raise ValueError('Expected one top cell and a 1 nm database grid.')
    regions={}
    for index in layout.layer_indexes():
        info=layout.get_info(index)
        regions[(info.layer,info.datatype)]=k.Region(layout.top_cell().begin_shapes_rec(index)).merged()
    result=check(regions)
    result.update(gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),top=layout.top_cell().name,
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result
