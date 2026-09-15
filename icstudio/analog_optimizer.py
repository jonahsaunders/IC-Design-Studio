"""Bounded analog searches over immutable circuit/PVT jobs.

The optimizer orchestrates existing simulators. It never substitutes an estimated
gm/Id operating point for a circuit simulation or silently relaxes a requirement.
"""
import itertools
import math
from .model import clone, scalar, validate, digest, design_digest, uid, now
from . import studies, test_plans, variation_runs

KINDS = ('analog_optimizer', 'analog_gmid')
ACTIVE = ('Queued', 'Running', 'Stopping')
TERMINAL = ('Complete', 'Failed', 'Cancelled', 'Interrupted')


def targets(project, cid):
    from .design_ops import parameters
    resolved = parameters(project.get('parameters', {}))
    return ['@' + k for k, v in resolved.items() if isinstance(v, (int, float))] + studies.targets(project, cid)


def get_target(project, cid, target):
    if target.startswith('@'):
        from .design_ops import parameters
        return scalar(parameters(project.get('parameters', {}))[target[1:]])
    return studies.get_target(project, cid, target)


def set_target(project, cid, target, value):
    if target not in targets(project, cid):
        raise ValueError('Choose an existing numeric parameter: ' + target)
    if target.startswith('@'):
        project['parameters'][target[1:]] = str(scalar(value))
    else:
        studies.set_target(project, cid, target, value)


def grid(project, cid, axes):
    if not 1 <= len(axes) <= 3:
        raise ValueError('Choose one to three adjustable parameters.')
    used, grids = set(), []
    available = targets(project, cid)
    for axis in axes:
        lo, hi = scalar(axis['lower']), scalar(axis['upper'])
        count = int(axis['count'])
        if count != scalar(axis['count']) or not 2 <= count <= 500 or not lo < hi:
            raise ValueError('Each parameter needs increasing bounds and 2–500 samples.')
        members = {axis['target']: 1.}
        for link in axis.get('links', []):
            target, ratio = link['target'], scalar(link['ratio'])
            if ratio <= 0 or target in members:
                raise ValueError('Linked parameters need distinct targets and positive ratios.')
            members[target] = ratio
        for target in members:
            if target not in available or target in used:
                raise ValueError('Each adjustable or linked parameter must exist and occur once: ' + target)
            used.add(target)
        grids.append([{t: (lo + (hi - lo) * i / (count - 1)) * ratio for t, ratio in members.items()} for i in range(count)])
    if math.prod(map(len, grids)) > 500:
        raise ValueError('Reduce the grid to at most 500 candidates.')
    return [{k: v for part in combination for k, v in part.items()} for combination in itertools.product(*grids)]


def source_plan(source):
    """A saved analysis is also usable without creating a multi-test plan."""
    settings = source['settings']
    return dict(id='optimizer-source', name=source['name'], entries=[clone(source)],
                corners=[settings.get('corner', 'nominal')], temperatures=[settings.get('temperature', 27)], voltages=[])


def is_op(project, entry):
    settings = entry['settings']
    # Saved testbench decks currently capture selected probes, not the native
    # primitive-device vector contract. Use a saved OP analysis of the bench cell.
    return settings['type'] == 'op'


def objectives(spec):
    return spec.get('objectives') or ([spec['objective']] if spec.get('objective') else [])


