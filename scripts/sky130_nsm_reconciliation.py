"""Reconcile only the literal NSM width/spacing records with empty operands.

NSM_keepout is the published union of the drawing and mask. Both must be
measured empty, including hierarchy. This never discharges frame/die-cut
requirements, and never claims execution on a non-empty nitride seal.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k

from icstudio.digital_sky130_scope import validate as validate_scope
from scripts import check_sky130_filled_replay as fixture
from scripts import sky130_geometry_reconciliation as geometry
from scripts import sky130_scope_corrections as scope
from scripts.sky130_global_geometry import layer_metadata, LAYER_MAP_PATH, LAYER_MAP_SHA256
from scripts.sky130_rule_errors import validate as validate_catalog
from scripts.sky130_rule_inventory import manual_rows

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/validation/sky130-nsm-reconciliation-2026-10-14.json'
SOURCE = 'docs/rules/periphery/p043-nsm_dotdash.csv'
DEFINITION = 'docs/rules/layers/table-c3-device-lvs-other.csv'
MAPPING = 'docs/rules/gds_layers.csv'
PAIRS = ((61, 20), (22, 0))
# These are exact source records, not a scan for names containing "nsm".
OPERANDS = (
    'diff_not_NSM3_exempt', 'tap_not_NSM3_exempt', 'fomDummyDRC_not_NSM3_exempt',
    'FOMmk_not_NSM3_exempt', 'poly_not_NSM3_exempt', 'P1Mmk_not_NSM3_exempt',
    'li1_not_NSM3_exempt', 'LI1Mmk_not_NSM3_exempt', 'met1_not_NSM3_exempt',
    'MM1mk_not_NSM3_exempt', 'met2_not_NSM3_exempt', 'MM2Mk_not_NSM3_exempt',
    'met3_not_NSM3_exempt', 'MM3mk_not_NSM3_exempt', 'met4_not_NSM3_exempt',
    'MM4mk_not_NSM3_exempt', 'met5_not_NSM3_exempt', 'MM5mk_not_NSM3_exempt',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bindings(catalog):
    validate_catalog(catalog)
    rows = {r['id']: r for r in catalog['rows']}
    result = {}

    def add(number, rule, description, record):
        key = 'r'+str(number)
        if rows[key]['rule'] != rule or rows[key]['description'] != description:
            raise ValueError('Changed explicit nitride-seal catalog record: '+key)
        result[key] = dict(rule=rule, description=description, parent=SOURCE+'#'+str(record))

    add(950, 'nsm.1', '3 min. width of nsm', 1)
    add(951, 'nsm.2', '4 min. spacing/notch of nsm', 2)
    for index, operand in enumerate(OPERANDS):
        add(952+index*2, 'nsm.3', '1 min. spacing of '+operand+' & nsm OR NSMmk', 3)
        add(953+index*2, 'nsm.3', operand+' must not overlap nsm OR NSMmk', 3)
    return result


def source_proof(source, inventory, catalog):
    """Read the pinned CSV bytes; do not trust a rule-name correspondence."""
    source = Path(source)
    files = {}
    for name in (SOURCE, DEFINITION, MAPPING):
        raw = (source/name).read_bytes()
        expected = inventory['source_files'][name]['sha256']
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Changed nitride-seal source bytes: '+name)
        files[name] = expected
    definitions = list(csv.DictReader(io.StringIO((source/DEFINITION).read_text(encoding='utf-8'))))
    definition = [row for row in definitions if row['Name'] == 'NSM_keepout']
    if len(definition) != 1 or definition[0]['Defining algorithm'] != 'nsm.dg OR nsm.mk':
        raise ValueError('Changed nitride-seal keepout definition.')
    published = list(csv.DictReader(io.StringIO((source/MAPPING).read_text(encoding='utf-8'))))
    layer_metadata()
    mapped = {tuple(row['pair']): row for row in json.loads(LAYER_MAP_PATH.read_bytes())['layers']}
    aliases = []
    for name, purpose, pair in (('nsm', 'drawing', PAIRS[0]), ('cnsm', 'mask', PAIRS[1])):
        matches = [r for r in published if r['Layer name'] == name and r['Purpose'] == purpose]
        if (len(matches) != 1 or matches[0]['GDS layer:datatype'] != ':'.join(map(str, pair))
                or matches[0]['Description'] != 'Nitride seal mask'
                or not any(a['name'] == name and a['purpose'] == purpose and a['source'] == 'published'
                           for a in mapped[pair]['aliases'])):
            raise ValueError('Changed nitride-seal drawing/mask mapping.')
        aliases.append(dict(name=name, purpose=purpose, pair=list(pair)))
    parsed = {r['record']: r for r in manual_rows((source/SOURCE).read_bytes(), SOURCE)}
    indexed = {r['id']: r for r in inventory['rule_rows']}
    for record, rule, value in ((1, 'nsm.1', '3.000'), (2, 'nsm.2', '4.000'), (3, 'nsm.3', '1.000')):
        row = parsed[record]
        if row['rule'] != rule or row['value'] != value or row['unit'] != 'µm':
            raise ValueError('Changed nitride-seal parent requirement.')
        if any(indexed[row['id']].get(key) != row[key] for key in
               ('record', 'rule', 'source', 'source_sha256', 'description', 'flags', 'value', 'unit')):
            raise ValueError('Nitride-seal inventory differs from captured source.')
    return dict(files=files, definition=definition[0], aliases=aliases,
                layer_map_sha256=LAYER_MAP_SHA256, bindings=bindings(catalog),
                rationale='Both actual nitride-seal operands are empty. Width, self-spacing and spacing/no-overlap to their union have no subject geometry. Exemption selections cannot add geometry to an empty union. The separate nsm.3a/nsm.3b frame and die-cut requirements are not covered.')


def measure(layout):
    """Count every referenced raw shape; a text/path cannot disappear in a union."""
    if len(layout.top_cells()) != 1 or abs(layout.dbu-.001) > 1e-12:
        raise ValueError('Expected one top and a 1 nm database unit.')
    top = layout.top_cell()
    counts = {}
    for pair in PAIRS:
        count = 0
        iterator = top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():
            count += 1
            iterator.next()
        counts[str(pair)] = count
    return dict(top=top.name, shape_counts=counts,
                measurement='all recursively referenced shapes, including texts and paths')


def is_absent(measurement):
    counts = measurement['shape_counts']
    if set(counts) != {str(pair) for pair in PAIRS} or any(type(v) is not int or v < 0 for v in counts.values()):
        raise ValueError('Missing or invalid nitride-seal operand measurement.')
    return all(value == 0 for value in counts.values())


def audit(gds):
    before = sha(gds)
    layout = k.Layout(); layout.read(str(gds))
    result = measure(layout)
    if sha(gds) != before:
        raise ValueError('Nitride-seal input changed during measurement.')
    return dict(**result, gds_sha256=before, checker_sha256=sha(__file__))


def reconcile(catalog, baseline, corrected, measurement):
    selected = bindings(catalog)
    source_rows = {r['id']: r for r in catalog['rows']}
    result = deepcopy(baseline)
    rows = {r['id']: r for r in result['rows']}
    if (len(rows) != len(result['rows']) or set(rows) != set(source_rows)
            or result['counts'] != dict(Counter(r['disposition'] for r in rows.values()))):
        raise ValueError('Missing, duplicate or miscounted catalog baseline.')
    for key, row in rows.items():
        if any(row.get(field) != source_rows[key][field] for field in ('id', 'record', 'rule')):
            raise ValueError('Changed catalog baseline identity.')
    if (baseline['case'] != corrected['case']
            or baseline['gds_sha256'] != corrected['gds_sha256']
            or measurement['gds_sha256'] != baseline['gds_sha256']
            or measurement['top'] != baseline['top'] or measurement['checker_sha256'] != sha(__file__)):
        raise ValueError('Mismatched nitride-seal case, GDS, top or measurement source.')
    validate_scope(corrected)
    parents = {r['id']: r for r in corrected['rows']}
    absent = is_absent(measurement)
    for key, binding in selected.items():
        parent = parents[binding['parent']]
        if (rows[key]['disposition'] != 'unreviewed' or parent['rule'] != binding['rule']
                or parent['source_sha256'] != '232fb1afb91d400f6bbaea0ee52b39a22e831e0668b87b439edef759d1c6942c'
                or parent['source'] != SOURCE or parent['record'] != int(binding['parent'].rsplit('#', 1)[1])):
            raise ValueError('Changed or already reviewed nitride-seal parent/record.')
        if absent:
            if (parent['disposition'] != 'absent-operand'
                    or parent['witnesses'] != {str(pair): 0 for pair in PAIRS}
                    or any(type(v) is not int for v in parent['witnesses'].values())):
                raise ValueError('Historical parent has no matching measured absence.')
            rows[key].update(disposition='absent-operand', binding=key,
                             description=binding['description'], parent=binding['parent'])
    result['counts'] = dict(Counter(r['disposition'] for r in result['rows']))
    return result


def build(progress=None):
    baseline = geometry.build()
    if (json.dumps(baseline, indent=2, ensure_ascii=False)+'\n').encode() != geometry.OUTPUT.read_bytes():
        raise ValueError('Preceding geometry reconciliation no longer reproduces.')
    corrected = scope.build()
    if (json.dumps(corrected, indent=2, ensure_ascii=False)+'\n').encode() != scope.OUTPUT.read_bytes():
        raise ValueError('Preceding scope correction no longer reproduces.')
    catalog = json.loads((ROOT/geometry.previous.CATALOG).read_bytes())
    inventory = json.loads((ROOT/geometry.previous.PERIPHERY).read_bytes())
    cases = []
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)/'inputs'
        manifest = fixture.unpack(fixture.BUNDLE, folder)
        proof = source_proof(folder/'sources', inventory, catalog)
        for entry in manifest['cases']:
            name = entry['case']
            old = next(row for row in baseline['cases'] if row['case'] == name)
            manual = next(row for row in corrected['cases'] if row['case'] == name)
            measurement = audit(folder/entry['gds'])
            reviewed = reconcile(catalog, old, manual, measurement)
            changes = [row for row, before in zip(reviewed['rows'], old['rows']) if row != before]
            if {r['id'] for r in changes} != set(proof['bindings']):
                raise ValueError('Exact final reference does not establish the selected absence.')
            cases.append(dict(case=name, measurement=measurement, counts=reviewed['counts'],
                              periphery_counts=manual['counts'], new_error_decisions=changes))
            if progress: progress(dict(case=name, new_absence_decisions=len(changes), counts=reviewed['counts']))
    sources = [Path(__file__), ROOT/'tests/test_sky130_nsm_reconciliation.py']
    inputs = [geometry.OUTPUT, scope.OUTPUT, ROOT/geometry.previous.CATALOG,
              ROOT/geometry.previous.PERIPHERY, LAYER_MAP_PATH]
    return dict(schema=1, chunk=6, status='partial-error-operand-review', qualified=False, chunk_complete=False,
                execution_mode='fresh-recursive-operand-measurement-and-source-reconciliation',
                bundle=dict(path=fixture.BUNDLE.relative_to(ROOT).as_posix(), sha256=fixture.BUNDLE_SHA256),
                inputs={p.relative_to(ROOT).as_posix(): sha(p) for p in inputs},
                source_files={p.relative_to(ROOT).as_posix(): sha(p) for p in sources},
                proof=proof, cases=cases,
                scope='Only r950-r987 gain measured absent-operand decisions. All other error records and periphery decisions are unchanged. No non-empty NSM rule execution, frame/die-cut acceptance, fresh six-profile/native run, timing, application integration or chunk 6 completion is claimed.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    args=parser.parse_args();report=build(progress=lambda value: print(json.dumps(value), flush=True))
    raw=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if OUTPUT.read_bytes()!=raw: raise ValueError('Saved NSM reconciliation differs from current evidence.')
    else: OUTPUT.write_bytes(raw)
    print(json.dumps(dict(status=report['status'], qualified=False, chunk_complete=False)))


if __name__=='__main__': main()
