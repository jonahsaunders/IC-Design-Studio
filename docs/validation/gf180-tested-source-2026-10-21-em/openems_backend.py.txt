"""Optional openEMS job preparation and evidence checks, independent of Qt.

All dimensions passed to the external driver are micrometres. The measurement
fixture is deliberately part of the run identity, never saved into the layout.
"""
import hashlib
import json
import math
import re
import shutil
from pathlib import Path

from . import inductor_em
from .layout import kdb, polygon
from .model import atomic_write, clone, digest

DRIVER = Path(__file__).parent/'assets'/'openems'/'driver.py'
DEFAULTS = dict(f_start_hz=1e9, f_stop_hz=3e9, samples=101, mesh_um=2.,
                margin_um=100., reference_clearance_um=100., end_db=-50.,
                max_steps=2000000, max_cells=2000000, timeout_s=1800,
                threads=2, mesh_check=True, mesh_tolerance=.05)
FIXTURE = ('Two vertical 50-ohm ports from P and N to a common top PEC reference '
           'plane; differential Z = Z11 + Z22 - Z12 - Z21. Fixture-inclusive; '
           'no port de-embedding. Five other boundaries use MUR absorption.')


def settings(values):
    if not isinstance(values, dict) or set(values)-set(DEFAULTS):
        raise ValueError('Unknown openEMS settings.')
    result = {**DEFAULTS, **values}
    ranges = dict(f_start_hz=(1e3, 1e12), f_stop_hz=(1e3, 1e12), samples=(2, 10000),
                  mesh_um=(.001, 1000), margin_um=(1, 10000),
                  reference_clearance_um=(1, 10000), end_db=(-100, -20),
                  max_steps=(100, 100000000), max_cells=(1000, 20000000),
                  timeout_s=(1, 86400), threads=(1, 64), mesh_tolerance=(.001, .5))
    for key, (lo, hi) in ranges.items():
        value = result[key]
        if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f'{key}: use a finite value between {lo:g} and {hi:g}.')
        if key in ('samples', 'max_steps', 'max_cells', 'timeout_s', 'threads') and type(value) is not int:
            raise ValueError(key+': use an integer.')
    if result['f_start_hz'] >= result['f_stop_hz']:
        raise ValueError('Stop frequency must exceed start frequency.')
    if type(result['mesh_check']) is not bool: raise ValueError('mesh_check must be boolean.')
    return result


