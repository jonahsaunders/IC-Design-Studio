"""Selected imported repeated-cell MiM hierarchy with native connectivity.

One 2x10 um capacitor leaf is reused twice with independent ordered terminals.
Project/stream hierarchy is preserved; only the private native verification
stream is flattened. No direct hierarchical native extraction, distributed RC,
electrical, installed, full-family or release qualification is inferred.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.layout import kdb
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference, run
from icstudio.model import clone, file_digest, load_project, save_project, scalar
from icstudio.stream_contract import compare
from scripts.qualify_sky130_mim2 import fixture
from scripts.qualification_geometry import masks, same_regions, texts
from scripts import sky130_li_resume as identity
from scripts.qualify_standard_mos import write
from scripts.qualify_standard_mos_layout import technology

PLATES = (1, 2)
PORTS = ('P1', 'N1', 'P2', 'N2')
ANGLES = (0, 90)
TOP, LEAF = 'mim_pair', 'mim_leaf'
FAULTS = ('merged-reference-terminal', 'missing-reference-instance',
          'second-reference-width', 'physical-missing-instance')
EXCHANGE_FAULTS = ('missing-instance', 'lost-mirror', 'lost-rotation',
                   'renamed-top-terminal', 'changed-leaf-mask')
STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')
CONTRACT_PATH = 'docs/qualification/sky130-mim-hierarchy-v1.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def full_model(plate):
    require(plate in PLATES, 'Unknown MiM construction.')
    return f'sky130_fd_pr__cap_mim_m3_{plate}'


def transforms(angle):
    require(angle in ANGLES, 'Unreviewed parent orientation.')
    db = kdb(); whole = db.Trans(angle//90, False, 0, 0)
    return [whole * db.Trans(), whole * db.Trans(1, True, 40000, 0)]


def make_stream(leaf_path, target, plate, angle):
    """Assemble existing exported geometry; never regenerate device masks here."""
    full_model(plate)
    db = kdb(); ly = db.Layout(); ly.read(str(leaf_path))
    require(ly.cells() == 1 and len(list(ly.top_cells())) == 1, 'Expected one leaf cell.')
    leaf = ly.top_cell(); leaf.name = LEAF
    labels = texts(ly, leaf)
    require(len(labels) == 2 and {t.string for _, _, t in labels} == {'P', 'N'},
            'The exported leaf must carry exactly its two terminal labels.')
    top = ly.create_cell(TOP)
    for number, trans in enumerate(transforms(angle), 1):
        top.insert(db.CellInstArray(leaf.cell_index(), trans))
        for layer, purpose, text in labels:
            placed = text.transformed(trans)
            placed.string = text.string + str(number)
            top.shapes(ly.layer(layer, purpose)).insert(placed)
    ly.write(str(target))
    return inspect_stream(target, plate, angle, leaf_path)


def inspect_stream(path, plate, angle, leaf_path):
    db = kdb(); ly = db.Layout(); ly.read(str(path))
    source = db.Layout(); source.read(str(leaf_path))
    require(math.isclose(ly.dbu, .001, rel_tol=0, abs_tol=1e-15), 'Changed stream grid.')
    require({c.name for c in ly.each_cell()} == {LEAF, TOP}, 'Expected exactly two cells.')
    require([c.name for c in ly.top_cells()] == [TOP], 'Changed hierarchy top.')
    leaf, top = ly.cell(LEAF), ly.cell(TOP)
    require(not list(leaf.each_inst()), 'The selected capacitor leaf must be flat.')
    require(not masks(ly, top), 'The clean parent must not contain direct masks.')
    instances = list(top.each_inst())
    require(len(instances) == 2 and {i.cell_index for i in instances} == {leaf.cell_index()},
            'Both references must reuse the same leaf exactly twice.')
    def placement(i):
        t = i.cplx_trans
        require(t.mag == 1 and max(1, i.na) == max(1, i.nb) == 1,
                'Magnified or array placement is outside this class.')
        return t.angle, t.is_mirror(), t.disp.x, t.disp.y
    expected = sorted((t.angle*90, t.is_mirror(), t.disp.x, t.disp.y) for t in transforms(angle))
    require(sorted(placement(i) for i in instances) == expected, 'Changed rotation, mirror or placement.')
    same_regions(masks(source, source.top_cell()), masks(ly, leaf))
    labels = texts(ly, leaf)
    require(len(labels) == 2 and {t.string for _, _, t in labels} == {'P', 'N'},
            'Child-local labels changed.')
    expected_labels = []
    for number, trans in enumerate(transforms(angle), 1):
        for layer, purpose, text in labels:
            point = trans * db.Point(text.x, text.y)
            expected_labels.append((layer, purpose, text.string+str(number), point.x, point.y))
    actual_labels = [(a, b, t.string, t.x, t.y) for a, b, t in texts(ly, top)]
    require(sorted(actual_labels) == sorted(expected_labels), 'Changed independent top-terminal anchors.')
    cap_mask = (89, 44) if plate == 1 else (97, 44)
    marker = masks(ly, leaf).get(cap_mask, db.Region())
    require(marker.count() == 1 and marker.area() == 2000*10000 and
            marker.bbox().width() == 2000 and marker.bbox().height() == 10000,
            'Changed 2x10 um leaf capacitor marker.')
    return dict(sha256=file_digest(path), cells=2, reused_leaf=LEAF, instances=2,
                placements=[list(x) for x in expected], terminal_anchors=[list(x) for x in sorted(expected_labels)],
                width_um=2, length_um=10, plate=plate, model=full_model(plate))


def selected(plate, fault=None):
    require(fault in (None, *FAULTS), 'Unreviewed reference mutation.')
    full = full_model(plate)
    rows = ['.subckt capacitor_leaf P N', f'XLEAF P N {full} w=2 l=10 m=1', '.ends capacitor_leaf']
    if fault == 'second-reference-width':
        rows += ['.subckt changed_leaf P N', f'XLEAF P N {full} w=3 l=10 m=1', '.ends changed_leaf']
    rows += ['.subckt '+TOP+' '+' '.join(PORTS), 'X1 P1 N1 capacitor_leaf']
    if fault != 'missing-reference-instance':
        node = 'P1' if fault == 'merged-reference-terminal' else 'P2'
        cell = 'changed_leaf' if fault == 'second-reference-width' else 'capacitor_leaf'
        rows.append(f'X2 {node} N2 {cell}')
    return reference('\n'.join([*rows, '.ends '+TOP, '']), TOP)


def native_devices(path, plate, missing=False):
    text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', Path(path).read_text())
    rows = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    count = 1 if missing else 2
    require(len(rows) == count+2 and rows[0][:2] == ['.subckt', TOP] and
            rows[-1] in (['.ends'], ['.ends', TOP]), 'Changed native boundary or capacitor count.')
    ports = rows[0][2:]
    require(ports == list(PORTS) or (missing and ports == ['P1', 'N1']), 'Changed native terminal order.')
    require(len({r[0].lower() for r in rows[1:-1]}) == count, 'Duplicate native capacitor names.')
    pairs = []
    for row in rows[1:-1]:
        require(len(row) in (6, 7) and row[0].lower().startswith('x') and row[3] == full_model(plate),
                'Changed native capacitor type/model.')
        fields = [item.split('=', 1) for item in row[4:]]
        require(all(len(item) == 2 for item in fields), 'Malformed native capacitor parameter.')
        params = {key.lower(): scalar(value) for key, value in fields}
        require(len(params) == len(fields) and set(params) in ({'w', 'l'}, {'w', 'l', 'm'}) and
                (params['w'], params['l'], params.get('m', 1)) == (2, 10, 1),
                'Changed native width, length or multiplicity.')
        pairs.append(row[1:3])
    expected = [['P1', 'N1']] if missing else [['P1', 'N1'], ['P2', 'N2']]
    require(sorted(pairs) == expected, 'Changed native electrode polarity or independent graph.')
    return dict(sha256=file_digest(path), devices=count, terminal_pairs=sorted(pairs), top_ports=ports,
                model=full_model(plate), width_um=2, length_um=10, multiplicity=1)


def deleted_instance(project):
    changed = clone(project); top = next(c for c in changed['cells'] if c['id'] == changed['top'])
    instances = top['layout_instances']
    require(len(instances) == 2 and sum(bool(i['mirror']) for i in instances) == 1,
            'Expected the two declared occurrences before deletion.')
    top['layout_instances'] = [i for i in instances if not i['mirror']]
    return changed


def check_fault(result, folder, fault, plate):
    require([s['name'] for s in result['stages']] == list(STAGES), 'Incomplete native stage sequence.')
    stages = {s['name']: s for s in result['stages']}
    require(result['status'] == 'failed' and result['drc_count'] == 0 and
            all(stages[n]['status'] == 'passed' for n in STAGES[:3]), 'Fault failed setup/DRC instead of its declared graph.')
    native = native_devices(folder/'lvs-extraction/extracted.spice', plate, fault == 'physical-missing-instance')
    native_log = (folder/'lvs-extraction/native-extraction.log').read_text()
    require(re.findall(r'^STUDIO_MAGIC_COMPLETE[ \t]*$', native_log, re.M) == ['STUDIO_MAGIC_COMPLETE'],
            'Native extraction did not complete exactly once.')
    if stages['lvs_extraction']['status'] == 'failed':
        require(fault == 'physical-missing-instance' and native['top_ports'] == ['P1', 'N1'] and
                stages['lvs']['status'] == stages['integrity']['status'] == 'not_run' and
                stages['lvs_extraction'].get('error', '').startswith('Extracted port order differs from the schematic: '),
                'Unexpected post-extraction failure.')
    else:
        require(stages['lvs_extraction']['status'] == stages['integrity']['status'] == 'passed' and
                stages['lvs']['status'] == 'failed', 'Fault did not reach completed strict LVS.')
        log = (folder/'lvs/lvs.log').read_text()
        require(bool(re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching', log, re.I)),
                'Native LVS did not report a graph/property mismatch.')
        if fault == 'second-reference-width':
            require(full_model(plate) in log and re.search(r'(?m)^\s*w\s+circuit1:\s*3(?:\.0*)?\s+circuit2:\s*2(?:\.0*)?\s*\(', log),
                    'Native LVS did not report the predefined W3 versus W2 property mismatch.')
    return dict(detected=True, fault=fault, native=native, stages={k: v['status'] for k, v in stages.items()},
                report_sha256=file_digest(folder/'report.json'))


def corrupt_exchange(source, target, fault, plate):
    require(fault in EXCHANGE_FAULTS, 'Unreviewed exchange corruption.')
    db = kdb(); ly = db.Layout(); ly.read(str(source)); top, leaf = ly.cell(TOP), ly.cell(LEAF)
    instances = list(top.each_inst())
    if fault == 'missing-instance':
        instances[1].delete()
    elif fault in ('lost-mirror', 'lost-rotation'):
        second = next(i for i in instances if i.cplx_trans.is_mirror()); t = second.cplx_trans
        second.cplx_trans = db.ICplxTrans(1, 0 if fault == 'lost-rotation' else t.angle,
                                        False if fault == 'lost-mirror' else t.is_mirror(), t.disp.x, t.disp.y)
    elif fault == 'renamed-top-terminal':
        for index in ly.layer_indexes():
            for shape in top.shapes(index).each():
                if shape.is_text() and shape.text.string == 'P2':
                    text = shape.text; text.string = 'P1'; shape.text = text
    else:
        leaf.shapes(ly.layer((70 if plate == 1 else 71), 20)).insert(db.Box(100000, 100000, 100500, 100500))
    ly.write(str(target))


def case(tech, plate, out, tools, execution_id):
    folder = out/f'p{plate}'; folder.mkdir(); record = dict(plate=plate, status='RUNNING', execution_id=execution_id,
        layouts=[], faults=[], exchange_controls=[])
    try:
        leaf = fixture(tech, (2, 10, 1), plate)
        save_project(leaf, folder/'leaf.icproj'); leaf = load_project(folder/'leaf.icproj')
        leaf_path = folder/'leaf.gds'; export_layout(leaf, leaf_path)
        for angle in ANGLES:
            dest = folder/f'r{angle}'; dest.mkdir()
            proof = make_stream(leaf_path, dest/'input.gds', plate, angle)
            project, warnings = read_layout(dest/'input.gds'); link_technology(project, tech)
            top = next(c for c in project['cells'] if c['id'] == project['top']); top['ports'] = list(PORTS)
            save_project(project, dest/'saved.icproj'); reopened = load_project(dest/'saved.icproj')
            require(reopened['cells'] == project['cells'], 'Save/reopen changed hierarchy.')
            export_layout(reopened, dest/'export.gds'); export_layout(reopened, dest/'export.oas')
            exchange = dict(gds=compare(dest/'input.gds', dest/'export.gds'),
                            oasis=compare(dest/'input.gds', dest/'export.oas', text_presentation=False))
            imported, _ = read_layout(dest/'export.oas'); link_technology(imported, tech)
            next(c for c in imported['cells'] if c['id'] == imported['top'])['ports'] = list(PORTS)
            export_layout(imported, dest/'reimported.gds')
            exchange['reimported'] = compare(dest/'input.gds', dest/'reimported.gds', text_presentation=False)
            inspect_stream(dest/'reimported.gds', plate, angle, leaf_path)
            native_out = dest/'physical'; result = run(imported, imported['top'], native_out, tools, selected(plate))
            require(result['status'] == 'passed' and result['drc_count'] == 0 and
                    [s['name'] for s in result['stages']] == list(STAGES) and
                    all(s['status'] == 'passed' for s in result['stages']), result.get('error', 'Native hierarchy failed.'))
            record['layouts'].append(dict(rotation=angle, execution_id=execution_id, geometry=proof,
                exchange=exchange, import_warnings=warnings, project_sha256=file_digest(dest/'saved.icproj'),
                native=native_devices(native_out/'lvs-extraction/extracted.spice', plate),
                report_sha256=file_digest(native_out/'report.json')))
            if angle != 0:
                continue
            for fault in FAULTS:
                job = dest/fault; changed = deleted_instance(imported) if fault == 'physical-missing-instance' else imported
                save_project(changed, dest/(fault+'.icproj'))
                result = run(changed, changed['top'], job, tools, selected(plate, fault))
                record['faults'].append(check_fault(result, job, fault, plate))
            for fault in EXCHANGE_FAULTS:
                path = dest/(fault+'.gds'); corrupt_exchange(dest/'input.gds', path, fault, plate)
                try:
                    inspect_stream(path, plate, angle, leaf_path)
                except ValueError as error:
                    record['exchange_controls'].append(dict(fault=fault, rejected=True, error=str(error), sha256=file_digest(path)))
                else:
                    raise ValueError('Exchange corruption accepted: '+fault)
        require(len(record['layouts']) == 2 and len(record['faults']) == 4 and len(record['exchange_controls']) == 5,
                'Incomplete selected hierarchy case.')
        record['status'] = 'PASS'
    except Exception as error:
        record.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    write(folder/'record.json', record)
    return record


def source_files():
    contract = json.loads((ROOT/CONTRACT_PATH).read_bytes())
    files = [*sorted((ROOT/'icstudio').glob('*.py')), *sorted((ROOT/'scripts').glob('*.py')),
             ROOT/'tests/test_sky130_mim_hierarchy.py',
             ROOT/'tests/test_sky130_mim_hierarchy_audit.py',
             ROOT/'examples/sky130-qualification-lock.json',
             ROOT/'docs/qualification/sky130-mim-contract-v1.json', ROOT/CONTRACT_PATH,
             *(ROOT/s['path'] for s in contract['sources'].values() if 'path' in s)]
    return {p.relative_to(ROOT).as_posix(): file_digest(p) for p in files}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('sky130', 'magic', 'netgen', 'output'):
        ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--plates', type=int, nargs='+', choices=PLATES, default=list(PLATES))
    args = ap.parse_args()
    if len(set(args.plates)) != len(args.plates):
        ap.error('Choose distinct plates.')
    require(sys.platform == 'linux', 'Use the reviewed ordinary-user Linux native runtime.')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False); started = time.monotonic()
    contract = json.loads((ROOT/CONTRACT_PATH).read_bytes())
    report = dict(schema=1, suite='sky130-mim-hierarchy-v1', execution_id=uuid.uuid4().hex,
        execution_root=str(out), source_root=str(ROOT), status='RUNNING', chunk=7, qualified=False,
        full_family=False, release_ready=False, signoff=False, installed=False, chunk_complete=False,
        scope=__doc__, selected_plates=args.plates, full_plates=list(PLATES), contract=contract, cases=[])
    write(out/'qualification.json', report)
    (out/'acceptance-contract.json').write_bytes((ROOT/CONTRACT_PATH).read_bytes())
    report['acceptance_contract_sha256'] = file_digest(out/'acceptance-contract.json')
    try:
        tools = {k: str(getattr(args, k).resolve(strict=True)) for k in ('magic', 'netgen')}
        tech, process = technology('sky130A', args.sky130)
        report.update(process=process, tools={k: dict(path=v, sha256=file_digest(v)) for k, v in tools.items()})
        for name, source in contract['sources'].items():
            path = ROOT/source['path'] if 'path' in source else args.sky130/source['physical_asset']
            require(file_digest(path) == source['sha256'], 'Contract source differs: '+name)
            retained = out/'contract-sources'/name; retained.parent.mkdir(parents=True, exist_ok=True)
            retained.write_bytes(path.read_bytes())
            require(file_digest(retained) == source['sha256'], 'Contract source changed during capture: '+name)
        before = source_files(); write(out/'source-files.json', before)
        for name, digest in before.items():
            path = out/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes((ROOT/name).read_bytes())
            require(file_digest(path) == digest, 'Source changed during capture.')
        pdk = identity.tree(args.sky130); write(out/'physical-package-files.json', pdk)
        (out/'package.json').write_bytes((args.sky130/'package.json').read_bytes())
        with identity.controlled_environment():
            runtime = identity.runtime(tools); write(out/'runtime-before.json', runtime)
            for plate in args.plates:
                row = case(tech, plate, out, tools, report['execution_id']); report['cases'].append(row)
                write(out/'qualification.json', report); print(plate, row['status'], row.get('error', ''), flush=True)
                require(row['status'] == 'PASS', 'Hierarchy case failed: '+str(plate))
            after_runtime = identity.runtime(tools); write(out/'runtime-after.json', after_runtime)
        require(runtime == after_runtime, 'Runtime identity changed.')
        require(before == source_files(), 'Source identity changed.')
        require(pdk == identity.tree(args.sky130), 'Physical package changed.')
        report.update(status='PASS', guards=dict(source=True, physical_package=True, runtime=True),
                      source_files_sha256=file_digest(out/'source-files.json'),
                      physical_package_files_sha256=file_digest(out/'physical-package-files.json'),
                      runtime_before_sha256=file_digest(out/'runtime-before.json'),
                      runtime_after_sha256=file_digest(out/'runtime-after.json'))
    except Exception as error:
        report.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    report['seconds'] = time.monotonic()-started; write(out/'qualification.json', report)
    write(out/'manifest.json', {p.relative_to(out).as_posix(): file_digest(p)
        for p in sorted(out.rglob('*')) if p.is_file() and p != out/'manifest.json'})
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
