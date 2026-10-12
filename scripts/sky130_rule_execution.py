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
from scripts.sky130_low_voltage_geometry import audit as low_voltage_geometry
from scripts.sky130_low_voltage_geometry import check as geometry_checks
from scripts.sky130_interconnect_geometry import audit as interconnect_geometry
from scripts.sky130_interconnect_geometry import check as interconnect_checks


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

GEOMETRY_BINDINGS={
    'nwell.1':('nwell.1',),'nwell.2a':('nwell.2a',),
    'nwell.2b':('nwell.2a',),'nwell.4':('nwell.4',),
    'difftap.1':('difftap.1.diff','difftap.1.tap'),
    **{'difftap.'+s:('difftap.'+s,) for s in ('2','2b','3','8','9','10','11')},
    **{'poly.'+s:('poly.'+s,) for s in ('1a','2','4','5','6','7','8','10','11','12')},
    **{'npc.'+s:('npc.'+s,) for s in ('1','2','4')},'npc.3':('npc.2',),
    **{'licon.'+s:('licon.'+s,) for s in ('1','2','4','5a','6','8','9','11','13','14','15','16','17','18')},
    'licon.3':('licon.1',),'licon.11a':('licon.11ab',),'licon.11b':('licon.11ab',),
}

INTERCONNECT_BINDINGS={
    **{'li.'+s+'.-':('li.'+s+'.-',) for s in ('1','3','5','6')},
    **{'m1.'+s:('m1.'+s,) for s in ('1','2','4','5','6','7')},
    **{'m2.'+s:('m2.'+s,) for s in ('1','2','4','5','6','7')},
    **{'m3.'+s:('m3.'+s,) for s in ('1','2','4','6')},
    **{'m4.'+s:('m4.'+s,) for s in ('1','2','3','4a')},
    **{'m5.'+s:('m5.'+s,) for s in ('1','2','3','4')},
    'ct.1':('ct.size',),'ct.2':('ct.2',),'ct.3':('ct.size',),'ct.4':('ct.4',),
    'via.1a':('via.size',),'via.2':('via.2',),'via.3':('via.size',),
    'via.4a':('via.4a',),'via.5a':('via.5a',),
    'via2.1a':('via2.size',),'via2.2':('via2.2',),'via2.3':('via2.size',),
    'via2.4':('via2.4',),'via2.5':('via2.5',),'via2.X.1':('via2.X.1',),
    'via3.1':('via3.size',),'via3.2':('via3.2',),'via3.3':('via3.size',),
    'via3.4':('via3.4',),'via3.5':('via3.5',),
    'via4.1':('via4.size',),'via4.2':('via4.2',),'via4.3':('via4.size',),'via4.4':('via4.4',),
    **{'licon.'+s:('licon.'+s,) for s in ('5b','5c','7','8a')},
}


def bind_interconnect(review,interconnect):
    """Keep all companion geometry/profile checks mandatory for this batch."""
    for report,inventory_fn in ((review['raw_geometry'],raw_checks),
            (review['low_voltage_geometry'],geometry_checks),(interconnect,interconnect_checks)):
        inventory={r['rule'] for r in inventory_fn({})['checks']}
        if report['gds_sha256']!=review['gds_sha256']:
            raise ValueError('Interconnect/companion reports refer to different submitted layouts.')
        if (len(report['checks'])!=len(inventory) or
                {r['rule'] for r in report['checks']}!=inventory or
                report['status']!='PASS' or report['violations']!=0 or
                any(type(r['violations']) is not int or r['violations']!=0 for r in report['checks'])):
            raise ValueError('A failed, duplicate or incomplete interconnect/companion profile cannot establish execution.')
    result=deepcopy(review);seen=[]
    for row in result['rows']:
        if row['rule'] not in INTERCONNECT_BINDINGS:continue
        if row['disposition']!='execution-review-required':
            raise ValueError('An interconnect binding would overwrite a different disposition.')
        seen.append(row['rule'])
        row.update(disposition='executed-reviewed',reason='Reviewed selected aluminium metal/contact requirement executed with all companion geometry and profile guards passing.',
            execution=dict(checker_sha256=interconnect['checker_sha256'],checks=list(INTERCONNECT_BINDINGS[row['rule']])))
    if Counter(seen)!=Counter(INTERCONNECT_BINDINGS.keys()):
        raise ValueError('The source inventory does not contain each reviewed interconnect rule exactly once.')
    result.update(counts=dict(Counter(r['disposition'] for r in result['rows'])),
        interconnect_geometry=interconnect,qualified=False,chunk_complete=False,
        scope='Reviewed low-voltage implant/well/gate/contact and selected aluminium interconnect requirements plus explicit block applicability. Unbound periphery/error-catalog, huge-metal, density, electrical and application requirements remain open.')
    return result


