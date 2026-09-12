"""Validate portable named simulation setups before saving or launching."""
from .model import scalar


def validate_plan(project):
    from .test_plans import validate_plans
    validate_plans(project)
    setups=project.get('simulation_setups',[])
    if not isinstance(setups,list) or len(setups)>100:raise ValueError('Use at most 100 named analysis setups.')
    cells={c['id'] for c in project['cells']}
    for s in setups:
        if not isinstance(s,dict) or not isinstance(s.get('name'),str) or not s['name'].strip() or len(s['name'])>100:raise ValueError('Each analysis setup requires a name of 1–100 characters.')
        if s.get('cell') not in cells:raise ValueError('An analysis setup refers to a missing cell. Remove that setup before deleting its cell.')
        if s.get('engine') not in ('builtin','ngspice'):raise ValueError('Unknown analysis setup engine.')
        if not isinstance(s.get('enabled',True),bool):raise ValueError('Analysis setup enabled state must be a checkbox value.')
        a=s.get('settings')
        if isinstance(a,dict) and a.get('type') in ('xschem','program'):
            if s['engine']!='ngspice':raise ValueError('Xschem programs run with ngspice.')
            continue
        if not isinstance(a,dict) or a.get('type') not in ('tran','op','dc','ac','noise'):raise ValueError('Choose a supported circuit analysis in each setup.')
        for key in ('stop','step','dc_start','dc_stop','dc_step','start','end','points','temperature'):
            if key not in a:raise ValueError('Missing analysis setup field: '+key)
            scalar(a[key])
        if not isinstance(a.get('source'),str):raise ValueError('Missing analysis source name.')
