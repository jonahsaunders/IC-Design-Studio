"""Place declared top labels on their unique physical conductor, preserving masks.

Pin marker polygons identify ports but are never treated as conductive material.
An overlapping pin annotation must touch exactly one merged metal island.
"""
from collections import Counter
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import klayout.db as k

from scripts.ihp_lvs_reference import encode_reference, logical_lines, master_pins, require

MASTERS_SHA256 = 'ae02cdc40c81943bbc3f4a16a6760e01afd12764a94e7836b7e168edf40ae29c'
DECK_SHA256 = 'c83cd4b9cb02ac08fc6a554b5a2de464c14459557d891358d531fcc2aff269c2'
PORT_PATTERN = 'N' + '[0-9]' * 7


def prepare_reference(raw, masters_bytes, database):
    """Bind the exact HD library before interpreting unitless CDL dimensions."""
    normalized = masters_bytes.replace(b'\r\n', b'\n')
    require(hashlib.sha256(normalized).hexdigest() == MASTERS_SHA256,
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
        normalized_masters_sha256=MASTERS_SHA256,
        cdl_separators_removed=separators, dimension_scale=1e-6)


def strict_deck(upstream_bytes, top):
    """Adapt the exact reference deck; no global supply ties or pin equivalences.

    The tested scope is the HD standard-cell references, not all SKY130 devices.
    The native graph is flattened so real taps outside an individual cell can
    establish its body connection. Soft connections reject use of wells or
    substrate as substitutes for metal supply wiring.
    """
    require(hashlib.sha256(upstream_bytes).hexdigest() == DECK_SHA256, 'Unreviewed SKY130 LVS deck.')
    require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top) is not None, 'Unsupported top name.')
    code = ET.fromstring(upstream_bytes).findtext('text')
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
    reader = Path(__file__).with_name('sky130_cdl_reader.rb').read_text(encoding='utf-8')
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
