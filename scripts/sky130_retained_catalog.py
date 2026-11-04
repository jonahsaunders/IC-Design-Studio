"""Authenticate a complete prior catalog without describing it as fresh execution.

The historical application-integration sources are retained verbatim;
they did not calculate the catalog decisions. All prior geometry helpers and
other source dependencies must still match. Current application validation is
a separate, mandatory part of the batch audit.
"""
from collections import Counter
import hashlib,json
from pathlib import Path
from scripts import sky130_catalog_queue as queue

ROOT=queue.ROOT
BASELINE='docs/validation/sky130-family-package-2026-10-15.json'
BASELINE_SHA='c217dcab9c14c96a402c9e513b66a5e36aa6653b502314e6444a4f7a28959cda'
AUDIT='docs/validation/sky130-family-package-audit-2026-10-15.json'
AUDIT_SHA='a4f1f4c957bbd95316dabc4005e0dcf18b476a28427123e7f6b1807e809936b7'
SNAPSHOTS={name:'docs/validation/sky130-metal-width-baseline-source-2026-10-15/'+Path(name).name+'.txt'
           for name in ('icstudio/digital_sky130_rule_worker.py','icstudio/digital_sky130_rules.py','tests/test_sky130_application_rules.py')}

SNAPSHOTS.update({name:'docs/validation/sky130-retained-integration-source-2026-10-17/'+Path(name).name+'.txt'
    for name in ('icstudio/digital_flow.py','icstudio/digital_macro.py','icstudio/interchange.py')})


# Preserve the exact tested converter; current mask-read safety is tested separately.
SNAPSHOTS['icstudio/engines.py']='docs/validation/retained-engine-source-2026-10-18/engines.py.txt'

def require(condition,message):
    if not condition:raise ValueError(message)


def checked(root,name,digest):
    root=Path(root).resolve();path=(root/name).resolve()
    require(path.is_relative_to(root),'Retained catalog dependency escapes repository.')
    raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'Changed retained catalog dependency: '+name)
    return raw


def validate(base,audit,catalog):
    require(base.get('schema')==1 and base.get('chunk')==6 and base.get('qualified')is False and base.get('chunk_complete')is False,
            'Unexpected baseline qualification or schema.')
    require(audit.get('qualified')is False and audit.get('chunk_complete')is False and audit.get('status')=='family-package-application-integration-verified',
            'Unverified baseline audit.')
    require(audit.get('measurements')==dict(path=BASELINE,sha256=BASELINE_SHA) and audit.get('source_files')==base.get('source_files'),
            'Baseline audit does not bind the complete catalog and its sources.')
    require(base.get('reference_cases')==list(queue.CASES)==base.get('selected_cases') and
            [r['case'] for r in base['cases']]==list(queue.CASES)==[r['case'] for r in audit['cases']],
            'Baseline omits or duplicates a reference.')
    queue.validate_catalog(catalog)
    for row,accepted in zip(base['cases'],audit['cases']):
        queue.validate_rows(row['rows'],catalog)
        counts=dict(Counter(r['disposition'] for r in row['rows']))
        require(counts==row['counts']==accepted['counts'] and row['gds_sha256']==accepted['gds_sha256'],
                'Baseline reference identity or counts changed.')
        require(set(row['provenance'])=={r['id'] for r in row['rows'] if r['disposition']!='unreviewed'},
                'Baseline has incomplete decision provenance.')
        require(accepted['application']['status']=='application-checks-and-export-pass','Baseline application was not accepted.')
    require(set(audit['systems'])=={'win32','linux'},'Baseline lacks both operating systems.')
    for system in audit['systems'].values():
        test=system['tests']
        require(test['status']=='PASS' and test['tests']==286 and test['failures']==test['errors']==test['skipped']==0,
                'Baseline regression validation failed or skipped.')
        require(system['controls']['status']=='PASS' and len(system['controls']['cases'])==29,'Baseline controls incomplete.')
        require(set(system['replays'])==set(queue.CASES) and all(r['result']['status']=='PASS' for r in system['replays'].values()),
                'Baseline full-catalog replays incomplete.')
    require(audit['systems']['win32']['controls']['cases']==audit['systems']['linux']['controls']['cases'],
            'Baseline cross-system controls differ.')
    for case in queue.CASES:
        require(audit['systems']['win32']['replays'][case]['result']['data_sha256']==
                audit['systems']['linux']['replays'][case]['result']['data_sha256'],'Baseline cross-system catalogs differ.')


def load(root=ROOT):
    base=json.loads(checked(root,BASELINE,BASELINE_SHA));audit=json.loads(checked(root,AUDIT,AUDIT_SHA))
    for name,digest in base['inputs'].items():checked(root,name,digest)
    sources={};historical={}
    require(set(SNAPSHOTS)<=base['source_files'].keys(),'Historical source identity is missing.')
    for name,digest in base['source_files'].items():
        actual=SNAPSHOTS.get(name,name);checked(root,actual,digest);sources[actual]=digest
        if name in SNAPSHOTS:historical[name]=dict(path=actual,sha256=digest)
    catalog=json.loads((Path(root)/queue.CATALOG).read_bytes())
    require(queue.CATALOG in base['inputs'] or queue.CATALOG in base['source_files'],'Catalog is not authenticated by baseline.')
    validate(base,audit,catalog)
    return base,dict(catalog=dict(path=BASELINE,sha256=BASELINE_SHA),audit=dict(path=AUDIT,sha256=AUDIT_SHA),
        historical_application_sources=historical,authenticated_sources=sources,
        execution='Prior decisions and source proofs are authenticated retained results, not rerun geometry. '
                  'Only the new metal-width checker executes here. Current application, export and regression validation is recorded separately.')
