"""Three-terminal RF pw2dn geometry/connectivity verification.

The three native diodes below are planar geometry records, NOT simulation
models. In particular, the n-well skirt perimeter includes its inner boundary;
it must not be fed to a junction capacitance model as an electrical perimeter.
No substrate junction is removed or collapsed into the two-terminal RF model.
"""
import json
import math
from pathlib import Path
import re

from .model import atomic_write, file_digest, scalar
from .sky130_rf_verification import MASKS as NW_MASKS, RULE_SOURCE, _execute

MASKS = dict(NW_MASKS, DNW=(64, 18))
MODELS = ('rf_pw2dn_geometry', 'isolation_dnwell_geometry', 'isolation_nwell_skirt_geometry')
SCOPE = ('One rectangular RF p-well in a deep n-well with contacted n-well and '
         'substrate rings. Public block DRC and complete three-terminal planar '
         'geometry/connectivity comparison only; no electrical isolation model, '
         'parasitic accuracy, arbitrary circuits or fabrication qualification.')


def contacts(source, top, ports):
    import klayout.db as k
    source = Path(source); before = file_digest(source)
    ly = k.Layout(); ly.read(str(source)); cell = ly.cell(top)
    if cell is None or any(cell.each_inst()) or abs(ly.dbu-.001)>1e-12:
        raise ValueError('RF isolation requires a flat layout on the 1 nm grid.')
    if len(ports)!=3 or len({p.casefold() for p in ports})!=3:
        raise ValueError('RF isolation requires three distinct explicit terminals.')
    failures=[]
    allowed=set(MASKS.values())|{(68,5),(68,16)}
    for index in ly.layer_indexes():
        info=ly.get_info(index); pair=(info.layer,info.datatype)
        for shape in cell.shapes(index).each():
            if pair not in allowed or (shape.is_text() and pair not in {(68,5),(68,16)}):
                failures.append(dict(kind='unsupported-mask-or-text',layer=list(pair)));break
    def region(pair):
        index=ly.find_layer(*pair)
        return k.Region() if index is None else k.Region([
            s.polygon for s in cell.shapes(index).each() if not s.is_text()]).merged()
    r={name:region(pair) for name,pair in MASKS.items()}
    nw,rf,dnw=(r[name] for name in ('NW','RF','DNW'))
    def rectangular(a):
        return a.count()==1 and next(a.each()).is_box()
    def holes(a):
        result=k.Region()
        for p in a.each():
            for i in range(p.holes()):result.insert(k.Polygon(list(p.each_point_hole(i))))
        return result.merged()
    hole=holes(nw);outer=(nw|hole).merged()
    if nw.count()!=1 or hole.count()!=1 or not rectangular(outer):
        failures.append(dict(kind='requires-one-rectangular-nwell-ring'))
    if not rectangular(rf) or not (rf^hole).is_empty():
        failures.append(dict(kind='rf-marker-must-equal-nwell-hole',rule='rfdiode.1/.3'))
    if (not rectangular(dnw) or not (rf-dnw).is_empty()
            or not (dnw-outer).is_empty() or (dnw&nw).is_empty()
            or (nw-dnw).is_empty()):
        failures.append(dict(kind='requires-deep-well-overlap-and-exposed-nwell-skirt'))
    if not ((dnw-nw)^rf).is_empty():
        failures.append(dict(kind='unaccounted-pwell-region'))
    nt=(r['TAP']&r['NS']&nw).merged()
    pa=(r['TAP']&r['PS']&rf).merged()
    ps=((r['TAP']&r['PS'])-outer).merged()
    if not (r['TAP']-(nt|pa|ps)).is_empty() or not (r['NS']&r['PS']).is_empty():
        failures.append(dict(kind='unclassified-or-ambiguous-tap'))
    for name,taps,enclosed in (('cathode',nt,rf),('substrate',ps,outer)):
        h=holes(taps)
        if taps.count()!=1 or h.count()!=1 or not (enclosed-h).is_empty():
            failures.append(dict(kind='missing-continuous-contact-ring',domain=name))
    if not ((region((68,16))|region((68,5)))-r['M1']).is_empty():
        failures.append(dict(kind='pin-geometry-without-metal'))
    if not (r['LC']-(nt|pa|ps)).is_empty() or not (r['LC']-r['LI']).is_empty():
        failures.append(dict(kind='licon-without-tap-or-local-interconnect'))
    if not (r['MC']-r['LI']).is_empty() or not (r['MC']-r['M1']).is_empty():
        failures.append(dict(kind='mcon-without-both-metals'))
    # Only written conductors may establish contact continuity. Wells, taps,
    # implants, substrate, contact labels and the reference cannot heal opens.
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
            if shape.is_text():
                t=shape.text;labels.setdefault(t.string,[]).append(probe('M1',k.Point(t.x,t.y)))
    if set(labels)!=set(ports):failures.append(dict(kind='unexpected-or-missing-port',actual=sorted(labels)))
    for name,nets in labels.items():
        if None in nets or len(set(nets))!=1:
            failures.append(dict(kind='disconnected-port-metal',port=name,nets=nets))
    port_nets={name:nets[0] for name,nets in labels.items() if nets and None not in nets and len(set(nets))==1}
    if len(set(port_nets.values()))!=3:failures.append(dict(kind='shorted-or-disconnected-terminals'))
    domains=[];roles={}
    for name,taps in (('anode',pa),('cathode',nt),('substrate',ps)):
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
        else:roles[name]=matches[0]
        domains.append(dict(domain=name,tap_components=taps.count(),contacts=count,metal_nets=nets))
    if len(set(roles.values()))!=3:failures.append(dict(kind='ambiguous-terminal-roles'))
    net_ids={n.cluster_id for c in netter.netlist().each_circuit() for n in c.each_net()}
    if net_ids!=set(port_nets.values()):failures.append(dict(kind='unaccounted-metal-net',nets=sorted(net_ids)))
    messages=[str(e) for e in netter.each_log_entry()]
    if messages:failures.append(dict(kind='metal-extraction-diagnostics',messages=messages))
    if file_digest(source)!=before:raise ValueError('RF isolation layout changed during checking.')
    geometry={name:dict(area_um2=a.area()*ly.dbu**2,perimeter_um=a.perimeter()*ly.dbu)
              for name,a in zip(MODELS,(rf,dnw,(nw-dnw).merged()))}
    return dict(schema=1,passed=not failures,qualified=False,gds_sha256=before,
                failures=failures,domains=domains,port_metal=labels,terminal_roles=roles,
                geometry=geometry,engine_version=k.__version__,rule_source=RULE_SOURCE,scope=SCOPE)


