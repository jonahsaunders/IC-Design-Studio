"""Extend explicit SKY130 error bindings without changing historical evidence.

Only the literal error IDs below are reviewed. Their exact catalog text is
protected by the catalog's canonical source hash. Parent records, individual
checks, checker bytes and all companion profiles must agree. Shared names or
passing native summary counts never create a binding.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import klayout.db as k

from scripts import sky130_error_reconciliation as previous
from scripts import sky130_global_geometry as global_geometry

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/validation/sky130-geometry-reconciliation-2026-10-14.json'
RAW = 'raw_geometry'
LOW = 'low_voltage_geometry'
METAL = 'interconnect_geometry'
WIDE = 'wide_metal_geometry'
GLOBAL = 'global_geometry'


def parent(section, record):
    return f'docs/rules/periphery/{section}.csv#{record}'


def geometry_bindings():
    """Reviewed error IDs -> actual checks -> exact parent source records."""
    bindings = {}

    def add(ids, profile, check, section, record, disposition='executed-reviewed'):
        for number in ids:
            name = 'r' + str(number)
            if name in bindings:
                raise ValueError('Duplicate new binding: ' + name)
            bindings[name] = dict(profile=profile, checks=[check],
                                  parents=[parent(section, record)], disposition=disposition)

    for ids, check, record in (
        ((398,), 'nwell.1', 1), ((399,), 'nwell.2a', 2), ((400,), 'nwell.4', 4)):
        add(ids, LOW, check, 'p021-nwell_dotdash', record)
    for number in range(1, 7):
        add((404 + number,), RAW, 'hvtp.' + str(number), 'p023-hvtp_dotdash', number)
    for ids, check, record in (
        ((427, 428), 'difftap.1.diff', 1), ((430, 431), 'difftap.1.tap', 1),
        ((433,), 'difftap.2', 2), ((434,), 'difftap.2b', 4), ((435,), 'difftap.3', 5),
        ((440,), 'difftap.8', 10), ((441,), 'difftap.9', 11),
        ((442,), 'difftap.10', 12), ((443,), 'difftap.11', 13)):
        add(ids, LOW, check, 'p026-difftap_dotdash', record)
    # Separate implant polarity and exact parent records; the catalog spells
    # these nsd/psd while the manual groups them under n/ psd.
    for offset, polarity in ((0, 'n'), (16, 'p')):
        for ids, check, record in (
            ((459, 460), f'n/psd.1.{polarity}', 1),
            ((462, 463), f'n/psd.2.{polarity}', 2),
            ((464,), f'n/psd.5a.{polarity}', 4), ((465,), f'n/psd.5b.{polarity}', 5),
            ((466,), f'n/psd.7.{polarity}', 7), ((467,), f'n/psd.8.{polarity}', 8),
            ((468,), f'n/psd.9.{polarity}', 9),
            ((469,), 'n/psd.10a' if polarity == 'n' else 'n/psd.10b', 10 if polarity == 'n' else 11),
            ((470,), f'n/psd.11.{polarity}', 12)):
            add(tuple(number + offset for number in ids), RAW, check, 'p032-n_psd_dotdash', record)
    for ids, check, record in (
        ((516,), 'poly.1a', 3), ((518, 519), 'poly.2', 5),
        ((523,), 'poly.4', 7), ((524,), 'poly.5', 8), ((525,), 'poly.6', 9),
        ((526,), 'poly.7', 10), ((527,), 'poly.8', 11),
        ((531,), 'poly.10', 13), ((532,), 'poly.11', 14), ((533,), 'poly.12', 15)):
        add(ids, LOW, check, 'p028-poly_dotdash', record)
    for ids, check, record in (
        ((706,), 'npc.1', 1), ((707,), 'npc.2', 2), ((708, 709), 'npc.4', 4)):
        add(ids, LOW, check, 'p032-npc_dotdash', record)
    for ids, profile, check, record in (
        ((711, 712), LOW, 'licon.2', 4), ((716,), LOW, 'licon.4', 9),
        ((717,), LOW, 'licon.5a', 10), ((718,), METAL, 'licon.5b', 11),
        ((719,), METAL, 'licon.5c', 12), ((720,), LOW, 'licon.6', 13),
        ((721,), METAL, 'licon.7', 14), ((722,), LOW, 'licon.8', 15),
        ((723,), METAL, 'licon.8a', 16), ((725, 726), LOW, 'licon.11', 19),
        ((727, 728), LOW, 'licon.11ab', 20), ((729, 730), LOW, 'licon.11ab', 21),
        ((735, 736, 737), LOW, 'licon.1', 1), ((746, 747), LOW, 'licon.9', 17),
        ((748, 749), LOW, 'licon.13', 25), ((750,), LOW, 'licon.14', 26),
        ((751, 752), LOW, 'licon.15', 27), ((755, 756), LOW, 'licon.16', 28),
        ((757,), LOW, 'licon.17', 29), ((758,), LOW, 'licon.18', 30)):
        add(ids, profile, check, 'p034-licon_dotdash', record)
    for ids, check, record in (
        ((763, 764), 'li.1.-', 1), ((767, 768), 'li.3.-', 4),
        # The adjacent enclosure check also enforces complete containment.
        ((770, 771), 'li.5.-', 6), ((772, 773), 'li.6.-', 7)):
        add(ids, METAL, check, 'p035-li_dotdash_dotdash', record)
    for ids, check, record in (
        ((777, 778, 779), 'ct.size', 1), ((780,), 'ct.2', 2), ((784,), 'ct.4', 4)):
        add(ids, METAL, check, 'p035-ct_dotdash', record)
    for section, rows in (
        ('p038-m1_dotdash', (
            ((787,), 'm1.1', 2), ((788,), 'm1.2', 3), ((791, 792), 'm1.4', 6),
            ((795,), 'm1.5', 8), ((796,), 'm1.6', 9), ((797, 798), 'm1.7', 10))),
        ('p040-m2_dotdash', (
            ((817,), 'm2.1', 2), ((818,), 'm2.2', 3), ((821, 822), 'm2.4', 7),
            ((823,), 'm2.5', 8), ((824,), 'm2.6', 9), ((825, 826), 'm2.7', 10))),
        ('p042-m3_dotdash', (
            ((860,), 'm3.1', 2), ((861,), 'm3.2', 3), ((862, 863), 'm3.4', 8), ((864,), 'm3.6', 11))),
        ('p044-m4_dotdash', (
            ((878,), 'm4.1', 2), ((879,), 'm4.2', 3), ((880, 881), 'm4.3', 4), ((882,), 'm4.4a', 6))),
        ('p044-m5_dotdash', (
            ((894,), 'm5.1', 1), ((895,), 'm5.2', 2), ((896, 897), 'm5.3', 3), ((898,), 'm5.4', 4))),
        ('p039-via_dotdash', (
            ((800, 801, 802), 'via.size', 1), ((804,), 'via.2', 3),
            ((808, 809), 'via.4a', 5), ((814,), 'via.5a', 8))),
        ('p041-via2_dotdash', (
            ((848, 849, 850), 'via2.size', 2), ((851,), 'via2.2', 8),
            ((855, 856), 'via2.4', 10), ((859,), 'via2.5', 12))),
        ('p042-via3_dotdash', (
            ((867, 868, 869), 'via3.size', 1), ((871,), 'via3.2', 3),
            ((875, 876), 'via3.4', 5), ((877,), 'via3.5', 6))),
        ('p044-via4_dotdash', (
            ((885, 886, 887), 'via4.size', 1), ((888,), 'via4.2', 2), ((892, 893), 'via4.4', 4))),
    ):
        for ids, check, record in rows:
            add(ids, METAL, check, section, record)
    for ids, check, section, records in (
        ((789, 790), 'm1.wide_spacing', 'p038-m1_dotdash', (5, 4)),
        ((819, 820), 'm2.wide_spacing', 'p040-m2_dotdash', (5, 4)),
        ((865, 866), 'm3.wide_spacing', 'p042-m3_dotdash', (7, 6)),
        ((883, 884), 'm4.wide_spacing', 'p044-m4_dotdash', (8, 7))):
        for number, record in zip(ids, records):
            add((number,), WIDE, check, section, record)
    # Ring operands cannot exist under the exact-square contact guards.
    # This is absence, not execution of ring-width/enclosure semantics.
    for ids, profile, check, section, record in (
        ((713, 714, 715), LOW, 'licon.1', 'p034-licon_dotdash', 1),
        ((781, 782, 783), METAL, 'ct.size', 'p035-ct_dotdash', 1),
        ((805, 806, 807), METAL, 'via.size', 'p039-via_dotdash', 1),
        ((852, 853, 854), METAL, 'via2.size', 'p041-via2_dotdash', 2),
        ((872, 873, 874), METAL, 'via3.size', 'p042-via3_dotdash', 1),
        ((889, 890, 891), METAL, 'via4.size', 'p044-via4_dotdash', 1)):
        add(ids, profile, check, section, record, 'absent-operand')
    return bindings


# Catalog operand, source alias, purpose, GDS pair, angle ID, containment ID.
# Explicit aliases disambiguate drawing vs mask and preserve installed-only
# purposes. Metop1-8 and ambiguous FOM wording deliberately remain unbound.
MASK_OPERANDS = (
    ('cfom', 'cfom', 'drawing', (22, 20), 176, 331),
    ('clvtnm', 'clvtnm', 'drawing', (25, 44), 177, 332),
    ('chvtpm', 'chvtpm', 'drawing', (88, 44), 178, 333),
    ('conom', 'conom', 'drawing', (87, 44), 179, 334),
    ('clvom', 'clvom', 'drawing', (45, 20), 180, 335),
    ('cntm', 'cntm', 'drawing', (26, 20), 181, 336),
    ('chvntm', 'chvntm', 'drawing', (38, 20), 182, 337),
    ('cnpc', 'cnpc', 'drawing', (44, 20), 183, 338),
    ('cnsdm', 'cnsdm', 'drawing', (29, 20), 184, 339),
    ('cpsdm', 'cpsdm', 'drawing', (31, 20), 185, 340),
    ('cli1m', 'cli1m', 'drawing', (115, 44), 186, 341),
    ('cviam3', 'cviam3', 'drawing', (112, 20), 187, 342),
    ('cviam4', 'cviam4', 'drawing', (117, 20), 188, 343),
    ('PMM2mk', 'cpmm2', 'mask', (94, 0), 189, 344),
    ('CU1Mmk', 'ccu1m', 'mask', (93, 0), 190, 345),
    ('RPMmk', 'crpm', 'mask', (96, 0), 191, 346),
    ('PBOmk', 'cpbo', 'mask', (99, 0), 192, 347),
    ('PDMmk', 'cpdm', 'mask', (37, 0), 193, 348),
    ('NSMmk', 'cnsm', 'mask', (22, 0), 194, 349),
    ('MM5mk', 'cmm5', 'mask', (59, 0), 195, 350),
    ('VIM4mk', 'cviam4', 'mask', (58, 0), 196, 351),
    ('MM4mk', 'cmm4', 'mask', (51, 0), 197, 352),
    ('VIM3mk', 'cviam3', 'mask', (50, 0), 198, 353),
    ('MM3mk', 'cmm3', 'mask', (34, 0), 199, 354),
    ('VIM2mk', 'cviam2', 'mask', (44, 0), 200, 355),
    ('MM2mk', 'cmm2', 'mask', (41, 0), 201, 356),
    ('VIMmk', 'cviam', 'mask', (40, 0), 202, 357),
    ('MM1mk', 'cmm1', 'mask', (36, 0), 203, 358),
    ('CTM1mk', 'cctm1', 'mask', (35, 0), 204, 359),
    ('LI1Mmk', 'cli1m', 'mask', (56, 0), 205, 360),
    ('LICM1mk', 'clicm1', 'mask', (43, 0), 206, 361),
    ('PSDMmk', 'cpsdm', 'mask', (32, 0), 207, 362),
    ('NSDMmk', 'cnsdm', 'mask', (30, 0), 208, 363),
    ('LDNTMmk', 'cldntm', 'mask', (11, 0), 209, 364),
    ('NPCMmk', 'cnpc', 'mask', (49, 0), 210, 365),
    ('HVNTMmk', 'chvntm', 'mask', (39, 0), 211, 366),
    ('NTMmk', 'cntm', 'mask', (27, 0), 212, 367),
    ('P1Mmk', 'cp1m', 'mask', (28, 0), 213, 368),
    ('LVOMmk', 'clvom', 'mask', (46, 0), 214, 369),
    ('ONOMmk', 'conom', 'mask', (88, 0), 215, 370),
    ('TUNMmk', 'ctunm', 'mask', (20, 0), 216, 371),
    ('HVTRMmk', 'chvtrm', 'mask', (98, 0), 217, 372),
    ('HVTPMmk', 'chvtpm', 'mask', (97, 0), 218, 373),
    ('LVTNMmk', 'clvtnm', 'mask', (25, 0), 219, 374),
    ('NWMmk', 'cnwm', 'mask', (21, 0), 220, 375),
    ('DNMmk', 'cdnm', 'mask', (48, 0), 221, 376),
    ('FOMmk', 'cfom', 'mask', (23, 0), 222, 377),
)
EDIT_OPERANDS = (
    ('NTMdrop', 'cntm', 'maskdrop', (26, 22), 158, 241),
    ('LVTNMdrop', 'clvtnm', 'maskdrop', (25, 42), 159, 242),
    ('HVTPMdrop', 'chvtpm', 'maskdrop', (97, 42), 160, 243),
    ('LI1Mdrop', 'cli1m', 'maskdrop', (115, 42), 161, 244),
    ('LICM1drop', 'clicm1', 'maskdrop', (106, 42), 162, 245),
    ('PSDMdrop', 'cpsdm', 'maskdrop', (31, 22), 163, 246),
    ('NSDMdrop', 'cnsdm', 'maskdrop', (29, 22), 164, 247),
    ('P1Mdrop', 'cp1m', 'maskdrop', (33, 42), 165, 248),
    ('FOMdrop', 'cfom', 'maskdrop', (22, 22), 166, None),
    ('NTMadd', 'cntm', 'maskadd', (26, 21), 167, 249),
    ('LVTNMadd', 'clvtnm', 'maskadd', (25, 43), 168, 250),
    ('HVTPMadd', 'chvtpm', 'maskadd', (97, 43), 169, 251),
    ('LI1Madd', 'cli1m', 'maskadd', (115, 43), 170, 252),
    ('LICM1add', 'clicm1', 'maskadd', (106, 43), 171, 253),
    ('PSDMadd', 'cpsdm', 'maskadd', (31, 21), 172, 254),
    ('NSDMadd', 'cnsdm', 'maskadd', (29, 21), 173, 255),
    ('P1Madd', 'cp1m', 'maskadd', (33, 43), 174, 256),
    ('FOMadd', 'cfom', 'maskadd', (22, 21), 175, 257),
)


def mask_bindings(catalog):
    global_geometry.layer_metadata()  # verifies the pinned map before reading
    layers = {tuple(row['pair']): row for row in json.loads(global_geometry.LAYER_MAP_PATH.read_bytes())['layers']}
    edits, restricted = global_geometry.mask_purposes()
    source = {row['id']: row for row in catalog['rows']}
    result = {}
    for table, containment_check, parent_record, admitted in (
        (MASK_OPERANDS, 'x.15a', 29, restricted), (EDIT_OPERANDS, 'x.9', 16, edits)):
        for operand, alias, purpose, pair, angle_id, containment_id in table:
            aliases = {(item['name'], item['purpose'].replace(' ', '').lower()) for item in layers[pair]['aliases']}
            if (alias, purpose) not in aliases or pair not in admitted:
                raise ValueError('Unreviewed mask-purpose mapping: ' + operand)
            for number, check, record, description in (
                (angle_id, 'x.3a', 10, f'non-octagonal {operand} edge'),
                (containment_id, containment_check, parent_record,
                 f'{operand} must be enclosed by COREID' if containment_check == 'x.9' else
                 f'X.15a: layer {operand} allowed inside areaid:mt or inside areaid.sl or inside areaid.ft')):
                if number is None:
                    continue
                error_id = 'r' + str(number)
                if source[error_id]['rule'] != check or source[error_id]['description'] != description:
                    raise ValueError('Changed reviewed mask catalog record: ' + error_id)
                result[error_id] = dict(profile=GLOBAL, checks=[check],
                    parents=[parent('p018-x_dotdash', record)], disposition='executed-reviewed',
                    operand=operand, alias=alias, purpose=purpose, pair=list(pair))
    return result


def notch_cases():
    cases = []
    def add(profile, check, pairs, minimum):
        for pair in pairs:
            cases.append(dict(profile=profile, check=check, pair=pair, minimum_nm=minimum))
    for check, pair in (('n/psd.2.n', (93, 44)), ('n/psd.2.p', (94, 20)), ('hvtp.2', (78, 44))):
        add(RAW, check, [pair], 380)
    for check, pair, minimum in (
        ('nwell.2a', (64, 20), 1270), ('difftap.3', (65, 20), 270),
        ('difftap.3', (65, 44), 270), ('poly.2', (66, 20), 210),
        ('npc.2', (95, 20), 270), ('licon.2', (66, 44), 170)):
        add(LOW, check, [pair], minimum)
    for metal, (drawn, fill, _, spacing, _, _) in previous.PROFILES[METAL].METALS.items():
        add(METAL, metal + ('.3.-' if metal == 'li' else '.2'), [drawn, fill], spacing)
    for contact, (pair, _, spacing) in previous.PROFILES[METAL].CUTS.items():
        add(METAL, contact + '.2', [pair], spacing)
    for metal, (drawn, fill, spacing) in previous.PROFILES[WIDE].LAYERS.items():
        add(WIDE, metal + '.wide_spacing', [drawn, fill], spacing)
    return cases


def notch_controls():
    """Run a single merged U polygon at -1/0/+1 nm, in four orientations."""
    rows = []
    for case in notch_cases():
        for delta in (-1, 0, 1):
            gap = case['minimum_nm'] + delta
            region = k.Region(k.Box(0, 0, 10_000 + gap, 10_000))
            region -= k.Region(k.Box(5000, 5000, 5000 + gap, 11_000))
            for rotation in (0, 1, 2, 3):
                transformed = region.transformed(k.Trans(rotation, False, 0, 0))
                if transformed.count() != 1:
                    raise ValueError('Notch control is not a single connected polygon.')
                report = previous.PROFILES[case['profile']].check({case['pair']: transformed})
                count = next(row['violations'] for row in report['checks'] if row['rule'] == case['check'])
                if type(count) is not int or (count > 0) != (delta < 0):
                    raise ValueError('Notch boundary control failed: ' + str(case))
                rows.append(dict(profile=case['profile'], check=case['check'], pair=list(case['pair']),
                                 minimum_nm=case['minimum_nm'], delta_nm=delta,
                                 rotation=rotation * 90, violations=count))
    return dict(status='PASS', controls=len(rows), rows=rows,
                scope='Individual spacing/notch arithmetic; contact-shaped U coupons intentionally violate exact-square guards and are not legal device layouts.')


def validate_notch_controls(report):
    expected = Counter((case['profile'], case['check'], tuple(case['pair']), case['minimum_nm'], delta, rotation)
                       for case in notch_cases() for delta in (-1, 0, 1) for rotation in (0, 90, 180, 270))
    actual = Counter((row['profile'], row['check'], tuple(row['pair']), row['minimum_nm'], row['delta_nm'], row['rotation'])
                     for row in report['rows'])
    if (report.get('status') != 'PASS' or type(report.get('controls')) is not int
            or report['controls'] != sum(expected.values()) or actual != expected
            or any(type(row['violations']) is not int or row['violations'] < 0
                   or (row['violations'] > 0) != (row['delta_nm'] < 0) for row in report['rows'])):
        raise ValueError('Failed, incomplete or duplicate notch controls.')


def reconcile(catalog, periphery, review, bindings, controls):
    validate_notch_controls(controls)
    result = previous.reconcile(catalog, periphery, review)
    parents = deepcopy(previous.validate_review(review, periphery))
    source = {row['id']: row for row in catalog['rows']}
    rows = {row['id']: row for row in result['rows']}
    for error_id, binding in bindings.items():
        if not error_id.startswith('r') or rows[error_id]['disposition'] != 'unreviewed':
            raise ValueError('Binding would replace reviewed or chip coverage: ' + error_id)
        report = review[binding['profile']]
        checks = set()
        for parent_id in binding['parents']:
            ancestor = parents[parent_id]
            execution = ancestor.get('execution', {})
            if ancestor['disposition'] != 'executed-reviewed' or execution.get('checker_sha256') != report['checker_sha256']:
                raise ValueError('Missing executed parent for ' + error_id)
            checks.update(execution['checks'])
        if not set(binding['checks']) <= checks:
            raise ValueError('Parent check does not cover ' + error_id)
        rows[error_id].update(disposition=binding['disposition'],
                             description=source[error_id]['description'],
                             binding=error_id)
    result['counts'] = dict(Counter(row['disposition'] for row in result['rows']))
    # x.3 is the heading whose numeric child is x.3a. The retained strict
    # global check also checks seal and other excluded purposes conservatively.
    angle_checks = ['x.2.diff', 'x.2.active_interconnect', 'x.2.upper_via', 'x.3a']
    spacing = {}
    for case in notch_cases():
        spacing.setdefault(case['profile'], set()).add(case['check'])
    extra = {
        parent('p018-x_dotdash', 9): dict(rule='x.3', profiles={GLOBAL: angle_checks},
            reason='Numeric child x.3a and the stronger orthogonal checks cover every known polygon purpose, without seal exemptions.'),
        parent('p018-x_dotdash', 13): dict(rule='x.6', profiles={key: sorted(values) for key, values in spacing.items()},
            reason='Every same-layer spacing operation in the selected executable profiles includes intra-polygon notches; complete -1/0/+1 nm controls execute on each operand and orientation.'),
    }
    manual_source = {row['id']: row for row in periphery['rule_rows']}
    for source_id, binding in extra.items():
        if parents[source_id]['disposition'] != 'execution-review-required' or parents[source_id]['rule'] != binding['rule']:
            raise ValueError('Changed global obligation: ' + source_id)
        for profile, required_checks in binding['profiles'].items():
            present = {row['rule'] for row in review[profile]['checks']}
            if not set(required_checks) <= present:
                raise ValueError('Missing global-obligation check.')
        parents[source_id].update(disposition='executed-reviewed')
        binding['description'] = manual_source[source_id]['description']
    result.update(periphery_counts=dict(Counter(row['disposition'] for row in parents.values())),
                  periphery_bindings=extra)
    return result


def build():
    # This independently validates all historical input hashes and OS audit
    # identities. It intentionally does not change the old runner or report.
    baseline = previous.build()
    checkpoint = json.loads((ROOT / previous.CHECKPOINT).read_bytes())
    data = json.loads((ROOT / checkpoint['data']['path']).read_bytes())
    catalog = json.loads((ROOT / previous.CATALOG).read_bytes())
    periphery = json.loads((ROOT / previous.PERIPHERY).read_bytes())
    bindings = geometry_bindings()
    masks = mask_bindings(catalog)
    if set(bindings) & set(masks):
        raise ValueError('Duplicate geometry/mask binding.')
    bindings.update(masks)
    controls = notch_controls()
    cases = [reconcile(catalog, periphery, review, bindings, controls) for review in data]
    for case, old in zip(cases, baseline['cases']):
        if case['gds_sha256'] != old['gds_sha256']:
            raise ValueError('Changed filled reference identity.')
    return dict(schema=1, status='partial-geometry-reconciliation', qualified=False, chunk_complete=False,
                execution_mode='retained-final-layout-evidence-and-fresh-notching-controls',
                source_revision=baseline['source_revision'], source_lock_sha256=baseline['source_lock_sha256'],
                inputs=baseline['inputs'],
                source_files={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (Path(__file__), Path(previous.__file__), ROOT / 'tests/test_sky130_geometry_reconciliation.py')},
                new_error_bindings=bindings, notch_controls=controls, cases=cases,
                scope='Explicit FEOL/BEOL/mask error records and two global periphery obligations. '
                      'Ring operands are absent under exact-square guards. Unbound and chip records remain open. '
                      'No fresh filled-GDS, native-engine, timing, Windows or application acceptance is asserted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    content = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode()
    if args.check:
        if args.output.read_bytes() != content:
            raise ValueError('Saved geometry reconciliation differs from reproduced evidence.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    print(json.dumps(dict(status=report['status'], new_error_bindings=len(report['new_error_bindings']),
                          notch_controls=report['notch_controls']['controls'],
                          cases={row['case']: dict(errors=row['counts'], periphery=row['periphery_counts']) for row in report['cases']},
                          chunk_complete=False)))


if __name__ == '__main__':
    main()
