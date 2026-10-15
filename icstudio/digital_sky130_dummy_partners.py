"""Empty known partners of five dummy-FOM binary relations.

No construction or absence of fomDummyDRC is inferred. In particular, missing
enclosing geometry is never evidence that a dummy-FOM enclosure rule passes.
"""
from pathlib import Path
from .model import file_digest

RECIPE = 'sky130-dummy-known-partners-v1'
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c3-device-lvs-other.csv': 'e56b7c0570f4ce5e4c0a002ddd0cc82f4c0e0d12d98a7634d419e0abd6a1fd98',
    'docs/rules/layers/table-c4b-layer-description.csv': 'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f',
    'docs/rules/periphery/p018-x_dotdash.csv': '0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567',
    'docs/rules/periphery/p043-nsm_dotdash.csv': '232fb1afb91d400f6bbaea0ee52b39a22e831e0668b87b439edef759d1c6942c'})
LAYERS = dict(seal=(81, 1), diecut=(81, 11), fuse_m2_guard=(69, 17),
              fuse_m3=(70, 17), fuse_m4=(71, 17), fuse_m5=(72, 17), fuse_target=(76, 44))
PARTNERS = dict(SEALID=('seal',), dieCut=('diecut',),
                fuse=('fuse_m2_guard', 'fuse_m3', 'fuse_m4', 'fuse_m5', 'fuse_target'))
CHECKS = {
    'r1259': dict(rule='fomdmy.4', operation='spacing', partner='SEALID', limit_nm=1000),
    'r1260': dict(rule='fomdmy.4', operation='overlap', partner='SEALID'),
    'r1261': dict(rule='fomdmy.6', operation='spacing', partner='fuse', limit_nm=3250),
    'r1262': dict(rule='fomdmy.6', operation='overlap', partner='fuse'),
    'r1272': dict(rule='fomdmy.13', operation='spacing', partner='dieCut', limit_nm=500),
}
SCOPE = ('Five dummy-FOM spacing/overlap records have independently defined seal, fuse or die-cut '
    'partners. All raw data on a partner must be absent throughout the reachable hierarchy. '
    'The fuse census includes the published metal4 fuse and target, installed metal3/5 fuse aliases '
    'and a conservative metal2 guard. No raw purpose is asserted for fomDummyDRC, and its absence '
    'is not inferred from drawn dummy or native waffle data. Any present partner, including text '
    'or unsupported geometry, leaves its records unreviewed. Missing enclosing regions, required '
    'markers, chip context and all other dummy-FOM obligations remain separate. This is an empty '
    'operand proof, not numerical verification of nonempty dummy fill.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected(measurements, top, digest):
    require(isinstance(measurements, dict) and measurements.keys() == LAYERS.keys(),
            'Incomplete dummy-FOM partner census.')
    for value in measurements.values():
        require(isinstance(value, dict) and set(value) == {'raw_shapes', 'texts'} and
                all(type(n) is int and n >= 0 for n in value.values()) and
                value['texts'] <= value['raw_shapes'], 'Invalid dummy-FOM partner census.')
    rows = []
    for key, check in CHECKS.items():
        witnesses = {name: measurements[name]['raw_shapes'] for name in PARTNERS[check['partner']]}
        absent = not any(witnesses.values())
        rows.append(dict(id=key, **check, witnesses=witnesses,
            disposition='absent-operand' if absent else 'unreviewed',
            reason='empty-known-partner' if absent else 'present-partner-needs-dummy-construction'))
    pending = sum(row['disposition'] == 'unreviewed' for row in rows)
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, qualified=False, chunk_complete=False,
                top=top, gds_sha256=digest, measurements=measurements, rows=rows, unreviewed=pending,
                status='review-required' if pending else 'dummy-partner-absence-reviewed')


def measure(layout):
    require(len(layout.top_cells()) == 1, 'Dummy-FOM partner census requires one top cell.')
    result = {}
    for name, pair in LAYERS.items():
        raw = texts = 0; it = layout.top_cell().begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():
            raw += 1; texts += int(it.shape().is_text()); it.next()
        result[name] = dict(raw_shapes=raw, texts=texts)
    return result


def audit(path):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    result = expected(measure(layout), layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'Layout changed during dummy-FOM partner census.')
    return result


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing dummy-FOM partner evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest),
            'Changed dummy-FOM partner evidence. Recheck Finish.')
    return report


def validate_saved(report, path):
    actual = audit(path); evaluate(report, actual['gds_sha256'], actual['top'])
    require(report == actual, 'Dummy-FOM partner evidence differs from the actual layout. Recheck Finish.')
    return report
