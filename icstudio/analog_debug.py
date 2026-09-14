"""Instance-aware navigation of immutable analog simulation evidence."""
import re
from .model import clone


def contexts(project, root):
    """Keep repeated masters separate; port nets follow the selected instance."""
    by = {c['id']: c for c in project['cells']}
    result = []
    def walk(cid, path, mapping, parents):
        if cid in parents or len(parents) > 12:
            raise ValueError('Recursive or excessively deep circuit hierarchy.')
        cell = by[cid]
        def net(name):
            return name if name == '0' or name in project.get('global_nets', []) else mapping.get(name, path + name)
        result.append(dict(cell_id=cid, path=path, nets={n: net(n) for d in cell['devices'] for n in d['nets'].values()}))
        for d in cell['devices']:
            if d['kind'] == 'X':
                walk(d['cell'], path + d['name'] + '/', {pin: net(n) for pin, n in d['nets'].items()}, parents + [cid])
    walk(root, '', {}, [])
    return result


def operating_rows(project, root, result):
    """Only display captured values, never infer model internals or current."""
    by = {c['id']: c for c in project['cells']}
    devices = {k.casefold(): v for k, v in result.get('device_operating_point', {}).items()}
    currents = {k.casefold(): v for k, v in result.get('operating_currents', {}).items()}
    volts = {k.casefold(): v for k, v in result.get('operating_point', {}).items()}
    volts['0'] = 0.
    rows = []
    for context in contexts(project, root):
        for d in by[context['cell_id']]['devices']:
            if d['kind'] == 'X' or d.get('native_spice', {}).get('type') == 'program':
                continue
            name = context['path'] + d['name']; values = clone(devices.get(name.casefold(), {}))
            if name.casefold() in currents: values['current'] = currents[name.casefold()]
            pins = {pin: context['nets'][net] for pin, net in d['nets'].items()}
            rows.append(dict(cell_id=context['cell_id'], path=context['path'], object=d['id'], name=name,
                             pins=pins, voltages={pin: volts.get(net.casefold()) for pin, net in pins.items()}, values=values))
    return rows


def convergence_hints(log):
    """Actionable suggestions accompany the original log; no silent solver edits."""
    rules = [
        (r'singular matrix|floating|no dc path', 'Check floating nodes', 'Inspect the named node for a DC path to ground, missing bulk connections, and loops of ideal voltage sources.'),
        (r'timestep too small|time step too small', 'Inspect the failing time', 'Check abrupt source edges and ideal switching loops; give pulse sources finite rise/fall times and review initial bias.'),
        (r'converg|iteration limit|gmin|source stepping', 'Check operating bias', 'Run an operating-point analysis first. Check supply polarity, W/L units, model corner, and bulk terminals before changing solver tolerances.'),
        (r'unknown subckt|unknown model|could not find.*model|can.t find.*model', 'Resolve the device model', 'Check the linked library, model name, corner section, and embedded model assets in this saved run.'),
    ]
    return [dict(title=title, detail=detail) for pattern, title, detail in rules if re.search(pattern, log, re.I)]


def comparison_rows(report):
    """Join by identity and unit, retaining missing/failed measurements."""
    stages = {s['name']: s.get('evidence', {}) for s in report.get('stages', [])}
    rows = []
    for field in ('measurements', 'specifications'):
        before = {m['name']: m for m in stages.get('schematic_simulation', {}).get(field, [])}
        after = {m['name']: m for m in stages.get('post_layout_simulation', {}).get(field, [])}
        for name in dict.fromkeys([*before, *after]):
            a, b = before.get(name, {}), after.get(name, {})
            comparable = bool(a and b and a.get('unit', '') == b.get('unit', ''))
            av, bv = a.get('value'), b.get('value')
            rows.append(dict(name=name, kind=field, unit=a.get('unit', b.get('unit', '')), before=av, after=bv,
                             delta=bv-av if comparable and av is not None and bv is not None else None,
                             before_status=a.get('status', 'NOT RUN'), after_status=b.get('status', 'NOT RUN'),
                             detail='Units differ; values cannot be compared.' if a and b and not comparable else a.get('error', '') or b.get('error', '')))
    return rows
