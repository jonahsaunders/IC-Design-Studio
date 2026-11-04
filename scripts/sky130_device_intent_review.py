"""Bind every final HD MOS gate to native device types and published tables.

This adds a device-intent prerequisite to selected absence decisions. Created
mask operands remain obligations: they are never excused by missing drawn data.
"""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from scripts import sky130_esd_fuse_review as previous
from scripts import check_sky130_circuit_invariance as circuit
from scripts import sky130_grid_geometry as grid

ROOT = previous.ROOT
sha = previous.sha
TABLES = ROOT / 'docs/qualification/sky130-device-tables'
OUTPUT = ROOT / 'docs/validation/sky130-device-intent-2026-10-14.json'
HASHES = {
    'table-f2a-lvs.tsv': 'c19398018c0f45674c7162077af48c57f5113617691cb985b7985f7e362de3e3',
    'table-f2b-mask.tsv': '7db89f09785ab8508ec0cef35cb0ce2a97a18241a3e54294a49c489c2cbaf47a',
}
NFET = 'sky130_fd_pr__nfet_01v8'
PFET = 'sky130_fd_pr__pfet_01v8_hvt'
OTHER = {'sky130_fd_pr__diode_pw2nd_05v5', 'sky130_fd_pr__res_generic_po'}
PAIRS = {'hvtr': (18, 20), 'hvi': (75, 20), 'lvtn': (125, 44), 'tap': (65, 44)}


def source_proof(source):
    tables = {}
    for name, digest in HASHES.items():
        path = TABLES / name
        if sha(path) != digest:
            raise ValueError('Changed published device table: ' + name)
        raw = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8')), delimiter='\t'))
        header = [s.strip() for s in raw[0]]
        if len(set(header)) != len(header):
            raise ValueError('Ambiguous device-table columns.')
        rows = []
        for index, row in enumerate(raw[1:], 1):
            # F2b omits the final comments field on 74 rows; no device/mask
            # field is padded or inferred. Exact raw bytes are locked above.
            if len(row) == len(header) - 1 and header[-1] == 'Drawn Route / Comments':
                row = [*row, '']
            if len(row) != len(header):
                raise ValueError('Incomplete device-table row.')
            rows.append(dict(record=index, **dict(zip(header, (s.strip() for s in row)))))
        tables[name] = rows
    def select(table, key, value, record):
        rows = [r for r in tables[table] if r[key] == value and r['record'] == record]
        if len(rows) != 1:
            raise ValueError('Missing exact device-table row.')
        return rows[0]
    n = select('table-f2a-lvs.tsv', 'Layout Model', 'nshort', 11)
    p = select('table-f2a-lvs.tsv', 'Layout Model', 'phighvt', 14)
    varactor = select('table-f2a-lvs.tsv', 'Layout Model', 'xchvnwc', 23)
    nm = select('table-f2b-mask.tsv', 'Layout Model and required schematic element', NFET, 12)
    pm = select('table-f2b-mask.tsv', 'Layout Model and required schematic element', PFET, 16)
    if (n['Name'] != nm['Name'] or p['Name'].replace(' [#f10]_', '') != pm['Name']
            or n['hvtr.dg'] != '-' or p['hvtr.dg'] != '-'
            or n['hvi:dg'] != '-' or p['hvi:dg'] != '-'
            or p['hvtp:dg'] != 'D' or p['lvtn:dg'] != 'C'
            or pm['LVTNM'] != 'C' or pm['NCM'] != 'C'
            or any(varactor[key] != 'D' for key in ('tap.dg', 'poly.dg', 'lvtn:dg', 'hvi:dg'))):
        raise ValueError('Changed reviewed device/implant semantics.')
    inventory = json.loads((ROOT / previous.previous.marker.nsm.geometry.previous.PERIPHERY).read_bytes())
    names = ('docs/rules/layers/table-f2a-lvs-key.rst', 'docs/rules/layers/table-f2b-mask-key.rst',
             'docs/rules/periphery-rules.rst', 'docs/rules/periphery/p024-hvtr_dotdash.csv',
             'docs/rules/periphery/p034-licon_dotdash.csv')
    files = {}
    for name in names:
        path = Path(source) / name
        if sha(path) != inventory['source_files'][name]['sha256']:
            raise ValueError('Changed device-context source: ' + name)
        files[name] = sha(path)
    text = (Path(source) / names[0]).read_text(encoding='utf-8')
    if any(value not in text for value in ('Layer illegal for the device', 'only created by CAD')):
        raise ValueError('Changed drawn/created/illegal legend.')
    context = (Path(source) / names[2]).read_text(encoding='utf-8')
    if 'Function: Define low VT adjust implant region for pmedlvtrf;' not in context:
        raise ValueError('Changed HVTR device context.')
    return dict(source_revision=inventory['source_revision'], table_hashes=HASHES, files=files,
                device_rows=dict(nmos=n, pmos=p, hv_varactor=varactor), mask_rows=dict(nmos=nm, pmos=pm),
                interpretation='F2a marks HVTR illegal for both permitted HD MOS types; the HVTR table names the low-Vt RF device. The floating-gate HV varactor requires drawn tap, poly, LVTN and HVI. F2b still requires generated LVTNM/NCM for the HD high-Vt PMOS.')


