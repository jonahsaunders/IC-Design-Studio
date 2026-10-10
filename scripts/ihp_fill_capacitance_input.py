"""Explicit electrical-purpose mapping for bounded IHP fill qualification.

This produces a disposable extraction view. It never changes the deliverable.
Only rectangular, uncontacted N+ active fill in ordinary PWell is supported;
the pinned manual's nSD definition and absence of modifiers are checked. The
native diffusion capacitance model still needs a separate junction model.
"""
import hashlib
from pathlib import Path

METALS={'Metal1':8,'Metal2':10,'Metal3':30,'Metal4':50,'Metal5':67,'TopMetal1':126,'TopMetal2':134}
MODIFIERS=((31,0),(32,0),(44,0),(46,21),(7,21),(28,0),(14,0),(5,0),(6,0),(26,0))


def prepare(layout, labels, state):
    import klayout.db as k
    if state not in ('original','metal','active'):raise ValueError('Unknown electrical representation.')
    tops=list(layout.top_cells())
    if layout.dbu!=.001 or len(tops)!=1:raise ValueError('Expected one IHP top on the 1 nm grid.')
    top=tops[0];top.flatten(True)
    def region(n,d):
        i=layout.find_layer(n,d)
        return k.Region() if i is None else k.Region(top.begin_shapes_rec(i)).merged()
    before={(layout.get_info(i).layer,layout.get_info(i).datatype):region(layout.get_info(i).layer,layout.get_info(i).datatype) for i in layout.layer_indices()}
    active=region(1,22)
    if active.is_empty():raise ValueError('Active-fill model coverage requires actual active fill.')
    for pair in MODIFIERS:
        if not (active & region(*pair)).is_empty():raise ValueError('Active fill intersects a process modifier or circuit device.')
    if not region(5,22).is_empty():raise ValueError('Poly fill needs a separate device extraction model.')
    for idx in layout.layer_indices():
        for shape in list(top.shapes(idx).each()):
            if shape.is_text():shape.delete()
    inventory=[];expected=dict(before)
    for n in (1,*METALS.values()):
        fill=region(n,22)
        if fill.is_empty():raise ValueError('A required fill level is missing.')
        polygons=list(fill.each())
        if any(not p.is_box() for p in polygons):raise ValueError('Nonrectangular fill is unsupported.')
        if not fill.interacting(before.get((n,0),k.Region())).is_empty():
            raise ValueError('Floating fill touches existing circuit material.')
        polygons.sort(key=lambda p:(p.bbox().left,p.bbox().bottom,p.bbox().right,p.bbox().top))
        mapped=n!=1 and state!='original' or n==1 and state=='active'
        if state=='original' or mapped:
            top.shapes(layout.layer(n,22)).clear();expected[n,22]=k.Region()
        if mapped:
            top.shapes(layout.layer(n,0)).insert(fill)
            expected[n,0]=(before.get((n,0),k.Region())+fill).merged()
        for i,p in enumerate(polygons):
            b=p.bbox();alias=f'FILL{n:03d}_{i:06d}'
            row=dict(alias=alias,layer=n,box_nm=[b.left,b.bottom,b.right,b.top],mapped=mapped)
            if n==1:row.update(junction_model='dantenna',width_um=b.width()/1000,length_um=b.height()/1000)
            inventory.append(row)
            if mapped:
                pos=b.center();top.shapes(layout.layer(n,0 if n==1 else 25)).insert(k.Text(alias,k.Trans(pos.x,pos.y)))
    for pair,wanted in expected.items():
        if not (region(*pair)^wanted).is_empty():raise ValueError('Extraction view changed an unrelated physical mask.')
    netnames=set();aliases=set();pin_regions={n:k.Region() for n in METALS.values()};named=[]
    for net in labels['nets']:
        alias=net['alias']
        if (net['net'] in netnames or alias in aliases or not alias.startswith('NET') or
                len(alias)!=9 or not alias[3:].isdigit()):raise ValueError('Invalid or ambiguous electrical net identity.')
        netnames.add(net['net']);aliases.add(alias)
        for pin in net['pins']:
            n=METALS[pin['layer']];b=k.Box(*pin['box_nm'])
            if b.width()<=0 or b.height()<=0:raise ValueError('Invalid physical terminal.')
            pin_regions[n].insert(b)
        if net['pins']:
            pin=net['pins'][0];n=METALS[pin['layer']];pos=k.Box(*pin['box_nm']).center()
            top.shapes(layout.layer(n,25)).insert(k.Text(alias,k.Trans(pos.x,pos.y)));named.append(alias)
    for n,pins in pin_regions.items():
        if not (pins-region(n,0)).is_empty():raise ValueError('Checkpoint terminal is not contained in the actual GDS metal.')
    return dict(schema=1,qualified=False,state=state,fill=inventory,named_nets=named,
                active_process='Uncontacted N+ active in ordinary PWell; no implant, silicide, oxide or well modifiers.',
                scope='Disposable capacitance extraction view; requires native model, junction response and performance validation.')


def write(gds, labels, state, output):
    import klayout.db as k
    output=Path(output)
    if output.exists():raise ValueError('Use a new extraction-view path.')
    ly=k.Layout();ly.read(str(gds));record=prepare(ly,labels,state)
    options=k.SaveLayoutOptions();options.gds2_write_timestamps=False;ly.write(str(output),options)
    check=k.Layout();check.read(str(output))
    if check.dbu!=ly.dbu or len(list(check.top_cells()))!=1 or check.top_cell().name!=ly.top_cell().name:
        raise ValueError('Written extraction view changed its grid or top.')
    for idx in ly.layer_indices():
        info=ly.get_info(idx);other=check.find_layer(info.layer,info.datatype)
        a=k.Region(ly.top_cell().begin_shapes_rec(idx))
        b=k.Region() if other is None else k.Region(check.top_cell().begin_shapes_rec(other))
        if not (a^b).is_empty():raise ValueError('Written extraction view changed a physical mask.')
        texts=lambda layout,i: sorted(s.text.to_s() for s in layout.top_cell().shapes(i).each() if s.is_text())
        if texts(ly,idx)!=([] if other is None else texts(check,other)):
            raise ValueError('Written extraction view changed a net label.')
    record.update(source_gds_sha256=hashlib.sha256(Path(gds).read_bytes()).hexdigest(),
                  extraction_gds_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  physical_masks_and_labels_readback_verified=True)
    return record