def prepare(project, cid, plan, spec, prepare_job, _changes=None):
    """Validate the entire experiment before any jobs are saved or enqueued."""
    from .wavecalc import parse, UNITS
    test_plans.validate_plans({**project, 'test_plans': [plan]})
    if plan.get('compare_layout') or any(e['engine'] == 'digital' for e in plan['entries']):
        raise ValueError('Choose an analog schematic plan. Verify extracted performance in Verification runs after applying a candidate.')
    kind = spec.get('kind', 'analog_optimizer')
    if kind not in KINDS:
        raise ValueError('Unknown analog optimizer mode.')
    if spec.get('strategy') == 'adaptive' and _changes is None:
        from .analog_adaptive import start
        return start(project, cid, plan, spec, prepare_job)
    changes = grid(project, cid, spec['axes']) if _changes is None else _changes
    nconditions = len(plan['entries']) * len(plan['corners']) * len(plan['temperatures']) * max(1, len(plan.get('voltages', [])))
    budget = int(spec.get('budget', 100))
    if not 1 <= budget <= 500 or len(changes) * nconditions > budget:
        raise ValueError(f'This grid needs {len(changes) * nconditions} simulations. Reduce samples/PVT conditions or raise the budget (maximum 500).')
    entries = {e['id']: e for e in plan['entries']}
    if kind == 'analog_optimizer':
        if not 1 <= len(objectives(spec)) <= 3: raise ValueError('Choose one to three objectives.')
        for objective in objectives(spec):
            if objective['entry_id'] not in entries or objective['goal'] not in ('minimize', 'maximize', 'target') or objective.get('unit', '') not in UNITS:
                raise ValueError('Choose an objective test, goal and supported unit.')
            parse(objective['expression']); scalar(objective.get('target', 0))
    gm = spec.get('gmid')
    if kind == 'analog_gmid' and (len(entries) != 1 or not gm):
        raise ValueError('The gm/Id explorer requires one operating-point test and a MOS instance.')
    if gm:
        if gm['entry_id'] not in entries or not is_op(project, entries[gm['entry_id']]):
            raise ValueError('Select an operating-point analysis for gm/Id readouts and limits.')
        device_geometry(project, entries[gm['entry_id']]['cell'], gm['device'])
        for key in ('min', 'max', 'headroom'):
            if gm.get(key) not in (None, ''): scalar(gm[key])
        if any(scalar(gm[k]) <= 0 for k in ('min', 'max') if gm.get(k) not in (None, '')):
            raise ValueError('gm/Id limits must be positive.')
        if gm.get('min') not in (None, '') and gm.get('max') not in (None, '') and scalar(gm['min']) > scalar(gm['max']):
            raise ValueError('The lower gm/Id limit exceeds the upper limit.')
    group, jobs, base = uid(), [], design_digest(project)
    for candidate, delta in enumerate(changes, 1):
        q = clone(project)
        for target, value in delta.items(): set_target(q, cid, target, value)
        validate(q)
        batch = test_plans.prepare(q, plan, prepare_job)
        for job in batch:
            # A corner/supply/plan override must never cancel a search dimension.
            for target, value in delta.items():
                if not math.isclose(get_target(job['project'], cid, target), value, rel_tol=1e-12, abs_tol=1e-30):
                    raise ValueError('A plan, supply or corner overrides adjustable parameter ' + target + '. Remove that overlap.')
            from .run_environment import stamp
            job['environment'] = stamp(job)
            job['case'].update(kind=kind, group=group, index=len(jobs) + 1, candidate=candidate,
                               changes=clone(delta), base_design_hash=base)
            job['case']['fingerprint'] = digest({k: v for k, v in job.items() if k != 'case'})
            jobs.append(job)
    return dict(schema=1, id=group, created=now(), name=spec.get('name') or ('gm/Id sweep' if kind == 'analog_gmid' else 'Analog search'),
                project_id=project['id'], base_design_hash=base, cell_id=cid,
                spec={**clone(spec), 'kind': kind}, plan=clone(plan), jobs=jobs)


def device_geometry(project, root, name):
    from .analog_debug import contexts
    for context in contexts(project, root):
        cell = next(c for c in project['cells'] if c['id'] == context['cell_id'])
        for d in cell['devices']:
            if (context['path'] + d['name']).casefold() != name.casefold(): continue
            if not _mos(project, d):
                raise ValueError('Select a MOS instance with exposed operating-point vectors.')
            if d.get('native_spice') or d.get('model_ref'):
                # gm/Id itself needs no width normalization. Model parameter names,
                # scale, fingers and subcircuit multiplicity are not interchangeable.
                return dict(width=None, length=None, cell_id=cell['id'], width_target=None, length_target=None)
            from .model import flatten
            resolved=next(v for v in flatten(project,root) if v['name'].casefold()==name.casefold())
            return dict(width=scalar(resolved['params']['w']),
                        length=scalar(resolved['params']['l']),
                        cell_id=cell['id'], width_target=d['name'] + '.params.w', length_target=d['name'] + '.params.l')
    raise ValueError('MOS instance not found: ' + name)


def _mos(project, device):
    from .catalog import binding_for
    binding = binding_for(project['pdk'], device) if device.get('model_ref') else {}
    native = device.get('native_spice', {})
    if (binding or native).get('operating_point_device'): return True
    if device['kind'] in ('NMOS', 'PMOS'): return True
    if native.get('type') == 'device':
        from .native_spice import render
        return render(device).split()[0][0].upper() == 'M'
    return False


