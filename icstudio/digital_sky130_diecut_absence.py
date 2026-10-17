"""Known empty die-cut operand proves spacing absence, never enclosure."""
from pathlib import Path
from .model import file_digest

RECIPE = 'sky130-empty-diecut-spacing-operand-v1'
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c4b-layer-description.csv': 'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f',
    'docs/rules/periphery/p043-nsm_dotdash.csv': '232fb1afb91d400f6bbaea0ee52b39a22e831e0668b87b439edef759d1c6942c'})
DIECUT = (81, 11)
TARGETS = ('diff', 'tap', 'fomDummyDRC', 'FOMmk', 'poly', 'P1Mmk', 'li1', 'LI1Mmk',
           'met1', 'MM1mk', 'met2', 'MM2Mk', 'met3', 'MM3mk', 'met4', 'MM4mk', 'met5', 'MM5mk')
CHECKS = {f'r{1006+i}': dict(rule='nsm.3b', operation='spacing', limit_nm=3000,
                           other_operand=name+'_not_NSM3b_exempt') for i, name in enumerate(TARGETS)}
SCOPE = ('Eighteen nsm.3b spacing records name dieCut; the manual specifies areaid.dt and the '
    'published GDS and C4 tables identify 81:11 as areaid die cut. Empty raw data on that purpose '
    'throughout the reachable hierarchy proves no spacing pairs exist, independent of the unknown '
    'other operand. Any raw shape, including text, paths or unsupported geometry, prevents this '
    'absence proof. No blanking exemption, generated-mask recipe, die outline or chip scope is '
    'inferred. Missing die-cut data never proves that omission is valid, that frame enclosure is '
    'satisfied, or that complete-chip rules pass. Present die-cut cases remain unreviewed here; '
    'the separate numeric frame-bound checker retains its own drawn-layer results.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected(measurements, top, digest):
    require(isinstance(measurements, dict) and set(measurements) == {'raw_diecut_shapes', 'diecut_texts'} and
            all(type(n) is int and n >= 0 for n in measurements.values()) and
            measurements['diecut_texts'] <= measurements['raw_diecut_shapes'], 'Invalid die-cut operand census.')
    absent = measurements['raw_diecut_shapes'] == 0
    rows = [dict(id=key, **check, disposition='absent-operand' if absent else 'unreviewed',
                 reason='empty-known-diecut-operand' if absent else 'present-diecut-needs-other-operand')
            for key, check in CHECKS.items()]
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, qualified=False, chunk_complete=False,
                top=top, gds_sha256=digest, measurements=measurements, rows=rows,
                unreviewed=0 if absent else len(rows), status='diecut-operand-absent' if absent else 'review-required')


def measure(layout):
    require(len(layout.top_cells()) == 1, 'Die-cut census requires one top cell.')
    raw = texts = 0; it = layout.top_cell().begin_shapes_rec(layout.layer(*DIECUT))
    while not it.at_end():
        raw += 1; texts += int(it.shape().is_text()); it.next()
    return dict(raw_diecut_shapes=raw, diecut_texts=texts)


def audit(path):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    report = expected(measure(layout), layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'Layout changed during die-cut census.')
    return report


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing die-cut operand evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest), 'Changed die-cut operand evidence. Recheck Finish.')
    return report


def validate_saved(report, path):
    actual = audit(path); evaluate(report, actual['gds_sha256'], actual['top'])
    require(report == actual, 'Die-cut evidence differs from the actual layout. Recheck Finish.')
    return report