RECIPE='''source($input)
report_lvs($report)
target_netlist($automatic)
flat
NW=polygons(64,20)
DNW=polygons(64,18)
RF=polygons(81,125)
TAP=polygons(65,44)
NS=polygons(93,44)
PS=polygons(94,20)
LC=polygons(66,44)
LI=polygons(67,20)
MC=polygons(67,44)
M1=polygons(68,20)
LABEL=labels(68,5)+labels(68,16)
PW=DNW-NW
SKIRT=NW-DNW
SUB=extent.sized(1.0)
OUTSIDE=SUB-(DNW+NW)
PA=TAP & PS & PW
NT=TAP & NS & NW
PT=TAP & PS & OUTSIDE
TA=polygon_layer
TK=polygon_layer
TS1=polygon_layer
TN1=polygon_layer
TS2=polygon_layer
TN2=polygon_layer
[["rf_pw2dn_geometry",PW,DNW,TA,TK],
 ["isolation_dnwell_geometry",SUB,DNW,TS1,TN1],
 ["isolation_nwell_skirt_geometry",SUB,SKIRT,TS2,TN2]].each do |name,p,n,a,c|
  d=extract_devices(diode(name), {"P"=>p,"N"=>n,"tA"=>a,"tC"=>c})
  d.enable_parameter("A",true)
  d.enable_parameter("P",true)
end
# Body-domain joins are authorized only by the preceding metal-contact proof.
connect(PW,PW)
connect(DNW,DNW)
connect(NW,NW)
connect(DNW,NW)
connect(SUB,SUB)
connect(TA,PW)
connect(TK,DNW)
connect(TS1,SUB)
connect(TS2,SUB)
connect(TN1,DNW)
connect(TN2,NW)
connect(PA,PW)
connect(NT,NW)
connect(PT,SUB)
connect(PA,LC)
connect(NT,LC)
connect(PT,LC)
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
puts "ICSTUDIO_RF_ISOLATION_GEOMETRY_COMPLETE"
'''


