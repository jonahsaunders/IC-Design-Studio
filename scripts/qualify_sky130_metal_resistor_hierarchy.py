"""Fresh selected imported-hierarchy checks for SKY130 LI/M1--M4 resistors.

One 2x5 um straight leaf is reused twice with independent named terminals.
This checks imported hierarchical placement/exchange and native connectivity;
it does not qualify a parameterized array, electrical envelope or release.
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
from icstudio.layout import kdb, polygon, rect
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference, run
from icstudio.model import clone, file_digest, load_project, save_project, scalar
from icstudio.stream_contract import compare
from scripts import qualify_sky130_metal_resistor_layouts as straight
from scripts import sky130_li_resume as identity
from scripts.qualify_standard_mos import write
from scripts.qualify_standard_mos_layout import technology
from scripts.qualification_geometry import masks, same_regions, texts

MODELS = ('l1', 'm1', 'm2', 'm3', 'm4')
PORTS = ('A1', 'B1', 'A2', 'B2')
ANGLES = (0, 90)
TOP, LEAF = 'res_pair', 'res_leaf'
FAULTS = ('merged-reference-terminal', 'missing-reference-instance',
          'second-reference-width', 'physical-cross-instance-short')
EXCHANGE_FAULTS = ('missing-instance', 'lost-mirror', 'lost-rotation',
                   'renamed-top-terminal', 'changed-leaf-mask')
STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')
CONTRACT = dict(schema=1, models=list(MODELS), width_um=2, length_um=5,
    child_instances=2, top_ports=list(PORTS), top_rotations=list(ANGLES),
    child_transforms=[dict(rotation=0, mirror=False, x_nm=0, y_nm=0),
                      dict(rotation=90, mirror=True, x_nm=40000, y_nm=0)],
    faults=list(FAULTS), exchange_faults=list(EXCHANGE_FAULTS),
    clean_drc_count=0, source_classes=['imported hierarchical straight resistor'],
    native_fault_expected={
        'merged-reference-terminal': 'DRC/extraction/integrity pass; completed strict LVS rejects changed graph.',
        'missing-reference-instance': 'DRC/extraction/integrity pass; completed strict LVS rejects missing resistor.',
        'second-reference-width': 'DRC/extraction/integrity pass; completed strict LVS rejects second width 3 instead of 2 um.',
        'physical-cross-instance-short': 'DRC passes; native extraction shows exactly the intended shared A node and rejects missing distinct interface, or strict LVS rejects that shared-node graph.'},
    exclusions=['Parameterized arrays/snakes', 'New contacts/vias', 'Electrical hierarchy response',
                'Full physical classes/envelope', 'Installed/release/fabrication qualification'])


def require(condition, message):
    if not condition:
        raise ValueError(message)


def transforms(angle):
    require(angle in ANGLES, 'Unreviewed top orientation.')
    db = kdb(); whole = db.Trans(angle//90, False, 0, 0)
    return [whole * db.Trans(), whole * db.Trans(1, True, 40000, 0)]


def make_stream(leaf_path, target, model, angle):
    """Assemble existing exported geometry; never regenerate device masks here."""
    require(model in MODELS, 'Unknown resistor model.')
    db = kdb(); ly = db.Layout(); ly.read(str(leaf_path))
    require(ly.cells() == 1 and len(list(ly.top_cells())) == 1, 'Expected one leaf cell.')
    leaf = ly.top_cell(); leaf.name = LEAF
    labels = texts(ly, leaf)
    require(len(labels) == 2 and {t.string for _, _, t in labels} == {'R1', 'R2'},
            'The exported leaf must carry exactly its two terminal labels.')
    top = ly.create_cell(TOP)
    for number, trans in enumerate(transforms(angle), 1):
        top.insert(db.CellInstArray(leaf.cell_index(), trans))
        for layer, purpose, text in labels:
            placed = text.transformed(trans)
            placed.string = ('A' if text.string == 'R1' else 'B') + str(number)
            top.shapes(ly.layer(layer, purpose)).insert(placed)
    ly.write(str(target))
    return inspect_stream(target, model, angle, leaf_path)


def inspect_stream(path, model, angle, leaf_path):
    db = kdb(); ly = db.Layout(); ly.read(str(path))
    source = db.Layout(); source.read(str(leaf_path))
    require(math.isclose(ly.dbu, .001, rel_tol=0, abs_tol=1e-15), 'Changed stream grid.')
    require({c.name for c in ly.each_cell()} == {LEAF, TOP}, 'Expected exactly two cells.')
    require([c.name for c in ly.top_cells()] == [TOP], 'Changed hierarchy top.')
    leaf, top = ly.cell(LEAF), ly.cell(TOP)
    require(not list(leaf.each_inst()), 'The selected resistor leaf must be flat.')
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
    require(len(labels) == 2 and {t.string for _, _, t in labels} == {'R1', 'R2'},
            'Child-local labels changed.')
    expected_labels = []
    for number, trans in enumerate(transforms(angle), 1):
        for layer, purpose, text in labels:
            point = trans * db.Point(text.x, text.y)
            expected_labels.append((layer, purpose, ('A' if text.string == 'R1' else 'B')+str(number), point.x, point.y))
    actual_labels = [(a, b, t.string, t.x, t.y) for a, b, t in texts(ly, top)]
    require(sorted(actual_labels) == sorted(expected_labels), 'Changed independent top-terminal anchors.')
    gds = straight.MODELS[model][0]; marker = masks(ly, leaf).get((gds, 13), db.Region())
    require(marker.count() == 1 and marker.area() == 2000*5000 and
            marker.bbox().width() == 2000 and marker.bbox().height() == 5000,
            'Changed 2x5 um leaf resistor marker.')
    return dict(sha256=file_digest(path), cells=2, reused_leaf=LEAF, instances=2,
                placements=[list(x) for x in expected], terminal_anchors=[list(x) for x in sorted(expected_labels)],
                marker_width_um=2, marker_length_um=5, model=model)


def selected(model, fault=None):
    require(model in MODELS and fault in (None, *FAULTS), 'Unreviewed reference.')
    full = 'sky130_fd_pr__res_generic_'+model
    rows = ['.subckt resistor_leaf A B', f'RLEAF A B {full} w=2 l=5 m=1', '.ends resistor_leaf']
    if fault == 'second-reference-width':
        rows += ['.subckt changed_leaf A B', f'RLEAF A B {full} w=3 l=5 m=1', '.ends changed_leaf']
    rows += ['.subckt '+TOP+' '+' '.join(PORTS), 'X1 A1 B1 resistor_leaf']
    if fault != 'missing-reference-instance':
        node = 'A1' if fault == 'merged-reference-terminal' else 'A2'
        cell = 'changed_leaf' if fault == 'second-reference-width' else 'resistor_leaf'
        rows.append(f'X2 {node} B2 {cell}')
    return reference('\n'.join([*rows, '.ends '+TOP, '']), TOP)


def native_devices(path, model, short=False):
    text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', Path(path).read_text())
    rows = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows) == 4 and rows[0][:2] == ['.subckt', TOP] and
            rows[-1] in (['.ends'], ['.ends', TOP]), 'Changed native top/directives/device count.')
    headers = [(TOP, ' '.join(rows[0][2:]))]; lines = rows[1:3]
    require(len({row[0].lower() for row in lines}) == 2, 'Duplicate native resistor instance.')
    pairs = []
    for row in lines:
        require(len(row) >= 6 and row[0].lower().startswith('r') and
                row[3] == 'sky130_fd_pr__res_generic_'+model, 'Incorrect native resistor type/model.')
        fields = [item.split('=', 1) for item in row[4:]]
        require(all(len(item) == 2 for item in fields), 'Malformed native resistor parameter.')
        params = {key.lower(): scalar(value) for key, value in fields}
        require(len(params) == len(fields) and set(params) in ({'w', 'l'}, {'w', 'l', 'm'}) and
                params['w'] == 2 and params['l'] == 5 and params.get('m', 1) == 1,
                'Changed extracted width, length or multiplicity.')
        pairs.append(frozenset(row[1:3]))
    if short:
        common = pairs[0] & pairs[1]
        require(len(common) == 1 and common <= {'A1', 'A2'} and
                {tuple(sorted(pair-common)) for pair in pairs} == {('B1',), ('B2',)},
                'Native fault is not the intended cross-instance A short.')
        retained = set().union(*pairs)
        require(headers[0][1].split() in (list(PORTS), [p for p in PORTS if p in retained]),
                'The short changed an unrelated native interface terminal/order.')
    else:
        require(set(pairs) == {frozenset(('A1', 'B1')), frozenset(('A2', 'B2'))} and
                headers[0][1].split() == list(PORTS), 'Child-local nets merged or top terminal order changed.')
    return dict(sha256=file_digest(path), devices=2, terminal_pairs=[sorted(x) for x in pairs],
                top_ports=headers[0][1].split(), model=model, width_um=2, length_um=5)


def bridge(project, model):
    """Only connect A1 to A2 outside both resistor bodies; retain leaf bytes."""
    p = clone(project); top = next(c for c in p['cells'] if c['id'] == p['top'])
    labels = {t['text']: (t['x'], t['y']) for t in top['layout_texts']}
    a, b = labels['A1'], labels['A2']; width = 400; y = min(a[1], b[1])-4000
    escape_x = b[0]-1000
    layer = next(x['name'] for x in p['pdk']['layers'] if
                 (x['gds'], x['datatype']) == (straight.MODELS[model][0], 20))
    # Stop the two landing joins at their anchor: a symmetric end cap can
    # intrude into a body when the real generator landing is only .285 um long.
    added = [rect(layer, a[0]-width//2, y-width//2, width, a[1]-y+width//2),
             rect(layer, min(a[0], escape_x)-width//2, y-width//2, abs(a[0]-escape_x)+width, width),
             rect(layer, escape_x-width//2, y-width//2, width, b[1]-y+width),
             rect(layer, escape_x-width//2, b[1]-width//2, b[0]-escape_x+width//2, width)]
    db = kdb(); addition = db.Region(); body = db.Region()
    for shape in added: addition.insert(polygon(shape))
    layers = {v['name']: (v['gds'], v['datatype']) for v in p['pdk']['layers']}
    cells = {c['id']: c for c in p['cells']}
    for instance in top['layout_instances']:
        transform = db.ICplxTrans(1, instance['rotation'], instance['mirror'], instance['x'], instance['y'])
        for shape in cells[instance['cell']]['shapes']:
            if layers[shape['layer']] == (straight.MODELS[model][0], 13):
                body.insert(polygon(shape).transformed(transform))
    require((addition & body).is_empty(), 'The intended connectivity fault also changes a resistor body.')
    top['shapes'] += added
    return p


def check_fault(result, folder, fault, model):
    require([s['name'] for s in result['stages']] == list(STAGES), 'Incomplete native stage sequence.')
    states = {s['name']: s for s in result['stages']}
    require(result['status'] == 'failed' and all(states[n]['status'] == 'passed' for n in STAGES[:3]) and
            result['drc_count'] == 0, 'Fault must pass native DRC and fail connectivity, not setup.')
    deck = folder/'lvs-extraction/extracted.spice'
    native = native_devices(deck, model, short=fault == 'physical-cross-instance-short')
    if states['lvs_extraction']['status'] == 'failed':
        require(fault == 'physical-cross-instance-short' and states['lvs']['status'] == 'not_run' and
                states['integrity']['status'] == 'not_run' and
                native['top_ports'] != list(PORTS) and
                states['lvs_extraction'].get('error', '').startswith('Extracted port order differs from the schematic: '),
                'Unexpected native extraction failure.')
    else:
        require(states['lvs_extraction']['status'] == states['integrity']['status'] == 'passed' and
                states['lvs']['status'] == 'failed', 'Fault did not reach completed strict LVS.')
        log = (folder/'lvs/lvs.log').read_text()
        require(bool(re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching', log, re.I)),
                'Native LVS did not report a circuit/property/interface mismatch.')
    return dict(detected=True, fault=fault, native=native, stages={k: v['status'] for k, v in states.items()},
                report_sha256=file_digest(folder/'report.json'))


def corrupt_exchange(source, target, fault, model):
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
                if shape.is_text() and shape.text.string == 'A2':
                    text = shape.text; text.string = 'A1'; shape.text = text
    else:
        leaf.shapes(ly.layer(straight.MODELS[model][0], 20)).insert(db.Box(100000, 100000, 100500, 100500))
    ly.write(str(target))


def case(tech, model, out, tools, execution_id):
    folder = out/model; folder.mkdir(); record = dict(model=model, status='RUNNING', execution_id=execution_id,
        layouts=[], faults=[], exchange_controls=[])
    try:
        leaf = straight.generate(tech, model, 2, 5, folder/'generator', tools['magic'])
        leaf_path = folder/'leaf.gds'; export_layout(leaf, leaf_path)
        for angle in ANGLES:
            dest = folder/f'r{angle}'; dest.mkdir()
            proof = make_stream(leaf_path, dest/'input.gds', model, angle)
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
            inspect_stream(dest/'reimported.gds', model, angle, leaf_path)
            native_out = dest/'physical'; result = run(imported, imported['top'], native_out, tools, selected(model))
            require(result['status'] == 'passed' and result['drc_count'] == 0 and
                    [s['name'] for s in result['stages']] == list(STAGES) and
                    all(s['status'] == 'passed' for s in result['stages']), result.get('error', 'Native hierarchy failed.'))
            record['layouts'].append(dict(rotation=angle, execution_id=execution_id, geometry=proof,
                exchange=exchange, import_warnings=warnings, project_sha256=file_digest(dest/'saved.icproj'),
                native=native_devices(native_out/'lvs-extraction/extracted.spice', model),
                report_sha256=file_digest(native_out/'report.json')))
            if angle != 0:
                continue
            for fault in FAULTS:
                job = dest/fault; changed = bridge(imported, model) if fault == 'physical-cross-instance-short' else imported
                save_project(changed, dest/(fault+'.icproj'))
                result = run(changed, changed['top'], job, tools, selected(model, fault))
                record['faults'].append(check_fault(result, job, fault, model))
            for fault in EXCHANGE_FAULTS:
                path = dest/(fault+'.gds'); corrupt_exchange(dest/'input.gds', path, fault, model)
                try:
                    inspect_stream(path, model, angle, leaf_path)
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
    files = [*sorted((ROOT/'icstudio').glob('*.py')), *sorted((ROOT/'scripts').glob('*.py')),
             ROOT/'tests/test_sky130_metal_resistor_hierarchy.py',
             ROOT/'tests/test_sky130_metal_resistor_hierarchy_audit.py',
             ROOT/'examples/sky130-qualification-lock.json',
             ROOT/'docs/qualification/sky130-li-contract-v1.json']
    return {p.relative_to(ROOT).as_posix(): file_digest(p) for p in files}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('sky130', 'magic', 'netgen', 'output'):
        ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--models', nargs='+', choices=MODELS, default=list(MODELS))
    args = ap.parse_args()
    if len(set(args.models)) != len(args.models):
        ap.error('Choose distinct models.')
    require(sys.platform == 'linux', 'Use the reviewed ordinary-user Linux native runtime.')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False); started = time.monotonic()
    report = dict(schema=1, suite='sky130-metal-resistor-hierarchy-v1', execution_id=uuid.uuid4().hex,
        execution_root=str(out), source_root=str(ROOT), status='RUNNING', chunk=7, qualified=False,
        full_family=False, release_ready=False, signoff=False, installed=False, chunk_complete=False,
        scope=__doc__, selected_models=args.models, full_models=list(MODELS), contract=CONTRACT, cases=[])
    write(out/'qualification.json', report); write(out/'acceptance-contract.json', CONTRACT)
    report['acceptance_contract_sha256'] = file_digest(out/'acceptance-contract.json')
    try:
        tools = {k: str(getattr(args, k).resolve(strict=True)) for k in ('magic', 'netgen')}
        tech, process = technology('sky130A', args.sky130)
        report.update(process=process, tools={k: dict(path=v, sha256=file_digest(v)) for k, v in tools.items()})
        before = source_files(); write(out/'source-files.json', before)
        for name, digest in before.items():
            path = out/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes((ROOT/name).read_bytes())
            require(file_digest(path) == digest, 'Source changed during capture.')
        pdk = identity.tree(args.sky130); write(out/'physical-package-files.json', pdk)
        (out/'package.json').write_bytes((args.sky130/'package.json').read_bytes())
        with identity.controlled_environment():
            runtime = identity.runtime(tools); write(out/'runtime-before.json', runtime)
            for model in args.models:
                row = case(tech, model, out, tools, report['execution_id']); report['cases'].append(row)
                write(out/'qualification.json', report); print(model, row['status'], row.get('error', ''), flush=True)
                require(row['status'] == 'PASS', 'Hierarchy case failed: '+model)
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
