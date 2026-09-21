"""Seeded trial expansion and explicit, PVT-separated campaign yield evidence."""
import itertools
import math
import random
from .model import clone, scalar, digest


def configuration(project,plan):
    raw=plan.get('statistics')
    if not raw:return None
    if not isinstance(raw,dict):raise ValueError('Statistical verification needs a saved sampling configuration.')
    spec=clone(raw);kind=spec.get('kind')
    if kind not in ('monte_carlo','correlated','model_mismatch'):raise ValueError('Choose independent tolerances, correlated tolerances or a validated model mismatch distribution.')
    if type(spec.get('count')) is not int or not 2<=spec['count']<=10000:raise ValueError('Statistical campaigns need 2–10,000 trials within the case limit.')
    if type(spec.get('seed')) is not int or not -(2**63)<=spec['seed']<2**63:raise ValueError('Enter a signed 64-bit integer sampling seed.')
    if any(e['engine']=='digital' for e in plan['entries']):raise ValueError('Use an analog-only plan for statistical verification.')
    cid=spec.get('cell')
    if cid not in {c['id'] for c in project['cells']}:raise ValueError('Choose the circuit cell containing the statistical parameter targets.')
    if kind=='model_mismatch':
        declared=project['pdk'].get('statistical_models',{}).get(spec.get('model'),{})
        if not declared.get('validated') or not declared.get('evidence') or not declared.get('variations'):
            raise ValueError('Choose a validated PDK statistical model with evidence and explicit numeric parameter mappings.')
        spec['variations']=clone(declared['variations']);spec['model_evidence']=clone(declared)
    rows=spec.get('variations')
    if not isinstance(rows,list) or not 1<=len(rows)<=8:raise ValueError('Choose one to eight statistical parameter mappings.')
    if any(row.get('target') in ('temperature','supply') for row in rows):
        raise ValueError('Keep temperature and supply as explicit PVT conditions; statistical targets must name circuit parameters.')
    from .analog_robustness import validate_variables
    validate_variables(project,cid,plan,rows,'tolerance')
    extended=any(row.get('absolute_sigma') or row.get('group') or row.get('rho') or row['target'].startswith('@') or '.model_params.' in row['target'] for row in rows)
    legacy=kind=='monte_carlo' or kind=='model_mismatch' and not extended
    if legacy:
        from .studies import targets
        for row in rows:
            if row['target'] not in targets(project,cid):raise ValueError('Independent component tolerances require an existing numeric component target.')
            if row.get('absolute_sigma') or row.get('group') or row.get('rho'):
                raise ValueError('Choose correlated tolerances to use absolute sigma or shared normal factors.')
            if not 0<scalar(row.get('relative_sigma',0))<1:raise ValueError('Independent relative sigma must be between zero and one.')
    spec['sampling']='legacy-independent-v1' if legacy else 'shared-normal-factor-v1'
    spec['scope']=('Validated PDK statistical model: '+str(spec['model']) if kind=='model_mismatch' else
                   'User-declared component tolerances; this is not foundry manufacturing yield.')
    return spec


def samples(project,plan,spec=None):
    """Same trial realization across every test and PVT corner; never resample."""
    spec=spec or configuration(project,plan)
    if spec is None:
        yield None,{}
        return
    cid=spec['cell'];rows=spec['variations']
    if spec['sampling']=='legacy-independent-v1':
        from .studies import get_target
        rng=random.Random(spec['seed'])
        def independent():
            for _ in range(spec['count']):
                changes={}
                for row in rows:
                    sigma=scalar(row['relative_sigma'])
                    multiplier=1+(rng.gauss(0,sigma) if row.get('distribution','normal')=='normal' else rng.uniform(-math.sqrt(3)*sigma,math.sqrt(3)*sigma))
                    changes[row['target']]=get_target(project,cid,row['target'])*multiplier
                yield changes
        stream=independent()
    else:
        from .analog_robustness import iter_tolerance
        stream=iter_tolerance(project,cid,plan,rows,spec['count'],spec['seed'])
    for trial,changes in enumerate(stream,1):yield trial,changes


def report(plan,rows):
    """Reduce scalar status evidence, counting each shared trial exactly once.

    A failed simulation or missing/error measurement is unresolved, never a
    statistical circuit failure. Confidence is withheld until all trials resolve.
    PVT conditions are reported separately; joint yield requires every condition.
    """
    spec=plan.get('statistics')
    if not spec:return None
    from .analog_robustness import wilson
    total=spec['count'];entries={e['id'] for e in plan['entries']}
    conditions=[(c,scalar(t),scalar(v) if v is not None else None)
                for c,t,v in itertools.product(plan['corners'],plan['temperatures'],plan.get('voltages') or [None])]
    # One byte per expected case; state vectors stay small even for 10,000 cases.
    states={condition:{trial:{} for trial in range(1,total+1)} for condition in conditions}
    for row in rows:
        labels=row['labels'];condition=tuple(labels.get(k) for k in ('corner','temperature','voltage'));trial=labels.get('trial');entry=row.get('entry_id')
        if condition not in states or trial not in states[condition] or entry not in entries or labels.get('seed')!=spec['seed']:continue
        requirements=(row.get('summary') or {}).get('requirements',[])
        outcomes=[r.get('status') for r in requirements]
        state='unresolved'
        if row['state']=='Complete' and outcomes and all(v in ('PASS','FAIL') for v in outcomes):
            state='failed' if 'FAIL' in outcomes else 'passed'
        states[condition][trial][entry]=state
    def outcome(per_entry):
        values=list(per_entry.values())
        if len(values)!=len(entries) or 'unresolved' in values:return 'unresolved'
        return 'failed' if 'failed' in values else 'passed'
    per_condition={condition:{trial:outcome(by_entry) for trial,by_entry in trials.items()} for condition,trials in states.items()}
    def summarize(values):
        passed=values.count('passed');failed=values.count('failed');unknown=total-passed-failed
        return dict(trials=total,passed=passed,failed=failed,unresolved=unknown,
                    pass_fraction=passed/total if unknown==0 else None,
                    confidence_95=wilson(passed,total) if unknown==0 else None,
                    unresolved_bounds=[passed/total,(passed+unknown)/total])
    condition_rows=[dict(corner=c,temperature=t,voltage=v,**summarize(list(trials.values()))) for (c,t,v),trials in per_condition.items()]
    joint=[]
    for trial in range(1,total+1):
        outcomes=[trials[trial] for trials in per_condition.values()]
        joint.append('unresolved' if 'unresolved' in outcomes else 'failed' if 'failed' in outcomes else 'passed')
    return dict(kind=spec['kind'],seed=spec['seed'],model=spec.get('model'),
                scope='Validated PDK statistical model: '+str(spec.get('model')) if spec['kind']=='model_mismatch' else 'User-declared tolerances; this is not foundry manufacturing yield.',
                confidence_method='95% Wilson binomial interval over independent trials; shared PVT cases are not independent samples.',
                pvt=condition_rows,joint=summarize(joint))
