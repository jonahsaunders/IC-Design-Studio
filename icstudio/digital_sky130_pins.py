"""Preserve actual OpenDB boundary-pin metal in SKY130 GDS exports.

The upstream DEF reader writes boundary pins as nonconductive pin annotations.
Routes can stop at the inside edge of these pins. Copy the separately captured
OpenDB shapes to the drawing purpose. Also remove the sole permitted stream
annotation: a top-level prBoundary box matching the independent OpenDB die.
Retain other annotations and geometry; reject other forbidden boundary data.
"""
import json
from pathlib import Path
import shutil

from .model import file_digest

LAYERS = {'li1': 67, 'met1': 68, 'met2': 69, 'met3': 70, 'met4': 71, 'met5': 72}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(source, inventory):
    """Validate the independent intent and construct the sole allowed mask delta."""
    import klayout.db as k
    layout = k.Layout(); layout.read(str(source))
    require(len(layout.top_cells()) == 1, 'SKY130 pin export requires one top cell.')
    top = layout.top_cell()
    require(inventory.get('schema') == 1 and top.name == inventory.get('top') and
            abs(layout.dbu - .001) < 1e-12, 'SKY130 pin inventory, top or grid differs.')
    ports = inventory['ports']
    require(ports and len({p['name'] for p in ports}) == len(ports), 'Duplicate or missing SKY130 ports.')
    die = k.Region(k.Box(*inventory['die_nm']))
    expected = {layer: k.Region() for layer in LAYERS.values()}
    labels = {}
    for layer in LAYERS.values():
        for shape in top.shapes(layout.layer(layer, 5)).each():
            require(shape.is_text(), 'A SKY130 port-label layer contains a polygon.')
            name = shape.text.string
            require(name not in labels, 'Repeated top-level SKY130 port label.')
            labels[name] = (layer, shape.text.x, shape.text.y)
    require(set(labels) == {p['name'] for p in ports}, 'SKY130 top port labels differ from OpenDB.')
    for port in ports:
        require(port['boxes'], 'A SKY130 port has no geometry.')
        labeled = False
        for item in port['boxes']:
            require(item['layer'] in LAYERS, 'Unsupported SKY130 port layer.')
            bounds = item['box_nm']
            require(len(bounds) == 4 and all(type(x) is int for x in bounds) and
                    bounds[0] < bounds[2] and bounds[1] < bounds[3], 'Invalid SKY130 port box.')
            layer = LAYERS[item['layer']]; box = k.Box(*bounds)
            expected[layer].insert(box)
            text_layer, x, y = labels[port['name']]
            labeled |= text_layer == layer and box.contains(k.Point(x, y))
        require(labeled, 'A SKY130 port label is outside its independent OpenDB geometry.')
    changes = []
    for layer, pins in expected.items():
        pins.merge()
        annotations = k.Region(top.shapes(layout.layer(layer, 16))).merged()
        require((pins ^ annotations).is_empty(), 'SKY130 pin annotations differ from OpenDB.')
        require((pins - die).is_empty(), 'A SKY130 pin extends outside the declared die.')
        drawing = k.Region(top.begin_shapes_rec(layout.layer(layer, 20))).merged()
        # Every boundary shape must already touch its routed conductor. Missing
        # routes require implementation repair, never automatic metal bridges.
        for polygon in pins.each():
            touching = drawing.interacting(k.Region(polygon))
            require(touching.count() == 1 and not (touching & k.Region(polygon)).is_empty(),
                    'A SKY130 port has missing or disconnected routed metal.')
        added = pins - drawing
        changes.append(dict(layer=layer, pin_polygons=pins.count(),
                            added_polygons=added.count(), added_area_nm2=added.area()))
        top.shapes(layout.layer(layer, 20)).insert(added)
    return layout, changes


def write(source, target, inventory):
    import klayout.db as k
    source, target = Path(source), Path(target)
    require(source.resolve() != target.resolve(), 'Preserve the original SKY130 stream.')
    digest = file_digest(source)
    layout, changes = prepare(source, inventory)
    from .digital_sky130_boundaries import remove_outline
    boundary_export = remove_outline(layout, inventory)
    require(file_digest(source) == digest, 'The SKY130 input stream changed.')
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
    layout.write(str(target), options)
    result = dict(schema=2, status='pin-metal-exported', top=layout.top_cell().name,
                  source_gds_sha256=digest, gds_sha256=file_digest(target),
                  checkpoint_sha256=inventory['checkpoint_sha256'], ports=len(inventory['ports']), layers=changes,
                  boundary_export=boundary_export)
    verify(source, target, inventory)
    return result


