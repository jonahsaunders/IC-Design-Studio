"""Resolved, revision-bound evidence and single-variable simulation experiments."""
import ast
from collections import Counter
import json
import re
from . import ai_context, studies
from .ai_testbench import number
from .analog_debug import contexts, operating_rows, requirement_waveform
from .model import clone, digest, scalar, validate
from .test_plans import requirements


def bench_for(job):
    key = job['settings'].get('testbench')
    return next((b for b in job['project'].get('testbenches', []) if b['id'] == key), None)


def solver(job):
    # Historical saved-bench jobs sometimes recorded the default engine, while
    # the worker always dispatched the bench to ngspice.
    return 'ngspice' if job['settings']['type']=='testbench' else job['engine']


def conditions(job):
    analysis = (bench_for(job) or {}).get('analysis', job['settings'])
    labels = job.get('comparison_conditions', job.get('case', {}).get('labels', {}))
    return {k:v for k,v in {**labels, 'corner':analysis.get('corner', labels.get('corner','nominal')),
                            'temperature':analysis.get('temperature',labels.get('temperature',27))}.items() if v is not None}


def checks(row):
    job, result = row['job'], row.get('result') or {}
    definitions = requirements(job)
    measured = result.get('measurements') or {}
    measurements = measured.get('measurements', []) if isinstance(measured, dict) else measured
    items = []
    for category, rows in [('specification', result.get('specifications') or []), ('measurement', measurements)]:
        for actual in rows:
            definition = next((d for d in definitions if d['name'] == actual.get('name')
                               and bool(d.get('measurement')) == (category == 'measurement')), {})
            fields = {k: actual[k] for k in ('name','unit','min','max','expression','node','source','kind') if k in actual}
            fields.update(definition)
            identity = (category, fields.get('definition') or digest(fields))
            items.append(dict(definition=fields, identity=identity, actual=ai_context.public_fields(actual,
                              ('name','unit','value','status','error','margin','minimum','maximum'), 400)))
    return items


def saved_check(row, name):
    return next((c for c in checks(row) if c['definition'].get('name') == name), None)


def compatible_runs(studio, row, check):
    if not check:
        return []
    job = row['job']
    def scope(j):
        analysis = (bench_for(j) or {}).get('analysis', j['settings'])
        return (j['project']['id'], j['cell'], solver(j), j['settings']['type'],
                j['settings'].get('testbench'), analysis.get('type'))
    matches = []
    for other in reversed(studio.run_manager.rows):
        if other['id'] == row['id'] or other['state'] != 'Complete' or scope(other['job']) != scope(job):
            continue
        matched = next((c for c in checks(other) if c['identity'] == check['identity']), None)
        if matched:
            matches.append((other, matched))
    return matches


def references(definition):
    found = []
    if definition.get('expression'):
        try:
            tree = ast.parse(definition['expression'], mode='eval')
        except (SyntaxError, ValueError):
            return found
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('V','I'):
                found.extend(('voltage' if node.func.id == 'V' else 'current', a.value) for a in node.args
                             if isinstance(a, ast.Constant) and isinstance(a.value, str))
    for key, kind in [('node','voltage'), ('source','current')]:
        if definition.get(key):
            found.append((kind, definition[key]))
    return list(dict.fromkeys(found))


def devices_for(row, definition, probe, device):
    result = row.get('result') or {}
    refs = references(definition)
    if probe:
        refs.append(probe)
    names = {n.casefold() for _, n in refs}
    if not names and not device:
        return []
    rows = operating_rows(row['job']['project'], row['job']['cell'], result)
    return [d for d in rows if d['name'] == device or d['name'].casefold() in names or
            any(net.casefold() in names for net in d['pins'].values())][:32]


def trace_view(result, definition, probe=None):
    if not result or not result.get('x'):
        return None
    if not probe:
        try:
            derived = requirement_waveform(result, definition)
        except (SyntaxError, ValueError):
            derived = None
        if derived:
            return derived
    for kind, name in ([probe] if probe else references(definition)):
        traces = result.get('currents' if kind == 'current' else 'traces', {})
        key = next((k for k in traces if k.casefold() == name.casefold()), None)
        if key is not None:
            return {**result, 'traces': {name: traces[key]}, 'plot_unit': 'A' if kind == 'current' else result.get('plot_unit','V')}
    return None


