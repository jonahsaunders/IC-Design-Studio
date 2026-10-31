"""Keep the mask-derived hugePad obligation open in current SKY130 reports.

The historical drawn-pad measurement is retained. It does not establish the
absence of hugePad, which the published C3 table derives from pad.mk.
"""
from collections import Counter
from copy import deepcopy

ROW = dict(id='docs/rules/periphery/p045-pad_dotdash.csv#2',
           source='docs/rules/periphery/p045-pad_dotdash.csv', record=2, rule='pad.3',
           source_sha256='e01d6f79b2aaaee9f7422170c60f4cccdba989bfba67fefd06c7f6cf34c1a395')
REASON = ('C3 defines hugePad as pad.mk with width > 100um. Absence of drawn pad:dg '
          'does not prove that mask-derived subject absent. Mask construction and '
          'the conflicting maximum/minimum area descriptions require review.')
REVIEW = dict(schema=1, revision='sky130-hugepad-mask-scope-v1', qualified=False,
              source='docs/rules/layers/table-c3-device-lvs-other.csv',
              source_sha256='e56b7c0570f4ce5e4c0a002ddd0cc82f4c0e0d12d98a7634d419e0abd6a1fd98',
              definition='pad.mk with width > 100um', correction=ROW, reason=REASON)


def target(ledger):
    rows = ledger.get('rows', [])
    if (len({r['id'] for r in rows}) != len(rows) or
            ledger.get('counts') != dict(Counter(r['disposition'] for r in rows))):
        raise ValueError('Changed SKY130 ledger inventory or counts.')
    selected = [r for r in rows if r['id'] == ROW['id']]
    if len(selected) != 1 or any(selected[0].get(k) != v for k, v in ROW.items()):
        raise ValueError('Changed or missing SKY130 hugePad source row.')
    row = selected[0]
    if row['disposition'] not in ('absent-operand', 'execution-review-required') or 'execution' in row:
        raise ValueError('Unreviewed SKY130 hugePad disposition or execution claim.')
    return row


def correct(ledger):
    result = deepcopy(ledger)
    target(result).update(disposition='execution-review-required', reason=REASON)
    result['counts'] = dict(Counter(r['disposition'] for r in result['rows']))
    result['pad_scope_review'] = deepcopy(REVIEW)
    validate(result)
    return result


def validate(ledger):
    row = target(ledger)
    if (ledger.get('pad_scope_review') != REVIEW or row['disposition'] != 'execution-review-required'
            or row.get('reason') != REASON):
        raise ValueError('SKY130 hugePad mask review is missing or discharged; recheck this saved result.')
    return ledger