def bind_geometry(review,geometry):
    """Extend a checked implant ledger without dropping any prior requirement."""
    # Revalidate the mandatory companion report, including its guards. A
    # geometry-only report cannot establish the selected doping profile.
    companion=review['raw_geometry']
    if companion['gds_sha256']!=review['gds_sha256']:
        raise ValueError('Companion implant report refers to a different layout.')
    implant_inventory={r['rule'] for r in raw_checks({})['checks']}
    if (companion['status']!='PASS' or companion['violations']!=0 or
            len(companion['checks'])!=len(implant_inventory) or
            {r['rule'] for r in companion['checks']}!=implant_inventory or
            any(type(r['violations']) is not int or r['violations']!=0 for r in companion['checks'])):
        raise ValueError('A failed or incomplete companion implant profile cannot establish geometry execution.')
    if geometry['gds_sha256']!=review['gds_sha256']:
        raise ValueError('Geometry reports refer to different submitted layouts.')
    checks={r['rule']:r for r in geometry['checks']}
    inventory={r['rule'] for r in geometry_checks({})['checks']}
    if (len(checks)!=len(geometry['checks']) or checks.keys()!=inventory or
            geometry['status']!='PASS' or geometry['violations']!=0 or
            any(type(r['violations']) is not int or r['violations']!=0 for r in checks.values())):
        raise ValueError('A failed, duplicate or incomplete geometry check/profile cannot establish execution.')
    result=deepcopy(review);seen=[]
    for row in result['rows']:
        if row['rule'] not in GEOMETRY_BINDINGS:continue
        if row['disposition']!='execution-review-required':
            raise ValueError('A geometry binding would overwrite a different disposition.')
        seen.append(row['rule']);names=GEOMETRY_BINDINGS[row['rule']]
        reason='Reviewed low-voltage drawn-mask requirement executed with all geometry and implant profile guards passing.'
        if row['rule'] in ('nwell.2b','npc.3'):
            reason='The manual-merge trigger is absent because the complete spacing/notch check passes.'
        row.update(disposition='executed-reviewed',reason=reason,
            execution=dict(checker_sha256=geometry['checker_sha256'],checks=list(names)))
    if Counter(seen)!=Counter(GEOMETRY_BINDINGS.keys()):
        raise ValueError('The source inventory does not contain each reviewed geometry rule exactly once.')
    result.update(counts=dict(Counter(r['disposition'] for r in result['rows'])),
        low_voltage_geometry=geometry,qualified=False,chunk_complete=False,
        scope='Reviewed low-voltage implant, well, diffusion, gate, NPC and licon requirements plus explicit block applicability. Remaining periphery, error-catalog, density, electrical and application requirements remain open.')
    return result


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
    result=bind_geometry(bind(review,raw),low_voltage_geometry(path))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=result['low_voltage_geometry']['gds_sha256']:
        raise ValueError('Submitted layout changed during geometry execution.')
    result=bind_interconnect(result,interconnect_geometry(path))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=result['interconnect_geometry']['gds_sha256']:
        raise ValueError('Submitted layout changed during interconnect execution.')
    result['checker_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result