SUPPORTED = ('op','tran','ac','dc','noise','testbench')


def device_parameters(job):
    project, root = job['project'], job['cell']
    tree = contexts(project,root)
    occurrences = Counter(c['cell_id'] for c in tree)
    cells = {c['id']:c for c in project['cells']}
    for context in tree:
        cid = context['cell_id']
        if occurrences[cid] != 1:
            continue
        cell = cells[cid]
        # Numeric study fields depend on the device, its cell and global parameters.
        # Resolve against that scope so the study API needn't rescan every sibling.
        local_cell = {**cell, 'devices':[]}
        local_project = {**project,'cells':[local_cell]}
        for device in cell['devices']:
            local_cell['devices'] = [device]
            for field in studies.targets(local_project,cid):
                yield context['path'] + field, cid, field, studies.get_target(local_project,cid,field)


def parameters(job):
    if job['settings']['type'] not in SUPPORTED or job['engine'] not in ('builtin','ngspice'):
        return {}
    analysis = (bench_for(job) or {}).get('analysis', job['settings'])
    values = {'temperature': analysis.get('temperature', 27)}
    for key, _, _, value in device_parameters(job):
        values[key] = value
    return values


def variant_job(job, target, value):
    choices = parameters(job)
    if target not in choices:
        raise ValueError('Choose a listed simulation parameter.')
    value = number(value)
    if value == scalar(choices[target]):
        raise ValueError('Enter a different value for the variant.')
    variant = clone(job)
    if target == 'temperature':
        if value <= -273.15:
            raise ValueError('Temperature must exceed absolute zero.')
        variant['settings']['temperature'] = value
        bench = bench_for(variant)
        if bench:
            bench['analysis']['temperature'] = value
    else:
        cid, field = next((cid,field) for key,cid,field,_ in device_parameters(job) if key==target)
        studies.set_target(variant['project'], cid, field, value)
    validate(variant['project'])
    return variant


def split_suggestion(answer, choices):
    """Optional final model suggestion. The simulator accepts only a reviewed native target."""
    match = re.search(r'\n*```experiment\s*\n(.*?)\n```\s*$', answer, re.S | re.I)
    if not match:
        return answer, None
    try:
        item = json.loads(match[1])
        if isinstance(item, dict) and set(item) == {'target','value'} and item['target'] in choices:
            number(item['value'])
            return answer[:match.start()].strip(), (item['target'], str(item['value']))
    except (ValueError, TypeError, OverflowError, RecursionError):
        pass
    return answer[:match.start()].strip(), None


def evidence(studio, row, check, probe, device):
    job = row['job']
    detail = dict(run=row['name'], state=row['state'], revision=job['project']['revision'],
                  engine=solver(job), analysis=job['settings']['type'], conditions=conditions(job),
                  log_tail=ai_context.excerpt(row.get('log',''), 3500))
    cell = next(c for c in job['project']['cells'] if c['id']==job['cell'])
    detail['circuit'] = cell['name']
    mentioned = ai_context.mentioned_devices(cell,detail['log_tail'])
    if mentioned:
        detail['devices_mentioned_in_log'] = mentioned
    definition = check['definition'] if check else {}
    if check:
        detail['requirement'] = {**definition, **check['actual']}
        detail['other_recorded_conditions'] = [
            dict(run=r['name'], revision=r['job']['project']['revision'], conditions=conditions(r['job']), **c['actual'])
            for r, c in compatible_runs(studio, row, check)[:24]]
    elif row['state'] != 'Complete' or ai_context.failed_checks(row):
        detail['failed_checks'] = ai_context.failed_checks(row)[:32]
    devices = devices_for(row, definition, probe, device)
    if devices:
        detail['connected_devices'] = [{k:d[k] for k in ('name','pins','voltages','values')} for d in devices[:12]]
    view = trace_view(row.get('result'), definition, probe)
    if view:
        name, values = next(iter(view['traces'].items()))
        if values:
            detail['waveform'] = dict(trace=name, samples=len(values), minimum=min(values), maximum=max(values),
                                     final=values[-1], unit=view.get('plot_unit','V'))
    choices = parameters(job)
    if choices:
        detail['experiment_parameters'] = dict(list(choices.items())[:96])
    return detail
