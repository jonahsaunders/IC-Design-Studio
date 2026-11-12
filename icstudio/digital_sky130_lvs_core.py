"""Strict SKY130 HD reference conversion, mask-preserving labels and native audit.

Application version of the previously tested Studio qualification adapters in
scripts/{ihp_lvs_reference,sky130_lvs_reference,sky130_diode_lvs,check_ihp_lvs,
check_sky130_lvs}. Historical scripts retain their original source identities.
"""
from collections import Counter
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import klayout.db as k

MASTERS_SHA256 = 'ae02cdc40c81943bbc3f4a16a6760e01afd12764a94e7836b7e168edf40ae29c'
PVT_MASTERS_SHA256 = '35bdf5f2cd1c5d841dcc3d0fe4c34b3f0e8c57a3e25282aa1d716ad7cf2a1aa6'
DECK_SHA256 = '1afade11dd24ea4e64d1ffba54fc17a8f110286712ab942928d2f5e021bb3caf'
PORT_PATTERN = 'N' + '[0-9]' * 7
CELL = 'sky130_fd_sc_hd__diode_2'
MODEL = 'sky130_fd_pr__diode_pw2nd_05v5'
SPICE_SHA256 = '67b980af74314791f0ea796118c740730958e5cb7083d58acab20c17781bee45'
GDS_SHA256 = '7198f35a0a4bde6ba7155242c567b21644b04696c39734b604490c09e6709c90'
ASSETS = Path(__file__).parent/'assets/verification/sky130/lvs'


def require(condition, message):
    if not condition:
        raise ValueError(message)

def logical_lines(text):
    lines = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('*'):
            continue
        if line.lstrip().startswith('+'):
            require(bool(lines), 'Orphan CDL continuation.')
            lines[-1] += ' ' + line.lstrip()[1:].strip()
        else:
            lines.append(line.strip())
    return lines

def master_pins(text):
    masters = {}
    for line in logical_lines(text):
        tokens = line.split()
        if tokens[0].upper() == '.SUBCKT':
            require(len(tokens) >= 2 and tokens[1] not in masters, 'Repeated master definition.')
            require(all(re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in tokens[1:]),
                    'Master naming needs a separate adapter.')
            masters[tokens[1]] = tokens[2:]
    require(bool(masters), 'No CDL master definitions.')
    return masters

def encode_reference(raw, masters, database):
    """Check every exported instance terminal against OpenDB, then encode."""
    lines = logical_lines(raw)
    require(len(lines) >= 2 and lines[0].split()[0].upper() == '.SUBCKT' and
            lines[-1].split()[0].upper() == '.ENDS', 'Expected one complete top-level CDL circuit.')
    header = lines[0].split()
    top = database['top']
    require(header[1] == top, 'CDL top differs from the captured checkpoint.')
    ports = header[2:]
    port_names = [p['name'] for p in database['ports']]
    require(len(set(ports)) == len(ports) and set(ports) == set(port_names), 'CDL ports differ from OpenDB.')
    port_nets = {p['net']: p['name'] for p in database['ports']}
    require('' not in port_nets and len(port_nets) == len(port_names),
            'Disconnected or multiply aliased boundary ports need a separate adapter.')
    cells = master_pins(masters)
    instances = {i['name']: i for i in database['database']['instances']}
    require(len(instances) == len(database['database']['instances']), 'Repeated OpenDB instance names.')
    parsed = []; disconnected = {}
    connected_names = {p['net'] for i in instances.values() for p in i['pins'] if p['net']} | set(port_nets)
    nets = set(ports)
    seen = set()
    for line in lines[1:-1]:
        tokens = line.split()
        require(len(tokens) >= 3 and tokens[0].startswith('X'), 'Unexpected top-level CDL element.')
        name, master = tokens[0][1:], tokens[-1]
        require(name in instances and name not in seen and master in cells, 'Unknown or repeated CDL instance.')
        inst = instances[name]
        require(inst['master'] == master, 'CDL master differs from OpenDB.')
        pin_names = cells[master]
        values = tokens[1:-1]
        require(len(values) == len(pin_names), 'CDL instance arity differs from its master.')
        actual = {p['name']: p['net'] for p in inst['pins']}
        require(len(actual) == len(inst['pins']) and set(pin_names) == set(actual), 'Master pins differ from OpenDB.')
        for p, n in zip(pin_names, values):
            if actual[p]:
                require(port_nets.get(actual[p], actual[p]) == n,
                        'CDL terminal differs from the preserved implementation.')
            else:
                require(re.fullmatch(r'_unconnected_\d+', n) is not None and
                        n not in connected_names and n not in ports and n not in disconnected,
                        'A disconnected terminal was shorted or given an ambiguous name.')
                disconnected[n] = dict(instance=name, pin=p)
        seen.add(name); nets.update(values); parsed.append((name, values, master))
    require(seen == set(instances), 'CDL omitted implementation instances, including fillers.')
    uses = Counter(n for _, values, _ in parsed for n in values)
    require(all(uses[n] == 1 for n in disconnected), 'A disconnected terminal was connected to another instance.')
    net_map = {name: 'N' + str(i).zfill(7) for i, name in enumerate(sorted(nets))}
    inst_map = {name: 'I' + str(i).zfill(7) for i, name in enumerate(sorted(instances))}
    output = ['* Lossless top naming; see aliases.json.', '.SUBCKT ' + top + ' ' + ' '.join(net_map[p] for p in ports)]
    output += ['X' + inst_map[name] + ' ' + ' '.join(net_map[n] for n in values) + ' ' + master
               for name, values, master in parsed]
    output += ['.ENDS ' + top, '', masters]
    mapping = dict(schema=1, top=top, nets=net_map, instances=inst_map,
                   ports={p: net_map[p] for p in ports}, source_cdl_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                   masters_sha256=hashlib.sha256(masters.encode()).hexdigest(),
                   boundary_net_names=port_nets, disconnected_terminals=disconnected,
                   checked_instances=len(parsed), checked_terminals=sum(len(v) for _, v, _ in parsed))
    return '\n'.join(output) + '\n', mapping