def measure(layout):
    diagnostic = grid.check(layout)
    unsupported = [r for r in diagnostic['checks'] if r['rule'].startswith('profile.') and r['violations']]
    if unsupported:
        raise ValueError('Unsupported geometry for device-intent measurement: ' + str(unsupported))
    top = layout.top_cell()
    def region(pair):
        return k.Region(top.begin_shapes_rec(layout.layer(*pair))).merged()
    diff, poly, well, hvtp, tap = [region(p) for p in ((65,20), (66,20), (64,20), (78,44), (65,44))]
    gates = (diff & poly).merged()
    p = (gates & well).merged(); n = (gates - well).merged()
    raw = {}
    for name, pair in PAIRS.items():
        iterator = top.begin_shapes_rec(layout.layer(*pair)); count = 0
        while not iterator.at_end():
            count += 1; iterator.next()
        raw[name] = count
    return dict(top=top.name, gates=gates.count(), nfet_gates=n.count(), pfet_gates=p.count(),
                straddling_gates=sum(not (k.Region(g)&well).is_empty() and not (k.Region(g)-well).is_empty() for g in gates.each()),
                pfet_outside_hvtp=(p-hvtp).count(), hvtp_over_nfet=(n&hvtp).count(),
                poly_tap_intersections=(poly&tap).count(), raw=raw)


def decisions(measured, models):
    values = [measured[key] for key in ('gates','nfet_gates','pfet_gates','straddling_gates',
                                       'pfet_outside_hvtp','hvtp_over_nfet','poly_tap_intersections')]
    if (set(measured['raw']) != set(PAIRS) or any(type(v) is not int or v < 0 for v in
            [*values, *measured['raw'].values(), *models.values()]) or not models):
        raise ValueError('Invalid device census.')
    if (set(models) - {NFET, PFET, *OTHER} or measured['gates'] == 0
            or models.get(NFET, 0) != measured['nfet_gates']
            or models.get(PFET, 0) != measured['pfet_gates']
            or measured['gates'] != measured['nfet_gates'] + measured['pfet_gates']
            or any(measured[key] for key in ('straddling_gates','pfet_outside_hvtp','hvtp_over_nfet'))):
        raise ValueError('Physical MOS gates do not establish the declared HD device census.')
    hvtr = measured['raw']['hvtr'] == 0
    varactor = (measured['raw']['hvi'] == 0 and measured['raw']['lvtn'] == 0
                and measured['poly_tap_intersections'] == 0)
    return dict(
        hvtr_3=dict(disposition='absent-operand' if hvtr else 'execution-review-required',
                    reason='Every physical MOS gate is accounted for by the native HD census. Both source-defined HD types prohibit HVTR; the named low-Vt RF subject is absent.' if hvtr else 'HVTR is present; absence cannot discharge this requirement.'),
        licon_19=dict(disposition='absent-operand' if varactor else 'execution-review-required',
                     reason='The native device census contains no varactor; both required drawn selectors and all poly/tap intersections are absent.' if varactor else 'An HV-varactor selector or physical gate candidate is present.'),
        retained_generated_mask_obligations=['lvtn.4b', 'ncm.3'])


def audit(gds, native_path, expected_native_sha256):
    gds_hash, native_hash = sha(gds), sha(native_path)
    if native_hash != expected_native_sha256:
        raise ValueError('Native extraction differs from its accepted capture.')
    native = circuit.headers(native_path)
    models = dict(sorted(Counter(d[2] for d in native['devices']).items()))
    layout = k.Layout(); layout.read(str(gds))
    measured = measure(layout)
    result = decisions(measured, models)
    if sha(gds) != gds_hash or sha(native_path) != native_hash:
        raise ValueError('Device-intent inputs changed while reading.')
    return dict(gds_sha256=gds_hash, native_ext_sha256=native_hash, native_models=models,
                measurement=measured, decisions=result, checker_sha256=sha(__file__),
                native_reader_sha256=sha(circuit.__file__))


