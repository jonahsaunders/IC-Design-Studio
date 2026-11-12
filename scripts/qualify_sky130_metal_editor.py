"""Fresh native DRC/LVS of app-generated straight LI/M1--M4 layouts.

Selected geometry boundaries, regeneration and exchange only. Full device
operating ranges, contacts/arrays, reliability and installed acceptance remain
separate requirements. Original package manifests and source bytes are intact.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device, link_technology
from icstudio.interchange import export_layout
from icstudio.layout_eco import regenerate
from icstudio.layout_import import read_layout
from icstudio.model import clone, example, file_digest, load_project, save_project
from icstudio.physical import connectivity
from icstudio.physical_cells import assign_port, ports
from icstudio.sky130_devices import install
from icstudio.testbenches import native_subcircuit
from scripts.qualification_geometry import same_masks
from scripts.qualify_standard_mos import load_technology, write
from scripts.qualify_standard_mos_layout import technology
from scripts import qualify_sky130_metal_resistor_layouts as physical

SIZES = ((.5, .5), (2, 5), (5, 2), (.505, 2.005), (10, 10), (10, .5))


def editor_layout(physical_tech, model, w, l, folder, magic):
    folder.mkdir()
    tech, identity = load_technology('sky130A')
    p = example('empty'); p['pdk'] = clone(tech); c = p['cells'][0]
    c['name'] = 'coupon'; c['ports'] = ['R1', 'R2']
    key = 'li' if model == 'l1' else model
    d = create_device(tech, 'sky130_fd_pr/res_generic_'+key+'.sym', 'RES')
    d['nets'] = {'m': 'R1', 'p': 'R2'}
    d['model_params'].update(w=2, l=5, mult=1); c['devices'] = [d]
    install(p, c['id'], d['id'])
    pins = {v['pin']: v['id'] for v in c['layout_pins']}
    d['model_params'].update(w=w, l=l); regenerate(p, c['id'], d['id'])
    if pins != {v['pin']: v['id'] for v in c['layout_pins']}:
        raise ValueError('Regeneration lost terminal identities.')
    for pin in c['layout_pins']:
        assign_port(p, c['id'], d['nets'][pin['pin']], pin['layer'], pin['point'])
    if connectivity(p, c['id'])['issues']:
        raise ValueError('Native editor terminal connectivity failed.')
    save_project(p, folder/'editor.icproj'); reopened = load_project(folder/'editor.icproj')
    if reopened['cells'] != p['cells']:
        raise ValueError('Editor save/reopen changed the layout.')
    circuit = native_subcircuit(reopened, reopened['top'])
    (folder/'editor.spice').write_bytes(circuit.encode())
    rows = [line.split() for line in circuit.splitlines() if line.startswith('R_')]
    if (len(rows) != 1 or rows[0][1:4] != ['R1', 'R2', 'sky130_fd_pr__res_generic_'+model]
            or dict(v.split('=', 1) for v in rows[0][4:]) != {'w': f'{w:g}', 'l': f'{l:g}', 'm': '1'}):
        raise ValueError('Editor model/terminal/geometry export differs.')
    export_layout(reopened, folder/'editor.gds')
    # Physical and simulation packages have distinct immutable identities.
    # Transfer only the actual stream masks/labels into the locked physical
    # adapter, never relabel a mixed technology as either original package.
    imported, _ = read_layout(folder/'editor.gds'); same_masks(reopened, imported)
    link_technology(imported, physical_tech); imported['cells'][0]['ports'] = ['R1', 'R2']
    labels = ports(imported, imported['top'])
    if len(labels) != 2 or {v['name'] for v in labels} != {'R1', 'R2'}:
        raise ValueError('The exported stream must contain both actual terminal labels.')
    for label in labels:
        assign_port(imported, imported['top'], label['name'], label['layer'], label['point'])
    same_masks(reopened, imported)
    write(folder/'editor-identity.json', dict(simulation_package=identity,
          package_manifest_sha256=file_digest(Path(tech['package_root'])/'package.json'),
          editor_sha256=file_digest(folder/'editor.icproj'), schematic_sha256=file_digest(folder/'editor.spice'),
          gds_sha256=file_digest(folder/'editor.gds'), model=model, width_um=w, length_um=l,
          terminal_ids_preserved=True, transferred='GDS masks and port labels only'))
    return imported


def execute(tech, model, w, l, out, tools):
    return physical.case(tech, model, w, l, out, tools, generate_layout=editor_layout)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('sky130', 'magic', 'netgen', 'output'):
        ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--models', nargs='+', choices=physical.MODELS, default=list(physical.MODELS))
    ap.add_argument('--pilot', action='store_true')
    ap.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    args = ap.parse_args()
    if len(set(args.models)) != len(args.models): ap.error('Choose distinct models.')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    tech, identity = technology('sky130A', args.sky130)
    tools = {k: str(getattr(args, k).resolve(strict=True)) for k in ('magic', 'netgen')}
    files = [*sorted((ROOT/'icstudio').glob('*.py')), *sorted((ROOT/'scripts').glob('*.py'))]
    before = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in files}
    write(out/'source-files.json', before)
    sizes = [(2, 5)] if args.pilot else SIZES
    selected = [(m, w, l) for m in args.models for w, l in sizes]
    report = dict(schema=1, status='RUNNING', chunk=7, qualified=False, chunk_complete=False,
        geometry_path='native_editor', scope=__doc__, physical_package=identity, platform=platform.platform(),
        selected_cases=[f'{m}-w{w:g}-l{l:g}' for m, w, l in selected],
        full_declared_cases=[f'{m}-w{w:g}-l{l:g}' for m in physical.MODELS for w, l in SIZES],
        source_files_sha256=file_digest(out/'source-files.json'), cases=[],
        tools={key: dict(path=path, sha256=file_digest(path)) for key, path in tools.items()})
    write(out/'qualification.json', report)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(execute, tech, m, w, l, out, tools) for m, w, l in selected]
        for done in as_completed(jobs):
            row = done.result(); report['cases'].append(row); write(out/'qualification.json', report)
            print(row['name'], row['status'], row.get('error', ''), flush=True)
    report['implementation_unchanged'] = before == {p.relative_to(ROOT).as_posix(): file_digest(p) for p in files}
    report['tools_unchanged'] = all(file_digest(path) == report['tools'][key]['sha256'] for key, path in tools.items())
    report['status'] = 'PASS' if (report['implementation_unchanged'] and report['tools_unchanged']
        and len(report['cases']) == len(selected) and all(c['status'] == 'PASS' for c in report['cases'])) else 'FAIL'
    report['cases'].sort(key=lambda c: c['name']); write(out/'qualification.json', report)
    write(out/'manifest.json', {p.relative_to(out).as_posix(): file_digest(p)
        for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'manifest.json'})
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