def device_names(project, root):
    from .analog_debug import contexts
    names = []
    for context in contexts(project, root):
        cell = next(c for c in project['cells'] if c['id'] == context['cell_id'])
        for d in cell['devices']:
            if _mos(project, d):
                names.append(context['path'] + d['name'])
    return names


def read_gmid(job, result, name):
    geometry = device_geometry(job['project'], job['cell'], name)
    values = {k.casefold(): v for k, v in result.get('device_operating_point', {}).items()}.get(name.casefold(), {})
    try: current, gm = scalar(values['id']), scalar(values['gm'])
    except (KeyError, ValueError, TypeError):
        raise ValueError('No finite Id and gm were captured for ' + name + '.') from None
    if abs(current) <= 1e-18 or abs(gm) <= 0:
        raise ValueError('gm/Id is unavailable at zero/negligible current or gm.')
    out = {**geometry, 'id': current, 'gm': gm, 'gmid': abs(gm / current),
           'current_density': abs(current) / geometry['width'] if geometry['width'] and geometry['width'] > 0 else None,
           'source': values.get('source', result.get('engine', ''))}
    for key in ('vgs', 'vds', 'headroom'):
        if values.get(key) is not None: out[key] = scalar(values[key])
    if not all(math.isfinite(out[k]) for k in ('gmid', 'current_density') if out[k] is not None):
        raise ValueError('Nonfinite gm/Id or current density.')
    return out


def width_estimate(point, desired_current):
    current = scalar(desired_current)
    if not point.get('current_density'):
        raise ValueError('Width normalization is unavailable for this model. gm/Id remains valid; sweep its explicit sizing parameters in Circuit search.')
    if current <= 0 or point['current_density'] <= 0:
        raise ValueError('Enter a positive drain current for the width estimate.')
    return current / point['current_density']


def _requirements(job, result):
    from .specifications import for_job, evaluate_rows
    failures = [r['name'] + ': ' + (r['error'] or r['status']) for r in evaluate_rows(for_job(job), result) if r['status'] != 'PASS']
    measured = {m['name']: m for m in result.get('measurements', {}).get('measurements', [])}
    for required in test_plans.requirements(job):
        if not required.get('measurement'): continue
        actual = measured.get(required['name'], {})
        if actual.get('status') not in ('PASS', 'passed'):
            failures.append(required['name'] + ': ' + actual.get('status', 'missing measurement'))
    return failures


