"""IC Design Studio external openEMS driver (project license).

Executed by the user's solver Python, independent of the application package.
Only uses public openEMS/CSXCAD APIs; no third-party source is bundled here.
One process per excitation prevents native solver state leaking between runs.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import traceback
from pathlib import Path


def emit(**values):
    print('ICSTUDIO_EM:'+json.dumps(values, allow_nan=False), flush=True)


def dependencies():
    import numpy as np
    import CSXCAD
    import openEMS
    from CSXCAD.SmoothMeshLines import SmoothMeshLines
    versions = {'python': platform.python_version(), 'numpy': np.__version__}
    for name, module in [('openEMS', openEMS), ('CSXCAD', CSXCAD)]:
        try: version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: version = getattr(module, '__version__', 'unreported')
        versions[name] = str(version)
    for name in ('AddLumpedPort', 'SetGaussExcite', 'SetBoundaryCond', 'Run'):
        if not hasattr(openEMS.openEMS, name): raise RuntimeError('openEMS Python API is missing '+name)
    return np, CSXCAD.ContinuousStructure, openEMS.openEMS, SmoothMeshLines, versions


def build(data, scale, active, deps):
    np, ContinuousStructure, openEMS, smooth, versions = deps
    opts = data['settings']; low, high = data['bounds_um']; layers = data['layers']
    fdtd = openEMS(EndCriteria=10**(opts['end_db']/10), NrTS=opts['max_steps'])
    fdtd.SetGaussExcite((opts['f_start_hz']+opts['f_stop_hz'])/2,
                       (opts['f_stop_hz']-opts['f_start_hz'])/2)
    fdtd.SetBoundaryCond(['MUR', 'MUR', 'MUR', 'MUR', 'MUR', 'PEC'])
    csx = ContinuousStructure(); fdtd.SetCSX(csx); grid = csx.GetGrid(); grid.SetDeltaUnit(1e-6)
    props = {}; zlines = [low[2], high[2]]; eps0 = 8.8541878128e-12
    # A physical PEC plane inside the domain connects the two port caps.
    # Merely terminating ports on a boundary does not create that conductor.
    reference = csx.AddMetal('fixture_reference')
    reference.AddBox([low[0], low[1], data['reference_plane_um']], high, priority=200)
    zlines.append(data['reference_plane_um'])
    maxeps = max(l.get('epsilon_r', 1) for l in layers)
    maxcell = min(opts['mesh_um']*scale, 299792458/opts['f_stop_hz']/math.sqrt(maxeps)/20*1e6)
    outercell = min(10*opts['mesh_um']*scale, 299792458/opts['f_stop_hz']/math.sqrt(maxeps)/20*1e6)
    localcell = min(maxcell, data['feature_size_um']*scale)
    for index, layer in enumerate(layers):
        eps = layer.get('epsilon_r', 1)
        sigma = layer.get('conductivity_s_m', 0)
        sigma += 2*math.pi*data['loss_reference_hz']*eps0*eps*layer.get('loss_tangent', 0)
        prop = csx.AddMaterial('physical_'+str(index)); prop.SetMaterialProperty(epsilon=eps, kappa=sigma)
        props[layer['name']] = prop
        z0 = layer['z_um']; z1 = z0+layer['thickness_um']; zlines.extend([z0, z1])
        if layer['kind'] in ('dielectric', 'substrate'):
            prop.AddBox([low[0], low[1], z0], [high[0], high[1], z1], priority=1)
        else:
            # Resolve metal thickness and high-frequency skin depth with >=3
            # and >=2 cells respectively. Excessive meshes fail before Run.
            skin_um = math.sqrt(2/(2*math.pi*opts['f_stop_hz']*4e-7*math.pi*sigma))*1e6
            step = min(maxcell, layer['thickness_um']/3, skin_um/2)*scale
            n = math.ceil((z1-z0)/step)
            if n > 10000: raise ValueError('A metal layer needs over 10,000 z cells. Reduce frequency or use a specialized thin-sheet model.')
            zlines.extend(np.linspace(z0, z1, n+1).tolist())
        if len(zlines) > 10000: raise ValueError('Over 10,000 required z mesh lines. Reduce frequency or use a specialized model.')
    for solid in data['solids']:
        layer = next(l for l in layers if l['name'] == solid['layer'])
        props[solid['layer']].AddLinPoly(np.array(solid['points_um']).T, norm_dir='z',
                                       elevation=layer['z_um'], length=layer['thickness_um'], priority=10)
    ports = []
    for number, port in enumerate(data['ports'], 1):
        ports.append(fdtd.AddLumpedPort(number, 50, port['start_um'], port['stop_um'],
                                        'z', excite=1 if number == active else 0, priority=100))
    axes = []
    bounds = data['geometry_bounds_um']
    for axis in (0, 1):
        n = math.ceil((bounds[axis+2]-bounds[axis])/localcell)
        if n > 10000: raise ValueError('Over 10,000 mesh lines on one axis; reduce geometry scope or frequency.')
        mandatory = [low[axis], high[axis], bounds[axis], bounds[axis+2]]+data['features_um'][axis]
        for start, stop in data['via_intervals_um'][axis]:
            mandatory += np.linspace(start, stop, math.ceil(3/scale)+1).tolist()
        mandatory = np.unique(np.round(mandatory, 9))
        if len(mandatory) > 10000: raise ValueError('Over 10,000 required mesh lines. Reduce the simulation context.')
        regular = np.linspace(bounds[axis], bounds[axis+2], n+1)
        # Do not create tiny accidental cells where a regular line almost
        # coincides with a required via/port edge. Required lines stay exact.
        indices = np.searchsorted(mandatory, regular)
        distance = np.minimum(abs(regular-mandatory[np.clip(indices, 0, len(mandatory)-1)]),
                              abs(regular-mandatory[np.clip(indices-1, 0, len(mandatory)-1)]))
        regular = regular[distance > .15*localcell]
        axes.append(smooth(np.unique(np.r_[mandatory, regular]), outercell, ratio=1.4))
    axes.append(smooth(np.unique(np.round(zlines, 9)), outercell, ratio=1.4))
    # openEMS allocates/counts the grid lines' product, including boundary
    # storage, rather than only the interior geometric voxels.
    counts = [len(a) for a in axes]; cells = math.prod(counts)
    if cells > opts['max_cells']:
        raise ValueError(f'Mesh requires {cells:,} cells, exceeding the {opts["max_cells"]:,} limit. Reduce scope, review mesh settings or raise the memory limit.')
    if any(np.min(np.diff(a)) < 1e-6 for a in axes):
        raise ValueError('Mesh lines are less than 0.001 nm apart. Check physical layer elevations and port geometry.')
    for axis, lines in zip('xyz', axes): grid.AddLine(axis, lines)
    emit(state='mesh', cells=cells, mesh_lines=counts, scale=scale, port=active)
    return fdtd, csx, ports, cells, counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--model', type=Path)
    parser.add_argument('--scale', type=float, choices=(1., .7), default=1.)
    parser.add_argument('--port', type=int, choices=(1, 2), default=1)
    parser.add_argument('--setup-only', action='store_true')
    args = parser.parse_args(); deps = dependencies()
    if args.probe:
        # Exercise the geometry/port bindings as well as importing modules;
        # older bindings can import successfully with incompatible NumPy.
        np, ContinuousStructure, openEMS, _, _ = deps
        csx = ContinuousStructure(); fdtd = openEMS(); fdtd.SetCSX(csx)
        material = csx.AddMaterial('probe'); material.SetMaterialProperty(epsilon=1, kappa=1)
        material.AddLinPoly(np.array([[0., 1., 1.], [0., 0., 1.]]), 'z', 0, 1)
        fdtd.AddLumpedPort(1, 50, [0, 0, 0], [1, 1, 1], 'z', excite=1)
        emit(state='ready', versions=deps[-1]); return
    if args.model is None: parser.error('--model is required')
    data = json.loads(args.model.read_text(encoding='utf-8'))
    if data.get('schema') != 1: raise ValueError('Unsupported simulation model schema.')
    encoded = json.dumps({k: v for k, v in data.items() if k != 'run_hash'}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest() != data.get('run_hash'):
        raise ValueError('The staged physical model or solver settings changed. Prepare a new run.')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != data.get('driver_sha256'):
        raise ValueError('The staged solver driver changed. Prepare a new run.')
    name = ('base' if args.scale == 1 else 'fine')+'-'+str(args.port)
    directory = args.model.resolve().parent/name; directory.mkdir(exist_ok=False)
    fdtd, csx, ports, cells, counts = build(data, args.scale, args.port, deps)
    csx.Write2XML(str(directory/'model.xml'))
    if args.setup_only:
        emit(state='setup_complete', versions=deps[-1], cells=cells); return
    emit(state='running', versions=deps[-1], port=args.port, scale=args.scale)
    fdtd.Run(str(directory), cleanup=False, numThreads=data['settings']['threads'])
    np = deps[0]; opts = data['settings']
    frequency = np.geomspace(opts['f_start_hz'], opts['f_stop_hz'], opts['samples'])
    for port in ports: port.CalcPort(str(directory), frequency, ref_impedance=50)
    incident = ports[args.port-1].uf_inc
    magnitude = np.abs(incident); peak = np.max(magnitude)
    # Pulse spectra carry a time normalization. An absolute voltage threshold
    # incorrectly rejects high-frequency runs; check relative dynamic range.
    if not np.all(np.isfinite(incident)) or peak < np.finfo(float).tiny or np.min(magnitude) < 1e-6*peak:
        raise ValueError('Insufficient incident signal in the requested band.')
    scattering = np.array([p.uf_ref/incident for p in ports]).T
    if not np.all(np.isfinite(scattering)): raise ValueError('Non-finite S parameters.')
    output = dict(run_hash=data['run_hash'], scale=args.scale, port=args.port,
                  versions=deps[-1], cells=cells, mesh_lines=counts,
                  frequency_hz=frequency.tolist(), s_real=scattering.real.tolist(), s_imag=scattering.imag.tolist())
    target = args.model.resolve().parent/(name+'.json')
    temporary = target.with_suffix('.tmp'); temporary.write_text(json.dumps(output, allow_nan=False), encoding='utf-8'); temporary.replace(target)
    emit(state='complete', port=args.port, scale=args.scale)


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        emit(state='error', error=str(exc)); traceback.print_exc(); raise SystemExit(1)
