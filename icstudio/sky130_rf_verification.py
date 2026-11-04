"""Bounded, explicit-mask SKY130 RF n-well diode verification.

Only one rectangular ps2nw junction with a contacted substrate ring is accepted.
Written LI/M1 connectivity is proved before joining taps to physical body domains.
No implicit labels, device filtering, reference-driven extraction or mask removal.
This does not cover pw2dn, multi-device layouts, parasitics or fabrication signoff.
"""
import json
import math
from pathlib import Path
import re
import shutil

from .model import atomic_write, file_digest, scalar

MODEL = 'sky130_fd_pr__model__parasitic__rf_diode_ps2nw'
MASKS = dict(NW=(64,20), RF=(81,125), TAP=(65,44), NS=(93,44), PS=(94,20),
             LC=(66,44), LI=(67,20), MC=(67,44), M1=(68,20))
RULE_SOURCE = 'https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html#rfdiode'


def assets():
    from .digital_sky130_native import resources
    root = resources()
    return {n: root/n for n in ('sky130A_mr.drc', 'GPL-3.0.txt', 'categories.json')}


def copy_assets(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for name,path in assets().items():
        shutil.copyfile(path,destination/name)
        if file_digest(destination/name)!=file_digest(path):raise ValueError('RF rule transfer changed '+name)


def contacts(source, top, ports):
    """Audit every tap/contact and terminal using metal-only connectivity."""
    import klayout.db as k
    source = Path(source); before = file_digest(source)
    ly = k.Layout(); ly.read(str(source)); cell = ly.cell(top)
    if cell is None or any(cell.each_inst()) or abs(ly.dbu-.001)>1e-12:
        raise ValueError('RF verification requires a flat layout on the 1 nm grid.')
    if len(ports)!=2 or len({p.casefold() for p in ports})!=2:
        raise ValueError('RF n-well verification requires two distinct explicit terminals.')
    allowed = set(MASKS.values()) | {(68,5),(68,16)}
    failures=[]
    for index in ly.layer_indexes():
        info=ly.get_info(index); pair=(info.layer,info.datatype)
        for shape in cell.shapes(index).each():
            if pair not in allowed or (shape.is_text() and pair not in {(68,5),(68,16)}):
                failures.append(dict(kind='unsupported-mask-or-text',layer=list(pair)))
                break
    def region(pair):
        index=ly.find_layer(*pair)
        return k.Region() if index is None else k.Region([
            s.polygon for s in cell.shapes(index).each() if not s.is_text()]).merged()
    r={name:region(pair) for name,pair in MASKS.items()}
    nw,rf=r['NW'],r['RF']
    rectangles=list(nw.each())
    rectangular=len(rectangles)==1 and rectangles[0].is_box()
    if not rectangular:failures.append(dict(kind='requires-one-rectangular-nwell'))
    if rf.is_empty() or not (rf^nw).is_empty():
        failures.append(dict(kind='rf-marker-must-equal-nwell',rule='rfdiode.2'))
    if any(not p.is_box() for p in rf.each()):
        failures.append(dict(kind='rf-marker-must-be-rectangular',rule='rfdiode.1'))
    # Pin-purpose polygons are annotations, never extra electrical conductor.
    if not ((region((68,16))|region((68,5)))-r['M1']).is_empty():
        failures.append(dict(kind='pin-geometry-without-metal'))
    nt=(r['TAP'] & r['NS'] & nw).merged()
    pt=((r['TAP'] & r['PS'])-nw).merged()
    if not (r['TAP']-(nt|pt)).is_empty() or not (r['NS']&r['PS']).is_empty():
        failures.append(dict(kind='unclassified-or-ambiguous-tap'))
    holes=k.Region()
    for p in pt.each():
        for i in range(p.holes()):holes.insert(k.Polygon(list(p.each_point_hole(i))))
    if pt.count()!=1 or holes.count()!=1 or not (nw-holes).is_empty():
        failures.append(dict(kind='missing-continuous-substrate-ring'))
    if not (r['LC']-(nt|pt)).is_empty() or not (r['LC']-r['LI']).is_empty():
        failures.append(dict(kind='licon-without-tap-or-local-interconnect'))
    if not (r['MC']-r['LI']).is_empty() or not (r['MC']-r['M1']).is_empty():
        failures.append(dict(kind='mcon-without-both-metals'))
    # Diffusion, implants, wells, substrate, licon and text NEVER join these nets.
    netter=k.LayoutToNetlist(cell.name,ly.dbu)
    for name in ('LI','MC','M1'):
        netter.register(r[name],name);netter.connect(r[name])
    netter.connect(r['LI'],r['MC']);netter.connect(r['MC'],r['M1'])
    netter.extract_netlist();netter.check_extraction_errors()
    def probe(layer,point):
        net=netter.probe_net(r[layer],point)
        return None if net is None else net.cluster_id
    labels={}
    for pair in ((68,5),(68,16)):
        index=ly.find_layer(*pair)
        if index is None:continue
        for shape in cell.shapes(index).each():
            if not shape.is_text():continue
            t=shape.text
            labels.setdefault(t.string,[]).append(probe('M1',k.Point(t.x,t.y)))
    if set(labels)!=set(ports):failures.append(dict(kind='unexpected-or-missing-port',actual=sorted(labels)))
    for name,nets in labels.items():
        if None in nets or len(set(nets))!=1:
            failures.append(dict(kind='disconnected-port-metal',port=name,nets=nets))
    port_nets={name:nets[0] for name,nets in labels.items() if nets and None not in nets and len(set(nets))==1}
    if len(set(port_nets.values()))!=2:failures.append(dict(kind='shorted-or-disconnected-terminals'))
    domains=[];terminal_roles={}
    for name,taps in (('anode',pt),('cathode',nt)):
        nets=[];count=0
        if taps.is_empty():failures.append(dict(kind='missing-tap',domain=name))
        for tap in taps.each():
            cuts=r['LC'].inside(k.Region(tap))
            if cuts.is_empty():failures.append(dict(kind='uncontacted-tap',domain=name))
            for cut in cuts.each():
                count+=1;nets.append(probe('LI',cut.bbox().center()))
        matches=[p for p,n in port_nets.items() if nets and set(nets)=={n}]
        if None in nets or len(matches)!=1:
            failures.append(dict(kind='disconnected-tap-metal',domain=name,nets=nets))
        else:terminal_roles[name]=matches[0]
        domains.append(dict(domain=name,tap_components=taps.count(),contacts=count,metal_nets=nets))
    if len(set(terminal_roles.values()))!=2:failures.append(dict(kind='ambiguous-terminal-roles'))
    # A floating metal island is not silently omitted from the bounded coupon.
    net_ids={n.cluster_id for c in netter.netlist().each_circuit() for n in c.each_net()}
    if net_ids!=set(port_nets.values()):failures.append(dict(kind='unaccounted-metal-net',nets=sorted(net_ids)))
    messages=[str(e) for e in netter.each_log_entry()]
    if messages:failures.append(dict(kind='metal-extraction-diagnostics',messages=messages))
    if file_digest(source)!=before:raise ValueError('RF layout changed during contact checking.')
    return dict(schema=1,passed=not failures,qualified=False,gds_sha256=before,failures=failures,
                domains=domains,port_metal=labels,terminal_roles=terminal_roles,
                junction=dict(area_um2=nw.area()*ly.dbu**2,perimeter_um=nw.perimeter()*ly.dbu),
                engine_version=k.__version__,rule_source=RULE_SOURCE,
                scope='One rectangular RF n-well diode with a continuous contacted substrate ring; written LI/M1 connectivity only.')


RECIPE = '''source($input)
report_lvs($report)
target_netlist($automatic)
flat
NW=polygons(64,20)
RF=polygons(81,125)
TAP=polygons(65,44)
NS=polygons(93,44)
PS=polygons(94,20)
LC=polygons(66,44)
LI=polygons(67,20)
MC=polygons(67,44)
M1=polygons(68,20)
LABEL=labels(68,5)+labels(68,16)
SUB=extent.sized(1.0)
NT=TAP & NS & NW
PT=(TAP & PS)-NW
selected=NW & RF
TA=polygon_layer
TC=polygon_layer
d=extract_devices(diode("rf_ps2nw"), {"P"=>SUB,"N"=>selected,"tA"=>TA,"tC"=>TC})
d.enable_parameter("A",true)
d.enable_parameter("P",true)
# Hard body joins are allowed only AFTER the independent written-contact audit.
connect(SUB,SUB)
connect(NW,NW)
connect(TA,SUB)
connect(TC,NW)
connect(PT,SUB)
connect(NT,NW)
connect(PT,LC)
connect(NT,LC)
connect(LC,LI)
connect(LI,MC)
connect(MC,M1)
connect(M1,LABEL)
top_level(true)
netlist
l2n_data.check_extraction_errors
netlist.make_top_level_pins
writer=RBA::NetlistSpiceWriter.new
writer.use_net_names=true
netlist.write($native,writer)
l2n_data.write_l2n($native+".l2n")
puts "ICSTUDIO_RF_NWELL_EXTRACTION_COMPLETE"
'''


def circuit(text, top, native=False):
    """Strict one-device grammar: no ignored directives, parameters or elements."""
    lines=[s.split() for s in re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines()
           if s.strip() and not s.lstrip().startswith('*')]
    if (len(lines)!=3 or len(lines[0])!=4 or lines[0][0].lower()!='.subckt'
            or lines[0][1].casefold()!=top.casefold()
            or lines[-1][0].lower()!='.ends' or len(lines[-1]) not in (1,2)
            or (len(lines[-1])==2 and lines[-1][1].casefold()!=top.casefold())):
        raise ValueError('RF comparison needs exactly one flat two-terminal subcircuit and one device.')
    pins=lines[0][2:]; row=lines[1]; keys=('a','p') if native else ('area','perim')
    if (len({p.casefold() for p in pins})!=2 or len(row)!=6
            or row[0][0].upper()!=('D' if native else 'X')
            or row[3].casefold()!=('rf_ps2nw' if native else MODEL).casefold()
            or {v.casefold() for v in row[1:3]}!={p.casefold() for p in pins}
            or any('=' not in v for v in row[4:])):
        raise ValueError('Unexpected RF device, model, terminal or parameter count.')
    params={k.casefold():v for k,v in (s.split('=',1) for s in row[4:])}
    if set(params)!=set(keys):raise ValueError('RF area and perimeter must each occur exactly once.')
    values=[scalar(params[key]) for key in keys]
    if not all(math.isfinite(v) and v>0 for v in values):raise ValueError('Invalid RF geometry.')
    if native:values=[values[0]*1e12,values[1]*1e6]
    return dict(ports=pins,terminals=row[1:3],model=MODEL,area_um2=values[0],perimeter_um=values[1])


def compare(reference_text, extracted_text, top):
    wanted=circuit(reference_text,top);actual=circuit(extracted_text,top)
    for key in ('ports','terminals'):
        if [v.casefold() for v in wanted[key]]!=[v.casefold() for v in actual[key]]:
            raise ValueError('RF strict LVS '+key+' mismatch.')
    for key in ('area_um2','perimeter_um'):
        if not math.isclose(wanted[key],actual[key],rel_tol=1e-10,abs_tol=1e-10):
            raise ValueError('RF strict LVS '+key+' mismatch.')
    return dict(unique_match=True,comparison='Strict complete single-device graph and area/perimeter; no black boxes or parameter filtering.',reference=wanted,extracted=actual)


def _execute(executable, recipe, settings, folder):
    from .engines import execute
    args=[str(executable),'-b','-r',str(recipe)]
    for key,value in settings.items():args+=['-rd',key+'='+str(value)]
    atomic_write(folder/'command.json',json.dumps(args,indent=2))
    try:log=execute(args,folder,timeout=300)
    except Exception as exc:atomic_write(folder/'console.log',str(exc));raise
    atomic_write(folder/'console.log',log)
    if re.search(r'(?m)^ERROR:',log):raise ValueError('RF native engine reported an error; see console.log.')
    return log


def drc(executable, source, top, technology, folder):
    from .digital_sky130_native import FLAGS, measured, DECK_SHA256, REVISION
    folder=Path(folder);folder.mkdir();bundle=assets()
    for name,path in bundle.items():shutil.copyfile(path,folder/name)
    checks={p:file_digest(p) for p in [Path(source),*bundle.values(),*(folder/n for n in bundle)]}
    settings=dict(input=Path(source).resolve(),top_cell=top,report=folder/'report.lyrdb',thr='1',**FLAGS)
    log=_execute(executable,folder/'sky130A_mr.drc',settings,folder)
    if log.splitlines().count('release 2026.03.30_01.00')!=1:raise ValueError('RF full public DRC did not complete.')
    result=measured(folder/'report.lyrdb',top)
    if any(file_digest(p)!=sha for p,sha in checks.items()):raise ValueError('RF DRC inputs changed.')
    return dict(violations=result['markers'],rules=result['violations'],categories=result['categories'],
                source_commit=REVISION,deck_sha256=DECK_SHA256,settings={k:str(v) for k,v in settings.items()})


def extract(executable, source, top, ports, technology, folder):
    from .ihp_klayout_lvs import order_top_ports
    folder=Path(folder);folder.mkdir();proof=contacts(source,top,ports)
    atomic_write(folder/'contacts.json',json.dumps(proof,indent=2))
    if not proof['passed']:raise ValueError('RF recognition/contact audit failed; see contacts.json.')
    recipe=folder/'extract.lvs';atomic_write(recipe,RECIPE)
    hashes={p:file_digest(p) for p in (Path(source),recipe)}
    settings=dict(input=Path(source).resolve(),report=folder/'extraction.lvsdb',automatic=folder/'automatic.cir',native=folder/'native.cir')
    log=_execute(executable,recipe,settings,folder)
    if log.splitlines().count('ICSTUDIO_RF_NWELL_EXTRACTION_COMPLETE')!=1:raise ValueError('RF native extraction did not complete.')
    raw=(folder/'native.cir').read_text(encoding='utf-8')
    raw,order=order_top_ports(raw,top,ports);device=circuit(raw,top,native=True)
    if device['terminals']!=[proof['terminal_roles'][key] for key in ('anode','cathode')]:
        raise ValueError('RF native terminals disagree with written-metal proof.')
    for key in ('area_um2','perimeter_um'):
        if not math.isclose(device[key],proof['junction'][key],rel_tol=1e-10,abs_tol=1e-10):
            raise ValueError('RF native junction geometry disagrees with independent mask measurement.')
    a,k=device['terminals']
    converted=f'.subckt {top} {" ".join(ports)}\nX1 {a} {k} {MODEL} area={device["area_um2"]:.17g} perim={device["perimeter_um"]:.17g}\n.ends {top}\n'
    output=folder/'extracted.spice';atomic_write(output,converted)
    if any(file_digest(p)!=sha for p,sha in hashes.items()):raise ValueError('RF extraction inputs changed.')
    return dict(deck='lvs-extraction/extracted.spice',sha256=file_digest(output),native_sha256=file_digest(folder/'native.cir'),
                recipe_sha256=file_digest(recipe),contacts=proof,top_port_order=order,
                conversion='Single native D rf_ps2nw to public X model; SI area/perimeter converted to um^2/um; all terminals and measured parameters preserved.')
