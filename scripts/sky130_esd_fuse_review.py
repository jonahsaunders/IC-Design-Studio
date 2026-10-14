"""Source-bound empty-target proofs for ESD implant and fuse requirements.

No marker is synthesized and no nonempty device is accepted. In particular,
empty NCM is NOT evidence that the P+ diffusion needing NCM is absent.
The ESD proof instead requires the selecting areaid.ed layer to be empty.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from scripts import sky130_waffle_density_review as previous
from scripts.sky130_rule_inventory import manual_rows
from scripts.sky130_global_geometry import layer_metadata, LAYER_MAP_PATH, LAYER_MAP_SHA256

ROOT = previous.ROOT
OUTPUT = ROOT / 'docs/validation/sky130-esd-fuse-2026-10-14.json'
sha = previous.sha
DEFINITION = 'docs/rules/layers/table-c3-device-lvs-other.csv'
NCM = 'docs/rules/periphery/p025-ncm_dotdash.csv'
GENERAL = 'docs/rules/periphery/p018-x_dotdash.csv'
FUSE = 'docs/rules/periphery/p046-mf_dotdash.csv'
ESD_PAIR = (81, 19)
# The published five-metal fuse purpose and target are checked along with
# every fuse alias in the captured installed map. An unknown metal2 fuse
# purpose is also rejected, so using another level cannot evade this proof.
FUSE_PAIRS = ((69, 17), (70, 17), (71, 17), (72, 17), (76, 44))
PAIRS = (ESD_PAIR, *FUSE_PAIRS)
DEFINITIONS = {
    'P+_diff': 'Diff AND Nwell',
    'fuse:dg': 'met2:fe for S8D*/S8TM*, met3.fe for S8TEE*/S8TNV/S8Q*/SP8TEE-5R/SP8Q*, met4.fe for S8P*/SP8P*',
    'fuse_contact': '(fuse_metal overlapping fuse:dg) NOT fuse:dg',
    'fuse_shield': 'Metal line (same metal level as fuse) between fuse and periphery, not overlapping contacts or vias, with specified dimensions',
    'non-isolated fuse edge': 'Long edge of the fuse spaced to Met2/Met3/Met4  less than a specified amount',
}
# Literal IDs, not prefix matching or a rule-name-based exemption.
FUSE_BINDINGS = {
    'r1280': ('mf.1&2', ('mf.1', 'mf.2')),
    'r1281': ('mf.1&2', ('mf.1',)), 'r1282': ('mf.1&2', ('mf.1',)),
    'r1283': ('mf.1&2', ('mf.2',)), 'r1284': ('mf.1&2', ('mf.2',)),
    'r1285': ('mf.3', ('mf.3',)), 'r1286': ('mf.5', ('mf.5',)),
    'r1287': ('mf.22', ('mf.22',)), 'r1288': ('mf.6', ('mf.6',)),
    'r1289': ('mf.6', ('mf.6',)), 'r1290': ('mf.7', ('mf.7',)),
    'r1291': ('mf.7', ('mf.7',)), 'r1292': ('mf.8', ('mf.8',)),
    'r1293': ('mf.8', ('mf.8',)), 'r1294': ('mf.9', ('mf.9',)),
    'r1295': ('mf.9', ('mf.9',)), 'r1296': ('mf.10', ('mf.10',)),
    'r1297': ('mf.10', ('mf.10',)), 'r1298': ('mf.11', ('mf.11',)),
    'r1299': ('mf.11', ('mf.11',)), 'r1300': ('mf.19', ('mf.19',)),
    'r1301': ('mf.19', ('mf.19',)), 'r1302': ('mf.12', ('mf.12',)),
    'r1303': ('mf.4', ('mf.4',)), 'r1304': ('mf.13', ('mf.13',)),
    'r1305': ('mf.14', ('mf.14',)), 'r1306': ('mf.15a', ('mf.15', 'mf.16')),
    'r1307': ('mf.15b', ('mf.15', 'mf.16')), 'r1308': ('mf.18', ('mf.18',)),
    'r1309': ('mf.20', ('mf.20',)), 'r1310': ('mf.24', ('mf.24',)),
    'r1311': ('mf.24', ('mf.24',)),
}


def source_proof(source, inventory, catalog):
    source = Path(source)
    previous.bindings(catalog, inventory)  # authenticates the complete catalog
    indexed = {r['id']: r for r in inventory['rule_rows']}
    files = {}
    for name in (NCM, GENERAL, FUSE, DEFINITION):
        path = source / name
        if sha(path) != inventory['source_files'][name]['sha256']:
            raise ValueError('Changed ESD/fuse source: ' + name)
        files[name] = sha(path)
        if name != DEFINITION:
            for row in manual_rows(path.read_bytes(), name):
                if any(row[key] != indexed[row['id']][key] for key in
                       ('record', 'rule', 'description', 'flags', 'value', 'unit', 'source_sha256')):
                    raise ValueError('Inventory differs from the captured rule source.')
    definitions = {r['Name']: r['Defining algorithm'] for r in
                   csv.DictReader(io.StringIO((source / DEFINITION).read_text(encoding='utf-8')))}
    if any(definitions.get(key) != value for key, value in DEFINITIONS.items()):
        raise ValueError('Changed target definition.')
    def parent(name, rule, record=None):
        rows = [r for r in indexed.values() if r['source'] == name and r['rule'] == rule
                and (record is None or r['record'] == record)]
        if len(rows) != 1:
            raise ValueError('Ambiguous source parent.')
        return rows[0]
    esd = parent(NCM, 'ncm.4')
    if (esd['description'] != 'Min enclosure of P+diff within (areaid:ed AndNot areaid:de) by Ncm'
            or esd['value'] != '0.180' or esd['unit'] != 'µm' or esd['flags'] != ['P']):
        raise ValueError('Changed ESD-selected target.')
    fuse = [r for r in indexed.values() if r['source'] == GENERAL and r['rule'] == 'x.11'
            and r['description'] == 'Metal fuses are drawn in met4']
    if len(fuse) != 1 or fuse[0]['flags'] != ['LVS'] or fuse[0]['value'] or fuse[0]['unit']:
        raise ValueError('Changed metal4 fuse requirement.')
    rows = {r['id']: r for r in catalog['rows']}
    relations = {}
    for key, (rule, parents) in FUSE_BINDINGS.items():
        row = rows[key]
        if row['rule'] != rule:
            raise ValueError('Changed literal fuse catalog binding.')
        relations[key] = dict(rule=rule, description=row['description'],
                              parents=[parent(FUSE, name)['id'] for name in parents])
    layer_metadata()
    layers = {tuple(r['pair']): r for r in json.loads(LAYER_MAP_PATH.read_bytes())['layers']}
    for pair, name, purpose, provenance in (
        (ESD_PAIR, 'areaid.ed', 'identifier', 'published'),
        ((71, 17), 'met4', 'fuse', 'published'), ((76, 44), 'target', 'drawing', 'published'),
        ((70, 17), 'met3', 'fuse', 'installed'), ((72, 17), 'met5', 'fuse', 'installed'),
    ):
        if not any(a['name'] == name and a['purpose'] == purpose and a['source'] == provenance
                   for a in layers[pair]['aliases']):
            raise ValueError('Changed ESD/fuse layer mapping.')
    if not {pair for pair, r in layers.items() if any(a['purpose'] == 'fuse' for a in r['aliases'])} <= set(FUSE_PAIRS):
        raise ValueError('An additional fuse purpose needs review.')
    return dict(files=files, definitions=DEFINITIONS, layer_map_sha256=LAYER_MAP_SHA256,
                esd_parent=esd['id'], fuse_parent=fuse[0]['id'], bindings=relations,
                caveats=[
                    'Fuse catalog distances differ from manual values in several rows; emptiness holds under both. No numeric fuse execution or resolution of those discrepancies is claimed.',
                    'Raw metal2 69:17 is a conservative rejection guard, not an asserted published layer mapping.',
                    'No conclusions about ncm.3, device voltage intent, RF selection, frame boundaries, grid units or x.20 are made.',
                ])


def measure(layout):
    if len(layout.top_cells()) != 1 or abs(layout.dbu - .001) > 1e-12:
        raise ValueError('Expected one top and 1 nm database units.')
    # Count raw shapes (including text and degenerate paths), without Boolean
    # geometry that could discard an operand. Arrays and transforms retain
    # nonemptiness even when their coordinates need a different geometry check.
    counts = {}
    for pair in PAIRS:
        iterator = layout.top_cell().begin_shapes_rec(layout.layer(*pair))
        count = 0
        while not iterator.at_end():
            count += 1
            iterator.next()
        counts[str(pair)] = count
    return dict(top=layout.top_cell().name, counts=counts)


def audit(path):
    before = sha(path)
    layout = k.Layout()
    layout.read(str(path))
    result = measure(layout)
    if sha(path) != before:
        raise ValueError('Input changed during ESD/fuse measurement.')
    return dict(**result, gds_sha256=before, checker_sha256=sha(__file__))


def reconcile(manual, catalog_review, measurement, proof):
    previous.marker.validate_scope(manual)
    inventory = json.loads((ROOT / previous.marker.nsm.geometry.previous.PERIPHERY).read_bytes())
    catalog = json.loads((ROOT / previous.marker.nsm.geometry.previous.CATALOG).read_bytes())
    previous.bindings(catalog, inventory)
    for supplied, original, keys in (
        (manual['rows'], inventory['rule_rows'], ('record', 'rule', 'source', 'source_sha256')),
        (catalog_review['rows'], catalog['rows'], ('record', 'rule')),
    ):
        actual = {r['id']: r for r in supplied}
        expected = {r['id']: r for r in original}
        if (len(actual) != len(supplied) or set(actual) != set(expected)
                or any(actual[key].get(field) != row[field] for key, row in expected.items() for field in keys)):
            raise ValueError('Incomplete or changed source ledger.')
    counts = measurement['counts']
    if (set(counts) != {str(p) for p in PAIRS}
            or any(type(v) is not int or v < 0 for v in counts.values())):
        raise ValueError('Invalid ESD/fuse measurements.')
    if (manual['case'] != catalog_review['case'] or manual['gds_sha256'] != measurement['gds_sha256']
            or catalog_review['gds_sha256'] != measurement['gds_sha256']
            or catalog_review['top'] != measurement['top'] or measurement['checker_sha256'] != sha(__file__)):
        raise ValueError('ESD/fuse evidence identity differs.')
    result, errors = deepcopy(manual), deepcopy(catalog_review)
    periphery = {r['id']: r for r in result['rows']}
    rows = {r['id']: r for r in errors['rows']}
    if (len(rows) != len(errors['rows'])
            or errors['counts'] != dict(Counter(r['disposition'] for r in errors['rows']))):
        raise ValueError('Changed catalog ledger.')
    for key in (proof['esd_parent'], proof['fuse_parent']):
        if periphery[key]['disposition'] != 'execution-review-required':
            raise ValueError('Source parent was already discharged.')
    def discharge(key, witnesses, reason):
        periphery[key].update(disposition='absent-operand', witnesses=witnesses, reason=reason,
                              semantic_review='sky130-esd-fuse-targets-v1')
    if counts[str(ESD_PAIR)] == 0:
        discharge(proof['esd_parent'], {str(ESD_PAIR): 0},
                  'Empty raw areaid.ed makes P+diff within (areaid.ed AND NOT areaid.de) empty, regardless of NCM presence or the interpretation of within.')
    absent_fuses = all(counts[str(pair)] == 0 for pair in FUSE_PAIRS)
    if absent_fuses:
        discharge(proof['fuse_parent'], {str(pair): 0 for pair in FUSE_PAIRS},
                  'The C3-defined metal4 fuse, every additional captured fuse purpose, the metal2 guard and the independent fuse target are all absent.')
    for key, relation in proof['bindings'].items():
        row = rows[key]
        if row['disposition'] != 'unreviewed' or row['rule'] != relation['rule']:
            raise ValueError('Changed or already reviewed fuse catalog record.')
        for key_parent in relation['parents']:
            parent = periphery[key_parent]
            if (parent['disposition'] != 'absent-operand'
                    or parent.get('witnesses') != {'(71, 17)': 0, '(76, 44)': 0}
                    or any(type(v) is not int for v in parent['witnesses'].values())):
                raise ValueError('Fuse parent lacks its independent absence witnesses.')
        if absent_fuses:
            row.update(disposition='absent-operand', binding=key, **deepcopy(relation),
                       absence_proof='No fuse or target exists. C3 fuse contacts, shields and non-isolated edges all depend on a fuse; their selected subjects are empty.')
    result['counts'] = dict(Counter(r['disposition'] for r in result['rows']))
    errors['counts'] = dict(Counter(r['disposition'] for r in errors['rows']))
    previous.marker.validate_scope(result)
    return result, errors


def build():
    latest = previous.build()
    if (json.dumps(latest, indent=2, ensure_ascii=False) + '\n').encode() != previous.OUTPUT.read_bytes():
        raise ValueError('Previous density review no longer reproduces.')
    marker = json.loads(previous.marker.OUTPUT.read_bytes())
    nsm = json.loads(previous.marker.nsm.OUTPUT.read_bytes())
    geometry = json.loads(previous.marker.nsm.geometry.OUTPUT.read_bytes())
    manual = json.loads(previous.marker.nsm.scope.OUTPUT.read_bytes())
    catalog = json.loads((ROOT / previous.marker.nsm.geometry.previous.CATALOG).read_bytes())
    inventory = json.loads((ROOT / previous.marker.nsm.geometry.previous.PERIPHERY).read_bytes())
    cases = []
    with TemporaryDirectory() as td:
        folder = Path(td) / 'inputs'
        manifest = previous.marker.nsm.fixture.unpack(previous.marker.nsm.fixture.BUNDLE, folder)
        proof = source_proof(folder / 'sources', inventory, catalog)
        for entry in manifest['cases']:
            name = entry['case']
            pick = lambda data: next(r for r in data['cases'] if r['case'] == name)
            baseline = previous.preceding(pick(geometry), pick(nsm), pick(marker))
            baseline = previous.reconcile(catalog, inventory, baseline, pick(manual), previous.audit(folder / entry['gds']))
            if baseline['counts'] != pick(latest)['counts']:
                raise ValueError('Latest catalog did not reconstruct.')
            measurement = audit(folder / entry['gds'])
            reviewed, errors = reconcile(pick(manual), baseline, measurement, proof)
            changes = lambda after, before: [r for r, old in zip(after['rows'], before['rows']) if r != old]
            cases.append(dict(case=name, measurement=measurement, periphery_counts=reviewed['counts'],
                              error_counts=errors['counts'], new_periphery_decisions=changes(reviewed, pick(manual)),
                              new_error_decisions=changes(errors, baseline),
                              open_periphery=[r for r in reviewed['rows'] if r['disposition'] in
                                              ('execution-review-required', 'definition-required')]))
    paths = [previous.OUTPUT, previous.marker.nsm.scope.OUTPUT, ROOT / previous.marker.nsm.geometry.previous.CATALOG,
             ROOT / previous.marker.nsm.geometry.previous.PERIPHERY, LAYER_MAP_PATH]
    return dict(schema=1, chunk=6, status='partial-esd-fuse-target-review', qualified=False, chunk_complete=False,
                source_files={p.relative_to(ROOT).as_posix(): sha(p) for p in
                              (Path(__file__), ROOT / 'tests/test_sky130_esd_fuse.py')},
                inputs={p.relative_to(ROOT).as_posix(): sha(p) for p in paths},
                bundle=latest['bundle'], proof=proof, cases=cases,
                scope='Two explicit periphery targets and 32 fuse catalog records are absent on the exact filled reference layouts. Nonempty ESD/fuse devices are not qualified; remaining required rules stay open.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    raw = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode()
    if args.check:
        if OUTPUT.read_bytes() != raw:
            raise ValueError('Saved ESD/fuse review differs.')
    else:
        OUTPUT.write_bytes(raw)
    print(json.dumps({r['case']: {'periphery': r['periphery_counts'], 'catalog': r['error_counts']} for r in report['cases']}))