def prepare_reference(raw, masters_bytes, database):
    """Bind the exact HD library before interpreting unitless CDL dimensions."""
    normalized = masters_bytes.replace(b'\r\n', b'\n')
    require(hashlib.sha256(normalized).hexdigest() in (MASTERS_SHA256, PVT_MASTERS_SHA256),
            'Unreviewed SKY130 master library; units and devices need qualification.')
    encoded, aliases = encode_reference(raw, normalized.decode('utf-8'), database)
    pins = master_pins(encoded)
    fixed = []
    separators = 0
    for line in logical_lines(encoded):
        tokens = line.split()
        if tokens[0].startswith('X') and '/' in tokens:
            require(tokens.count('/') == 1 and tokens[-2] == '/', 'Ambiguous CDL separator.')
            tokens.pop(-2)
            require(tokens[-1] in pins and len(tokens) - 2 == len(pins[tokens[-1]]),
                    'CDL separator conversion changed terminal arity.')
            line = ' '.join(tokens)
            separators += 1
        fixed.append(line)
    # KLayout 0.30.5 accepts this numeric scale. A '1u' scale is ignored by
    # its options parser; the retained native diagnostic demonstrates that.
    reference = ('* Lossless SKY130 top naming and CDL separator conversion; CDL dimensions are micrometres.\n'
                 '.options scale=1e-6\n' + '\n'.join(fixed) + '\n')
    return reference, aliases, dict(
        upstream_masters_sha256=hashlib.sha256(masters_bytes).hexdigest(),
        normalized_masters_sha256=hashlib.sha256(normalized).hexdigest(),
        cdl_separators_removed=separators, dimension_scale=1e-6)

