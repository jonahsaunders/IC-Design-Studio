"""Signal-clearance IHP block fill using captured native rule macros.

The 9 um clearance exceeds the pinned extractor's 8 um interaction halo.
This is a bounded nominal model, not an independent field calibration.
Native before/after extraction and all layout checks remain mandatory.
"""
import collections
import math
from pathlib import Path
import shlex
import xml.etree.ElementTree as ET

METALS = {'Metal1':8, 'Metal2':10, 'Metal3':30, 'Metal4':50,
          'Metal5':67, 'TopMetal1':126, 'TopMetal2':134}
PHYSICAL_CELLS = {'sg13g2_decap_4', 'sg13g2_decap_8', 'sg13g2_fill_1', 'sg13g2_fill_2'}
PATTERNS = {'compact': (1.2, 5.2, 10., 5.2, 10., False),
            'balanced': (1.35, 8., 10., 8., 10., False),
            'dense': (1., 8., 10., 10., 6., True)}


def require(value, message):
    if not value:
        raise ValueError(message)


def conductors(ext, inventory):
    """Classify only unconnected, zero-R poly as capacitor-only conductors."""
    from scripts.check_ihp_flat_capacitance import raw_capacitors
    from scripts.ihp_cell_capacitance import protected_floating
    graph = raw_capacitors(ext)
    nodes, terminals, devices = {}, set(), []
    for line in Path(ext).read_text().splitlines():
        row = shlex.split(line)
        if not row:
            continue
        if row[0] in ('node', 'substrate'):
            nodes[row[1]] = row
        elif row[0] == 'port':
            terminals.add(row[1])
        elif row[0] == 'device':
            require(len(row) == 19 and row[1] == 'msubckt' and
                    row[2] in ('sg13_lv_nmos', 'sg13_lv_pmos'),
                    'IHP block fill requires the captured low-voltage MOS standard cells.')
            terminals.update(row[i] for i in (9, 10, 13, 16))
            devices.append(tuple(row))
    aliases = {r['alias'] for r in inventory['nets']}
    rails = {r['alias'] for r in inventory['nets'] if r['sig_type'] in ('POWER', 'GROUND')}
    require(len(rails) == 2 and aliases <= nodes.keys() and devices,
            'Native extraction must contain every checkpoint net and both supplies.')
    terminals |= aliases
    require(terminals <= nodes.keys(), 'A physical device terminal is missing.')
    floating = {n for n, t in nodes.items() if n not in terminals and
                t[0] == 'node' and t[6] == 'p' and float(t[2]) == 0}
    protected = set(nodes) - floating - rails
    require(not any(n.startswith('FILL') for n in nodes), 'Expected an unfilled circuit extraction.')
    require(all(math.isfinite(float(t[2])) and float(t[2]) >= 0 for t in nodes.values()),
            'Native node resistance is invalid.')
    return dict(graph=graph, nodes=nodes, devices=devices, floating=floating,
                protected=protected,
                protected_poly=protected_floating(graph, protected, floating))


def clearance(layout, inventory, native):
    import klayout.db as k
    from scripts.prepare_ihp_block_fill import masks
    before = masks(layout); region = k.Region()
    for item in inventory['instances']:
        require(item['master'].startswith('sg13g2_'), 'An unsupported macro needs a separate fill recipe.')
        if item['master'] not in PHYSICAL_CELLS:
            region.insert(k.Box(*item['box_nm']))
    for net in inventory['nets']:
        if net['sig_type'] in ('POWER', 'GROUND'):
            continue
        for item in net['wires'] + net['pins']:
            region.insert(k.Box(*item['box_nm']))
    for node in native['protected_poly']:
        row = native['nodes'][node]; x, y = int(row[4])*5, int(row[5])*5
        selected = before.get((5, 0), k.Region()).interacting(k.Region(k.Box(x-1, y-1, x+1, y+1)))
        require(not selected.is_empty(), 'A protected poly conductor is missing from GDS.')
        region += selected
    return region.merged().sized(9000) & k.Region(k.Box(*inventory['die_nm']))


def generation(macros, pattern):
    from scripts.prepare_ihp_block_fill import generation_script
    require(pattern in PATTERNS, 'Unknown IHP fill pattern.')
    spacing, w1, h1, w2, h2, _ = PATTERNS[pattern]
    body = generation_script(macros, exclusions=True)
    for n in range(1, 6):
        old = f"'distance_m{n}' => 1.5"
        require(body.count(old) == 1, 'Upstream metal pattern changed.')
        body = body.replace(old, f"'distance_m{n}' => {spacing}")
    require(body.count('width = 5.0') == body.count('height = 10.0') == 1,
            'Upstream top-metal dimensions changed.')
    body = body.replace('width = 5.0', f'width = {w1}').replace('height = 10.0', f'height = {h1}')
    if (w1, h1) != (w2, h2):
        old = 'pattern_tm2 = fill_pattern("TM2_FILL_CELL").shape(134, 22, box(0.0, 0.0, width, height))'
        step = '.fill(pattern_tm2, hstep(width + distance), vstep(height + distance))'
        require(body.count(old) == body.count(step) == 1, 'Upstream top-metal pattern changed.')
        body = body.replace(old, f'pattern_tm2 = fill_pattern("TM2_FILL_CELL").shape(134, 22, box(0.0, 0.0, {w2}, {h2}))')
        body = body.replace(step, f'.fill(pattern_tm2, hstep({w2} + distance), vstep({h2} + distance))')
    return body


