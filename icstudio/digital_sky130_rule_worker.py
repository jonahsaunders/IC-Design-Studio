"""Isolated runner for hash-authenticated, reviewed SKY130 checker sources."""
import importlib
import json
from pathlib import Path
import sys

from .digital_sky130_rules import resources, evaluate, require, SCOPE
from .digital_sky130_rules_lock import PROFILES, FILES, RECIPE
from .model import atomic_write, file_digest


def execute(request):
    output = Path(request['output']); output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, recipe=RECIPE, status='FAIL', qualified=False, chunk_complete=False, scope=SCOPE,
                  policy=request['policy'], gds_sha256=request['gds_sha256'],
                  checkpoint_sha256=request['checkpoint_sha256'], top=request['top'],
                  platform_fingerprint=request['platform_fingerprint'], profiles={})
    def save(name, value):
        atomic_write(output/name, json.dumps(value, indent=2)+'\n')
    try:
        policy = request['policy']; base = Path(request['resources']).resolve()
        resources(base, policy['preparation_sha256'])
        require(not any(name == 'scripts' or name.startswith('scripts.') for name in sys.modules),
                'Run SKY130 checkers in a fresh interpreter to avoid another helper namespace.')
        sys.dont_write_bytecode = True; sys.path.insert(0, str(base/'helpers'))
        from scripts import sky130_rule_execution as execution
        gds = Path(request['gds']); checkpoint = Path(request['checkpoint'])
        def unchanged():
            require(file_digest(gds) == request['gds_sha256'] and
                    file_digest(checkpoint) == request['checkpoint_sha256'], 'SKY130 inputs changed during checking.')
        unchanged()
        review = execution.applicability(gds, base/'sources'); save('applicability.json', review)
        errors = []
        for name, expected in PROFILES.items():
            try:
                value = importlib.import_module('scripts.'+expected['module']).audit(gds)
                report['profiles'][name] = value; save(name+'.json', value)
                if value['status'] != 'PASS':
                    errors.append(name+' failed')
            except Exception as error:
                errors.append(name+': '+str(error)); save(name+'.json', dict(status='ERROR', error=str(error)))
            unchanged()
            print('SKY130 '+name+': '+report['profiles'].get(name, {}).get('status', 'ERROR'), flush=True)
        require(not errors, '; '.join(errors))
        profiles = report['profiles']
        review = execution.bind(review, profiles['raw_geometry'])
        for bind, key in [(execution.bind_geometry, 'low_voltage_geometry'),
                          (execution.bind_interconnect, 'interconnect_geometry'),
                          (execution.bind_wide, 'wide_metal_geometry'),
                          (execution.bind_global, 'global_geometry'),
                          (execution.bind_connectivity, 'floating_connectivity')]:
            review = bind(review, profiles[key])
        review['checker_sha256'] = FILES['helpers/scripts/sky130_rule_execution.py']
        from .digital_sky130_scope import correct
        review = correct(review)
        from .digital_sky130_pad_scope import correct as correct_pad_scope
        review = correct_pad_scope(review)
        from .digital_sky130_catalog_context import audit as catalog_context
        report['catalog_context'] = catalog_context(gds)
        save('catalog_context.json', report['catalog_context'])
        from .digital_sky130_catalog_labels import audit as catalog_labels
        report['catalog_labels'] = catalog_labels(gds)
        save('catalog_labels.json', report['catalog_labels'])
        report.update(status='reviewed-profiles-pass', ledger=review,
                      coverage=dict(rows=len(review['rows']), counts=review['counts'], complete=False))
        unchanged(); resources(base, policy['preparation_sha256'])
        evaluate(report, request['gds_sha256'], request['checkpoint_sha256'], request['top'],
                 request['platform_fingerprint'], policy)
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        save('report.json', report)
    return report
