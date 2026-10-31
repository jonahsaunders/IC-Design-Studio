"""Explicit drawn-mask checks for the selected SKY130 low-voltage block profile.

Distances are integer nanometres. Unsupported process selectors and geometry
fail the profile; they never turn a failed requirement into an exemption. The
companion implant checker establishes doping and active/well classification.
This is a partial manual-rule implementation, not a qualification assertion.
"""
import hashlib
from pathlib import Path
import klayout.db as k


PROFILE_ABSENT = ((64,18),(19,44),(124,20),(124,21),(18,20),(11,44),
    (75,20),(80,20),(125,44),(125,20),(86,20),(79,20),(81,2),(81,10),
    (81,12),(81,57),(81,63),(74,21),(74,22),(65,13),(66,13))


def check(regions):
    get = lambda pair: regions.get(pair, k.Region()).merged()
    rows = []
    def add(rule, count, description):
        rows.append(dict(rule=rule, violations=int(count), description=description))
    def spacing(rule, a, b, distance, description):
        # A distance-only edge check does not reliably report full containment.
        add(rule, a.separation_check(b,distance).count()+(a&b).count(),description)
    def enclosure(rule, outer, inner, distance, description):
        add(rule, outer.enclosing_check(inner,distance).count()+(inner-outer).count(),description)

    for pair in PROFILE_ABSENT:
        add('profile.absent.'+str(pair),get(pair).count(),'Outside this selected low-voltage geometry profile.')
    diff,tap,poly,well,licon,li,npc,sc,psdm = (get(p) for p in
        ((65,20),(65,44),(66,20),(64,20),(66,44),(67,20),(95,20),(81,4),(94,20)))
    active=(diff|tap).merged();gate=(diff&poly).merged()
    add('profile.active_overlap',(diff&tap).count(),'Diffusion and tap may abut but cannot overlap.')
    add('profile.active_well_straddle',sum(not(k.Region(p)&well).is_empty() and
        not(k.Region(p)-well).is_empty() for p in active.each()),'Merged active islands cannot cross well boundaries.')
    for name,mask in (('diff',diff),('tap',tap),('poly',poly)):
        add('profile.manhattan.'+name,sum(e.dx()!=0 and e.dy()!=0 for e in mask.edges().each()),
            'The selected gate/endcap checks require Manhattan active and poly edges.')
    add('profile.rectangular_gate',sum(not p.is_box() for p in gate.each()),
        'Each gate intersection must be rectangular; bent/ring gates need a separate implementation.')
    add('profile.sc_straddle',sum(not(k.Region(p)&sc).is_empty() and
        not(k.Region(p)-sc).is_empty() for p in gate.each()),'Gate area must be wholly inside or outside areaid.sc.')
    # Exactly two opposite edges must come from diffusion, and the other two
    # from poly. This also rejects poly that ends within active, even when a
    # missing enclosure edge would make a distance-only check vacuously pass.
    ends=gate.edges()&diff.edges();sides=gate.edges()&poly.edges()
    # Index exact directed segments once. Re-intersecting the entire edge set
    # separately for each of tens of thousands of decap gates is quadratic.
    key=lambda e:(e.p1.x,e.p1.y,e.p2.x,e.p2.y)
    end_keys={key(e) for e in ends.each()};side_keys={key(e) for e in sides.each()}
    malformed=0
    for p in gate.each():
        edges={key(e) for e in p.each_edge()};pe=edges&end_keys;ps=edges&side_keys
        parallel=lambda keys:len({x1==x2 for x1,y1,x2,y2 in keys})==1
        malformed += (len(pe)!=2 or len(ps)!=2 or bool(pe&ps) or edges!=(pe|ps) or
                      not parallel(pe) or not parallel(ps))
    add('profile.crossing_gate',malformed,'Every gate has two diffusion ends and two distinct poly sides.')

    add('nwell.1',well.width_check(840).count(),'N-well width is at least 0.840 um.')
    add('nwell.2a',well.space_check(1270).count(),'N-well spacing and notches are at least 1.270 um.')
    add('nwell.4',well.not_interacting(tap&licon&well).count(),
        'Every merged N-well contains a tap contacted by licon, as specified by the manual.')
    for name,mask in (('diff',diff),('tap',tap)):
        add('difftap.1.'+name,mask.width_check(150).count(),'Diffusion and tap width is at least 0.150 um.')
    outside=gate-sc;inside=gate&sc
    add('difftap.2',(outside.edges()&ends).width_check(420).count(),
        'Channel width outside areaid.sc is at least 0.420 um.')
    add('difftap.2b',(inside.edges()&ends).width_check(360).count(),
        'Channel width inside areaid.sc is at least 0.360 um.')
    add('difftap.3',active.space_check(270).count(),'Non-abutting diffusion/tap spacing is at least 0.270 um.')
    enclosure('difftap.8',well,diff&well,180,'N-well encloses P+ diffusion by 0.180 um.')
    spacing('difftap.9',diff-well,well,340,'N+ diffusion is at least 0.340 um from N-well.')
    enclosure('difftap.10',well,tap&well,180,'N-well encloses N+ tap by 0.180 um.')
    spacing('difftap.11',tap-well,well,130,'P+ tap is at least 0.130 um from N-well.')

    add('poly.1a',poly.width_check(150).count(),'Poly width is at least 0.150 um.')
    add('poly.2',poly.space_check(210).count(),
        'All selected poly spacing/notches are at least 0.210 um, without using smaller-spacing exceptions.')
    # Use original poly edges outside diffusion. Clipping the field polygon
    # creates artificial edges at gate ends and would report zero spacing.
    field=poly.edges()-diff
    add('poly.4',field.separation_check(diff.edges(),75,metrics=k.Edges.Projection,
        ignore_angle=1).count(),'Parallel field-poly/diffusion edge spacing is at least 0.075 um.')
    spacing('poly.5',poly-diff,tap,55,'Field-poly to tap spacing is at least 0.055 um.')
    spacing('poly.6',gate,tap.interacting(diff),300,'Gate to abutting-tap spacing is at least 0.300 um.')
    add('poly.7',diff.edges().enclosing_check(sides,250).count(),
        'Diffusion extends beyond the poly sides of every gate by at least 0.250 um.')
    add('poly.8',poly.edges().enclosing_check(ends,130).count(),
        'Poly extends beyond both diffusion ends of every gate by at least 0.130 um.')
    add('poly.10',diff.corners_dots(90,90).interacting(poly).count(),'Poly cannot overlap inner diffusion corners.')
    add('poly.11',poly.corners_dots(-90,90).interacting(diff).count(),
        'Poly cannot make 90 degree turns on diffusion; gate termination is also rejected by the profile.')
    add('poly.12',((poly-well)&tap).count(),'Low-voltage poly outside N-well cannot overlap tap.')

    add('npc.1',npc.width_check(270).count(),'NPC width is at least 0.270 um.')
    add('npc.2',npc.space_check(270).count(),'NPC spacing/notches are at least 0.270 um.')
    spacing('npc.4',npc,gate,90,'NPC to gate spacing, without overlap, is at least 0.090 um.')

    # C3 defines poly_licon by absence of overlap with active outside poly.
    # Required overlap/straddle checks below prevent unsupported contacts from
    # disappearing through this derived-layer classification.
    pl=licon.not_overlapping(active-poly)
    dl=licon.overlapping(diff);tl=licon.overlapping(tap)
    al=licon.overlapping(active-poly)
    add('licon.1',sum(not p.is_box() or p.bbox().width()!=170 or p.bbox().height()!=170
        for p in licon.each()),'Every selected licon is an exact 0.170 um square; no resistor/seal exceptions are used.')
    add('licon.2',licon.space_check(170).count(),'Licon spacing is at least 0.170 um.')
    add('licon.4',licon.not_overlapping(li).count()+licon.not_overlapping(poly|active).count(),
        'Every licon overlaps local interconnect and poly, diffusion or tap.')
    enclosure('licon.5a',diff,dl,40,'Diffusion encloses its licons by 0.040 um.')
    add('licon.6',(tl-tap).count(),'A licon that overlaps tap cannot straddle its boundary.')
    enclosure('licon.8',poly,pl,50,'Poly encloses poly_licon by 0.050 um.')
    spacing('licon.9',pl,psdm,110,'Poly_licon to PSDM spacing, without overlap, is at least 0.110 um.')
    spacing('licon.11',al,outside,55,'Active licon to gate outside areaid.sc is at least 0.055 um.')
    spacing('licon.11ab',al,inside,50,'Active licon to gate inside areaid.sc is at least 0.050 um for both selected device classes.')
    spacing('licon.13',al,npc,90,'Active licon to NPC spacing, without overlap, is at least 0.090 um.')
    spacing('licon.14',pl,active,190,'Poly_licon to diffusion/tap spacing is at least 0.190 um.')
    enclosure('licon.15',npc,pl,100,'NPC encloses poly_licon by 0.100 um.')
    source=(diff-poly).interacting(tap)
    add('licon.16',source.not_covering(licon).count()+tap.not_covering(licon).count(),
        'Every source diffusion and tap fully encloses at least one licon; the profile keeps abutting active in one well.')
    add('licon.17',licon.overlapping(poly).overlapping(active).count(),'No licon overlaps both poly and diffusion/tap.')
    add('licon.18',(pl-npc).count(),'NPC completely encloses poly_licon.')
    violations=sum(r['violations'] for r in rows)
    return dict(schema=1,status='PASS' if not violations else 'FAIL',qualified=False,
        violations=violations,checks=rows,
        scope='Selected low-voltage well, diffusion, gate, NPC and licon geometry. Other manual requirements and process/device profiles remain separate.')


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
