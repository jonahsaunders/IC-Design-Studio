"""Supplement native DRC with checks on the original drawn implant masks.

Magic reconstructs some mask layers when importing GDS. Passing its internal
representation cannot establish these constraints on the submitted polygons.
This module covers the stated low-voltage HD checks, not all SKY130 rules.
Dimensions are integer nanometres on a validated 1 nm database grid.
"""
import argparse
import hashlib
import json
from pathlib import Path
import klayout.db as k


def check(regions):
    get = lambda pair: regions.get(pair, k.Region())
    rows = []
    def add(rule, count, description):
        rows.append(dict(rule=rule, violations=int(count), description=description))
    def holes(region):
        return [k.Polygon(list(p.each_point_hole(i))) for p in region.each() for i in range(p.holes())]
    # Fail closed on process selectors whose exceptions/derived device types
    # are not implemented in this checker. Standard-cell and diode identifiers
    # are permitted; this profile does not infer absent masks from cell names.
    for pair in ((64,18),(19,44),(124,20),(124,21),(18,20),(11,44),(75,20),
                 (80,20),(125,44),(125,20),(86,20),(79,20),(81,2),(74,22),(81,57),(81,63)):
        add('profile.'+str(pair), get(pair).count(), 'Outside the selected low-voltage HD implant profile.')
    diff, tap, poly, well = (get(p) for p in ((65,20),(65,44),(66,20),(64,20)))
    nsdm, psdm, hvtp = (get(p) for p in ((93,44),(94,20),(78,44)))
    active = (diff|tap).merged()
    nactive = ((diff-well)|(tap&well)).merged()
    pactive = ((diff&well)|(tap-well)).merged()
    add('n/psd.9.n', (nactive-nsdm).count(), 'Every low-voltage n-type active polygon is enclosed by NSDM.')
    add('n/psd.9.p', (pactive-psdm).count(), 'Every low-voltage p-type active polygon is enclosed by PSDM.')
    add('n/psd.8.n', (pactive&nsdm).count(), 'NSDM cannot overlap active regions of opposite doping.')
    add('n/psd.8.p', (nactive&psdm).count(), 'PSDM cannot overlap active regions of opposite doping.')
    # Subtract only the coincident portions of an opposite-doping active
    # boundary. Removing a whole polygon or edge that merely touches a tap
    # would incorrectly exempt the rest of a partially butting edge.
    for kind, drawn in (('5a',diff),('5b',tap)):
        for name, own, opposite, implant in (('n',drawn&nactive,pactive,nsdm),
                                            ('p',drawn&pactive,nactive,psdm)):
            nonbutting=own.edges()-opposite
            add('n/psd.'+kind+'.'+name,implant.edges().enclosing_check(nonbutting,125).count(),
                'Drawn implant enclosure of non-butting '+('diffusion' if kind=='5a' else 'tap')+' edges is 0.125 um.')
    for name, own, opposite, implant in (('n',nactive,pactive,nsdm),('p',pactive,nactive,psdm)):
        butting=own.edges()&opposite
        add('n/psd.6.'+name,(butting-implant).count(),
            'Coincident diffusion/tap butting edges have at least zero drawn implant enclosure.')
        add('n/psd.7.'+name,implant.edges().separation_check(opposite.edges()-own,130).count(),
            'Drawn implant spacing to opposite-doping non-butting active edges is 0.130 um.')
    for name, implant, minimum in (('n',nsdm,265000),('p',psdm,255000)):
        add('n/psd.1.'+name, implant.width_check(380).count(), 'Minimum drawn implant width 0.380 um.')
        add('n/psd.2.'+name, implant.space_check(380).count(), 'Minimum drawn implant spacing and notch 0.380 um.')
        add('n/psd.10'+('a' if name=='n' else 'b'), sum(p.area()<minimum for p in implant.each()),
            'Minimum drawn implant area 0.265 um2 (N), 0.255 um2 (P).')
        add('n/psd.11.'+name, sum(p.area()<265000 for p in holes(implant)), 'Minimum implant-hole area 0.265 um2.')
    pfet = (diff&well&poly).merged()
    inside = pfet.interacting(hvtp)
    outside = pfet-inside
    add('hvtp.1', hvtp.width_check(380).count(), 'Minimum HVTP width 0.380 um.')
    add('hvtp.2', hvtp.space_check(380).count(), 'Minimum HVTP spacing and notch 0.380 um.')
    add('hvtp.3', (inside.sized(180)-hvtp).count(), 'HVTP encloses every interacting low-voltage PFET gate by 0.180 um.')
    add('hvtp.4', outside.separation_check(hvtp,180).count(), 'Unselected low-voltage PFET gate spacing to HVTP is 0.180 um.')
    add('hvtp.5', sum(p.area()<265000 for p in hvtp.each()), 'Minimum HVTP area 0.265 um2.')
    add('hvtp.6', sum(p.area()<265000 for p in holes(hvtp)), 'Minimum HVTP-hole area 0.265 um2.')
    add('profile.active_overlap', (diff&tap).count(), 'Low-voltage diffusion and tap may abut, but must not overlap.')
    add('profile.active_well_straddle', sum(not (k.Region(p)&well).is_empty() and
        not (k.Region(p)-well).is_empty() for p in active.each()),
        'This checker requires each merged active island to stay on one side of the well boundary.')
    violations=sum(row['violations'] for row in rows)
    return dict(schema=1,status='PASS' if not violations else 'FAIL',qualified=False,
        violations=violations,checks=rows,
        scope='Selected low-voltage drawn implant coverage, non-butting enclosure, butting-edge coverage, opposite-active spacing, width/space/area/holes and HVTP gate enclosure. Full rule reconciliation and other process/device profiles remain separate.')


def audit(path):
    path=Path(path);layout=k.Layout();layout.read(str(path))
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:
        raise ValueError('Expected one top cell and a 1 nm database grid.')
    cell=layout.top_cell();regions={}
    for index in layout.layer_indexes():
        info=layout.get_info(index)
        regions[(info.layer,info.datatype)]=k.Region(cell.begin_shapes_rec(index)).merged()
    result=check(regions)
    result.update(gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),top=cell.name,
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gds',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.gds)
    args.output.write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps({key:value for key,value in result.items() if key!='checks'}))
    raise SystemExit(0 if result['status']=='PASS' else 1)
