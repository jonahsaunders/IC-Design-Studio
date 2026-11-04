"""Sampled mixed IHP NPN/SVaricap layouts with a common physical substrate.

Preserves both source coupons and their annotations, checks both public geometry
decks plus existing supplements, and requires strict extracted device/port
comparison. Not complete mixed-device or operating-envelope qualification.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.qualify_ihp_npn_layouts import CASES, generate, altered, model_name
from scripts.qualify_ihp_varactor_layouts import stream, detected as varactor_detected
from scripts.qualify_standard_mos import load_technology, write
from scripts.qualify_ihp_resistor_layouts import rotated, same_masks
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.layout import kdb
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference, run
from icstudio.model import file_digest, save_project, load_project, scalar
from icstudio.stream_contract import compare

PAIRS = ((CASES[0], 'small', 1), (CASES[4], 'small', 4), (CASES[8], 'large', 10))
PORTS = ['C', 'B', 'E', 'S', 'G1', 'W', 'G2']
FAULTS = ('npn-E-open', 'npn-reference-count', 'var-oxide-gap',
          'var-missing-recognition', 'var-gate-short', 'var-reference-fingers', 'reference-substrate',
          'npn-unrelated-diffusion', 'npn-unrelated-well')


def selected(pair, fault=None):
    item, size, nx = pair; _, w, l, count = item
    if fault == 'npn-reference-count': count += 1
    if fault == 'var-reference-fingers': nx += 1
    vw, vl = (3.74e-6, .3e-6) if size == 'small' else (9.74e-6, .8e-6)
    body = 'W' if fault == 'reference-substrate' else 'S'
    return reference('.subckt mixed_coupon ' + ' '.join(PORTS) + '\n'
        + f'XQ C B E S {model_name(item)} we={w}u le={l}u Nx={count}\n'
        + f'C1 G1 W G2 {body} sg13_hv_svaricap w={vw} l={vl} nx={nx} m=1\n'
        + '.ends mixed_coupon\n', 'mixed_coupon')


def build(tech, pair, folder, fault=None):
    folder.mkdir(parents=True, exist_ok=False)
    item, size, nx = pair
    p = generate(tech, item, folder/'npn-source')
    if fault == 'npn-E-open': p = altered(p, 'E-open')
    export_layout(p, folder/'npn.gds')
    var_fault = fault[4:] if fault in ('var-oxide-gap', 'var-missing-recognition', 'var-gate-short') else None
    source = stream(folder/'varactor.gds', size, nx, fault=var_fault)
    write(folder/'varactor-source.json', source)
    k = kdb(); ly = k.Layout(); ly.dbu = .001; top = ly.create_cell('mixed_coupon')
    expected = {}; texts = []
    for name, x in [('npn', 0), ('varactor', 100000)]:
        old = k.Layout(); old.read(str(folder/(name+'.gds'))); cell = old.top_cell(); transform = k.Trans(x, 0)
        for index in old.layer_indexes():
            info = old.get_info(index); pair_id = (info.layer, info.datatype)
            expected.setdefault(pair_id, k.Region()).insert(k.Region(cell.begin_shapes_rec(index)).transformed(transform))
            texts.extend((pair_id, s.text.string, s.text.x+x, s.text.y)
                         for s in cell.shapes(index).each() if s.is_text())
        child = ly.create_cell(name); child.copy_tree(cell)
        top.insert(k.CellInstArray(child.cell_index(), transform))
    top.flatten(True)
    actual_texts = []
    for index in ly.layer_indexes():
        info = ly.get_info(index); pair_id = (info.layer, info.datatype)
        if not (expected[pair_id] ^ k.Region(top.shapes(index))).is_empty():
            raise ValueError('Mixed placement changed source geometry.')
        actual_texts.extend((pair_id, s.text.string, s.text.x, s.text.y)
                            for s in top.shapes(index).each() if s.is_text())
    if sorted(actual_texts) != sorted(texts): raise ValueError('Mixed placement changed source annotations.')
    if fault in ('npn-unrelated-diffusion','npn-unrelated-well'):
        active=k.Region(top.shapes(ly.layer(1,0)));implant=k.Region(top.shapes(ly.layer(14,0)))
        guards=[p for p in (active & implant).merged().each() if p.holes()==1 and p.bbox().right<50000]
        if len(guards)!=1:raise ValueError('Missing unique NPN substrate guard for physical fault control.')
        box=guards[0].bbox();x=box.center().x;y=box.top-1800
        top.shapes(ly.layer(1 if fault=='npn-unrelated-diffusion' else 31,0)).insert(k.Box(x-200,y-200,x+200,y+200))
    ly.write(str(folder/'mixed.gds'))
    q, _ = read_layout(folder/'mixed.gds'); link_technology(q, tech); q['cells'][0]['ports'] = PORTS[:]
    q['cells'][0].setdefault('layout_ports', [])
    return q


def audit(path, pair):
    rows = [s.split() for s in path.read_text().splitlines()
            if s.strip() and not s.lstrip().startswith(('*', '.', '+'))]
    item, size, nx = pair; _, w, l, count = item
    vw, vl = (3.74e-6, .3e-6) if size == 'small' else (9.74e-6, .8e-6)
    expected = {model_name(item): (['C', 'B', 'E', 'S'], dict(we=w*1e-6, le=l*1e-6, nx=count, m=1)),
                'sg13_hv_svaricap': (['G1', 'W', 'G2', 'S'], dict(w=vw, l=vl, nx=nx, m=1))}
    if len(rows) != 2 or {r[5] for r in rows} != set(expected):
        raise ValueError('Mixed extraction must retain exactly both devices.')
    for row in rows:
        terminals, values = expected[row[5]]
        # The pinned public Netgen setup explicitly permits varactor pins 1/3
        # to exchange. Rotation changes their extraction order; W and SUB must
        # retain their separate roles, and NPN terminals never use this rule.
        allowed = [terminals]
        if row[5] == 'sg13_hv_svaricap': allowed.append(['G2', 'W', 'G1', 'S'])
        if row[1:5] not in allowed: raise ValueError('Mixed extraction changed terminal roles.')
        params = {key.lower(): scalar(value) for key, value in (s.split('=', 1) for s in row[6:])}
        # Native public varactor output has implicit unit multiplicity.
        if row[5] == 'sg13_hv_svaricap' and 'm' not in params: params['m'] = 1
        if set(params) != set(values) or any(not math.isclose(params[k], v, rel_tol=1e-9, abs_tol=abs(v)*1e-10) for k, v in values.items()):
            raise ValueError('Mixed extraction changed dimensions or multiplicity.')
    return dict(sha256=file_digest(path), devices=2, models=sorted(expected), terminal_roles_preserved=True)


def detected(result, folder, fault):
    stages = {s['name']: s for s in result['stages']}
    if result['status'] != 'failed' or any(stages[n]['status'] != 'passed' for n in ('preflight', 'layout_export')):
        return False
    if fault == 'var-oxide-gap': return varactor_detected(result, folder, 'oxide-gap', 'ihp-public')
    if fault in ('npn-unrelated-diffusion','npn-unrelated-well'):
        native=folder/'drc/npn-native/result.json'
        return (native.is_file() and stages['drc']['status']=='failed'
                and any('No unrelated diffusion or well may exist in the NPN area' in row['reason']
                        for row in json.loads(native.read_bytes())['findings']))
    native = folder/'lvs-extraction/native.cir'
    if fault in ('npn-E-open', 'var-gate-short'):
        declarations = re.findall(r'(?im)^\.subckt\s+mixed_coupon\s+([^\n]*)', native.read_text()) if native.is_file() else []
        return (stages['lvs_extraction'].get('error') == 'IHP extracted port names differ from the schematic.'
                and len(declarations) == 1 and set(declarations[0].split()) != set(PORTS))
    if fault == 'var-missing-recognition':
        # The remaining NPN prevents an empty-circuit shortcut. Require native
        # evidence that the varactor disappeared and an extraction/LVS failure.
        return (native.is_file() and 'sg13_hv_svaricap' not in native.read_text()
                and 'npn13G2' in native.read_text()
                and stages['lvs_extraction'].get('error') == 'IHP extracted port names differ from the schematic.'
                and stages['lvs_extraction']['status'] == 'failed')
    return varactor_detected(result, folder, 'reference-fingers', 'ihp-public')


def case(pair, folder, tools):
    item, size, nx = pair; folder.mkdir()
    row = dict(npn=item, varactor=[size, nx], layouts=[], faults=[], status='RUNNING')
    try:
        tech, identity = load_technology('ihp-sg13g2'); row['package'] = identity
        p = build(tech, pair, folder/'source'); save_project(p, folder/'saved.icproj')
        q = load_project(folder/'saved.icproj'); same_masks(p, q)
        for angle in (0, 90, 180, 270):
            if angle: q = rotated(q)
            dest = folder/('rotation-'+str(angle))
            result = run(q, q['top'], dest, tools, selected(pair), lvs_extractor='ihp-klayout', drc_engine='ihp-public')
            if result['status'] != 'passed': raise ValueError(result.get('error', 'Mixed layout failed.'))
            export_layout(q, folder/(str(angle)+'.oas'))
            row['layouts'].append(dict(rotation=angle, drc_count=result['drc_count'],
                exchange=compare(dest/'original.gds', folder/(str(angle)+'.oas'), text_presentation=False),
                native=audit(dest/'lvs-extraction/native.cir', pair),
                extracted=audit(dest/'lvs-extraction/extracted.spice', pair),
                report_sha256=file_digest(dest/'report.json')))
        for fault in FAULTS:
            q = build(tech, pair, folder/(fault+'-source'), fault) if fault in ('npn-E-open', 'var-oxide-gap', 'var-missing-recognition', 'var-gate-short', 'npn-unrelated-diffusion', 'npn-unrelated-well') else p
            dest = folder/fault
            result = run(q, q['top'], dest, tools, selected(pair, fault), lvs_extractor='ihp-klayout', drc_engine='ihp-public')
            found = detected(result, dest, fault)
            row['faults'].append(dict(name=fault, detected=found, error=result.get('error'), report_sha256=file_digest(dest/'report.json')))
            if not found: raise ValueError('Fault lacks the expected native evidence: '+fault)
        row['status'] = 'PASS'
    except Exception as exc: row.update(status='FAIL', error=str(exc), traceback=traceback.format_exc())
    write(folder/'record.json', row); return row


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True)
    for tool in ('magic', 'netgen', 'klayout'): ap.add_argument('--'+tool, type=Path, required=True)
    ap.add_argument('--workers', type=int, choices=(1, 2, 3), default=2)
    ap.add_argument('--large-third', action='store_true', help='Use the large Nx10 third pair (also the current default).')
    args = ap.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    tools = {name: str(getattr(args, name).resolve(strict=True)) for name in ('magic', 'netgen', 'klayout')}
    sources = {p.relative_to(ROOT).as_posix(): file_digest(p) for base in ('icstudio', 'scripts') for p in (ROOT/base).rglob('*.py')}
    write(out/'source-files.json', sources); (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report = dict(schema=1, chunk=7, chunk_complete=False, qualified=False, scope=__doc__, status='RUNNING', cases=[])
    pairs = (*PAIRS[:2], (CASES[8], 'large', 10)) if args.large_third else PAIRS
    report['requested_pairs'] = pairs
    report['unresolved_scope'] = 'Other device combinations, complete operating envelopes and installed acceptance remain open. The full public decks and native NPN supplement are required on every mixed layout.'
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(case, pair, out/('pair-'+str(i)), tools) for i, pair in enumerate(pairs)]
        for job in as_completed(jobs):
            row = job.result(); report['cases'].append(row); write(out/'qualification.json', report)
            print(row['npn'][0], row['status'], row.get('error', ''), flush=True)
    report['source_unchanged'] = all(file_digest(ROOT/name) == sha for name, sha in sources.items())
    report['status'] = 'PASS' if report['source_unchanged'] and len(report['cases']) == 3 and all(r['status'] == 'PASS' for r in report['cases']) else 'FAIL'
    write(out/'qualification.json', report)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
