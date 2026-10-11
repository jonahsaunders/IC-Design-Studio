"""Bind reviewed manual requirements to actual low-voltage drawn-mask checks.

This is a partial rule ledger. It neither treats a native deck's name mentions
as execution nor promotes missing/failed checks to passing requirements.
"""
from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
from scripts.sky130_block_applicability import audit as applicability
from scripts.sky130_raw_feol import audit as raw_feol
from scripts.sky130_raw_feol import check as raw_checks


RAW_BINDINGS={
    'n/psd.1':('n/psd.1.n','n/psd.1.p'),
    'n/psd.2':('n/psd.2.n','n/psd.2.p'),
    # Manual merge is required only below the minimum space. The complete
    # spacing/notch check establishes that its trigger is absent.
    'n/psd.3':('n/psd.2.n','n/psd.2.p'),
    'n/psd.5a':('n/psd.5a.n','n/psd.5a.p'),
    'n/psd.5b':('n/psd.5b.n','n/psd.5b.p'),
    'n/psd.6':('n/psd.6.n','n/psd.6.p'),
    'n/psd.7':('n/psd.7.n','n/psd.7.p'),
    'n/psd.8':('n/psd.8.n','n/psd.8.p'),
    'n/psd.9':('n/psd.9.n','n/psd.9.p'),
    'n/psd.10a':('n/psd.10a',),
    'n/psd.10b':('n/psd.10b',),
    'n/psd.11':('n/psd.11.n','n/psd.11.p'),
    **{'hvtp.'+str(i):('hvtp.'+str(i),) for i in range(1,7)},
}
# Preserve the published source spelling; checker identifiers omit this space.
RAW_BINDINGS={name.replace('n/psd.','n/ psd.'):checks for name,checks in RAW_BINDINGS.items()}


def bind(review,raw):
    if review['gds_sha256']!=raw['gds_sha256']:
        raise ValueError('Rule reports refer to different submitted layouts.')
    checks={r['rule']:r for r in raw['checks']}
    if len(checks)!=len(raw['checks']) or not checks:
        raise ValueError('Duplicate or empty raw rule inventory.')
    if (raw['status']!='PASS' or raw['violations']!=0 or
            any(type(r['violations']) is not int or r['violations']!=0 for r in checks.values())):
        raise ValueError('A failed or unsupported raw geometry profile cannot establish execution.')
    required={name for names in RAW_BINDINGS.values() for name in names}
    inventory={row['rule'] for row in raw_checks({})['checks']}
    if not required<=checks.keys() or checks.keys()!=inventory:
        raise ValueError('A required raw rule check or profile guard is absent or unexpected.')
    result=deepcopy(review);seen=[]
    for row in result['rows']:
        if row['rule'] not in RAW_BINDINGS:continue
        if row['disposition']!='execution-review-required':
            raise ValueError('A rule binding would overwrite a different disposition.')
        names=RAW_BINDINGS[row['rule']];seen.append(row['rule'])
        row.update(disposition='executed-reviewed',reason=(
            'The manual-merge trigger is absent: both drawn implant spacing/notch checks pass.' if row['rule']=='n/ psd.3' else
            'Reviewed low-voltage requirement is executed on the actual drawn masks with all profile guards passing.'),
            execution=dict(checker_sha256=raw['checker_sha256'],checks=list(names)))
    if Counter(seen)!=Counter(RAW_BINDINGS.keys()):
        raise ValueError('The source inventory does not contain each reviewed rule exactly once.')
    result.update(status='partial-rule-execution-reviewed',qualified=False,chunk_complete=False,
        counts=dict(Counter(r['disposition'] for r in result['rows'])),raw_geometry=raw,
        applicability_checker_sha256=review['checker_sha256'],
        scope='Eighteen reviewed low-voltage implant/HVTP requirements plus explicit block applicability. Remaining periphery, error-catalog, density, electrical and application requirements are still open.')
    return result


def audit(path,source):
    path=Path(path);review=applicability(path,source);raw=raw_feol(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=raw['gds_sha256']:
        raise ValueError('Submitted layout changed during rule execution.')
    result=bind(review,raw)
    result['checker_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result