def circuit(text,top,native=False):
    """Entire three-device planar graph, with no simulation-model substitution."""
    from .model import NAME, NET
    lines=[s.split() for s in re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines()
           if s.strip() and not s.lstrip().startswith('*')]
    if (not NAME.fullmatch(top) or len(lines)!=5 or len(lines[0])!=5
            or lines[0][0].lower()!='.subckt' or lines[0][1].casefold()!=top.casefold()
            or lines[-1][0].lower()!='.ends' or len(lines[-1]) not in (1,2)
            or (len(lines[-1])==2 and lines[-1][1].casefold()!=top.casefold())):
        raise ValueError('RF isolation needs exactly three ports and three geometry records.')
    pins=lines[0][2:]; pinset={p.casefold() for p in pins}; records={};names=set()
    if len(pinset)!=3 or any(not NET.fullmatch(p) for p in pins):raise ValueError('Invalid RF isolation ports.')
    keys=('a','p') if native else ('area','perim')
    for row in lines[1:-1]:
        if (len(row)!=6 or row[0][0].upper()!='D' or row[0].casefold() in names
                or row[3].casefold() not in MODELS or row[3].casefold() in records
                or len({v.casefold() for v in row[1:3]})!=2
                or not {v.casefold() for v in row[1:3]}<=pinset
                or any('=' not in v for v in row[4:])):
            raise ValueError('Unexpected RF isolation geometry record or terminal.')
        names.add(row[0].casefold());params={k.casefold():v for k,v in (s.split('=',1) for s in row[4:])}
        if set(params)!=set(keys):raise ValueError('RF isolation needs explicit unique area and perimeter.')
        values=[scalar(params[key]) for key in keys]
        if not all(math.isfinite(v) and v>0 for v in values):raise ValueError('Invalid RF isolation geometry.')
        if native:values=[values[0]*1e12,values[1]*1e6]
        records[row[3].casefold()]=dict(terminals=row[1:3],area_um2=values[0],perimeter_um=values[1])
    # Three distinct domains; both isolation footprints share S/K, not A/K.
    rf,dnw,skirt=(records[m]['terminals'] for m in MODELS)
    if (dnw!=skirt or rf[1].casefold()!=dnw[1].casefold()
            or {p.casefold() for p in (*rf,*dnw)}!=pinset):
        raise ValueError('RF isolation requires separate anode, cathode and substrate domains.')
    return dict(ports=pins,records=records,simulation_models=False)


def compare(reference_text,extracted_text,top):
    wanted=circuit(reference_text,top);actual=circuit(extracted_text,top)
    if [p.casefold() for p in wanted['ports']]!=[p.casefold() for p in actual['ports']]:
        raise ValueError('RF isolation strict comparison ports mismatch.')
    for model in MODELS:
        a,b=wanted['records'][model],actual['records'][model]
        if [p.casefold() for p in a['terminals']]!=[p.casefold() for p in b['terminals']]:
            raise ValueError('RF isolation strict comparison polarity mismatch.')
        for key in ('area_um2','perimeter_um'):
            if not math.isclose(a[key],b[key],rel_tol=1e-10,abs_tol=1e-10):
                raise ValueError('RF isolation strict comparison '+model+' '+key+' mismatch.')
    return dict(unique_match=True,qualified=False,scope=SCOPE,reference=wanted,extracted=actual)


def extract(executable,source,top,ports,technology,folder):
    from .ihp_klayout_lvs import order_top_ports
    folder=Path(folder);folder.mkdir();proof=contacts(source,top,ports)
    atomic_write(folder/'contacts.json',json.dumps(proof,indent=2))
    if not proof['passed']:raise ValueError('RF isolation contact audit failed; see contacts.json.')
    recipe=folder/'extract.lvs';atomic_write(recipe,RECIPE)
    hashes={p:file_digest(p) for p in (Path(source),recipe)}
    settings=dict(input=Path(source).resolve(),report=folder/'extraction.lvsdb',automatic=folder/'automatic.cir',native=folder/'native.cir')
    log=_execute(executable,recipe,settings,folder)
    if log.splitlines().count('ICSTUDIO_RF_ISOLATION_GEOMETRY_COMPLETE')!=1:
        raise ValueError('RF isolation native extraction did not complete.')
    raw=(folder/'native.cir').read_text(encoding='utf-8');raw,order=order_top_ports(raw,top,ports)
    actual=circuit(raw,top,native=True);roles=proof['terminal_roles'];rows=[]
    for i,model in enumerate(MODELS):
        measured=actual['records'][model]
        expected=[roles['anode' if i==0 else 'substrate'],roles['cathode']]
        if measured['terminals']!=expected:raise ValueError('RF isolation native terminals disagree with metal proof.')
        for key in ('area_um2','perimeter_um'):
            if not math.isclose(measured[key],proof['geometry'][model][key],rel_tol=1e-10,abs_tol=1e-10):
                raise ValueError('RF isolation native geometry disagrees with mask measurement.')
        rows.append(f'D{i+1} {" ".join(expected)} {model} area={measured["area_um2"]:.17g} perim={measured["perimeter_um"]:.17g}')
    converted='* Planar geometry records only; NOT a simulation deck.\n'+f'.subckt {top} {" ".join(ports)}\n'+'\n'.join(rows)+f'\n.ends {top}\n'
    output=folder/'extracted.spice';atomic_write(output,converted)
    if any(file_digest(p)!=sha for p,sha in hashes.items()):raise ValueError('RF isolation extraction inputs changed.')
    return dict(deck='lvs-extraction/extracted.spice',sha256=file_digest(output),native_sha256=file_digest(folder/'native.cir'),
                recipe_sha256=file_digest(recipe),contacts=proof,top_port_order=order,simulation_models=False,scope=SCOPE)