def transistor_deck(upstream_bytes, top):
    """Adapt the exact reference deck; no global supply ties or pin equivalences.

    The tested scope is the HD standard-cell references, not all SKY130 devices.
    The native graph is flattened so real taps outside an individual cell can
    establish its body connection. Soft connections reject use of wells or
    substrate as substitutes for metal supply wiring.
    """
    require(hashlib.sha256(upstream_bytes.replace(b'\r\n', b'\n')).hexdigest() == DECK_SHA256, 'Unreviewed SKY130 LVS deck.')
    require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top) is not None, 'Unsupported top name.')
    code = ET.fromstring(upstream_bytes).findtext('text')
    # The captured ORFS deck is the BSD-2-Clause original with only these
    # interface substitutions. Keep the original source and license with every
    # execution, rather than inferring a platform license from ORFS scripts.
    original = ET.parse(ASSETS/'original.lylvs').findtext('text')
    for old, new in (('$input', '$in_gds'), ('$report', '$report_file'),
                     ('$schematic', '$cdl_file'), ('input=my_layout', 'in_gds=my_layout'),
                     ('report=my_report', 'report_file=my_report'),
                     ('schematic=reference_netlist', 'cdl_file=reference_netlist'),
                     ('-r sky130.lvs', '-r sky130.lylvs'),
                     ('"sky130_fd_sc_hs.cdl"', '"sky130hd.cdl"')):
        original = original.replace(old, new)
    require(code == original, 'Captured extraction differs from the licensed original.')
    changes = {
        'schematic($cdl_file)': 'schematic($cdl_file, sky130_reader)',
        'report($report_file)': 'report_lvs($report_file)',
        'SUB = polygons(236, 0)': 'SUB = extent - NWELL',
        'connect_global(SUB, "VNB")': 'connect(SUB, SUB)',
        '# Flatten cells which are present in one netlist only':
            'netlist.make_top_level_pins\n# Flatten cells which are present in one netlist only',
        '\ndeep\n': '\nflat\n',
        'device_scaling(1000000)': 'device_scaling(1)',
        'connect(SUB,  PTAP)': 'soft_connect(PTAP, SUB)',
        'connect(NWELL,  NTAP)': 'soft_connect(NTAP, NWELL)',
        '\nnetlist # ... not really required': '\ntop_level(true)\nnetlist # ... not really required',
        'SUBPIN  = input(64, 59)': f'SUBPIN = labels(64, 59).texts("{PORT_PATTERN}")',
        '\nalign\n': (
            '\nschematic.flatten\n'
            f'reference_top = schematic.circuit_by_name("{top.upper()}")\n'
            'raise "Reference hierarchy was not flattened" unless reference_top && reference_top.each_subcircuit.to_a.empty?\n'
            'schematic.each_circuit.to_a.each { |c| schematic.remove(c) unless c == reference_top }\n'
            'schematic.simplify\n'),
    }
    for old, new in changes.items():
        require(code.count(old) == 1, 'Native deck structure changed: ' + old)
        code = code.replace(old, new)
    code = re.sub(r'(\w+TXT\s*=) input\((\d+), (\d+)\)',
                  rf'\1 labels(\2, \3).texts("{PORT_PATTERN}")', code)
    code = '\n'.join(line for line in code.splitlines() if not line.startswith('equivalent_pins(')) + '\n'
    reader = (ASSETS/'sky130_cdl_reader.rb').read_text(encoding='utf-8')
    return reader + '\n' + code + '\nputs "ICSTUDIO_SKY130_LVS_COMPLETE"\n'