def secondary(macros):
    from scripts.prepare_ihp_block_fill import MACROS, sha
    path = Path(macros)/'sg13g2_filler_TopMetal.lym'
    require(sha(path) == MACROS[path.name], 'Pinned top-metal macro changed.')
    text = ET.parse(path).getroot().findtext('text')
    step = '(fill_scope - exclLayTM1).fill(pattern_tm1, hstep(width + distance), vstep(height + distance))'
    text = text.replace('EdgeSeal.holes', 'fill_scope').replace('height = 10.0', 'height = 5.0')
    require(text.count(step) == 1, 'Upstream secondary pattern changed.')
    text = text.replace(step, '# TopMetal1 retains its first pattern.')
    return 'source($in_gds)\ntarget($out_gds, "ICSTUDIO_IHP_FILL")\nfill_scope = source.extent - source.input("10000/0")\n'+text


def electrical_view(source, inventory, target, *, filled=False):
    """Map actual filler to conducting masks without changing physical shapes."""
    import klayout.db as k
    from scripts.prepare_ihp_block_fill import masks
    layout = k.Layout(); layout.read(str(source)); top = layout.top_cell()
    require(layout.dbu == .001 and len(list(layout.top_cells())) == 1 and
            top.name == inventory['top'], 'Unexpected native electrical-view grid or top.')
    top.flatten(True); before = masks(layout); expected = dict(before); empty = k.Region()
    for index in layout.layer_indices():
        for shape in list(top.shapes(index).each()):
            if shape.is_text():
                shape.delete()
    if filled:
        active = before.get((1, 22), empty)
        require(not active.is_empty() and (active-before.get((14, 0), empty)).is_empty(),
                'Every active filler must be physical P+ substrate material.')
        for pair in ((31,0),(32,0),(44,0),(46,21),(7,21),(28,0),(5,0),(6,0),(26,0),(7,0),(1,0)):
            require((active & before.get(pair, empty)).is_empty(), 'Active fill touches circuit material or a modifier.')
        require(before.get((5,22),empty).is_empty(), 'Dummy MOS fill is unsupported.')
        for layer in (1, *METALS.values()):
            fill = before.get((layer,22),empty)
            polygons = sorted(fill.each(), key=lambda p:(p.bbox().left,p.bbox().bottom,p.bbox().right,p.bbox().top))
            require(polygons and all(p.is_box() for p in polygons) and
                    fill.interacting(before.get((layer,0),empty)).is_empty(),
                    'Filler must be rectangular and unconnected to original material.')
            top.shapes(layout.layer(layer,22)).clear()
            top.shapes(layout.layer(layer,0)).insert(fill)
            expected[layer,22] = empty
            expected[layer,0] = (before.get((layer,0),empty)+fill).merged()
            if layer != 1:
                for i, polygon in enumerate(polygons):
                    pos = polygon.bbox().center()
                    top.shapes(layout.layer(layer,25)).insert(k.Text(f'FILL{layer:03d}_{i:06d}',k.Trans(pos.x,pos.y)))
    aliases = set(); pin_regions = {layer:k.Region() for layer in METALS.values()}
    for net in inventory['nets']:
        require(net['alias'] not in aliases and net['pins'], 'An electrical label is duplicate or missing.')
        aliases.add(net['alias'])
        for pin in net['pins']:
            layer = METALS[pin['layer']]
            pin_regions[layer].insert(k.Box(*pin['box_nm']))
        pin = net['pins'][0]; pos = k.Box(*pin['box_nm']).center()
        top.shapes(layout.layer(METALS[pin['layer']],25)).insert(k.Text(net['alias'],k.Trans(pos.x,pos.y)))
    for layer, pins in pin_regions.items():
        require((pins-before.get((layer,0),empty)).is_empty(),
                'Checkpoint terminal is missing from original GDS.')
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
    require(not Path(target).exists(), 'Preserve the existing extraction view.')
    layout.write(str(target),options)
    check = k.Layout(); check.read(str(target)); after = masks(check)
    for pair in expected.keys() | after.keys():
        require((after.get(pair,empty)^expected.get(pair,empty)).is_empty(), 'Electrical mapping changed physical geometry.')


def compare_native(original, filled, inventory):
    from scripts.check_ihp_flat_capacitance import raw_capacitors
    from scripts.ihp_cell_capacitance import compare
    before = conductors(original, inventory)
    after = raw_capacitors(filled)
    devices, nodes = [], {}
    for line in Path(filled).read_text().splitlines():
        row = shlex.split(line)
        if row and row[0] == 'device': devices.append(tuple(row))
        if row and row[0] in ('node','substrate'): nodes[row[1]] = row
    require(collections.Counter(before['devices']) == collections.Counter(devices),
            'Fill changed physical device geometry or connectivity.')
    require(all(n in nodes and before['nodes'][n][2] == nodes[n][2] for n in before['protected']),
            'Fill changed native circuit resistance.')
    result = compare(before['graph'], after, before['protected'], before['floating'])
    # This recipe promises exact circuit invariance. Any residual requires a
    # separately reviewed extraction; the general research allowance is unused.
    require(result['status'] == 'cell-capacitance-subnetwork-identical',
            'Fill changed the circuit capacitance environment.')
    return result