def evaluate(manifest, rows):
    """Rank worst-condition objective scores; retain errors and incomplete cases."""
    from .wavecalc import evaluate as expression, UNITS
    current = variation_runs.latest(manifest, rows)
    spec, candidates, terminal = manifest['spec'], {}, 0
    for job in manifest['jobs']:
        case = job['case']; index = case['index']; row = current.get(index)
        item = candidates.setdefault(case['candidate'], dict(candidate=case['candidate'], changes=case['changes'],
                state='Pending', values=[], scores=[], failures=[], failure_details=[], metrics=[dict(values=[], scores=[]) for _ in objectives(spec)], points=[], runs=[], complete=0, total=0))
        item['total'] += 1
        if row: item['runs'].append(row['id'])
        state = row['state'] if row else 'Not queued'
        terminal += state in TERMINAL
        if state != 'Complete':
            if state in TERMINAL: item['failures'].append(case['test_name'] + ': ' + state)
            continue
        item['complete'] += 1
        result = row.get('result', {})
        try:
            if result.get('project_id') != manifest['project_id'] or result.get('design_hash') != design_digest(job['project']) or result.get('cell_id') != job['cell']:
                raise ValueError('Saved result identity does not match its circuit snapshot.')
            settings=job['settings']
            if settings['type']=='testbench':
                settings=next(t for t in job['project']['testbenches'] if t['id']==settings['testbench'])['analysis']
            if result.get('settings')!=settings:
                raise ValueError('Saved result analysis differs from the planned condition.')
            failed = _requirements(job, result)
            item['failures'] += failed
            from .specifications import for_job, evaluate_rows
            for definition in evaluate_rows(for_job(job), result):
                if definition['status'] != 'PASS':
                    item['failure_details'].append(dict(run_id=row['id'], definition=definition, condition=case['labels'], test=case['test_name']))
            gm = spec.get('gmid')
            if gm and case['entry_id'] == gm['entry_id']:
                point = read_gmid(job, result, gm['device'])
                point.update(index=index, run_id=row['id'], labels=case['labels'])
                item['points'].append(point)
                for key, operator in (('min', lambda a, b: a >= b), ('max', lambda a, b: a <= b)):
                    if gm.get(key) not in (None, '') and not operator(point['gmid'], scalar(gm[key])):
                        item['failures'].append('gm/Id ' + key + ' limit failed')
                        item['failure_details'].append(dict(run_id=row['id'],definition=dict(name='gm/Id '+key+' limit failed',device=gm['device']),condition=case['labels'],test=case['test_name']))
                if gm.get('headroom') not in (None, '') and ('headroom' not in point or point['headroom'] < scalar(gm['headroom'])):
                    item['failures'].append('Bias margin missing or below its minimum')
                    item['failure_details'].append(dict(run_id=row['id'],definition=dict(name='Bias margin missing or below its minimum',device=gm['device']),condition=case['labels'],test=case['test_name']))
            for n, objective in enumerate(objectives(spec)):
                if case['entry_id'] != objective['entry_id']: continue
                signal = expression(objective['expression'], result)
                if signal.x is not None or signal.unit != UNITS[objective.get('unit', '')]:
                    raise ValueError('Objective must produce one scalar with the declared unit.')
                value = scalar(signal.real_values()[0]); goal = objective['goal']
                score = abs(value - scalar(objective.get('target', 0))) if goal == 'target' else value if goal == 'minimize' else -value
                item['metrics'][n]['values'].append(value); item['metrics'][n]['scores'].append(score)
                if n == 0: item['values'].append(value); item['scores'].append(score)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            item['failures'].append(case['test_name'] + ': ' + str(exc))
            item['failure_details'].append(dict(run_id=row['id'], definition=dict(name=str(exc)), condition=case['labels'], test=case['test_name']))
    for item in candidates.values():
        item['failures'] = list(dict.fromkeys(item['failures']))
        finished = item['complete'] == item['total']
        item['state'] = 'Failed' if item['failures'] else 'Passed' if finished else 'Pending'
        for metric in item['metrics']:
            metric['score'] = max(metric['scores']) if metric['scores'] else None
            metric['value'] = metric['values'][metric['scores'].index(metric['score'])] if metric['scores'] else None
        item['score'] = max(item['scores']) if item['scores'] else None
        item['worst_value'] = item['values'][item['scores'].index(item['score'])] if item['scores'] else None
    passing = [c for c in candidates.values() if c['state'] == 'Passed' and c['score'] is not None]
    passing = [c for c in passing if all(m['score'] is not None for m in c['metrics'])]
    front = [c for c in passing if not any(
        all(a['score'] <= b['score'] for a, b in zip(other['metrics'], c['metrics'])) and
        any(a['score'] < b['score'] for a, b in zip(other['metrics'], c['metrics'])) for other in passing)]
    for item in candidates.values(): item['pareto'] = item in front
    best = min(passing, key=lambda c: (c['score'], c['candidate'])) if passing and len(objectives(spec)) == 1 else None
    batch_complete = terminal == len(manifest['jobs'])
    return dict(candidates=list(candidates.values()), best=best, pareto=[c['candidate'] for c in front], terminal=terminal, total=len(manifest['jobs']),
                batch_complete=batch_complete, complete=batch_complete and manifest.get('adaptive', {}).get('done', True), current=current)


def apply_candidate(project, manifest, rows, candidate):
    if manifest['spec']['kind'] != 'analog_optimizer':
        raise ValueError('Use a circuit search to validate and apply parameters from a gm/Id sweep.')
    if design_digest(project) != manifest['base_design_hash']:
        raise ValueError('The circuit changed after this search was planned. Run a new search before applying values.')
    report = evaluate(manifest, rows)
    selected = next((c for c in report['candidates'] if c['candidate'] == candidate), None)
    if not report['complete'] or not selected or selected['state'] != 'Passed':
        raise ValueError('Finish the search and select a candidate that passes every saved requirement and condition.')
    q = clone(project)
    for target, value in selected['changes'].items(): set_target(q, manifest['cell_id'], target, value)
    validate(q)
    project.clear(); project.update(q)
    return selected
