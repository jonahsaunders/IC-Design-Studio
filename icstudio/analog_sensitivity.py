"""Reproducible Morris trajectories and Jansen/Sobol pick-freeze experiments.

Inputs are independent, uniformly sampled *configured grid coordinates*; linked
targets move together. Failed/missing samples are never imputed or discarded.
"""
import math
import random
import statistics
from .model import clone
from . import analog_optimizer as opt, analog_adaptive as adaptive


def design(sizes, method, count, seed):
    count = int(count)
    if not sizes or not all(n >= 2 for n in sizes) or not 2 <= count <= 4096:
        raise ValueError('Use at least two samples and two levels per parameter.')
    rng = random.Random(int(seed)); coordinates = []; index = {}; blocks = []
    def add(point):
        key = tuple(point)
        if key not in index:
            index[key] = len(coordinates) + 1; coordinates.append(list(point))
        return index[key]
    if method == 'morris':
        for _ in range(count):
            point = []; steps = []
            for n in sizes:
                step = max(1, n // 2); start = rng.randrange(n - step)
                if rng.randrange(2): start += step; step = -step
                point.append(start); steps.append(step)
            order = list(range(len(sizes))); rng.shuffle(order); previous = add(point)
            for axis in order:
                point[axis] += steps[axis]; following = add(point)
                blocks.append(dict(axis=axis, before=previous, after=following,
                                   dx=steps[axis] / (sizes[axis] - 1)))
                previous = following
    elif method == 'sobol':
        for _ in range(count):
            a = [rng.randrange(n) for n in sizes]; b = [rng.randrange(n) for n in sizes]
            blocks.append(dict(a=add(a), b=add(b), ab=[add(a[:i] + [b[i]] + a[i+1:]) for i in range(len(sizes))]))
    else: raise ValueError('Choose Morris screening or Sobol interaction analysis.')
    return dict(method=method, count=count, seed=int(seed), coordinates=coordinates, blocks=blocks)


def prepare(project, cid, plan, spec, prepare_job, method='morris', count=6, seed=1):
    spec = clone(spec); spec.update(strategy='grid', screen_op=False)
    spec.pop('workflow', None); spec.pop('fidelity', None)
    grids = adaptive.axes(project, cid, spec)
    sampled = design([len(g) for g in grids], method, count, seed)
    m = opt.prepare(project, cid, plan, spec, prepare_job,
                    _changes=[adaptive.delta(grids, c) for c in sampled['coordinates']])
    m['name'] = ('Morris screening' if method == 'morris' else 'Sobol interactions') + ' · ' + plan['name']
    m['advanced'] = dict(kind='sensitivity', sampling=sampled)
    return m


def interval(values):
    ordered = sorted(values)
    return [ordered[int(.025 * (len(ordered)-1))], ordered[int(.975 * (len(ordered)-1))]] if ordered else None


def indices(blocks, values, axis):
    a = [values[b['a']] for b in blocks]; b = [values[b['b']] for b in blocks]
    ab = [values[row['ab'][axis]] for row in blocks]
    variance = statistics.variance(a + b)
    if variance <= 0: return None
    return (1 - statistics.fmean((y-z)**2 for y,z in zip(b,ab)) / (2*variance),
            statistics.fmean((x-z)**2 for x,z in zip(a,ab)) / (2*variance))


def analyze(manifest, rows):
    report = opt.evaluate(manifest, rows); sampled = manifest['advanced']['sampling']; output = []
    scope = 'Independent uniform grid coordinates; linked targets form one input. Indices depend on the chosen bounds and spacing.'
    for metric, objective in enumerate(opt.objectives(manifest['spec'])):
        values = {c['candidate']: c['metrics'][metric]['value'] for c in report['candidates']
                  if c['complete'] == c['total'] and c['metrics'][metric]['value'] is not None
                  and not c.get('evidence_errors')}
        if len(values) != len(sampled['coordinates']):
            output.append(dict(objective=objective['expression'], status='Incomplete', detail='Every sampled condition must return a valid objective. Retry failed simulations; no samples were imputed.'))
            continue
        for axis, definition in enumerate(manifest['spec']['axes']):
            row = dict(target=definition['target'], objective=objective['expression'], unit=objective.get('unit',''), status='Complete')
            rng = random.Random(sampled['seed'] + 101*axis + 1009*metric)
            if sampled['method'] == 'morris':
                effects = [(values[b['after']]-values[b['before']])/b['dx'] for b in sampled['blocks'] if b['axis']==axis]
                row.update(mu=statistics.fmean(effects), mu_star=statistics.fmean(abs(v) for v in effects),
                           sigma=statistics.stdev(effects) if len(effects)>1 else 0,
                           confidence=interval([statistics.fmean(abs(rng.choice(effects)) for _ in effects) for _ in range(200)]),
                           detail='Elementary effects across the normalized range. Spread reflects nonlinearity and/or interactions; it is not a causal attribution.')
            else:
                value = indices(sampled['blocks'], values, axis)
                if value is None:
                    row.update(status='Flat output', detail='No measurable output variance; sensitivity indices are undefined.')
                else:
                    boot = [indices([rng.choice(sampled['blocks']) for _ in sampled['blocks']], values, axis) for _ in range(200)]
                    boot = [v for v in boot if v is not None]
                    row.update(first_order=value[0], total_order=value[1],
                               first_confidence=interval([v[0] for v in boot]), confidence=interval([v[1] for v in boot]),
                               detail='Jansen first/total-order estimates with 95% bootstrap intervals. Finite-sample estimates can lie outside [0, 1]; they are not clipped.')
            output.append(row)
    return dict(method=sampled['method'], scope=scope, rows=output, complete=report['complete'])