def label_copy(source,target,mapping):
    ly=k.Layout();ly.read(str(source));tops=list(ly.top_cells())
    require(len(tops)==1 and tops[0].name==mapping['top'], 'Unexpected layout top.')
    top=tops[0];bounds=top.bbox();counts=Counter();placements=[]
    before={str(ly.get_info(i)):k.Region(top.begin_shapes_rec(i)).merged() for i in ly.layer_indices()}
    for i in list(ly.layer_indices()):
        info=ly.get_info(i)
        if info.datatype!=5 or info.layer not in (67,68,69,70,71,72):continue
        metal=k.Region(top.begin_shapes_rec(ly.layer(info.layer,20))).merged()
        pins=k.Region(top.shapes(ly.layer(info.layer,16))).merged()
        for shape in top.shapes(i).each():
            if not shape.is_text() or shape.text.string not in mapping['ports']:continue
            text=shape.text;old=text.trans.disp.to_p()
            annotations=[p for p in pins.each() if p.inside(old)]
            require(len(annotations)==1, 'Ambiguous or missing pin annotation: ' + text.string)
            annotation=k.Region(annotations[0])
            islands=[p for p in metal.each() if not (k.Region(p)&annotation).is_empty()]
            require(len(islands)==1, 'Pin spans disconnected conductors or has no metal: ' + text.string)
            overlap=annotation&k.Region(islands[0])
            # Use the center of a convex trapezoid so the new label is strictly
            # inside real metal, without relying on a concave polygon bbox.
            pieces=list(overlap.decompose_trapezoids_to_region().each())
            pieces.sort(key=lambda p:(-p.area(),str(p)))
            points=list(pieces[0].each_point_hull())
            point=k.Point(sum(p.x for p in points)//len(points),sum(p.y for p in points)//len(points))
            require(pieces[0].inside(point) and islands[0].inside(point), 'Label is not on its conductor.')
            placements.append(dict(port=text.string,alias=mapping['ports'][text.string],layer=info.layer,
                old_point=[old.x,old.y],new_point=[point.x,point.y],
                pin_area_dbu2=annotation.area(),pin_metal_area_dbu2=overlap.area(),metal_islands=1))
            counts[text.string]+=1;text.string=mapping['ports'][text.string]
            trans=text.trans;trans.disp=k.Vector(point.x,point.y);text.trans=trans;shape.text=text
    require(set(counts)==set(mapping['ports']) and all(n==1 for n in counts.values()), 'Missing or repeated port labels.')
    opt=k.SaveLayoutOptions();opt.gds2_write_timestamps=False;ly.write(str(target),opt)
    check=k.Layout();check.read(str(target))
    require(check.top_cell().bbox()==bounds and check.dbu==ly.dbu, 'Label adaptation changed extent or units.')
    require({str(check.get_info(i)) for i in check.layer_indices()}==set(before), 'Label adaptation changed layers.')
    for name,region in before.items():
        i=check.find_layer(k.LayerInfo.from_string(name))
        require(i is not None, 'Layer lost during label adaptation.')
        require((region ^ k.Region(check.top_cell().begin_shapes_rec(i)).merged()).is_empty(), 'Label adaptation changed a mask.')
    return dict(mask_preservation=True,renamed_labels=dict(counts),placements=placements,
        pin_markers_are_conductors=False,dbu_um=ly.dbu)

def reference_dimensions(source):
    require(hashlib.sha256(source).hexdigest()==SPICE_SHA256,'Unreviewed diode model source.')
    lines=logical_lines(source.decode('ascii'))
    require(len(lines)==3 and lines[0]=='.subckt '+CELL+' DIODE VGND VNB VPB VPWR'
            and lines[2]=='.ends','Unexpected diode reference interface.')
    m=re.fullmatch(r'XD0 VNB DIODE '+MODEL+r' perim=([\d.e+]+) area=([\d.e+]+)',lines[1])
    require(m is not None,'Unexpected diode topology or parameters.')
    # This library view uses area/perimeter factors referenced to 1e12/1e6.
    # Require agreement with the independently supplied source GDS below;
    # never infer these reference dimensions from a design being tested.
    return Decimal(m[2])/Decimal('1e12'),Decimal(m[1])/Decimal('1e6')

def verify_library(source_spice,source_gds,installed_gds):
    source_gds,installed_gds=Path(source_gds),Path(installed_gds)
    require(hashlib.sha256(source_gds.read_bytes()).hexdigest()==GDS_SHA256,'Unreviewed diode source layout.')
    area,perimeter=reference_dimensions(source_spice)
    source=k.Layout();source.read(str(source_gds));installed=k.Layout();installed.read(str(installed_gds))
    require(len(source.top_cells())==1 and source.top_cell().name==CELL and installed.cell(CELL) is not None,
            'Missing diode source or installed cell.')
    require(abs(source.dbu-.001)<1e-12 and abs(installed.dbu-.001)<1e-12,'Unexpected diode layout units.')
    def masks(layout,cell):
        result={}
        for index in layout.layer_indexes():
            info=layout.get_info(index);r=k.Region(cell.begin_shapes_rec(index)).merged()
            if not r.is_empty():result[(info.layer,info.datatype)]=r
        return result
    left=masks(source,source.top_cell());right=masks(installed,installed.cell(CELL))
    require(all((left.get(pair,k.Region())^right.get(pair,k.Region())).is_empty() for pair in left.keys()|right.keys()),
            'Installed diode masks differ from the independent reference.')
    diode=(left[(65,20)]&left[(93,44)]-left[(64,20)])&left[(81,23)]
    require(diode.count()==1 and Decimal(diode.area())/1000000==area and Decimal(diode.perimeter())/1000==perimeter,
            'Independent diode SPICE and source GDS dimensions disagree.')
    return dict(cell=CELL,model=MODEL,area_um2=str(area),perimeter_um=str(perimeter),
                source_spice_sha256=SPICE_SHA256,source_gds_sha256=GDS_SHA256,
                installed_gds_sha256=hashlib.sha256(installed_gds.read_bytes()).hexdigest(),
                polygon_layers_equal=True,reference_units_checked_against_source_layout=True)

def enrich_reference(reference,source_spice):
    area,perimeter=reference_dimensions(source_spice)
    empty='.SUBCKT '+CELL+' DIODE VGND VNB VPB VPWR\n.ENDS '+CELL
    require(reference.count(empty)==1,'Expected exactly one empty diode master in the pinned CDL.')
    return reference.replace(empty,empty.split('\n')[0]+f'\nD0 VNB DIODE {MODEL} A={area} P={perimeter}\n.ENDS '+CELL)

def strict_deck(upstream,top):
    code=transistor_deck(upstream,top)
    marker='# Define connectivity for netlist extraction'
    require(code.count(marker)==1,'Changed native connectivity section.')
    extra='''# Independently referenced low-voltage antenna diode; both dimensions compare.
NDIODE = (DIFF & NSDM - NWELL) & DIODE
diode_class = extract_devices(diode("'''+MODEL+'''"), { "P" => SUB, "N" => NDIODE, "tA" => SUB, "tC" => NSD })
diode_class.enable_parameter("P", true)
diode_class.enable_parameter("A", true)
'''
    code=code.replace(marker,extra+'\n'+marker)
    # Both diode properties are secondary in the native comparer unless
    # explicitly selected. Native area/perimeter fault controls enforce this.
    # These tolerances absorb floating arithmetic only, far below a DBU step.
    require(code.count('if ! compare')==1,'Changed native comparison section.')
    code=code.replace('if ! compare',f'tolerance("{MODEL}", "A", :absolute => 1e-12)\n'
                      f'tolerance("{MODEL}", "P", :absolute => 1e-12)\nif ! compare')
    return code

def port_match(pairs, expected):
    wanted = {p.casefold() for p in expected}
    return (bool(wanted) and len(wanted) == len(expected) == len(pairs) and
            all(p['status'] == 'Match' and p['layout'] and p['reference'] and
                p['layout'].casefold() == p['reference'].casefold() for p in pairs) and
            {p['layout'].casefold() for p in pairs if p['layout']} == wanted)

def native_audit(path, top, expected_ports):
    import klayout.db as k
    path = Path(path); db = k.LayoutVsSchematic(); db.read(str(path))
    xref = db.xref()
    if xref is None:
        raise ValueError('Missing native schematic comparison.')
    circuits = [dict(layout=p.first().name if p.first() else None,
                     reference=p.second().name if p.second() else None, status=str(p.status()))
                for p in xref.each_circuit_pair()]
    ctop = db.netlist().circuit_by_name(top)
    if ctop is None:
        raise ValueError('Expected top circuit was not extracted.')
    pins = [dict(layout=p.first().name() if p.first() else None,
                 reference=p.second().name() if p.second() else None, status=str(p.status()))
            for p in xref.each_pin_pair(ctop)]
    logs = [dict(severity=str(e.severity), category=e.category_name, message=e.message,
                 cell=e.cell_name, blocks_match=e.severity != k.LogEntryData.Info) for e in db.each_log_entry()]
    matched = (bool(circuits) and all(c['status'] == 'Match' for c in circuits) and
               port_match(pins, expected_ports) and not any(e['blocks_match'] for e in logs))
    inventory = {}
    for label, netlist in [('layout', db.netlist()), ('reference', db.reference)]:
        flat = netlist.dup(); flat.flatten(); cell = flat.top_circuit()
        if cell is None:
            raise ValueError('Incomplete flattened transistor inventory.')
        inventory[label] = dict(devices=dict(Counter(d.device_class().name.casefold() for d in cell.each_device())),
                                pins=sorted(p.name().casefold() for p in cell.each_pin()))
    return dict(schema=1, status='native-device-and-port-match' if matched else 'native-lvs-audit-failed',
                matched=matched, qualified=False, report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                top=top, circuits=circuits, extraction_log=logs, port_pairs=pins,
                port_labels_match=port_match(pins, expected_ports), expected_ports=sorted(expected_ports),
                port_case_policy='Native SPICE reader uppercases names; require unique case-insensitive graph-paired port names.',
                inventory=inventory)

def port_groups_match(pairs, expected):
    wanted = [p.casefold() for p in expected]
    if not wanted or len(set(wanted)) != len(wanted):
        return False
    if any(re.fullmatch(r'n[0-9]{7}', p) is None for p in wanted):
        return False
    seen = []
    for pair in pairs:
        if pair['status'] != 'Match' or not pair['layout'] or not pair['reference']:
            return False
        left = pair['layout'].casefold().split(',')
        right = pair['reference'].casefold().split(',')
        if Counter(left) != Counter(right) or len(set(left)) != len(left):
            return False
        seen.extend(left)
    return Counter(seen) == Counter(wanted)

def audit(path, top, expected_ports):
    result = native_audit(path, top, expected_ports)
    ports = port_groups_match(result['port_pairs'], expected_ports)
    circuits = result['circuits']
    result['port_labels_match'] = ports
    result['matched'] = (
        len(circuits) == 1 and circuits[0]['status'] == 'Match' and
        circuits[0]['layout'].casefold() == top.casefold() and
        circuits[0]['reference'].casefold() == top.casefold() and ports and
        result['inventory']['layout']['devices'] == result['inventory']['reference']['devices'] and
        not any(e['blocks_match'] for e in result['extraction_log']))
    result['status'] = 'native-device-and-port-match' if result['matched'] else 'native-lvs-audit-failed'
    result['port_case_policy'] = (
        'Unique N plus seven-digit aliases; case-insensitive native graph-paired '
        'port groups must agree exactly and cover every declared port once.')
    return result
