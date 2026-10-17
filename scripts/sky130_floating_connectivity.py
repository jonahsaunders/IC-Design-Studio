"""Require complete conductor paths to gates, diffusion or block metal pins.

Unlike the bundled neighbor-contact check, this builds complete connected
components through every contact level. No floating/tie labels or standard-cell
exemptions are used. Native dummy fill has separate purposes and is not routed
interconnect. The selected profile excludes capacitors and connectivity edits.
This supplements, rather than replaces, transistor/body/port LVS.
"""
import hashlib
from pathlib import Path
import klayout.db as k

LAYERS={'poly':(66,20),'licon':(66,44),'li1':(67,20),'mcon':(67,44),
        'm1':(68,20),'via':(68,44),'m2':(69,20),'via2':(69,44),
        'm3':(70,20),'via3':(70,44),'m4':(71,20),'via4':(71,44),'m5':(72,20)}
WIRES=('poly','li1','m1','m2','m3','m4','m5')
ABSENT=((89,44),(97,44),(74,20),(65,14),(66,14),(67,14),(68,14),(69,14),(70,14),(71,14),(72,14),
        (67,15),(68,15),(69,15),(70,15),(71,15),(72,15))
EXCEPTION_LABELS={prefix+'_'+suffix for prefix in ('poly','li1','m1','m2','m3','m4','m5') for suffix in ('float','tie')}


def check(regions,top_pins=None,labels=()):
    get=lambda pair:regions.get(pair,k.Region()).merged()
    top_pins=top_pins or {};checks=[]
    def add(rule,count,description):checks.append(dict(rule=rule,violations=count,description=description))
    for pair in ABSENT:
        add('profile.absent.'+str(pair),get(pair).count(),'Unreviewed capacitor/RDL/cut/short purpose is refused by this routed-conductor profile.')
    add('profile.exception_labels',sum(label.strip().casefold() in EXCEPTION_LABELS for label in labels),
        'No floating or parent-tie exception label is used; such declarations require separate review.')
    layers={name:get(pair) for name,pair in LAYERS.items()}
    # conb_1 contains poly-short annotations wholly inside already continuous
    # poly. They cannot add conductor or roots here. A marker outside the
    # actual poly, including one bridging a gap, remains unsupported.
    add('profile.poly_short_coverage',(get((66,15))-layers['poly']).count(),
        'Poly-short annotations must be wholly inside real poly and cannot create connectivity.')
    layers['sd']=(get((65,20))|get((65,44)))-layers['poly']
    layers['gate_root']=get((65,20))&layers['poly']
    # A pin annotation cannot bridge separate wires or connect two metal
    # levels. Root regions are separately clipped to each real conductor.
    for name in ('li1','m1','m2','m3','m4','m5'):
        pair=LAYERS[name];pin=top_pins.get((pair[0],16),k.Region()).merged()
        add('profile.pin_coverage.'+name,(pin-layers[name]).count(),'A block pin must be fully covered by its own drawn conductor.')
        layers[name+'_pin_root']=pin&layers[name]
    netter=k.LayoutToNetlist('TOP',.001)
    for name,region in layers.items():netter.register(region,name);netter.connect(region)
    names=list(LAYERS)
    for lower,upper in zip(names,names[1:]):netter.connect(layers[lower],layers[upper])
    netter.connect(layers['sd'],layers['licon'])
    netter.connect(layers['gate_root'],layers['poly'])
    for name in ('li1','m1','m2','m3','m4','m5'):netter.connect(layers[name+'_pin_root'],layers[name])
    netter.extract_netlist();circuit=netter.netlist().circuit_by_name('TOP')
    if circuit is None and any(not region.is_empty() for region in layers.values()):
        raise ValueError('Connectivity extraction did not retain the non-empty top circuit.')
    roots=['sd','gate_root']+[name+'_pin_root' for name in ('li1','m1','m2','m3','m4','m5')]
    covered={name:0 for name in layers};floating=[];nets=0;anchored=0
    for net in circuit.each_net() if circuit else ():
        nets+=1;shapes={name:netter.shapes_of_net(net,region,True) for name,region in layers.items()}
        for name,region in shapes.items():covered[name]+=region.area()
        has_root=any(not shapes[name].is_empty() for name in roots)
        wires={name:region for name,region in shapes.items() if name in WIRES and not region.is_empty()}
        if has_root:anchored+=1
        elif wires:
            floating.append(dict(layers=sorted(wires),bounds={name:str(region.bbox()) for name,region in sorted(wires.items())}))
    add('profile.complete_extraction',sum(covered[name]!=region.area() for name,region in layers.items()),
        'All submitted conductor and root area must be accounted for across extracted nets; omitted floating nets cannot become passes.')
    add('x.22',len(floating),'Every routed poly/LI/metal component needs a complete path to a gate, diffusion/tap or a top-level metal pin.')
    total=sum(row['violations'] for row in checks)
    return dict(schema=1,status='PASS' if not total else 'FAIL',qualified=False,violations=total,checks=checks,
        nets=nets,anchored_nets=anchored,floating=sorted(floating,key=lambda row:str(row)),
        layer_area_nm2={name:region.area() for name,region in sorted(layers.items())},
        covered_area_nm2=dict(sorted(covered.items())),
        scope='Complete drawn-conductor connectivity for the selected HD profile; no exception labels or standard-cell exemptions. Physical dummy fill, device/body correctness and chunk acceptance have separate gates.')


def audit(path):
    path=Path(path);layout=k.Layout();layout.read(str(path))
    if len(layout.top_cells())!=1 or abs(layout.dbu-.001)>1e-12:
        raise ValueError('Expected one top cell and a 1 nm database grid.')
    top=layout.top_cell();needed=set(LAYERS.values())|set(ABSENT)|{(65,20),(65,44),(66,15)}
    regions={pair:k.Region(top.begin_shapes_rec(layout.layer(*pair))) for pair in needed}
    top_pins={pair:k.Region(top.shapes(layout.layer(*pair))) for pair in [(n,16) for n in range(67,73)]}
    labels=[]
    for index in layout.layer_indexes():
        it=top.begin_shapes_rec(index);it.shape_flags=k.Shapes.STexts
        while not it.at_end():labels.append(it.shape().text.string);it.next()
    result=check(regions,top_pins,labels)
    result.update(gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),top=top.name,
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result
