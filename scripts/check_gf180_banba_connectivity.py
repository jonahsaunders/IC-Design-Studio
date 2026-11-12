"""Check written metal and declared contact anchors for the bounded Banba layout.

This four-metal/MIM-B reference check complements native device/substrate LVS.
It never connects polygons through text labels or the common substrate.
"""
from collections import Counter,defaultdict
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest,load_project


def inspect(gds,project):
    import klayout.db as k
    gds=Path(gds).resolve(strict=True);project=Path(project).resolve(strict=True)
    hashes={str(p):file_digest(p) for p in (gds,project)}
    p=load_project(project);cell=next(c for c in p['cells'] if c['name']=='banba_layout')
    if p['pdk'].get('banba_physical_stack',{}).get('physical_variant')!='B':
        raise ValueError('This checker requires the declared four-metal Banba reference.')
    devices={d['id']:d for d in cell['devices']};pins=cell['layout_pins'];ports=cell['layout_ports']
    if Counter((v['device_id'],v['pin']) for v in pins)!=Counter((d['id'],pin) for d in devices.values() for pin in d['nets']):
        raise ValueError('Every schematic terminal needs exactly one physical anchor.')
    if Counter(v['name'] for v in ports)!=Counter(cell['ports']):
        raise ValueError('Every top port needs exactly one physical anchor.')
    mapping={v['name']:(v['gds'],v['datatype']) for v in p['pdk']['layers']}
    ly=k.Layout();ly.read(str(gds));top=ly.cell('banba_layout')
    if top is None or len(list(ly.top_cells()))!=1 or abs(ly.dbu-.001)>1e-12:
        raise ValueError('Expected one Banba top cell on the 1 nm grid.')
    def region(number,datatype=0):
        index=ly.find_layer(number,datatype)
        return k.Region() if index is None else k.Region(top.begin_shapes_rec(index))
    netter=k.LayoutToNetlist(top.name,ly.dbu);layers={}
    for number in (34,36,42,46,75,35,38,40):
        shapes=region(number)
        if number in (34,36,42,46):shapes+=region(number,4)
        shapes.merge();layers[number]=shapes;netter.register(shapes,'mask_'+str(number));netter.connect(shapes)
    for lower,via,upper in ((34,35,36),(36,38,42)):
        netter.connect(layers[lower],layers[via]);netter.connect(layers[via],layers[upper])
    # In MIM B, via3 inside FuseTop reaches its upper plate, not underlying M3.
    ordinary=layers[40]-layers[75];mim=layers[40]&layers[75]
    for name,shapes,lower in (('ordinary_via3',ordinary,42),('mim_via3',mim,75)):
        netter.register(shapes,name);netter.connect(shapes);netter.connect(layers[lower],shapes);netter.connect(shapes,layers[40])
    netter.connect(layers[40],layers[46]);netter.extract_netlist()
    def probe(layer,point):
        pair=mapping[layer]
        if pair[1]!=0 or pair[0] not in layers:raise ValueError('Unsupported terminal metal layer.')
        net=netter.probe_net(layers[pair[0]],k.Point(*point))
        return None if net is None else net.cluster_id
    failures=[];anchors=[];expected=defaultdict(set);assigned=defaultdict(set)
    for pin in pins:
        d=devices[pin['device_id']];net=d['nets'][pin['pin']];cluster=probe(pin['layer'],pin['point'])
        row=dict(device=d['name'],pin=pin['pin'],net=net,cluster=cluster);anchors.append(row)
        if cluster is None:failures.append(dict(kind='unlanded-terminal',**row))
        else:expected[net].add(cluster);assigned[cluster].add(net)
    for port in ports:
        cluster=probe(port['layer'],port['point']);row=dict(port=port['name'],cluster=cluster);anchors.append(row)
        if cluster is None:failures.append(dict(kind='unlanded-port',**row))
        else:expected[port['name']].add(cluster);assigned[cluster].add(port['name'])
    for net,clusters in expected.items():
        if len(clusters)>1:failures.append(dict(kind='open',net=net,clusters=sorted(clusters)))
    for cluster,nets in assigned.items():
        if len(nets)>1:failures.append(dict(kind='short',cluster=cluster,nets=sorted(nets)))
    labels=[]
    for name,(number,datatype) in mapping.items():
        if datatype!=10 or number not in (34,36,42,46):continue
        index=ly.find_layer(number,datatype)
        if index is None:continue
        it=top.begin_shapes_rec(index)
        while not it.at_end():
            if it.shape().is_text():
                text=it.shape().text.transformed(it.trans());labels.append((text.string,number,text.x,text.y))
            it.next()
    wanted=[(v['name'],mapping[v['layer']][0],*v['point']) for v in ports]
    if Counter(labels)!=Counter(wanted):failures.append(dict(kind='changed-port-labels',actual=labels,expected=wanted))
    # These reference MOS/resistor body footprints promise a contact at the
    # explicit anchor. Other substrate taps cannot stand in for a missing one.
    contacts=region(33);tap_contacts=0
    for pin in pins:
        d=devices[pin['device_id']]
        body_device=d['kind'] in ('NMOS','PMOS') or d.get('model_ref',{}).get('device')=='symbols/ppolyf_u_1k.sym'
        if pin['pin']!='b' or not body_device:continue
        x,y=pin['point'];tap_contacts+=1
        if (contacts&k.Region(k.Box(x-1,y-1,x+1,y+1))).area()!=4:
            failures.append(dict(kind='missing-body-contact',device=d['name'],point_nm=[x,y]))
    logs=[str(v) for v in netter.each_log_entry()]
    if logs:failures.append(dict(kind='metal-extraction-diagnostics',messages=logs))
    if hashes!={str(p):file_digest(p) for p in (gds,project)}:raise ValueError('Input changed during connectivity checking.')
    return dict(schema=1,passed=not failures,qualified=False,scope=__doc__,gds_sha256=hashes[str(gds)],project_sha256=hashes[str(project)],
        engine_version=k.__version__,terminals=len(pins),ports=len(ports),body_contacts=tap_contacts,anchors=anchors,
        failure_counts=dict(Counter(f['kind'] for f in failures)),failures=failures,extraction_logs=logs)