def verify(source, target, inventory):
    """Read back only the allowed pin-metal addition and declared outline removal."""
    import klayout.db as k
    before, after = k.Layout(), k.Layout(); before.read(str(source)); after.read(str(target))
    require(len(before.top_cells()) == len(after.top_cells()) == 1 and
            before.top_cell().name == after.top_cell().name == inventory['top'] and
            before.dbu == after.dbu, 'The SKY130 export hierarchy or grid changed.')
    original, written = before.top_cell(), after.top_cell()
    from .digital_sky130_boundaries import OUTLINE, review, require_clean
    boundary_export = review(before, inventory)
    require_clean(after)
    pairs = {(ly.get_info(i).layer, ly.get_info(i).datatype) for ly in (before, after) for i in ly.layer_indexes()}
    expected = {layer: k.Region() for layer in LAYERS.values()}
    for port in inventory['ports']:
        for item in port['boxes']:
            expected[LAYERS[item['layer']]].insert(k.Box(*item['box_nm']))
    for pair in pairs:
        left = k.Region(original.begin_shapes_rec(before.layer(*pair))).merged()
        right = k.Region(written.begin_shapes_rec(after.layer(*pair))).merged()
        wanted = left | expected[pair[0]] if pair[0] in expected and pair[1] == 20 else left
        if pair == OUTLINE:
            wanted = k.Region()
        require((wanted ^ right).is_empty(), 'Unexpected SKY130 mask change: '+str(pair))
        def texts(layout, cell):
            iterator = cell.begin_shapes_rec(layout.layer(*pair)); values = []
            while not iterator.at_end():
                if iterator.shape().is_text():
                    values.append(iterator.shape().text.transformed(iterator.trans()).to_s())
                iterator.next()
            return sorted(values)
        require(texts(before, original) == texts(after, written), 'A SKY130 annotation changed.')
    return dict(status='verified', masks_preserved_except_declared_pin_metal=True,
                boundary_export=boundary_export)


def execute(r):
    if r.platform['name'] != 'sky130hd':
        return None
    directory = r.root/'sky130-pin-export'; directory.mkdir()
    checkpoint = r.root/r.artifacts['checkpoint']['path']
    require(file_digest(checkpoint) == r.artifacts['checkpoint']['sha256'], 'SKY130 checkpoint changed.')
    worker = directory/'inventory.py'
    shutil.copyfile(Path(__file__).with_name('digital_sky130_pin_inventory.py'), worker)
    inventory_path = directory/'inventory.json'
    r.command([r.tools['openroad'], '-exit', '-no_init', '-python', str(worker), str(checkpoint), str(inventory_path)],
              'Preserving SKY130 boundary-pin metal', fraction=.96)
    inventory = json.loads(inventory_path.read_text())
    require(inventory['checkpoint_sha256'] == r.artifacts['checkpoint']['sha256'] == file_digest(checkpoint),
            'SKY130 pin capture belongs to a different checkpoint.')
    original = dict(r.artifacts['gds'])
    report = write(r.root/original['path'], directory/'final.gds', inventory)
    report['source'] = original
    r.add_artifact('sky130_pin_source', r.root/original['path'])
    for name, path in [('sky130_pin_inventory', inventory_path), ('sky130_pin_worker', worker), ('gds', directory/'final.gds')]:
        r.add_artifact(name, path)
    r.save_json('sky130_pin_export', report, 'sky130-pin-export/report.json')
    return report


def validate_saved(data, root):
    artifacts = data['artifacts']
    keys = {'sky130_pin_export', 'sky130_pin_inventory', 'sky130_pin_worker', 'sky130_pin_source'}
    present = keys & artifacts.keys()
    root = Path(root)
    def read(key):
        record = artifacts[key]; path = (root/record['path']).resolve()
        require(path.is_relative_to(root.resolve()) and path.is_file() and file_digest(path) == record['sha256'],
                'Missing or changed SKY130 pin-export artifact: '+key)
        return path
    if not present:
        # Historical jobs without pin correction cannot bypass the explicit
        # boundary prohibition when revalidated for current SKY130 delivery.
        if data.get('platform', {}).get('name') == 'sky130hd' and 'gds' in artifacts:
            from .digital_sky130_boundaries import validate_delivery
            validate_delivery(read('gds'))
        return None
    require(present == keys, 'Incomplete SKY130 pin-export evidence.')
    for key in keys | {'gds', 'checkpoint'}:
        read(key)
    report = json.loads(read('sky130_pin_export').read_text())
    inventory = json.loads(read('sky130_pin_inventory').read_text())
    require(report.get('schema') == 2 and report.get('status') == 'pin-metal-exported' and
            report.get('source') == artifacts['sky130_pin_source'] and
            report.get('source_gds_sha256') == artifacts['sky130_pin_source']['sha256'] and
            report.get('gds_sha256') == artifacts['gds']['sha256'] and
            report.get('checkpoint_sha256') == inventory.get('checkpoint_sha256') == artifacts['checkpoint']['sha256'] and
            report.get('top') == inventory.get('top') and report.get('ports') == len(inventory['ports']),
            'SKY130 pin-export bindings differ from the saved job.')
    _, changes = prepare(read('sky130_pin_source'), inventory)
    require(report.get('layers') == changes, 'SKY130 pin-export geometry report differs from independent readback.')
    verified = verify(read('sky130_pin_source'), read('gds'), inventory)
    require(report.get('boundary_export') == verified['boundary_export'],
            'SKY130 boundary-export evidence differs from independent readback. Recheck Finish/export.')
    return report
