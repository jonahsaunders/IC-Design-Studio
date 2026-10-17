"""An absent frame marker cannot discharge enclosure of nonempty geometry.

Keep historical measurements. Reopen the two mixed/enclosure manual rows;
module spacing has a separately sufficient empty binary operand.
"""
from collections import Counter
from copy import deepcopy
from .digital_sky130_scope import correction

SOURCE_SHA256 = '0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567'
CORRECTIONS = (
    correction('p018-x_dotdash', 22, r'x.\n12a\n12b\n12c', SOURCE_SHA256,
        'The F flag limits these requirements to the frame, but absent areaid.mt and areaid.ft do not establish die-interior context. This combined row includes enclosure of non-ID geometry by areaid.mt; an absent encloser is insufficient to discharge it.'),
    correction('p018-x_dotdash', 26, 'x.12e', SOURCE_SHA256,
        'This frame-only rule requires enclosure of huge_metX by areaid.mt. Absent frame/module identifiers do not prove that huge_metX is absent or that the layout is inside a die; applicability remains unresolved.'),
)
REVIEW = dict(schema=1, revision='sky130-frame-enclosure-scope-v1', qualified=False,
              status='unsupported-frame-exclusions-reopened', corrections=list(CORRECTIONS))


def _rows(ledger):
    rows = ledger.get('rows', [])
    indexed = {row['id']: row for row in rows}
    if len(indexed) != len(rows) or ledger.get('counts') != dict(Counter(row['disposition'] for row in rows)):
        raise ValueError('Changed SKY130 frame-scope row inventory or counts.')
    for item in CORRECTIONS:
        row = indexed.get(item['id'], {})
        if any(row.get(key) != value for key, value in item.items() if key != 'reason'):
            raise ValueError('Changed or missing source row for SKY130 frame scope.')
    return indexed


def correct(ledger):
    result = deepcopy(ledger)
    indexed = _rows(result)
    for item in CORRECTIONS:
        row = indexed[item['id']]
        if row['disposition'] not in ('absent-operand', 'execution-review-required') or 'execution' in row:
            raise ValueError('Unexpected execution/disposition for unresolved SKY130 frame enclosure.')
        row.update(disposition='execution-review-required', reason=item['reason'])
    result['counts'] = dict(Counter(row['disposition'] for row in result['rows']))
    result['frame_scope_review'] = deepcopy(REVIEW)
    validate(result)
    return result


def validate(ledger):
    indexed = _rows(ledger)
    if ledger.get('frame_scope_review') != REVIEW:
        raise ValueError('SKY130 frame-scope review is missing or changed. Recheck Finish.')
    for item in CORRECTIONS:
        row = indexed[item['id']]
        if row['disposition'] != 'execution-review-required' or row.get('reason') != item['reason'] or 'execution' in row:
            raise ValueError('An unresolved SKY130 frame enclosure was incorrectly discharged.')
    return ledger
