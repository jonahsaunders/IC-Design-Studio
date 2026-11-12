"""Run selected IHP CMIM enclosure cases on complete imported devices.

MIM.c uses the original Vmim contacts; MIM.d uses an explicit TopVia1 cut.
This finite source workflow is not installed, electrical or family acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import clone, digest, file_digest, load_project, save_project
from icstudio.layout import rect
from icstudio.physical_cells import assign_port
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_ihp_mim_layout import generate, regions, rotate
from scripts.qualify_ihp_cmim_reference import catalog_project, physical
from scripts.check_ihp_cmim_enclosures import audit_case, audit_fault, safe_path

CONTRACT = ROOT / 'docs/qualification/ihp-cmim-enclosures-v1.json'
CONTRACT_SHA256 = '8f82d1ba570a7e831a55e751700b04d9f3e35a0bc007acdf7639c223dfda501b'
CASES = (('MIM.c', (580, 600, 620)), ('MIM.d', (340, 360, 380)))
FAULTS = ('missing-vmim', 'missing-topvia', 'wrong-contact-layer', 'cross-plate-short',
          'wrong-reference-width', 'swapped-electrodes')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def source_identity():
    require(file_digest(CONTRACT) == CONTRACT_SHA256, 'Changed enclosure source contract.')
    contract = json.loads(CONTRACT.read_bytes())
    files = dict(contract['source_sha256'])
    files.update({p.relative_to(ROOT).as_posix(): file_digest(p) for p in (ROOT / 'icstudio').glob('*.py')})
    for name in ('qualify_ihp_cmim_enclosures.py', 'check_ihp_cmim_enclosures.py', 'qualify_ihp_cmim_reference.py',
                 'qualify_ihp_mim_layout.py', 'qualify_standard_mos.py', 'ihp_cmim_boundary_audit.py'):
        path = ROOT / 'scripts' / name
        files[path.relative_to(ROOT).as_posix()] = file_digest(path)
    for name, expected in files.items():
        parts = Path(name).parts
        require('tmpuxoell2b' not in parts and '..' not in parts and not Path(name).is_absolute(), 'Invalid source path.')
        require(file_digest(ROOT / name) == expected, 'Changed source: ' + name)
    return files


def source_locked_contract():
    files = source_identity()
    require(all(files[name] == expected for name, expected in json.loads(CONTRACT.read_bytes())['source_sha256'].items()),
            'An enclosure rule source differs from the reviewed contract.')
    return files


def build_case(original, kind, margin):
    require((kind, margin) in {(rule, value) for rule, values in CASES for value in values}, 'Unknown enclosure selection.')
    q = clone(original); cell = q['cells'][0]
    layers = {(v['gds'], v['datatype']): v['name'] for v in q['pdk']['layers']}
    if kind == 'MIM.c':
        plate = [s for s in cell['shapes'] if s['layer'] == layers[(67, 0)]]
        require(len(plate) == 1 and any(x == 4100 for x, _ in plate[0]['points']), 'Unexpected original Metal5 plate.')
        plate[0]['points'] = [[3500 + margin if x == 4100 else x, y] for x, y in plate[0]['points']]
    else:
        cell['shapes'] = [s for s in cell['shapes'] if s['layer'] != layers[(129, 0)]]
        top = [s for s in cell['shapes'] if s['layer'] == layers[(126, 0)]]
        require(len(top) == 1 and any(x == 3300 for x, _ in top[0]['points']), 'Unexpected original TopMetal1 plate.')
        top[0]['points'] = [[3580 if x == 3300 else x, y] for x, y in top[0]['points']]
        cell['shapes'].append(rect(layers[(125, 0)], 3500 - margin - 420, -210, 420, 420))
    return q


def build_fault(original, name):
    require(name in FAULTS, 'Unknown contact control.')
    q = build_case(original, 'MIM.c', 600) if name == 'missing-vmim' else build_case(original, 'MIM.d', 360)
    cell = q['cells'][0]; layers = {(v['gds'], v['datatype']): v['name'] for v in q['pdk']['layers']}
    if name == 'missing-vmim':
        cell['shapes'] = [s for s in cell['shapes'] if s['layer'] != layers[(129, 0)]]
    if name in ('missing-topvia', 'wrong-contact-layer'):
        cell['shapes'] = [s for s in cell['shapes'] if s['layer'] != layers[(125, 0)]]
        if name == 'wrong-contact-layer':
            cell['shapes'].append(rect(layers[(66, 0)], 2720, -210, 420, 420))
    if name == 'cross-plate-short':
        cell['shapes'] += [rect(layers[(126, 0)], 3100, -820, 1000, 1640), rect(layers[(125, 0)], 3590, -210, 420, 420)]
    if name == 'swapped-electrodes':
        assign_port(q, cell['id'], 'C1', layers[(67, 0)], [3600, 0])
        assign_port(q, cell['id'], 'C2', layers[(126, 0)], [0, 0])
    return q


def validate_case(observed, rule, below):
    stages = observed['stages']; decks = observed['three_decks']
    require([d['name'] for d in decks] == ['main', 'maximal', 'metal-spacing'], 'Missing or reordered DRC checks.')
    require(all(type(d['violations']) is int and d['violations'] >= 0 and isinstance(d['categories'], list) for d in decks),
            'Malformed native finding counts.')
    require(all(stages[k] == 'passed' for k in ('preflight', 'layout_export', 'lvs_extraction', 'lvs', 'integrity')),
            'Enclosure device did not complete extraction and strict LVS.')
    actual = [sorted(x.strip("'\"") for x in d['categories']) for d in decks]
    counts = [d['violations'] for d in decks]
    require(actual == ([[rule], [], []] if below else [[], [], []]) and counts == ([1, 0, 0] if below else [0, 0, 0]),
            'Unexpected native enclosure findings.')
    require(stages['drc'] == ('failed' if below else 'passed'), 'Unexpected DRC stage.')


def validate_fault(name, observed, folder):
    stages = observed['stages']; flow = Path(folder) / 'job/physical-flow'; decks = observed['three_decks']
    require([d['name'] for d in decks] == ['main', 'maximal', 'metal-spacing'], 'Missing fault DRC checks.')
    require(all(type(d['violations']) is int and d['violations'] >= 0 and isinstance(d['categories'], list) for d in decks),
            'Malformed fault finding counts.')
    require(stages['preflight'] == stages['layout_export'] == 'passed', 'Fault did not reach native verification.')
    native = safe_path(flow / 'lvs-extraction/native.cir').read_text(encoding='utf-8')
    console = safe_path(flow / 'lvs-extraction/console.log').read_text(encoding='utf-8')
    for marker in ('NET_ONLY enabled', 'LVS Total Run time', '[layout_netlist] simplify: SKIPPED',
                   '[layout_netlist] combine_devices: SKIPPED', '[layout_netlist] purge: SKIPPED',
                   '[layout_netlist] purge_nets: SKIPPED', '[layout_netlist] purge_devices: SKIPPED'):
        require(marker in console, 'Fault extraction did not complete unfiltered.')
    lines = [line.split() for line in native.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(lines) == 3 and lines[0][:2] == ['.SUBCKT', 'coupon'] and lines[-1] == ['.ENDS', 'coupon'], 'Unexpected fault netlist.')
    unit = lines[1]
    require(len(unit) == 9 and unit[0].startswith('C') and unit[3:] == ['cap_cmim', 'w=7u', 'l=7u', 'A=49p', 'P=28u', 'm=1'],
            'Fault altered raw model or geometry.')
    rules = [sorted(x.strip("'\"") for x in d['categories']) for d in decks]
    counts = [d['violations'] for d in decks]
    if name in ('missing-vmim', 'missing-topvia', 'wrong-contact-layer', 'cross-plate-short'):
        require(stages['drc'] == stages['lvs_extraction'] == 'failed' and stages['lvs'] == stages['integrity'] == 'not_run' and
                observed.get('error') == 'IHP extracted port names differ from the schematic.', 'Expected application port guard did not fire.')
        if name == 'cross-plate-short':
            require(lines[0][2:] == ['C1|C2'] and unit[1:3] == ['C1|C2', 'C1|C2'] and rules == [['TV1.c', 'TV1.d'], [], []] and counts == [2, 0, 0], 'Short topology/findings differ.')
        else:
            main = ['V4.a'] if name == 'wrong-contact-layer' else []
            require(lines[0][2:] == ['C2'] and re.fullmatch(r'\\?\$\d+', unit[1]) and unit[2] == 'C2' and
                    rules == [main, ['MIM.h'], []] and counts == ([2, 1, 0] if main else [0, 1, 0]), 'Missing-contact topology/findings differ.')
    else:
        require(stages['drc'] == stages['lvs_extraction'] == stages['integrity'] == 'passed' and stages['lvs'] == 'failed' and
                rules == [[], [], []] and counts == [0, 0, 0], 'Expected strict LVS fault did not complete.')
        log = safe_path(flow / 'lvs/lvs.log').read_text(encoding='utf-8')
        if name == 'wrong-reference-width':
            require(unit[1:3] == ['C1', 'C2'] and 'Property errors were found.' in log and '5.04e-11' in log and '4.9e-11' in log,
                    'Width property mismatch not observed.')
        else:
            require(unit[1:3] == ['C2', 'C1'] and 'Final result: Top level cell failed pin matching.' in log,
                    'Swapped electrode mismatch not observed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true', help='Run only the legal TopVia1 360 nm case; never full selection.')
    for name in ('magic', 'netgen', 'klayout'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(); supplied = args.output.absolute()
    require('tmpuxoell2b' not in supplied.parts, 'Forbidden output path.')
    for parent in (*reversed(supplied.parents), supplied):
        require(not parent.is_symlink() and not parent.is_junction(), 'Linked output ancestor.')
    out = supplied.resolve(); require('tmpuxoell2b' not in out.parts and not out.is_relative_to(ROOT), 'Output must be outside source tree.')
    tools = {}
    for name in ('magic', 'netgen', 'klayout'):
        supplied_tool = getattr(args, name).absolute()
        require('tmpuxoell2b' not in supplied_tool.parts, 'Forbidden tool path.')
        for parent in (*reversed(supplied_tool.parents), supplied_tool):
            require(not parent.is_symlink() and not parent.is_junction(), 'Linked tool path.')
        resolved_tool = supplied_tool.resolve(strict=True)
        require('tmpuxoell2b' not in resolved_tool.parts, 'Forbidden resolved tool path.')
        tools[name] = str(resolved_tool)
    tool_hashes = {name: file_digest(path) for name, path in tools.items()}
    source = source_locked_contract(); out.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, status='RUNNING', pilot=args.pilot, qualified=False, installed_acceptance=False,
                  chunk_complete=False, scope=__doc__, source_contract_sha256=CONTRACT_SHA256,
                  source_files=source, tool_sha256=tool_hashes,
                  runtime_scope='Selected launcher bytes only; not a complete runtime identity.', cases=[], faults=[])
    write(out / 'report.json', report)
    try:
        tech, report['package'] = load_technology('ihp-sg13g2')
        original = generate(tech, 7, 7, out / 'generator', tools['magic'])
        def run_case(q, folder, wrong=False):
            layout = out / (folder.name + '-layout.icproj'); save_project(q, layout)
            reopened = load_project(layout); require(digest(q) == digest(reopened), 'Save/reopen changed layout.')
            project, _ = catalog_project(layout, tech, 7, 7)
            if wrong:
                project['cells'][0]['devices'][0]['model_params']['w'] = '7.2e-6'
            observed, _, _ = physical(project, folder, tools, 7, 7, audit_order=False)
            native = json.loads((folder / 'job/physical-flow/drc/result.json').read_bytes())
            require(type(native.get('schema')) is int and native['schema'] == 2, 'Expected fresh three-check DRC schema.')
            observed['three_decks'] = [dict(name=d['name'], violations=d['violations'], categories=d['categories'],
                                            report_sha256=d['report_sha256']) for d in native['decks']]
            return observed
        cases = (('MIM.d', (360,)),) if args.pilot else CASES
        for kind, margins in cases:
            for margin in margins:
                for angle in ((0,) if args.pilot else (0, 90)):
                    q = build_case(original, kind, margin); q = q if angle == 0 else rotate(q)
                    folder = out / f'{kind}-{margin}-{angle}'
                    observed = run_case(q, folder)
                    validate_case(observed, kind, not args.pilot and margin == margins[0])
                    independently_read = audit_case(folder, kind, margin, angle)
                    report['cases'].append(dict(rule=kind, margin_nm=margin, rotation=angle,
                                                independent_readback=independently_read, observed=observed))
                    write(out / 'report.json', report)
        if not args.pilot:
            for name in FAULTS:
                q = build_fault(original, name); folder = out / ('fault-' + name)
                observed = run_case(q, folder, wrong=name == 'wrong-reference-width')
                validate_fault(name, observed, folder)
                independently_read = audit_fault(folder, name)
                report['faults'].append(dict(fault=name, independent_readback=independently_read, observed=observed))
                write(out / 'report.json', report)
        require(source_locked_contract() == source and all(file_digest(tools[n]) == h for n, h in tool_hashes.items()),
                'Source or selected tool changed during execution.')
        report['status'] = 'OBSERVED_PILOT' if args.pilot else 'OBSERVED_FULL_SELECTION'
    except Exception as exc:
        report.update(status='FAIL', error=repr(exc), traceback=traceback.format_exc())
    write(out / 'report.json', report)
    print(json.dumps(dict(status=report['status'], cases=len(report['cases']), faults=len(report['faults']))))
    return int(report['status'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
