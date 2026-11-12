"""Written-metal continuity for GF180 C/D five-metal standard-cell layouts.

Terminal coverage is derived from the captured placement and independent cell
GDS, never from an arbitrary list of points on the candidate. This supplements
strict device/substrate LVS; it cannot establish connectivity acceptance alone.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path

from .model import file_digest

METALS = (34, 36, 42, 46, 81)
VIAS = (35, 38, 40, 41)
PREFIX = 'gf180mcu_fd_sc_mcu9t5v0__'
SCOPE = ('Top-port separation, captured port anchors and every placed 9-track '
         'cell VDD/VSS terminal through written metal and vias, including dummy '
         'metal. Requires separate strict device/substrate LVS, geometry, fill, '
         'extraction and timing acceptance.')


@dataclass(frozen=True)
class Point:
    name: str
    layer: int
    x: int
    y: int
    instance: str = ''

    def record(self):
        return dict(name=self.name, layer=self.layer, x=self.x, y=self.y,
                    **({'instance': self.instance} if self.instance else {}))


@dataclass(frozen=True)
class Terminals:
    """In-memory capture returned by capture(); not a saved acceptance report."""
    top: str
    variant: str
    ports: tuple[Point, ...]
    anchors: tuple[Point, ...]
    power: tuple[Point, ...]
    instances: tuple[str, ...]
    sources: tuple[tuple[str, str, str], ...]


def _layout(path, top_name):
    import klayout.db as k
    layout = k.Layout()
    layout.read(str(path))
    tops = list(layout.top_cells())
    if layout.dbu != .001 or len(tops) != 1 or tops[0].name != top_name:
        raise ValueError('Require exactly the declared top cell and a 1 nm GDS database grid.')
    if any(layout.get_info(i).layer == 53 and
           not k.Region(tops[0].begin_shapes_rec(i)).is_empty() for i in layout.layer_indexes()):
        raise ValueError('A sixth metal is outside the GF180 C/D five-metal scope.')
    return layout, tops[0]


def _region(layout, cell, number, datatype):
    import klayout.db as k
    index = layout.find_layer(number, datatype)
    return k.Region() if index is None else k.Region(cell.begin_shapes_rec(index)).merged()


def _labels(layout, cell, number):
    index = layout.find_layer(number, 10)
    return [] if index is None else [s.text for s in cell.shapes(index).each() if s.is_text()]


def _masks(layout, cell):
    return {(layout.get_info(i).layer, layout.get_info(i).datatype):
            _region(layout, cell, layout.get_info(i).layer, layout.get_info(i).datatype)
            for i in layout.layer_indexes()}


def _integer(value):
    return type(value) is int


def _nm(value):
    if (isinstance(value, bool) or not isinstance(value, (float, int)) or
            not math.isfinite(value) or not math.isclose(value * 1000, round(value * 1000),
                                                        rel_tol=0, abs_tol=1e-7)):
        raise ValueError('Port coordinates must be finite and on the 1 nm grid.')
    return round(value * 1000)


def capture(gds, database, preview, library, *, top_name, variant):
    """Bind complete terminal coverage to a placement and independent library.

    library maps each used master to {path, sha256}. The caller authenticates
    database/preview against its captured job, and the library hashes against
    its selected PDK revision. Their exact file identities are retained here.
    A separately filled/flattened candidate can then be checked with inspect().
    """
    import klayout.db as k
    if variant not in ('C', 'D'):
        raise ValueError('Only GF180 C/D five-metal layouts are supported.')
    sources = []

    def bind(role, path, expected=None):
        path = Path(path).resolve(strict=True)
        sha = file_digest(path)
        if expected is not None and sha != expected:
            raise ValueError('Source hash mismatch: ' + role)
        sources.append((role, str(path), sha))
        return path

    gds = bind('reference_gds', gds)
    database = bind('database', database)
    preview = bind('preview', preview)
    db = json.loads(database.read_text(encoding='utf-8-sig'))
    view = json.loads(preview.read_text(encoding='utf-8-sig'))
    units = db.get('dbu_per_micron')
    if (db.get('version') != 1 or not _integer(units) or units <= 0 or
            not isinstance(db.get('instances'), list) or not db['instances']):
        raise ValueError('Require a nonempty captured OpenDB placement with valid database units.')
    layout, top = _layout(gds, top_name)
    expected, placements, names = Counter(), {}, set()
    for item in db['instances']:
        name, master = item['name'], item['master']
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('Every placed instance must have a unique nonempty name.')
        names.add(name)
        if not master.startswith(PREFIX) or master not in library:
            raise ValueError('Missing independent 9-track GDS for ' + master)
        box = item['bbox']
        if (len(box) != 4 or any(not _integer(v) or v * 1000 % units for v in box)
                or box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError('Placement bounds must have positive area on the 1 nm grid.')
        x1, y1, x2, y2 = [v * 1000 // units for v in box]
        transforms = {'R0': (0, False, x1, y1), 'MX': (0, True, x1, y2),
                      'MY': (2, True, x2, y1), 'R180': (2, False, x2, y2)}
        if item['orientation'] not in transforms:
            raise ValueError('Unsupported standard-cell placement orientation.')
        pins = [p for p in item['pins'] if p['name'] in ('VDD', 'VSS')]
        if Counter(p['name'] for p in pins) != {'VDD': 1, 'VSS': 1} or any(p['net'] != p['name'] for p in pins):
            raise ValueError('Every placed cell must have captured VDD/VSS supply assignments.')
        key = (master, *transforms[item['orientation']])
        expected[key] += 1
        placements.setdefault(key, []).append(name)
    actual, checked_helpers = Counter(), set()
    for inst in top.each_inst():
        master = layout.cell(inst.cell_index).name
        if master.startswith(PREFIX):
            if inst.is_regular_array() or inst.is_complex():
                raise ValueError('Arrayed or scaled standard cells are unsupported.')
            tr = inst.trans
            actual[(master, tr.angle, tr.is_mirror(), tr.disp.x, tr.disp.y)] += 1
        elif master not in checked_helpers:
            # Stream-out may create hierarchical via cells, but may not hide
            # additional devices or standard cells in an uncounted hierarchy.
            cell = layout.cell(inst.cell_index)
            if any(layout.get_info(i).layer not in (*METALS, *VIAS) and
                   not k.Region(cell.begin_shapes_rec(i)).is_empty() for i in layout.layer_indexes()):
                raise ValueError('Uncaptured non-metal geometry in stream-out hierarchy: ' + master)
            checked_helpers.add(master)
    if actual != expected:
        raise ValueError('Written standard-cell placements differ from the captured OpenDB.')
    power = []
    for master in sorted({key[0] for key in expected}):
        entry = library[master]
        path = bind('library:' + master, entry['path'], entry['sha256'])
        lib, cell = _layout(path, master)
        a, b = _masks(layout, layout.cell(master)), _masks(lib, cell)
        empty = k.Region()
        if any(not (a.get(pair, empty) ^ b.get(pair, empty)).is_empty() for pair in a.keys() | b.keys()):
            raise ValueError('Placed cell masks differ from the independent GDS: ' + master)
        labels = [t for t in _labels(lib, cell, 34) if t.string in ('VDD', 'VSS')]
        if Counter(t.string for t in labels) != {'VDD': 1, 'VSS': 1}:
            raise ValueError('Independent cell GDS must identify exactly one VDD/VSS terminal.')
        for key, instances in placements.items():
            if key[0] != master:
                continue
            tr = k.Trans(*key[1:])
            for name in instances:
                for label in labels:
                    point = tr * k.Point(label.x, label.y)
                    power.append(Point(label.string, 34, point.x, point.y, name))
    ports = tuple(Point(t.string, layer, t.x, t.y)
                  for layer in METALS for t in _labels(layout, top, layer))
    if (len(ports) < 2 or any(not p.name for p in ports) or
            len({p.name for p in ports}) != len(ports) or not {'VDD', 'VSS'} <= {p.name for p in ports}):
        raise ValueError('Require unique top-port labels, including VDD and VSS.')
    anchors = []
    for pin in view['pins']:
        if pin['layer'] not in [f'Metal{i}' for i in range(1, 6)] or len(pin['point']) != 2:
            raise ValueError('Captured port has an unsupported metal or coordinate.')
        layer = METALS[int(pin['layer'][-1]) - 1]
        if pin.get('gds_layer', [layer, 0]) != [layer, 0]:
            raise ValueError('Captured port stream mapping disagrees with the GF180 stack.')
        anchors.append(Point(pin['name'], layer, *map(_nm, pin['point'])))
    if Counter(p.name for p in anchors) != Counter(p.name for p in ports):
        raise ValueError('Written top ports differ from the captured port set.')
    by_name = {p.name: p for p in ports}
    for pin in anchors:
        other = by_name[pin.name]
        if pin.layer != other.layer or (pin.name not in ('VDD', 'VSS') and pin != other):
            raise ValueError('Written signal-port position differs from its captured anchor.')
    for role, path, sha in sources:
        if file_digest(Path(path)) != sha:
            raise ValueError('Source changed during terminal capture: ' + role)
    return Terminals(top_name, variant, ports, tuple(anchors), tuple(power), tuple(sorted(names)), tuple(sources))


def inspect(gds, terminals):
    """Inspect a candidate using fresh capture() output, preserving all findings.

    Dummy metal participates electrically. Child text never joins shapes.
    Substrate-only faults intentionally remain outside this check's scope.
    """
    import klayout.db as k
    if not isinstance(terminals, Terminals) or not terminals.instances:
        raise ValueError('Capture the complete placement before checking a candidate.')
    coverage = Counter((p.instance, p.name) for p in terminals.power)
    if coverage != Counter((n, supply) for n in terminals.instances for supply in ('VDD', 'VSS')):
        raise ValueError('Incomplete placed-cell power-terminal coverage.')
    for role, path, sha in terminals.sources:
        if file_digest(Path(path)) != sha:
            raise ValueError('Captured source changed: ' + role)
    path = Path(gds).resolve(strict=True)
    sha = file_digest(path)
    layout, top = _layout(path, terminals.top)
    network = k.LayoutToNetlist(top.name, layout.dbu)
    layers = {}
    for number in (*METALS, *VIAS):
        shapes = _region(layout, top, number, 0)
        if number in METALS:
            shapes += _region(layout, top, number, 4)
        shapes.merge()
        layers[number] = shapes
        network.register(shapes, 'layer_' + str(number))
        network.connect(shapes)
    for lower, via, upper in zip(METALS, VIAS, METALS[1:]):
        network.connect(layers[lower], layers[via])
        network.connect(layers[via], layers[upper])
    network.extract_netlist()

    def probe(pin):
        net = network.probe_net(layers[pin.layer], k.Point(pin.x, pin.y))
        return None if net is None else net.cluster_id

    nets = {p.name: probe(p) for p in terminals.ports}
    failures = []
    if any(n is None for n in nets.values()):
        failures.append(dict(kind='missing-port-metal', ports=nets))
    connected = [n for n in nets.values() if n is not None]
    if len(set(connected)) != len(connected):
        failures.append(dict(kind='shorted-top-ports', ports=nets))
    labels = Counter((t.string, layer, t.x, t.y) for layer in METALS for t in _labels(layout, top, layer))
    if labels != Counter((p.name, p.layer, p.x, p.y) for p in terminals.ports):
        failures.append(dict(kind='changed-top-port-labels'))
    for group, kind in ((terminals.anchors, 'port-anchor-disconnected'),
                        (terminals.power, 'power-terminal-disconnected')):
        for pin in group:
            actual = probe(pin)
            if actual is None or actual != nets[pin.name]:
                failures.append(dict(kind=kind, pin=pin.record(), actual_net=actual, expected_net=nets[pin.name]))
    logs = [str(e) for e in network.each_log_entry()]
    if logs:
        failures.append(dict(kind='metal-extraction-diagnostics', messages=logs))
    if file_digest(path) != sha:
        raise ValueError('Candidate GDS changed during metal extraction.')
    return dict(schema=1, status='metal_checks_passed' if not failures else 'metal_checks_failed',
        passed=not failures, qualified=False, scope=SCOPE, variant=terminals.variant,
        top=terminals.top, engine_version=k.__version__, gds_sha256=sha,
        sources=[dict(role=r, path=p, sha256=s) for r, p, s in terminals.sources],
        port_nets=nets, port_anchors=len(terminals.anchors), placed_cells=len(terminals.instances),
        power_terminals=len(terminals.power), failure_counts=dict(Counter(f['kind'] for f in failures)),
        failures=failures, extraction_logs=logs)
