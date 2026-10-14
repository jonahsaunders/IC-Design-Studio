"""Source-backed corrections to three unsupported SKY130 absence decisions.

An absent enclosing layer cannot prove that its required target is absent.
These corrections reopen requirements; they do not invent missing chip geometry
or resolve ambiguous device selection. Original polygon measurements are kept.
"""
from collections import Counter
from copy import deepcopy


def correction(section, record, rule, source_sha256, reason):
    source = 'docs/rules/periphery/'+section+'.csv'
    return dict(id=source+'#'+str(record), source=source, record=record, rule=rule,
                source_sha256=source_sha256, reason=reason)


CORRECTIONS = (
    correction('p024-hvtr_dotdash', 3, 'hvtr.3',
        'ba7813ea0f6f272dbf0db6e4d7b1ddfd6c8e49b775311823094c6cad86b1776e',
        'The source requires enclosure of pfet by HVTR without explicitly restricting the target to an HVTR-selected device. Absent HVTR alone cannot prove that target absent; device-selection semantics require review.'),
    correction('p043-nsm_dotdash', 4, 'nsm.3a',
        '232fb1afb91d400f6bbaea0ee52b39a22e831e0668b87b439edef759d1c6942c',
        'The source requires areaid.ft enclosure of drawn/mask geometry and gives frame exceptions. It does not condition the check on NSM presence. Absent NSM cannot establish frame enclosure; complete-boundary geometry and applicability require review.'),
    correction('p043-nsm_dotdash', 5, 'nsm.3b',
        '232fb1afb91d400f6bbaea0ee52b39a22e831e0668b87b439edef759d1c6942c',
        'The source requires spacing from areaid.dt to drawn/mask geometry and gives frame exceptions. It does not condition the check on NSM presence. Absent NSM cannot establish die-cut spacing; complete-boundary geometry and applicability require review.'),
)
REVIEW = dict(schema=1, revision='sky130-enclosing-operand-scope-v1',
              status='unsupported-absence-decisions-reopened', qualified=False,
              corrections=list(CORRECTIONS))


def _rows(review):
    rows = review['rows']; indexed = {row['id']: row for row in rows}
    if len(indexed) != len(rows) or review.get('counts') != dict(Counter(row['disposition'] for row in rows)):
        raise ValueError('Changed SKY130 ledger row inventory or counts.')
    for item in CORRECTIONS:
        row = indexed.get(item['id'], {})
        if any(row.get(key) != value for key, value in item.items() if key != 'reason'):
            raise ValueError('Changed or missing source row for SKY130 scope correction.')
    return indexed


def correct(review):
    result = deepcopy(review); indexed = _rows(result)
    for item in CORRECTIONS:
        row = indexed[item['id']]
        if row['disposition'] not in ('absent-operand', 'execution-review-required') or 'execution' in row:
            raise ValueError('Unexpected execution/disposition for an unresolved SKY130 source requirement.')
        row.update(disposition='execution-review-required', reason=item['reason'])
        # Retain the measured witnesses: zero NSM/HVTR is still a real
        # observation, but it does not discharge these particular targets.
    result['counts'] = dict(Counter(row['disposition'] for row in result['rows']))
    result['scope_review'] = deepcopy(REVIEW)
    validate(result)
    return result


def validate(review):
    indexed = _rows(review)
    if review.get('scope_review') != REVIEW:
        raise ValueError('SKY130 source-scope correction is missing or changed. Recheck this result with the current rule policy.')
    for item in CORRECTIONS:
        row = indexed[item['id']]
        if row['disposition'] != 'execution-review-required' or row.get('reason') != item['reason'] or 'execution' in row:
            raise ValueError('An unresolved SKY130 enclosure/boundary requirement was incorrectly discharged.')
    return review
