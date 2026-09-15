"""Deterministic bounded pattern search, with a saved sensitivity-first seed.

Coordinates lie on each user-selected grid. Only proposed candidates become
simulation jobs; the Cartesian product is never materialized. Every proposal is
validated through the same simulator/PVT path as an exhaustive search.
"""
import itertools
import math
from .model import clone, scalar
from . import analog_optimizer as opt


def axes(project, cid, spec):
    requested = spec['axes']
    if not 1 <= len(requested) <= 3: raise ValueError('Choose one to three adjustable parameters.')
    grids, used = [], set()
    for axis in requested:
        values = opt.grid(project, cid, [axis])
        overlap = used.intersection(values[0])
        if overlap: raise ValueError('Each adjustable or linked parameter must occur once: ' + ', '.join(overlap))
        used.update(values[0]); grids.append(values)
    return grids


def delta(grids, coordinate):
    return {k: v for axis, i in zip(grids, coordinate) for k, v in axis[i].items()}


def start(project, cid, plan, spec, prepare_job):
    if spec.get('kind', 'analog_optimizer') != 'analog_optimizer': raise ValueError('Adaptive search requires circuit objectives.')
    grids = axes(project, cid, spec)
    center = [min(range(len(grid)), key=lambda i: abs(grid[i][axis['target']] - scalar(spec.get('initial', {}).get(axis['target'], opt.get_target(project, cid, axis['target']))))) for grid, axis in zip(grids, spec['axes'])]
    seed = [center]; probes = []
    for n, grid in enumerate(grids):
        pair = []
        for sign in (-1, 1):
            point = list(center); point[n] = max(0, min(len(grid) - 1, point[n] + sign))
            if point not in seed: seed.append(point)
            pair.append(seed.index(point) + 1)
        probes.append(pair)
    conditions = len(plan['entries']) * len(plan['corners']) * len(plan['temperatures']) * max(1, len(plan.get('voltages', [])))
    limit = int(spec.get('budget', 100)) // conditions
    if limit < len(seed): raise ValueError(f'Sensitivity first needs at least {len(seed) * conditions} simulations for the baseline and independent parameter probes.')
    m = opt.prepare(project, cid, plan, spec, prepare_job, _changes=[delta(grids, p) for p in seed])
    m['adaptive'] = dict(project=clone(project), coordinates=seed, probes=probes, max_candidates=min(limit, math.prod(map(len, grids))),
                         active=True, done=len(seed) >= min(limit, math.prod(map(len, grids))), batches=1, reason='')
    return m


def next_coordinate(manifest, report):
    state = manifest['adaptive']; grids = axes(state['project'], manifest['cell_id'], manifest['spec'])
    seen = {tuple(c) for c in state['coordinates']}
    # Feasible Pareto points guide local proposals. Before feasibility, retain
    # the measured objectives and prefer fewer failed requirements.
    measured = [c for c in report['candidates'] if c['metrics'] and all(m['score'] is not None for m in c['metrics'])]
    if measured:
        ranges = [(min(c['metrics'][i]['score'] for c in measured), max(c['metrics'][i]['score'] for c in measured)) for i in range(len(measured[0]['metrics']))]
        def rank(c):
            normalized = sum((m['score'] - lo) / (hi - lo) if hi > lo else 0 for m, (lo, hi) in zip(c['metrics'], ranges))
            return (bool(c['failures']), len(c['failures']), not c['pareto'], normalized, c['candidate'])
        centers = sorted(measured, key=rank)
        # Rotate the Pareto center to avoid hiding power/speed trade-offs behind
        # the normalized aggregate used only for proposal ordering.
        front = [c for c in centers if c['pareto']]
        if front:
            rotate = (state['batches'] - 1) % len(front); centers = front[rotate:] + front[:rotate] + [c for c in centers if not c['pareto']]
        for c in centers:
            point = state['coordinates'][c['candidate'] - 1]
            for distance in (max(1, max(len(g) for g in grids) // (2 ** min(8, state['batches']))), 1):
                for n, grid in enumerate(grids):
                    for sign in (-1, 1):
                        proposal = list(point); proposal[n] = max(0, min(len(grid) - 1, point[n] + sign * distance))
                        if tuple(proposal) not in seen: return proposal
    # Global coverage also handles flat objectives and all failed simulations.
    # A coprime walk visits each grid point once without storing the product.
    sizes = [len(g) for g in grids]; total = math.prod(sizes); step = max(1, int(total * .61803398875))
    while math.gcd(step, total) != 1: step += 1
    for i in range(total):
        index = (i * step + total // 2) % total; point = []
        for size in reversed(sizes): point.append(index % size); index //= size
        point.reverse()
        if tuple(point) not in seen: return point
    return None


def advance(manifest, rows, prepare_job):
    """Return a new checkpoint and only its new jobs; caller saves before enqueue."""
    m = clone(manifest); state = m['adaptive']; report = opt.evaluate(m, rows)
    if not state['active'] or state['done'] or not report['batch_complete']: return m, []
    if any(r['state'] in ('Cancelled', 'Interrupted') for r in report['current'].values()):
        state.update(active=False, reason='Paused after interruption. Resume retries unfinished simulations.'); return m, []
    if len(state['coordinates']) >= state['max_candidates']:
        state.update(done=True, active=False, reason='Simulation budget reached.'); return m, []
    point = next_coordinate(m, report)
    if point is None: state.update(done=True, active=False, reason='Every grid point has been tested.'); return m, []
    grids = axes(state['project'], m['cell_id'], m['spec'])
    batch = opt.prepare(state['project'], m['cell_id'], m['plan'], m['spec'], prepare_job, _changes=[delta(grids, point)])['jobs']
    candidate = len(state['coordinates']) + 1
    for n, job in enumerate(batch, len(m['jobs']) + 1): job['case'].update(group=m['id'], index=n, candidate=candidate)
    m['jobs'].extend(batch); state['coordinates'].append(point); state['batches'] += 1
    if len(state['coordinates']) >= state['max_candidates']: state.update(done=True, active=False, reason='Simulation budget reached.')
    return m, batch


def sensitivity(manifest, report):
    """Local finite differences of worst-condition metrics; not causal attribution."""
    state = manifest.get('adaptive'); out = []
    if not state: return out
    candidates = {c['candidate']: c for c in report['candidates']}
    for axis, pair in zip(manifest['spec']['axes'], state['probes']):
        low, high = [candidates.get(i) for i in pair]
        for n, objective in enumerate(opt.objectives(manifest['spec'])):
            row = dict(target=axis['target'], objective=objective.get('name') or objective['expression'], unit=objective.get('unit', ''),
                       slope=None, span_effect=None, run_ids=[], detail='Waiting for both sensitivity probes.')
            if low and high:
                lo, hi = low['metrics'][n].get('value'), high['metrics'][n].get('value')
                dx = high['changes'][axis['target']] - low['changes'][axis['target']]
                row['run_ids'] = low['runs'] + high['runs']
                if lo is not None and hi is not None and dx:
                    row.update(slope=(hi - lo) / dx, span_effect=(hi - lo) / dx * (scalar(axis['upper']) - scalar(axis['lower'])),
                               detail='Local finite difference; linked parameters move together. Worst PVT condition may change.')
            out.append(row)
    return out
