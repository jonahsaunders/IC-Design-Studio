"""Reconcile explicit SKY130 error records with retained block execution.

This is evidence reconciliation, not a new geometry run. A shared rule name
never transfers coverage: each selected error ID has a reviewed operand and
check binding. Chip-level rows and all unbound records remain open.
"""
from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import re

from scripts.sky130_rule_errors import validate as validate_catalog
from scripts.sky130_rule_inventory import REVISION, SOURCE_LOCK_SHA256, validate_unreviewed
from scripts import (
    sky130_raw_feol, sky130_low_voltage_geometry, sky130_interconnect_geometry,
    sky130_wide_metal, sky130_global_geometry, sky130_floating_connectivity,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'docs/qualification/sky130-error-rule-inventory.json'
PERIPHERY = 'docs/qualification/sky130-rule-inventory.json'
CHECKPOINT = 'docs/validation/sky130-floating-review-2026-10-11.json'
OUTPUT = 'docs/validation/sky130-error-reconciliation-2026-10-14.json'
GLOBAL_SOURCE = 'docs/rules/periphery/p018-x_dotdash.csv'
PROFILES = {
    'raw_geometry': sky130_raw_feol,
    'low_voltage_geometry': sky130_low_voltage_geometry,
    'interconnect_geometry': sky130_interconnect_geometry,
    'wide_metal_geometry': sky130_wide_metal,
    'global_geometry': sky130_global_geometry,
    'floating_connectivity': sky130_floating_connectivity,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reviewed_bindings():
    """Literal catalog IDs and operands; do not extend by name/prefix matching."""
    bindings = {}

    def angle(error_id, description, pair, check, source_record):
        bindings[error_id] = dict(
            rule='x.2' if error_id in {
                'r113', 'r114', 'r115', 'r116', 'r117', 'r118', 'r119', 'r120', 'r121', 'r122'
            } else 'x.3a',
            description=description, pair=list(pair), profile='global_geometry',
            checks=[check], source_records=[source_record], disposition='executed-reviewed',
            rationale='Every raw edge on this operand is checked, including hierarchy and holes; no angle exemption is used.')

    for error_id, description, pair, check, record in (
        ('r113', 'non-manhattan diffNOtSealUHVI edge', (65, 20), 'x.2.diff', 4),
        ('r114', 'non-manhattan tapNotSealUHVI edge', (65, 44), 'x.2.active_interconnect', 5),
        ('r115', 'non-manhattan poly_noESD_noAnch edge', (66, 20), 'x.2.active_interconnect', 5),
        ('r116', 'non-manhattan li1Peri_noSEAL_noAnch edge', (67, 20), 'x.2.active_interconnect', 5),
        ('r117', 'non-manhattan licon_nonSEAL edge', (66, 44), 'x.2.active_interconnect', 5),
        ('r118', 'non-manhattan mcon_nonSEAL edge', (67, 44), 'x.2.active_interconnect', 5),
        ('r119', 'non-manhattan via_nonSEAL edge', (68, 44), 'x.2.active_interconnect', 5),
        ('r120', 'non-manhattan via2_nonSEAL edge', (69, 44), 'x.2.active_interconnect', 5),
        ('r121', 'non-manhattan via3_nonSEAL edge', (70, 44), 'x.2.upper_via', 6),
        ('r122', 'non-manhattan via4_nonSEAL edge', (71, 44), 'x.2.upper_via', 6),
    ):
        angle(error_id, description, pair, check, record)

    # These drawn operands have explicit purposes in the pinned layer map.
    # Mask aliases and metop layers are intentionally not inferred here.
    for error_id, operand, pair in (
        ('r124', 'nwell', (64, 20)), ('r125', 'diff', (65, 20)),
        ('r126', 'dnwell', (64, 18)), ('r127', 'lvtn', (125, 44)),
        ('r128', 'hvtp', (78, 44)), ('r129', 'hvi', (75, 20)),
        ('r130', 'tunm', (80, 20)), ('r131', 'npc', (95, 20)),
        ('r132', 'nsdm', (93, 44)), ('r133', 'psdm', (94, 20)),
        ('r134', 'met1', (68, 20)), ('r135', 'met2', (69, 20)),
        ('r136', 'vhvi', (74, 21)), ('r137', 'met3', (70, 20)),
        ('r138', 'met4', (71, 20)), ('r139', 'met5', (72, 20)),
        ('r140', 'nsm', (61, 20)), ('r141', 'pad', (76, 20)),
        ('r142', 'ldntm', (11, 44)), ('r143', 'hvntm', (125, 20)),
        ('r144', 'pnp', (82, 44)), ('r145', 'capacitor', (82, 64)),
        ('r146', 'ncm', (92, 44)), ('r147', 'inductor', (82, 24)),
        ('r148', 'rpm', (86, 20)), ('r149', 'hvtr', (18, 20)),
    ):
        angle(error_id, 'non-octagonal '+operand+' edge', pair,
              'x.2.diff' if operand == 'diff' else 'x.3a', 4 if operand == 'diff' else 10)
        if operand == 'diff':
            bindings[error_id]['source_records'].append(10)

    # A whole-layer orthogonal check is stronger than the selected octagonal
    # subset checks. Do not cite x.3a alone: it excludes these orthogonal layers.
    for error_id, description, pair, check, record in (
        ('r223', 'non-octagonal tap_SEAL edge', (65, 44), 'x.2.active_interconnect', 5),
        ('r224', 'non-octagonal tap_ENID edge', (65, 44), 'x.2.active_interconnect', 5),
        ('r225', 'non-octagonal poly_ESD edge', (66, 20), 'x.2.active_interconnect', 5),
        ('r226', 'non-octagonal "li1" in core edge', (67, 20), 'x.2.active_interconnect', 5),
        ('r227', 'non-octagonal li1_SEAL edge', (67, 20), 'x.2.active_interconnect', 5),
        ('r228', 'non-octagonal licon_SEAL edge', (66, 44), 'x.2.active_interconnect', 5),
        ('r229', 'non-octagonal mcon_SEAL edge', (67, 44), 'x.2.active_interconnect', 5),
        ('r230', 'non-octagonal via_SEAL edge', (68, 44), 'x.2.active_interconnect', 5),
        ('r231', 'non-octagonal via2_SEAL edge', (69, 44), 'x.2.active_interconnect', 5),
        ('r232', 'non-octagonal via3_SEAL edge', (70, 44), 'x.2.upper_via', 6),
    ):
        angle(error_id, description, pair, check, record)
        bindings[error_id]['source_records'].append(10)

    for error_id, operand, layer in (
        ('r233', 'met5', 72), ('r234', 'met4', 71), ('r235', 'met3', 70),
        ('r236', 'met2', 69), ('r237', 'met1', 68), ('r238', 'li1', 67),
        ('r239', 'poly', 66), ('r240', 'diff', 65),
    ):
        bindings[error_id] = dict(rule='x.5', description=f'{operand}Pin must be enclosed by {operand}',
            pair=[layer, 16], drawing=[layer, 20], profile='global_geometry', checks=['x.5'],
            source_records=[12], disposition='executed-reviewed',
            rationale='The exact pin purpose is contained in its own drawn conductor; fill and other layers cannot supply coverage.')

    # The r-series is block-level evidence. Same-name s-series chip records
    # stay open. Each family has one executed graph check and three cases
    # whose label operands are absent under the mandatory no-exceptions guard.
    for ids, prefix, operand in (
        (('r1179', 'r1180', 'r1181', 'r1182'), 'poly', 'poly'),
        (('r1183', 'r1184', 'r1185', 'r1186'), 'li1', 'li1'),
        (('r1187', 'r1188', 'r1189', 'r1190'), 'm1', 'met1'),
        (('r1191', 'r1192', 'r1193', 'r1194'), 'm2', 'met2'),
        (('r1195', 'r1196', 'r1197', 'r1198'), 'm3', 'met3'),
        (('r1199', 'r1200', 'r1201', 'r1202'), 'm4', 'met4'),
        (('r1203', 'r1204', 'r1205', 'r1206'), 'm5', 'met5'),
    ):
        descriptions = (
            f'Floating {prefix}_float or {prefix}_tie text not over {operand}',
            f'{operand} marked with {prefix}_float not floating',
            f'Nets on {operand} is floating',
            f'Metal on {operand} is texted as both tied and floating (IP Level)',
        )
        for index, (error_id, description) in enumerate(zip(ids, descriptions)):
            bindings[error_id] = dict(rule='x.22', description=description,
                profile='floating_connectivity', source_records=[37],
                checks=['x.22', 'profile.complete_extraction'] if index == 2 else ['profile.exception_labels'],
                disposition='executed-reviewed' if index == 2 else 'absent-operand',
                rationale=('Complete components, including this conductor, reach a physical root; every layer area is accounted for.'
                           if index == 2 else 'The recursive, all-layer label scan finds no float/tie exceptions. This is not qualification of non-empty label semantics.'))
    return bindings


def _zero(value):
    return type(value) is int and value == 0


def validate_review(review, periphery):
    validate_unreviewed(periphery)
    if (review.get('schema') != 1 or review.get('status') != 'partial-rule-execution-reviewed'
            or review.get('qualified') is not False or review.get('chunk_complete') is not False
            or review.get('source_revision') != REVISION
            or review.get('source_lock_sha256') != SOURCE_LOCK_SHA256
            or not re.fullmatch('[0-9a-f]{64}', review.get('gds_sha256', ''))
            or not isinstance(review.get('top'), str) or not review['top']):
        raise ValueError('Invalid execution ledger identity or scope.')
    expected = {row['id']: row for row in periphery['rule_rows']}
    rows = review['rows']
    if len(rows) != len(expected) or Counter(row['id'] for row in rows) != Counter(expected.keys()):
        raise ValueError('Missing or duplicate periphery execution records.')
    for row in rows:
        if any(row.get(key) != expected[row['id']][key]
               for key in ('rule', 'source', 'source_sha256', 'record')):
            raise ValueError('Changed periphery execution source record.')
    if review.get('counts') != dict(Counter(row['disposition'] for row in rows)):
        raise ValueError('Execution ledger summary differs from its rows.')
    for key, filename in (('checker_sha256', 'sky130_rule_execution.py'),
                          ('applicability_checker_sha256', 'sky130_block_applicability.py')):
        if review.get(key) != sha((ROOT/'scripts'/filename).read_bytes()):
            raise ValueError('Execution ledger checker identity changed.')
    for key, module in PROFILES.items():
        report = review[key]
        inventory = {row['rule'] for row in module.check({})['checks']}
        checks = report['checks']
        if (report.get('gds_sha256') != review['gds_sha256'] or report.get('top') != review['top']
                or report.get('checker_sha256') != sha(Path(module.__file__).read_bytes())
                or report.get('qualified') is not False
                or report.get('status') != 'PASS' or not _zero(report.get('violations'))
                or len(checks) != len(inventory) or {row['rule'] for row in checks} != inventory
                or any(not _zero(row['violations']) for row in checks)):
            raise ValueError('Failed, incomplete or mismatched companion profile: '+key)
    global_report = review['global_geometry']
    if global_report.get('layer_map_sha256') != sky130_global_geometry.LAYER_MAP_SHA256:
        raise ValueError('Changed layer-purpose map identity.')
    connection = review['floating_connectivity']
    expected_layers = set(sky130_floating_connectivity.check({})['layer_area_nm2'])
    areas = connection['layer_area_nm2']
    if (set(areas) != expected_layers or connection['covered_area_nm2'] != areas
            or any(type(value) is not int or value < 0 for value in areas.values())
            or any(type(value) is not int or value < 0 for value in connection['covered_area_nm2'].values())
            or connection['floating'] != []
            or type(connection['nets']) is not int or type(connection['anchored_nets']) is not int
            or not 0 <= connection['anchored_nets'] <= connection['nets']):
        raise ValueError('Inconsistent complete-conductor extraction evidence.')
    return {row['id']: row for row in rows}


def reconcile(catalog, periphery, review):
    validate_catalog(catalog)
    manual = validate_review(review, periphery)
    bindings = reviewed_bindings()
    known, pins = sky130_global_geometry.layer_metadata()
    result = []
    for source in catalog['rows']:
        row = dict(id=source['id'], record=source['record'], rule=source['rule'], disposition='unreviewed')
        binding = bindings.get(source['id'])
        if binding is not None:
            if source['rule'] != binding['rule'] or source['description'] != binding['description']:
                raise ValueError('Changed reviewed catalog operand: '+source['id'])
            profile = review[binding['profile']]
            for index in binding['source_records']:
                parent = manual[GLOBAL_SOURCE+'#'+str(index)]
                if (parent['disposition'] != 'executed-reviewed'
                        or parent.get('execution', {}).get('checker_sha256') != profile['checker_sha256']):
                    raise ValueError('Missing reviewed parent execution for '+source['id'])
            parent_checks = {check for index in binding['source_records']
                             for check in manual[GLOBAL_SOURCE+'#'+str(index)]['execution']['checks']}
            # Exception-label absence is a mandatory profile guard, not a
            # parent rule pass. Do not relabel it as executed label behavior.
            if binding['disposition'] == 'executed-reviewed' and not set(binding['checks']) <= parent_checks:
                raise ValueError('Parent does not bind the required check for '+source['id'])
            pair = tuple(binding.get('pair', ()))
            if pair and pair not in known:
                raise ValueError('Unknown reviewed catalog layer.')
            if 'drawing' in binding and pins.get(pair) != tuple(binding['drawing']):
                raise ValueError('Reviewed pin maps to a different conductor.')
            row.update(disposition=binding['disposition'], evidence=deepcopy(binding))
        result.append(row)
    if set(bindings) - {row['id'] for row in result}:
        raise ValueError('Missing reviewed error catalog record.')
    return dict(case=review['case'], top=review['top'], gds_sha256=review['gds_sha256'],
                qualified=False, chunk_complete=False, rows=result,
                counts=dict(Counter(row['disposition'] for row in result)))


def _read_bound(root, reference):
    path = (root/reference['path']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Evidence path leaves the repository.')
    raw = path.read_bytes()
    if sha(raw) != reference['sha256']:
        raise ValueError('Changed retained evidence: '+reference['path'])
    return json.loads(raw)


def build(root=ROOT):
    root = Path(root)
    checkpoint_raw = (root/CHECKPOINT).read_bytes()
    checkpoint = json.loads(checkpoint_raw)
    if (checkpoint.get('chunk') != 6 or checkpoint.get('qualified') is not False
            or checkpoint.get('chunk_complete') is not False):
        raise ValueError('Retained checkpoint scope changed.')
    for name, digest in checkpoint['source_files'].items():
        _read_path = (root/name).resolve()
        if not _read_path.is_relative_to(root.resolve()) or sha(_read_path.read_bytes()) != digest:
            raise ValueError('Retained checker source changed: '+name)
    data = _read_bound(root, checkpoint['data'])
    for platform in ('linux', 'win32'):
        audit = _read_bound(root, checkpoint['audits'][platform])
        if (audit['platform'] != platform or audit['data_sha256'] != checkpoint['data']['sha256']
                or audit['source_files'] != checkpoint['source_files']):
            raise ValueError('Retained platform audit does not identify the same evidence.')
    expected_cases = {case['case']: case for case in checkpoint['cases']}
    if set(expected_cases) != {'counter', 'uart', 'apb'} or Counter(r['case'] for r in data) != Counter(expected_cases.keys()):
        raise ValueError('Missing or duplicate original reference cases.')
    for review in data:
        if (review['gds_sha256'] != expected_cases[review['case']]['gds_sha256']
                or review['counts'] != expected_cases[review['case']]['counts']):
            raise ValueError('Reference case differs from retained checkpoint.')
    catalog_raw = (root/CATALOG).read_bytes()
    periphery_raw = (root/PERIPHERY).read_bytes()
    return dict(schema=1, status='partial-error-catalog-reconciliation', qualified=False, chunk_complete=False,
        execution_mode='retained-evidence-reconciliation',
        scope='Explicit block error-record bindings to the retained geometry/connectivity execution. '
              'No new final-GDS, engine, Windows or installer execution is asserted. Unbound and chip records remain open.',
        source_revision=REVISION, source_lock_sha256=SOURCE_LOCK_SHA256,
        inputs={CATALOG: sha(catalog_raw), PERIPHERY: sha(periphery_raw), CHECKPOINT: sha(checkpoint_raw),
                checkpoint['data']['path']: checkpoint['data']['sha256']},
        checker_sha256=sha(Path(__file__).read_bytes()),
        cases=[reconcile(json.loads(catalog_raw), json.loads(periphery_raw), review) for review in data])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/OUTPUT)
    parser.add_argument('--check', action='store_true', help='Require the saved report to reproduce exactly.')
    args = parser.parse_args()
    report = build()
    content = (json.dumps(report, indent=2, ensure_ascii=False)+'\n').encode()
    if args.check:
        if args.output.read_bytes() != content:
            raise ValueError('Saved error reconciliation differs from reproduced evidence.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    print(json.dumps(dict(status=report['status'], execution_mode=report['execution_mode'],
                          cases={case['case']: case['counts'] for case in report['cases']}, qualified=False)))


if __name__ == '__main__':
    main()
