"""Independent retained-artifact audit of the selected imported MiM hierarchy.

Two existing capacitor occurrences remain editable hierarchy; native verification
uses a private flattened stream. No direct hierarchical Magic, RC, electrical,
installed, full-family or foundry qualification is inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_frozen_mim import require, sha, load, inventory, file_map, design_hash
from scripts.audit_sky130_metal_resistor_hierarchy import (
    cell_regions, same_masks, placements, transform, runtime, PHYSICAL_SHA, STAGES)
from scripts.audit_sky130_li_case import magic_log, check_netgen_inputs
from scripts.audit_sky130_mim_physical_case import execution_scripts

PLATES = (1, 2)
PORTS = ('P1', 'N1', 'P2', 'N2')
TOP, LEAF = 'mim_pair', 'mim_leaf'
FAULTS = ('merged-reference-terminal', 'missing-reference-instance',
          'second-reference-width', 'physical-missing-instance')
EXCHANGE = ('missing-instance', 'lost-mirror', 'lost-rotation',
            'renamed-top-terminal', 'changed-leaf-mask')
CONTRACT_PATH = 'docs/qualification/sky130-mim-hierarchy-v1.json'
CONTRACT_SHA = '7bfb3c4ac6c936e378faab28892e924f46e73295b468a8b45e265c9ef7c823a4'
TECH_SHA = '5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e'
PCELL_SHA = '48d2111c3246cbbed88bca5cf479dd8edc4ce4629d5241cca4102368765da69a'


def model(plate):
    require(type(plate) is int and plate in PLATES, 'Unknown MiM plate.')
    return f'sky130_fd_pr__cap_mim_m3_{plate}'


def literal_leaf(plate):
    """Independent literal mask/anchor contract for the existing 2x10 um leaf."""
    import klayout.db as db
    model(plate); regions = {}
    def box(layer, coords):
        regions.setdefault(layer, db.Region()).insert(db.Box(*coords))
    if plate == 1:
        box((70, 20), (-500, -500, 4500, 10500))
        box((89, 44), (0, 0, 2000, 10000))
        box((71, 20), (100, 100, 1900, 9900))
        box((71, 20), (2800, 4300, 4200, 5700))
        for x in range(300, 1501, 400):
            for y in range(300, 9501, 400): box((70, 44), (x, y, x+200, y+200))
        for x in (3100, 3500, 3900):
            for y in (4600, 5000, 5400): box((70, 44), (x-100, y-100, x+100, y+100))
        labels = [((71, 5), 'N', 3500, 5000), ((71, 5), 'P', 1000, 5000)]
    else:
        box((71, 20), (-500, -500, 6000, 10500))
        box((97, 44), (0, 0, 2000, 10000))
        box((72, 20), (0, 0, 2000, 10000))
        box((72, 20), (3700, 4000, 5700, 6000))
        for y in range(800, 9201, 1600): box((71, 44), (400, y-400, 1200, y+400))
        box((71, 44), (4300, 4600, 5100, 5400))
        labels = [((72, 5), 'N', 4700, 5000), ((72, 5), 'P', 1000, 5000)]
    return {k: v.merged() for k, v in regions.items()}, sorted(labels)


def leaf(path, plate):
    import klayout.db as db
    ly = db.Layout(); ly.read(str(path))
    require(ly.dbu == .001 and ly.cells() == 1 and len(list(ly.top_cells())) == 1 and
            ly.top_cell().name == 'device_coupon' and not list(ly.top_cell().each_inst()), 'Leaf stream hierarchy differs.')
    actual = cell_regions(ly, ly.top_cell()); expected = literal_leaf(plate)
    same_masks(actual[0], expected[0]); require(actual[1] == expected[1], 'Leaf electrode polarity/anchors differ.')
    return actual


def expected_flat(base, angle, missing=False):
    import klayout.db as db
    masks, labels = {}, []
    for n, place in enumerate(placements(angle), 1):
        tr = db.ICplxTrans(1, *place)
        if not (missing and n == 2):
            for key, region in base[0].items(): masks.setdefault(key, db.Region()).insert(region.transformed(tr))
        # Deleting the occurrence deliberately retains the declared top interface.
        for key, name, x, y in base[1]:
            px, py = transform((x, y), place); labels.append((key, name+str(n), px, py))
    return {k: v.merged() for k, v in masks.items()}, sorted(labels)


def stream(path, plate, angle, base, *, private=False, missing=False, corruption=None):
    import klayout.db as db
    ly = db.Layout(); ly.read(str(path)); require(ly.dbu == .001, 'Written stream grid differs.')
    require([c.name for c in ly.top_cells()] == [TOP], 'Written stream top differs.')
    top = ly.cell(TOP); masks, labels = cell_regions(ly, top)
    flat, anchors = expected_flat(base, angle, missing)
    if private:
        require(ly.cells() == 1 and not list(top.each_inst()), 'Private native stream must be flat.')
        same_masks(masks, flat); require(labels == anchors, 'Private stream terminal anchors differ.')
        return
    require({c.name for c in ly.each_cell()} == {TOP, LEAF}, 'Editable hierarchy was lost or substituted.')
    child = ly.cell(LEAF); require(not list(child.each_inst()), 'Unexpected nested leaf.')
    child_masks, child_labels = cell_regions(ly, child)
    expected = {k: v.dup() for k, v in base[0].items()}
    if corruption == 'changed-leaf-mask': expected[(69+plate, 20)].insert(db.Box(100000, 100000, 100500, 100500))
    same_masks(child_masks, expected); require(child_labels == base[1], 'Child labels differ.')
    wanted = placements(angle)
    if missing or corruption == 'missing-instance': wanted = wanted[:1]
    elif corruption == 'lost-mirror': wanted = [wanted[0], (wanted[1][0], False, *wanted[1][2:])]
    elif corruption == 'lost-rotation': wanted = [wanted[0], (0, wanted[1][1], *wanted[1][2:])]
    actual = []
    for instance in top.each_inst():
        t = instance.cplx_trans
        require(instance.cell_index == child.cell_index() and t.mag == 1 and max(1, instance.na) == max(1, instance.nb) == 1,
                'Child target/scale/array multiplicity differs.')
        actual.append((t.angle, t.is_mirror(), t.disp.x, t.disp.y))
    require(sorted(actual) == sorted(wanted) and not masks, 'Written hierarchy placement/direct masks differ.')
    if corruption == 'renamed-top-terminal': anchors = [(p, 'P1' if n == 'P2' else n, x, y) for p, n, x, y in anchors]
    require(labels == sorted(anchors), 'Written top-terminal anchors differ.')
    return dict(sha256=sha(path), cells=2, reused_leaf=LEAF, instances=2,
        placements=[list(p) for p in sorted(placements(angle))], terminal_anchors=[[a,b,n,x,y] for (a,b),n,x,y in anchors],
        width_um=2, length_um=10, plate=plate, model=model(plate))


def project_masks(cell, layers):
    import klayout.db as db
    masks = {}
    for shape in cell['shapes']:
        require(shape['kind'] in ('rect', 'polygon'), 'Unsupported imported shape.')
        polygon = db.Polygon(db.Box(*shape['points'][0], *shape['points'][1])) if shape['kind'] == 'rect' else db.Polygon([db.Point(*p) for p in shape['points']])
        for hole in shape.get('holes', []): polygon.insert_hole([db.Point(*p) for p in hole])
        masks.setdefault(layers[shape['layer']], db.Region()).insert(polygon)
    return {k: v.merged() for k, v in masks.items()}


def project(path, plate, angle, base, package, *, missing=False):
    value = load(path); cells = {c['name']: c for c in value['cells']}
    require(len(value['cells']) == 2 and set(cells) == {TOP, LEAF} and value['top'] == cells[TOP]['id'] and
            cells[TOP]['ports'] == list(PORTS), 'Saved project hierarchy/interface differs.')
    require(value['pdk']['package_lock'] == {k: package[k] for k in ('id', 'revision', 'files')}, 'Physical package lock differs.')
    layers = {r['name']: (r['gds'], r['datatype']) for r in value['pdk']['layers']}
    require(len(layers) == len(value['pdk']['layers']), 'Duplicate project layer.')
    for name, cell in cells.items():
        require(not cell['devices'] and not cell.get('layout_ports') and not cell.get('layout_pins'), 'Imported geometry was replaced by device objects.')
        same_masks(project_masks(cell, layers), base[0] if name == LEAF else {})
        labels = sorted((layers[r['layer']], r['text'], r['x'], r['y']) for r in cell.get('layout_texts', []))
        require(labels == (base[1] if name == LEAF else expected_flat(base, angle)[1]), 'Saved labels differ.')
    require(not cells[LEAF]['layout_instances'], 'Saved leaf unexpectedly contains children.')
    rows = cells[TOP]['layout_instances']; wanted = placements(angle)[:1] if missing else placements(angle)
    require(len(rows) == len(wanted) and len({r['id'] for r in rows}) == len(rows) and
            all(r['cell'] == cells[LEAF]['id'] and r['nx'] == r['ny'] == 1 for r in rows) and
            sorted((r['rotation'], r['mirror'], r['x'], r['y']) for r in rows) == sorted(wanted), 'Saved instance references/transforms differ.')
    return value


def leaf_project(path, plate, package, base):
    p = load(path); require(len(p['cells']) == 1 and p['top'] == p['cells'][0]['id'], 'Original leaf project differs.')
    c = p['cells'][0]; key = f'sky130_fd_pr/cap_mim_m3_{plate}.sym'
    require(c['name'] == 'device_coupon' and c['ports'] == ['P', 'N'] and len(c['devices']) == 1 and not c.get('layout_instances', []), 'Original leaf interface/device count differs.')
    d = c['devices'][0]
    require(d['model_ref'] == dict(pdk='sky130A', revision=package['revision'], device=key) and d['nets'] == dict(c0='P', c1='N') and
            d['model_params'] == dict(w=2, l=10, mf=1), 'Original application model/parameters differ.')
    require(p['pdk']['package_lock'] == {k: package[k] for k in ('id', 'revision', 'files')}, 'Original leaf package differs.')
    require(p['pdk']['simulation']['catalog'][key] == package['technology']['simulation']['catalog'][key], 'Original model binding differs.')
    layers = {r['name']: (r['gds'], r['datatype']) for r in p['pdk']['layers']}
    same_masks(project_masks(c, layers), base[0])
    require(sorted((layers[r['layer']], r['text'], r['x'], r['y']) for r in c['layout_texts']) == base[1], 'Original project/stream anchors differ.')


def native_circuit(path, plate, missing=False):
    text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', Path(path).read_text())
    rows = [r.split() for r in text.splitlines() if r.strip() and not r.lstrip().startswith('*')]; count = 1 if missing else 2
    require(len(rows) == count+2 and rows[0][:2] == ['.subckt', TOP] and rows[-1] in (['.ends'], ['.ends', TOP]), 'Native boundary/device count differs.')
    ports = rows[0][2:]; require(ports == list(PORTS) or missing and ports == ['P1', 'N1'], 'Native port order differs.')
    require(len({r[0].lower() for r in rows[1:-1]}) == count, 'Duplicate native instance name.')
    pairs = []
    for row in rows[1:-1]:
        require(len(row) in (6, 7) and re.fullmatch(r'[Xx][A-Za-z0-9_.$:]+', row[0]) and row[3] == model(plate), 'Native primitive/model differs.')
        fields = [v.split('=') for v in row[4:]]; require(all(len(v) == 2 for v in fields), 'Malformed native parameter.')
        params = {k.lower(): float(v) for k, v in fields}
        require(len(params) == len(fields) and set(params) in ({'w', 'l'}, {'w', 'l', 'm'}) and
                all(math.isfinite(v) for v in params.values()) and (params['w'], params['l'], params.get('m', 1)) == (2, 10, 1), 'Native dimensions/multiplicity differ.')
        pairs.append(row[1:3])
    require(sorted(pairs) == ([['P1','N1']] if missing else [['P1','N1'],['P2','N2']]), 'Native polarity/independent graph differs.')
    return dict(sha256=sha(path), devices=count, terminal_pairs=sorted(pairs), top_ports=ports,
                model=model(plate), width_um=2, length_um=10, multiplicity=1)


def reference_text(plate, fault=None):
    require(fault in (None, *FAULTS), 'Unknown reference mutation.')
    full = model(plate); lines = ['.subckt capacitor_leaf P N', f'XLEAF P N {full} w=2 l=10 m=1', '.ends capacitor_leaf']
    if fault == 'second-reference-width': lines += ['.subckt changed_leaf P N', f'XLEAF P N {full} w=3 l=10 m=1', '.ends changed_leaf']
    lines += ['.subckt mim_pair P1 N1 P2 N2', 'X1 P1 N1 capacitor_leaf']
    if fault != 'missing-reference-instance': lines += ['X2 '+('P1' if fault == 'merged-reference-terminal' else 'P2')+' N2 '+('changed_leaf' if fault == 'second-reference-width' else 'capacitor_leaf')]
    return '\n'.join([*lines, '.ends mim_pair', ''])


def scripts(folder, origin, pdk):
    old = ''.join(f'if {{![port "{n}" exists]}} {{error "Missing layout port {n}"}}\nport "{n}" index {i}\n' for i,n in enumerate(('P','N'),1))
    new = ''.join(f'if {{![port "{n}" exists]}} {{error "Missing layout port {n}"}}\nport "{n}" index {i}\n' for i,n in enumerate(PORTS,1))
    expected = {k: v.replace('"device_coupon"', '"mim_pair"').replace(old, new) for k,v in execution_scripts(str(origin), str(pdk/'libs.tech/magic/sky130A.tech')).items()}
    actual = {p.relative_to(folder).as_posix() for part in ('drc','lvs-extraction') for p in (folder/part).glob('*.tcl')}
    require(actual == set(expected), 'Native Tcl coverage differs.')
    for name, text in expected.items(): require((folder/name).read_text() == text, 'Native execution settings/input differs: '+name)


def normalization(folder, plate, count):
    """Read geometry and every native EXT line without calling the normalizer."""
    import klayout.db as db
    ly = db.Layout(); ly.read(str(folder/'layout.gds')); masks, _ = cell_regions(ly, ly.top_cell())
    capkey, bottomkey, cutkey = ((89,44),(70,20),(70,44)) if plate == 1 else ((97,44),(71,20),(71,44))
    caps = list(masks[capkey].each()); require(len(caps) == count, 'Native electrode count differs.')
    rows = []
    for cap in caps:
        box = cap.bbox(); require(cap.is_box() and sorted((box.width(),box.height())) == [2000,10000], 'Native capacitor geometry differs.')
        bottoms = [p for p in masks[bottomkey].each() if (db.Region(cap)-db.Region(p)).is_empty()]
        require(len(bottoms) == 1, 'Native bottom electrode is ambiguous.')
        bottom = bottoms[0].bbox(); extra = (bottom.width()-box.width(), bottom.height()-box.height())
        require(sorted(extra) == [1000, 3000 if plate == 1 else 4500], 'Native bottom extension differs.')
        axis = 'x' if extra[0] > extra[1] else 'y'
        require((box.width(),box.height()) == ((2000,10000) if axis == 'x' else (10000,2000)), 'Native physical orientation differs.')
        contacts = []
        for cut in masks[cutkey].each():
            region = db.Region(cut)
            if (region-db.Region(bottoms[0])).is_empty() and not (region-db.Region(cap)).is_empty():
                require((region & db.Region(cap)).is_empty(), 'Contact overlaps capacitor boundary.')
                v = cut.bbox(); contacts.append([v.left,v.bottom,v.right,v.top])
        rows.append(dict(model=model(plate), box=[box.left,box.bottom,box.right,box.top], axis=axis, bottom_contacts=contacts))
    ext = folder/'lvs-extraction'; proof = load(ext/'mim-orientation.json'); before = ext/'native-original.ext'; after = ext/(TOP+'.ext')
    require(proof['schema'] == 1 and proof['model'] == model(plate) and proof['models'] == [model(plate)] and
            proof['technology_sha256'] == TECH_SHA and proof['pcell_sha256'] == PCELL_SHA and
            proof['gds_sha256'] == sha(folder/'layout.gds') and proof['native_sha256'] == sha(before) and proof['corrected_sha256'] == sha(after) and
            proof['gds_dbu_um'] == .001 and proof['electrodes'] == rows, 'Orientation proof differs from actual masks/native inputs.')
    scale = proof['native_coordinate_nm']; require(scale in (5,10), 'Unknown native coordinate scale.')
    log = magic_log(ext/'native-extraction.log')
    scales = re.findall(r'^STUDIO_MIM_SCALE (\S+)$', log, re.M)
    require(len(scales) == 1 and math.isclose(float(scales[0])*1000, scale, abs_tol=1e-5), 'Native scale differs from orientation proof.')
    text = before.read_text(); require(not re.search(r'^use\s', text, re.M), 'Native EXT must be privately flattened.')
    seen, expected, changes = set(), [], []
    for line in text.splitlines(keepends=True):
        if line.startswith('device '):
            fields = shlex.split(line)
            require(len(fields) >= 9 and fields[:3] == ['device','csubckt',model(plate)] and fields[7].startswith('w=') and fields[8].startswith('l='), 'Unexpected native EXT primitive/parameters.')
            site = db.Box(*(int(v)*scale for v in fields[3:7])); matches = [i for i,r in enumerate(rows) if db.Box(*r['box']).contains(site.p1) and db.Box(*r['box']).contains(site.p2)]
            require(len(matches) == 1 and matches[0] not in seen, 'Native EXT location reused/substituted an electrode.')
            i = matches[0]; seen.add(i); box = db.Box(*rows[i]['box'])
            require([float(v.split('=')[1])*scale for v in fields[7:9]] == [box.width(),box.height()], 'Native EXT dimensions disagree with masks.')
            if rows[i]['axis'] == 'y':
                changed,n = re.subn(r'\bw=([^\s]+)(\s+)l=([^\s]+)', lambda m:'w='+m[3]+m[2]+'l='+m[1], line)
                require(n == 1, 'Ambiguous native W/L correction.')
                changes.append(dict(electrode=i,before=line.rstrip(),after=changed.rstrip())); line=changed
        expected.append(line)
    require(len(seen) == count and ''.join(expected) == after.read_text() and proof['changes'] == changes,
            'Native normalization changed connectivity or other EXT tokens, or lost an electrode.')
    return proof


def width_mismatch(log, plate):
    rows = re.findall(r'^[ \t]+w circuit1: (\S+)[ \t]+circuit2: (\S+)[ \t]+\(delta=40%, cutoff=1%\)$', log, re.M)
    require(len(rows) == 1 and tuple(map(float,rows[0])) == (3.,2.), 'Wrong-width fault lacks exact W3 versus W2 property error.')
    full = model(plate)
    blocks = re.findall(r'^([^\n]+ vs\. [^\n]+):\n[ \t]+w circuit1:', log, re.M)
    require(len(blocks) == 1 and all(full in side for side in blocks[0].split(' vs. ')) and
            re.findall(r'^The following cells had property errors:\n ([^\n]+)$',log,re.M) == [TOP], 'Wrong-width error is not bound to model/top.')
    final = re.findall(r'^Final result: (.+)$',log,re.M)
    require(final == ['Circuits match uniquely.'] and 'Property errors were found.' in log or
            final == ['Top level cell failed pin matching.'] and any(v in log for v in
                ('Netlists match with 2 symmetries with property errors.', 'Netlists match uniquely with property errors.')),
            'Wrong-width fault has unrelated native conclusion.')


def native(folder, origin, pdk, plate, angle, base, package, tools, fault=None):
    record = load(folder/'report.json'); stages = record['stages']; missing = fault == 'physical-missing-instance'
    require([r['name'] for r in stages] == list(STAGES), 'Missing/duplicate native stages.')
    states = [r['status'] for r in stages]
    allowed = (['passed']*6,) if fault is None else ((['passed']*4+['failed','passed'], ['passed']*3+['failed','not_run','not_run']) if missing else (['passed']*4+['failed','passed'],))
    require(states in allowed and record['status'] == ('failed' if fault else 'passed') and record['drc_engine'] == record['lvs_extractor'] == 'magic' and record['magic_drc_style'] == 'drc(full)', 'Wrong native stage/outcome/tool/style.')
    assets = {str(pdk/n): v for n,v in package['files'].items() if n.startswith(('libs.tech/magic/','libs.tech/netgen/'))}
    require(stages[0]['evidence']['assets'] == assets and stages[0]['evidence']['tools'] == tools, 'Native tool/PDK binding differs.')
    saved = project(folder/'input.icproj',plate,angle,base,package,missing=missing)
    require(record['design_hash'] == design_hash(saved) and record['cell_name'] == TOP, 'Native input design differs.')
    stream(folder/'original.gds',plate,angle,base,missing=missing); stream(folder/'layout.gds',plate,angle,base,private=True,missing=missing)
    ref = reference_text(plate,fault)
    for name in ('schematic.spice','schematic-lvs.spice'): require((folder/name).read_text() == ref, 'Reference changed beyond exact named fault.')
    require(record['reference'] == dict(top=TOP,ports=list(PORTS),sha256=hashlib.sha256(ref.encode()).hexdigest()), 'Reference receipt differs.')
    scripts(folder,origin,pdk); drc = magic_log(folder/'drc/console.log'); magic_log(folder/'lvs-extraction/console.log')
    require(re.findall(r'^STUDIO_DRC_COUNT (\d+)$',drc,re.M) == ['0'] and re.findall(r'^STUDIO_DRC_STYLE (.+)$',drc,re.M) == ['drc(full)'] and
            record['drc_count'] == record['magic_drc_count'] == 0 and (folder/'drc/findings.tsv').read_text() == '', 'Actual full DRC failed/incomplete.')
    extracted = native_circuit(folder/'lvs-extraction/extracted.spice',plate,missing)
    proof = normalization(folder,plate,1 if missing else 2)
    if states[3] == 'failed':
        require(missing and extracted['top_ports'] == ['P1','N1'] and stages[3].get('error','').startswith('Extracted port order differs from the schematic: ') and
                not (folder/'lvs/lvs.log').exists() and 'mim_orientation' not in record,
                'Missing-instance fault has unrelated interface failure.')
    else:
        require(record['mim_orientation'] == proof, 'Native orientation summary differs.')
        settings = dict(hierarchy=True,blackbox=False,merge='none',scale=False,capacitance_threshold='infinite',resistance_threshold='infinite',distributed_resistance=False)
        require(stages[3]['evidence'] == dict(deck='lvs-extraction/extracted.spice',sha256=extracted['sha256'],settings=settings), 'Extraction settings/digest differ.')
        log = (folder/'lvs/lvs.log').read_text(); console = (folder/'lvs/console.log').read_text(); check_netgen_inputs(console,origin,pdk)
        require(not re.search(r'invalid command|could not open|cannot open|Error in|Traceback',log+console,re.I), 'Native LVS infrastructure failed.')
        if fault:
            require(re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching',log,re.I), 'No actual native graph/property mismatch.')
            if fault == 'second-reference-width': width_mismatch(log,plate)
        else:
            require(re.findall(r'^Final result: (.+)$',log,re.M) == ['Circuits match uniquely.'] and 'Cell pin lists are equivalent.' in log and
                    not re.search(r'Property errors|do not match|disconnected node|no matching pin|altered',log,re.I), 'Native circuits did not match uniquely.')
        integrity = stages[-1]['evidence']
        require(integrity['verified'] is True and integrity['assets'] == assets and integrity['tools'] == tools, 'Native integrity binding differs.')
        file_map(folder,integrity['files'])
    return dict(detected=True,fault=fault,native=extracted,stages={r['name']:r['status'] for r in stages},report_sha256=sha(folder/'report.json'))


def audit(root, reviewed_source=None):
    root = Path(root).resolve(); report = load(root/'qualification.json')
    require(load(root/'manifest.json') == inventory(root,('manifest.json','audit.json')), 'Complete evidence inventory differs.')
    require(report.get('schema') == 1 and report.get('suite') == 'sky130-mim-hierarchy-v1' and report.get('status') == 'PASS' and
            all(report.get(k) is False for k in ('qualified','full_family','release_ready','signoff','installed','chunk_complete')) and
            not report.get('error') and not report.get('traceback'), 'Incomplete/overclaimed hierarchy evidence.')
    require(re.fullmatch('[0-9a-f]{32}',report['execution_id']) and PurePosixPath(report['execution_root']).is_absolute(), 'Invalid original execution identity.')
    origin = PurePosixPath(report['execution_root']); plates = report['selected_plates']
    require(plates and len(set(plates)) == len(plates) and all(type(p) is int and p in PLATES for p in plates) and report['full_plates'] == list(PLATES), 'Invalid selected plates.')
    contract = load(root/'acceptance-contract.json')
    require(CONTRACT_SHA and report['contract'] == contract and report['acceptance_contract_sha256'] == sha(root/'acceptance-contract.json') == CONTRACT_SHA, 'Unreviewed acceptance contract.')
    sources = load(root/'source-files.json')
    require(report['source_files_sha256'] == sha(root/'source-files.json') and inventory(root/'source') == sources, 'Captured source inventory differs.')
    required = {'scripts/qualify_sky130_mim_hierarchy.py','scripts/audit_sky130_mim_hierarchy.py','tests/test_sky130_mim_hierarchy.py','tests/test_sky130_mim_hierarchy_audit.py',CONTRACT_PATH,'examples/sky130-qualification-lock.json'}
    require(required <= sources.keys() and sources[CONTRACT_PATH] == CONTRACT_SHA, 'Missing source dependency/contract.')
    if reviewed_source is not None: require(all(sha(Path(reviewed_source)/n) == h for n,h in sources.items()), 'Captured source differs from reviewed files.')
    for name, source in contract['sources'].items():
        path = root/'source'/source['path'] if 'path' in source else root/'contract-sources'/name
        require(sha(path) == source['sha256'], 'Public source binding differs: '+name)
    package = load(root/'package.json'); require(sha(root/'package.json') == PHYSICAL_SHA, 'Physical package differs.')
    require(report['process']['target'] == 'sky130A' and report['process']['manifest_sha256'] == PHYSICAL_SHA and report['process']['revision'] == package['revision'], 'Process declaration differs.')
    pdk_files = load(root/'physical-package-files.json'); require(report['physical_package_files_sha256'] == sha(root/'physical-package-files.json'), 'Physical inventory hash differs.')
    require(pdk_files['package.json']['sha256'] == PHYSICAL_SHA and all(pdk_files[n]['sha256'] == h for n,h in package['files'].items()), 'Physical assets differ.')
    pdk = PurePosixPath(pdk_files['package.json']['resolved']).parent
    require(pdk.is_absolute() and all(PurePosixPath(pdk_files[n]['resolved']) == pdk/n for n in package['files']), 'Physical assets reference another root.')
    require(report['guards'] == dict(source=True,physical_package=True,runtime=True), 'Final guards missing.')
    tools = runtime(root,report); require([r['plate'] for r in report['cases']] == plates, 'Case coverage differs.')
    clean = faults = exchanges = 0
    from icstudio.stream_contract import compare
    for plate,row in zip(plates,report['cases']):
        folder = root/f'p{plate}'; require(load(folder/'record.json') == row and row['status'] == 'PASS' and row['execution_id'] == report['execution_id'], 'Case record differs.')
        base = leaf(folder/'leaf.gds',plate); leaf_project(folder/'leaf.icproj',plate,package,base)
        require([r['rotation'] for r in row['layouts']] == [0,90] and [r['fault'] for r in row['faults']] == list(FAULTS) and
                [r['fault'] for r in row['exchange_controls']] == list(EXCHANGE), 'Missing orientations/faults.')
        for angle,summary in zip((0,90),row['layouts']):
            dest = folder/f'r{angle}'
            require(summary['execution_id'] == report['execution_id'] and summary['project_sha256'] == sha(dest/'saved.icproj') and
                    summary['geometry'] == stream(dest/'input.gds',plate,angle,base), 'Saved orientation identity differs.')
            project(dest/'saved.icproj',plate,angle,base,package)
            for name in ('export.gds','export.oas','reimported.gds'): stream(dest/name,plate,angle,base)
            compare(dest/'input.gds',dest/'export.gds')
            compare(dest/'input.gds',dest/'export.oas',text_presentation=False)
            compare(dest/'input.gds',dest/'reimported.gds',text_presentation=False)
            require(set(summary['exchange']) == {'gds','oasis','reimported'} and all(v['status'] == 'passed' for v in summary['exchange'].values()), 'Reported stream exchange failed.')
            checked = native(dest/'physical',origin/f'p{plate}'/f'r{angle}'/'physical',pdk,plate,angle,base,package,tools)
            require(summary['native'] == checked['native'] and summary['report_sha256'] == checked['report_sha256'], 'Clean extraction summary differs.'); clean += 1
        for fault,summary in zip(FAULTS,row['faults']):
            project(folder/'r0'/(fault+'.icproj'),plate,0,base,package,missing=fault == FAULTS[-1])
            checked = native(folder/'r0'/fault,origin/f'p{plate}'/'r0'/fault,pdk,plate,0,base,package,tools,fault)
            require(summary == checked, 'Fault receipt differs from actual native result.'); faults += 1
        for fault,summary in zip(EXCHANGE,row['exchange_controls']):
            path = folder/'r0'/(fault+'.gds')
            require(summary['rejected'] is True and summary['error'] and summary['sha256'] == sha(path), 'Exchange control receipt differs.')
            stream(path,plate,0,base,corruption=fault)
            try: stream(path,plate,0,base)
            except ValueError: pass
            else: raise ValueError('Corrupt stream accepted.')
            exchanges += 1
    return dict(schema=1,status='PASS',suite=report['suite'],execution_id=report['execution_id'],original_execution_root=str(origin),
        qualification_sha256=sha(root/'qualification.json'),manifest_sha256=sha(root/'manifest.json'),source_files_sha256=sha(root/'source-files.json'),
        qualified=False,full_family=False,installed=False,release_ready=False,signoff=False,chunk_complete=False,
        counts=dict(models=len(plates),clean_layouts=clean,native_capacitors=clean*2,native_faults=faults,exchange_controls=exchanges),
        full_selected_models=plates == list(PLATES),source_binding='captured sources matched reviewed files' if reviewed_source else 'self-contained source inventory',scope=__doc__)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--reviewed-source',type=Path); parser.add_argument('--out',type=Path)
    args = parser.parse_args(); result = audit(args.root,args.reviewed_source); text = json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.out: require(not args.out.exists(),'Use a fresh audit receipt.'); args.out.write_text(text)
    print(text)


if __name__ == '__main__': main()
