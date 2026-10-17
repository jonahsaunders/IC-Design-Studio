"""Reconcile x.29 with an explicit, measured reference isolation choice.

The ordinary bulk references do not request deep-well isolation. Their measured
noncontained NFETs remain visible, and the enabled-switch control must fail.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from scripts import sky130_isolation_policy as policy
from scripts import sky130_voltage_intent_review as previous

ROOT=previous.ROOT
sha=previous.sha
require=previous.require
OPTIONS=ROOT/'docs/qualification/sky130-reference-rule-options.json'
OUTPUT=ROOT/'docs/validation/sky130-isolation-options-2026-10-14.json'
INVENTORY=ROOT/'docs/qualification/sky130-rule-inventory.json'
SCOPE=('Explicit ordinary-bulk reference choice for optional x.29; NOT_REQUESTED is retained separately '
       'from passing rule execution and absent operands. Every noncontained NFET is measured, '
       'and requesting isolation on these same layouts fails. Other physical requirements remain open.')


def read(name):
    return previous.read(ROOT/'docs/validation'/name)


def validate_rows(rows, inventory):
    source=inventory['rule_rows']
    require(len(rows)==len(source) and len({r['id'] for r in rows})==len(rows),
            'Missing or duplicate periphery source rows.')
    keys=('id','rule','source','source_sha256','record')
    # The retained ledger uses compact identities; prose/numeric fields live
    # in the authenticated source inventory. Any supplied copies must agree.
    optional=('description','flags','value','unit')
    require(all(all(row.get(key)==original[key] for key in keys)
                and all(key not in row or row[key]==original[key] for key in optional)
                for row,original in zip(rows,source)),
            'Changed or reordered periphery requirement.')


def preceding(case, inventory):
    pick=lambda data:next(c for c in data['cases'] if c['case']==case)
    base=pick(read('sky130-scope-corrections-2026-10-14.json'));rows=deepcopy(base['rows'])
    indexed={r['id']:r for r in rows}
    esd=pick(read('sky130-esd-fuse-2026-10-14.json'))
    for changed in esd['new_periphery_decisions']:
        require(indexed[changed['id']]['disposition']=='execution-review-required','Overlapping ESD/fuse review.')
        indexed[changed['id']].update(deepcopy(changed))
    require(dict(Counter(r['disposition'] for r in rows))==esd['periphery_counts'],'ESD/fuse ledger does not reconstruct.')
    device=pick(read('sky130-device-intent-2026-10-14.json'))
    for change in device['new_decisions']:
        row=indexed[change['parent']['id']]
        require(row==change['parent'],'Changed device-review parent.')
        row.update(deepcopy(change['decision']),semantic_review='sky130-device-intent-2026-10-14')
    require(dict(Counter(r['disposition'] for r in rows))==device['periphery_counts'],'Device ledger does not reconstruct.')
    voltage=pick(previous.read(previous.OUTPUT))
    for rule,decision in voltage['decisions'].items():
        matches=[r for r in rows if r['rule']==rule]
        require(len(matches)==1 and matches[0]['disposition']=='execution-review-required','Changed voltage-review parent.')
        matches[0].update(deepcopy(decision),semantic_review='sky130-voltage-intent-2026-10-14')
    require(dict(Counter(r['disposition'] for r in rows))==voltage['periphery_counts'],'Voltage ledger does not reconstruct.')
    validate_rows(rows,inventory)
    return rows,voltage


def reconcile(rows, inventory, result):
    validate_rows(rows,inventory)
    require(result==policy.evaluate(result['measurement'],result['options']), 'Changed isolation decision.')
    updated=deepcopy(rows);row=next(r for r in updated if r['id']==policy.RULE_ID)
    require(row['disposition']=='execution-review-required','Isolation option was already reconciled.')
    row.update(disposition=result['disposition'],isolation_check=deepcopy(result),
               reason='Explicit optional-rule policy; measured containment and enabled-switch behavior are retained.',
               semantic_review='sky130-isolation-options-v1')
    require(all(before==after for before,after in zip(rows,updated) if before['id']!=policy.RULE_ID),
            'An unrelated periphery requirement changed.')
    return updated


def build():
    prior=previous.read(previous.OUTPUT);audit=read('sky130-voltage-intent-audit-2026-10-14.json')
    require(sha(previous.OUTPUT)==audit['data']['sha256'] and prior['chunk_complete'] is False,
            'Changed voltage-intent predecessor.')
    for name,digest in prior['inputs'].items():previous.authenticated(ROOT/name,digest)
    contracts=previous.read(OPTIONS)
    require(contracts['schema']==1 and contracts['profile']=='sky130-hd-nominal-bulk'
            and contracts['qualified'] is False and [c['case'] for c in contracts['cases']]==['counter','uart','apb'],
            'Missing explicit reference isolation choices.')
    inventory=previous.read(INVENTORY);fixture=previous.previous.marker.nsm.fixture;cases=[]
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=policy.source_proof(folder/'sources',inventory)
        for entry in manifest['cases']:
            name=entry['case'];contract=next(c for c in contracts['cases'] if c['case']==name)
            rows,voltage=preceding(name,inventory)
            require(contract['gds_sha256']==entry['gds_sha256']==voltage['gds_sha256']
                    and contract['checkpoint_sha256']==voltage['checkpoint_sha256']
                    and contract['top']==entry['top'],'Isolation choice belongs to a different physical reference.')
            require(policy.mode(contract['options']) is False,'This captured bulk-reference contract must be explicit.')
            gds=folder/entry['gds'];layout=k.Layout();layout.read(str(gds))
            result=policy.check(layout,contract['options']);measurement=result['measurement']
            require(sha(gds)==entry['gds_sha256'] and measurement['top']==entry['top'],'Changed isolation layout.')
            native=voltage['execution']['contract_check']
            require(native['status']=='nominal-voltage-contract-consistent'
                    and native['native_models'][previous.voltage.NFET]==measurement['nfet_gates']
                    and native['native_models'][previous.voltage.PFET]==measurement['pfet_gates'],
                    'Fresh NFET/PFET census differs from the checked native reference.')
            control=policy.evaluate(measurement,{'nfet_in_dnwell':True})
            require(control['status']=='FAIL' and control['measured_noncontained_gates']==measurement['nfet_gates']>0
                    and measurement['raw_dnwell_shapes']==0,'Unexpected containment or empty reference control.')
            updated=reconcile(rows,inventory,result)
            cases.append(dict(case=name,gds_sha256=entry['gds_sha256'],checkpoint_sha256=voltage['checkpoint_sha256'],
                result=result,enabled_switch_control=control,
                new_periphery_decision=next(r for r in updated if r['id']==policy.RULE_ID),
                periphery_counts=dict(Counter(r['disposition'] for r in updated)),error_counts=voltage['error_counts'],
                open_periphery=[r for r in updated if r['disposition'] in ('execution-review-required','definition-required')]))
    inputs=[OPTIONS,previous.OUTPUT,ROOT/'docs/validation/sky130-voltage-intent-audit-2026-10-14.json',
            ROOT/'docs/validation/sky130-scope-corrections-2026-10-14.json',
            ROOT/'docs/validation/sky130-esd-fuse-2026-10-14.json',
            ROOT/'docs/validation/sky130-device-intent-2026-10-14.json',INVENTORY]
    sources=[Path(__file__),Path(policy.__file__),ROOT/'tests/test_sky130_isolation_policy.py',
             ROOT/'tests/test_sky130_isolation_review.py',Path(policy.grid.__file__)]
    return dict(schema=1,chunk=6,status='explicit-reference-isolation-policy-reviewed',qualified=False,chunk_complete=False,
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
        source_files={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        bundle=manifest,proof=proof,cases=cases,scope=SCOPE)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    report=build();raw=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:require(OUTPUT.read_bytes()==raw,'Saved isolation policy differs.')
    else:OUTPUT.write_bytes(raw)
    print(json.dumps({c['case']:c['periphery_counts'] for c in report['cases']}))