def build(captures_root):
    preceding = previous.build()
    if (json.dumps(preceding, indent=2, ensure_ascii=False)+'\n').encode() != previous.OUTPUT.read_bytes():
        raise ValueError('Previous ESD/fuse review no longer reproduces.')
    checkpoint = json.loads((ROOT/'docs/validation/sky130-fill-progress-2026-10-11.json').read_bytes())
    native_reference = checkpoint['audits']['circuit']['data']
    if sha(ROOT/native_reference['path']) != native_reference['sha256']:
        raise ValueError('Changed native circuit readback checkpoint.')
    native_data = json.loads((ROOT/native_reference['path']).read_bytes())
    catalog = json.loads((ROOT/previous.previous.marker.nsm.geometry.previous.CATALOG).read_bytes())
    cat = {r['id']:r for r in catalog['rows']}
    if any(cat[key]['rule'] != rule for key,rule in (('r426','hvtr.3'),('r759','licon.19'))):
        raise ValueError('Changed device-specific catalog IDs.')
    cases = []
    fixture = previous.previous.marker.nsm.fixture
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs'; manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources')
        for entry in manifest['cases']:
            name=entry['case'];prior=next(r for r in preceding['cases'] if r['case']==name)
            capture=next(r for r in checkpoint['references'] if r['case']==name)['native_circuit_capture']
            path=ROOT/capture['path']
            if sha(path)!=capture['sha256']:raise ValueError('Changed native capture identity.')
            record=json.loads(path.read_bytes()); variant=next(r for r in record['variants'] if r['variant']=='filled')
            expected=next(r for r in native_data if r['case']==name and r['variant']=='filled')
            digest=record['files']['filled/'+entry['top']+'.ext']
            variant_digest=(variant['capacitance']['source_ext_sha256'] if name=='counter'
                            else variant['native_ext_sha256'])
            if variant['source_gds_sha256']!=entry['gds_sha256'] or digest!=expected['filled_ext_sha256'] or digest!=variant_digest:
                raise ValueError('Native census is not from this exact filled reference.')
            native=Path(captures_root)/('sky130-filled-capacitance-v'+str(2 if name=='counter' else 3))/name/'filled'/(entry['top']+'.ext')
            execution=audit(folder/entry['gds'],native,digest)
            new=[]
            for rule,key,error in (('hvtr.3','hvtr_3','r426'),('licon.19','licon_19','r759')):
                parent=next(r for r in prior['open_periphery'] if r['rule']==rule)
                if parent['disposition']!='execution-review-required' or error in {r['id'] for r in prior['new_error_decisions']}:
                    raise ValueError('Changed device-review predecessor.')
                new.append(dict(parent=parent, error_id=error, decision=execution['decisions'][key]))
            passed=sum(r['decision']['disposition']=='absent-operand' for r in new)
            pcounts=dict(prior['periphery_counts']);pcounts['execution-review-required']-=passed;pcounts['absent-operand']+=passed
            ecounts=dict(prior['error_counts']);ecounts['unreviewed']-=passed;ecounts['absent-operand']+=passed
            cases.append(dict(case=name,execution=execution,new_decisions=new,periphery_counts=pcounts,error_counts=ecounts,
                              capture_record=capture))
    return dict(schema=1,chunk=6,status='partial-device-intent-review',qualified=False,chunk_complete=False,
                source_files={p.relative_to(ROOT).as_posix():sha(p) for p in
                              (Path(__file__),ROOT/'tests/test_sky130_device_intent.py',*sorted(TABLES.glob('*')))},
                predecessor=dict(path=previous.OUTPUT.relative_to(ROOT).as_posix(),sha256=sha(previous.OUTPUT)),
                proof=proof,cases=cases,
                scope='Fresh drawn-gate census matched to every native MOS device in the retained exact filled captures. Two selected target decisions gain device/source context. Generated implant masks, RF selection, voltage intent, grid, boundary and numeric pin spacing remain open; no new native extraction or application-policy change.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures-root',type=Path,required=True)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    report=build(args.captures_root);raw=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if OUTPUT.read_bytes()!=raw:raise ValueError('Saved device-intent review differs.')
    else:OUTPUT.write_bytes(raw)
    print(json.dumps({r['case']:r['periphery_counts'] for r in report['cases']}))