def model(data, values, cancelled=lambda: False):
    """Resolve physical masks and verify that each vertical port is unobstructed."""
    opts = settings(values)
    if not data['solver_stackup_complete']:
        raise ValueError('Complete the physical EM profile: '+'; '.join(data['solver_missing']))
    db = kdb(); regions = {}; solids = []; layers = data['stackup']['layers']
    physical = {l['name']: l for l in layers}; mapping = data['physical_layer_map']
    selected = data['context_geometry'] if data['scope'] == 'context' else data['geometry']
    for shape in selected:
        if cancelled(): raise InterruptedError('Preparation cancelled.')
        if shape['layer'] in mapping:
            name = mapping[shape['layer']]
            regions.setdefault(name, db.Region()).insert(polygon(shape))
    bbox = None; features = [[], []]; via_intervals = [[], []]; count = 0
    for name, region in regions.items():
        if cancelled(): raise InterruptedError('Preparation cancelled.')
        region.merge(); box = region.bbox(); bbox = box if bbox is None else bbox+box
        # Preserve holes by decomposition, then export exact mask vertices.
        for poly in region.each():
            parts = poly.decompose_trapezoids() if poly.holes() else [poly]
            for part in parts:
                part = db.Polygon(part)
                count += part.num_points()
                if count > 200000: raise ValueError('Automatic openEMS supports at most 200,000 mask vertices; reduce the simulation context.')
                solids.append(dict(layer=name, points_um=[[p.x/1000, p.y/1000] for p in part.each_point_hull()]))
            if physical[name]['kind'] == 'via' or poly.is_box():
                box = poly.bbox()
                for axis, pair in enumerate(((box.left, box.right), (box.bottom, box.top))):
                    features[axis].extend([pair[0]/1000, sum(pair)/2000, pair[1]/1000])
                    if physical[name]['kind'] == 'via': via_intervals[axis].append([pair[0]/1000, pair[1]/1000])
    if bbox is None or bbox.empty(): raise ValueError('The selected scope has no conductor geometry.')
    top = max(l['z_um']+l['thickness_um'] for l in layers)+opts['reference_clearance_um']
    bottom = min(l['z_um'] for l in layers)-opts['margin_um']
    ports = []
    for pin_name in ('p', 'n'):
        pin = next((p for p in data['pins'] if p['pin'].lower() == pin_name), None)
        if pin is None or pin['layer'] not in mapping: raise ValueError('P and N must each have a mapped physical conductor.')
        layer = physical[mapping[pin['layer']]]
        if layer['kind'] != 'conductor': raise ValueError('Ports must lie on conductor layers.')
        x, y = pin['point']; half = max(1, data['spec']['width']//4)
        footprint = db.Region(db.Box(x-half, y-half, x+half, y+half))
        if not (footprint-regions[layer['name']]).is_empty():
            raise ValueError(pin_name.upper()+': the automatic port does not fit inside its terminal pad.')
        z = layer['z_um']+layer['thickness_um']
        for name, region in regions.items():
            if physical[name]['z_um']+physical[name]['thickness_um'] > z+1e-9 and not (footprint & region).is_empty():
                raise ValueError(pin_name.upper()+': the vertical reference port intersects '+name+'. Use an unobstructed top conductor or export for a custom port fixture.')
        start = [(x-half)/1000, (y-half)/1000, z]
        stop = [(x+half)/1000, (y+half)/1000, top]
        ports.append(dict(name=pin_name.upper(), start_um=start, stop_um=stop))
        for axis in (0, 1): features[axis].extend([start[axis], (start[axis]+stop[axis])/2, stop[axis]])
    margin = opts['margin_um']
    return dict(schema=1, settings=opts, layers=clone(layers), solids=solids, ports=ports,
                bounds_um=[[bbox.left/1000-margin, bbox.bottom/1000-margin, bottom],
                           [bbox.right/1000+margin, bbox.top/1000+margin, top+max(opts['mesh_um'], 1.)]],
                reference_plane_um=top,
                geometry_bounds_um=[bbox.left/1000, bbox.bottom/1000, bbox.right/1000, bbox.top/1000],
                features_um=features, via_intervals_um=via_intervals,
                feature_size_um=min(data['spec']['width'], data['spec']['spacing'])/3000,
                fixture=FIXTURE, loss_reference_hz=(opts['f_start_hz']+opts['f_stop_hz'])/2,
                material_model='Uniform isotropic volumes. Dielectric loss tangent is represented by equivalent constant conductivity at the band centre, added to declared conductivity.')


def prepare(project, cid, did, scope, values, directory, cancelled=lambda: False):
    directory = Path(directory)
    data = inductor_em.manifest(project, cid, did, scope)
    prepared = model(data, values, cancelled)
    if cancelled(): raise InterruptedError('Preparation cancelled.')
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(DRIVER, directory/'driver.py')
    prepared['driver_sha256'] = hashlib.sha256((directory/'driver.py').read_bytes()).hexdigest()
    prepared['fingerprint'] = data['fingerprint']
    prepared['run_hash'] = digest(prepared)
    atomic_write(directory/'model.json', json.dumps(prepared, indent=2, allow_nan=False))
    atomic_write(directory/'manifest.json', json.dumps(data, indent=2, allow_nan=False))
    # Preserve masks with original GDS layer/datatype assignments for review.
    inductor_em.export_bundle(project, cid, did, directory/'exchange.zip', scope)
    return prepared


def stages(opts):
    return [(scale, port) for scale in ([1., .7] if opts['mesh_check'] else [1.]) for port in (1, 2)]


def stage_name(scale, port):
    return ('base' if scale == 1 else 'fine')+'-'+str(port)


def check_completion(log, directory, model_data, scale, port):
    """Exit zero alone also occurs on an openEMS time-step limit or abort."""
    if (Path(directory)/stage_name(scale, port)/'ABORT').exists():
        raise ValueError('openEMS was aborted; results were not attached.')
    if re.search(r'max\.?\s*(?:number of\s*)?time.?steps[^\n]{0,40}(?:was reached|reached before)|end.criteria.*not.*reach', log, re.I):
        raise ValueError('openEMS reached its time-step limit before energy convergence. Increase the limit or inspect the model and logs.')
    energies = [float(x.replace(' ', '')) for x in re.findall(r'\(\s*(-?\s*\d+(?:\.\d+)?)\s*dB\s*\)', log, re.I)]
    if not energies or energies[-1] > model_data['settings']['end_db']:
        raise ValueError('The solver log does not confirm the requested energy decay. Inspect the run log; no results were attached.')
    path = Path(directory)/(stage_name(scale, port)+'.json')
    data = json.loads(inductor_em._read(path))
    if data.get('run_hash') != model_data['run_hash'] or data.get('port') != port or data.get('scale') != scale:
        raise ValueError('Solver output does not match this run and excitation.')
    data['energy_db'] = energies[-1]
    return data


def finish(directory, model_data, columns):
    """Convert both excitations and keep simulation evidence bound to the layout."""
    directory = Path(directory); opts = model_data['settings']; base = None; touchstones = {}
    for scale in ([1., .7] if opts['mesh_check'] else [1.]):
        pair = [columns[stage_name(scale, p)] for p in (1, 2)]
        if pair[0]['versions'] != pair[1]['versions'] or pair[0]['mesh_lines'] != pair[1]['mesh_lines']:
            raise ValueError('The two excitations used different solver versions or mesh lines.')
        frequency = pair[0]['frequency_hz']
        if pair[1]['frequency_hz'] != frequency or len(frequency) != opts['samples']:
            raise ValueError('The two excitation sweeps do not match.')
        expected = [opts['f_start_hz']*(opts['f_stop_hz']/opts['f_start_hz'])**(i/(opts['samples']-1)) for i in range(opts['samples'])]
        if any(not math.isclose(f, e, rel_tol=1e-10) for f, e in zip(frequency, expected)):
            raise ValueError('Solver samples do not match the requested logarithmic frequency sweep.')
        if any(len(c.get(key, [])) != len(frequency) for c in pair for key in ('s_real', 's_imag')):
            raise ValueError('Incomplete two-port solver output.')
        lines = ['! '+FIXTURE, '# Hz S RI R 50']
        for i, f in enumerate(frequency):
            values = [f]
            for column in pair:
                if len(column['s_real'][i]) != 2 or len(column['s_imag'][i]) != 2:
                    raise ValueError('Each excitation must return both ports.')
                for row in (0, 1): values.extend([column['s_real'][i][row], column['s_imag'][i][row]])
            lines.append(' '.join(format(v, '.17g') for v in values))
        text = '\n'.join(lines)+'\n'; result = inductor_em.touchstone(text, 2)
        touchstones[scale] = text
        if base is None: base = result
    convergence = dict(energy_db={name: c['energy_db'] for name, c in columns.items()},
                       mesh_checked=opts['mesh_check'])
    if opts['mesh_check']:
        # Check complex impedance AND loss, so a small reactive error cannot
        # hide a large resistance (and therefore Q) error. Floors are explicit.
        z_errors = []; r_errors = []
        for br, bx, fr, fx in zip(base['z_real_ohm'], base['z_imag_ohm'], result['z_real_ohm'], result['z_imag_ohm']):
            z_errors.append(abs(complex(br-fr, bx-fx))/max(abs(complex(fr, fx)), 1e-3))
            r_errors.append(abs(br-fr)/max(abs(fr), 1e-3))
        convergence.update(max_relative_z_change=max(z_errors), max_relative_r_change=max(r_errors),
                           tolerance=opts['mesh_tolerance'], absolute_floor_ohm=1e-3)
        if max(z_errors+r_errors) > opts['mesh_tolerance']:
            atomic_write(directory/'mesh-comparison.json', json.dumps(convergence, indent=2))
            raise ValueError(f'Mesh refinement changed Z by {max(z_errors):.1%} or R by {max(r_errors):.1%}, above the {opts["mesh_tolerance"]:.1%} limit. Reduce mesh size and rerun. Results were not attached.')
    manifest = json.loads((directory/'manifest.json').read_text())
    evidence = dict(backend='openEMS', run_hash=model_data['run_hash'], driver_sha256=model_data['driver_sha256'],
                    fixture=model_data['fixture'], ports=model_data['ports'], bounds_um=model_data['bounds_um'],
                    material_model=model_data['material_model'], loss_reference_hz=model_data['loss_reference_hz'],
                    settings=opts, convergence=convergence,
                    stages={name: {k: c[k] for k in ('versions', 'cells', 'mesh_lines')} for name, c in columns.items()})
    source = ('openEMS external Python backend; '+FIXTURE+' '+model_data['material_model']+
              (' Two-mesh Z/R agreement checked.' if opts['mesh_check'] else ' Mesh convergence NOT checked.'))
    output = dict(schema=1, scope=manifest['scope'], fingerprint=manifest['fingerprint'],
                  port_definition=manifest['port_definition'], source=source, solver_run=evidence, **result)
    inductor_em.validate_results(output, manifest)
    atomic_write(directory/'results.json', json.dumps(output, indent=2, allow_nan=False))
    atomic_write(directory/'results.s2p', touchstones[.7 if opts['mesh_check'] else 1.])
    return output
