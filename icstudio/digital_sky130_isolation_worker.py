"""Fresh-process execution of the captured x.29 checker."""
import json
from pathlib import Path
import sys

from .digital_sky130_isolation import resources, evaluate, require, valid_policy, SCOPE
from .digital_sky130_isolation_lock import RECIPE, REVISION, RULE
from .model import atomic_write, file_digest


def execute(request):
    output = Path(request['output']); output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, recipe=RECIPE, revision=REVISION, rule=RULE, status='FAIL', qualified=False, scope=SCOPE,
                  **{key: request[key] for key in ('policy', 'gds_sha256', 'checkpoint_sha256', 'top', 'platform_fingerprint')})
    try:
        policy = request['policy']; valid_policy(policy)
        base = Path(request['resources']).resolve(); resources(base, policy['preparation_sha256'])
        require(not any(name == 'scripts' or name.startswith('scripts.') for name in sys.modules),
                'Run SKY130 isolation checking in a fresh interpreter.')
        sys.dont_write_bytecode = True; sys.path.insert(0, str(base/'helpers'))
        from scripts.sky130_isolation_geometry import check
        import klayout.db as k
        def unchanged():
            require(all(file_digest(request[key]) == request[key+'_sha256'] for key in ('gds', 'checkpoint')),
                    'SKY130 isolation inputs changed during checking.')
        unchanged(); layout = k.Layout(); layout.read(request['gds'])
        report.update(check(layout, policy['nfet_in_dnwell']))
        unchanged(); resources(base, policy['preparation_sha256'])
        evaluate(report, request['gds_sha256'], request['checkpoint_sha256'], request['top'],
                 request['platform_fingerprint'], policy)
        print('SKY130 NMOS isolation: '+report['status'], flush=True)
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        atomic_write(output/'report.json', json.dumps(report, indent=2)+'\n')
    return report
