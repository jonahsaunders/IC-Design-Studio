"""Native geometry/terminal checks for separately contacted GF180/IHP MOS copies.

Samples include minimum, interior and maximum unit geometry, multiplicities
2/3/16 and all eight orientations. No shared-finger, RC, mismatch or full
operating-envelope qualification is implied by this device-layout batch.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device, link_technology
from icstudio.interchange import export_layout
from icstudio.layout import polygon
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference, run
from icstudio.model import clone, example, file_digest, load_project, save_project
from icstudio.physical_cells import assign_port
from icstudio.process_adapters import ADAPTERS
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import PROFILES, load_technology
from scripts.qualify_standard_mos_layout import fault_detected

TARGETS = ('gf180mcuC', 'gf180mcuD', 'ihp-sg13g2')
FAULTS = ('missing-unit', 'gate-via-open', 'drain-via-open', 'source-via-open',
          'all-body-contacts-open', 'reference-count', 'reference-width', 'reference-gate-body')


def rejected(report, folder):
    if fault_detected(report, folder): return True
    stages = {s['name']: s['status'] for s in report['stages']}
    log = Path(folder)/'lvs/lvs.log'
    return (report['status'] == 'failed' and all(stages.get(n) == 'passed' for n in
            ('preflight', 'layout_export', 'lvs_extraction', 'integrity'))
            and stages.get('lvs') == 'failed' and log.is_file()
            and 'Final result: Top level cell failed pin matching.' in log.read_text(encoding='utf-8'))


def sizes(target):
    w, l = (.15, .13) if target == 'ihp-sg13g2' else (.22, .28)
    return ((w, l, 2), (1, 1, 3), (10, 10, 16))


def selected(target, polarity, size, fault=None):
    width, length, copies = size
    model = ADAPTERS[target].implementation().MODELS['PMOS' if polarity == 'p' else 'NMOS']
    if fault == 'reference-count': copies += 1
    if fault == 'reference-width': width *= 1.2
    pins = 'D B S G' if fault == 'reference-gate-body' else 'D G S B'
    return reference(f'.subckt parallel_coupon D G S B\nX1 {pins} {model} w={width:g}u l={length:g}u m={copies}\n.ends parallel_coupon\n', 'parallel_coupon')


def fixture(technology, target, polarity, size):
    width, length, copies = size
    p = example('empty'); p['pdk'] = clone(technology); c = p['cells'][0]
    c.update(name='parallel_coupon', ports=['D', 'G', 'S', 'B'])
    profile = PROFILES[target]
    d = create_device(p['pdk'], profile['prefix']+profile['symbols'][polarity == 'p']+'.sym', 'M1')
    d['params'].update(w=f'{width:g}u', l=f'{length:g}u')
    d.setdefault('model_params', {})['m'] = str(copies)
    d['nets'] = dict(d='D', g='G', s='S', b='B'); c['devices'] = [d]
    implementation = ADAPTERS[target].implementation()
    implementation.install_mos(p, c['id'], d['id'])
    for pin in c['layout_pins']:
        assign_port(p, c['id'], d['nets'][pin['pin']], pin['layer'], pin['point'])
    return p


def altered(project, target, fault):
    p = clone(project); c = p['cells'][0]
    if fault.startswith('reference-'): return p
    record = c['pdk_layouts'][0]; copies = record['parallel_units']['count']
    if fault == 'missing-unit':
        removed = [s for s in c['shapes'] if s.get('generator_role', '').startswith(f'parallel:{copies-1}:')]
    elif fault.endswith('-via-open'):
        pin = {'gate-via-open': 'g', 'drain-via-open': 'd', 'source-via-open': 's'}[fault]
        removed = [s for s in c['shapes'] if s.get('generator_role') == f'parallel:access:{pin}:{copies-1}:via']
        if len(removed) != 1: raise ValueError('Expected one selected via.')
    elif fault == 'all-body-contacts-open':
        ls = ADAPTERS[target].implementation().layers(p['pdk'])
        px, py = next(v['point'] for v in c['layout_pins'] if v['pin'] == 'b')
        import klayout.db as db
        points = [db.Point(px, py+offset[1]) for offset in record['parallel_units']['offsets_nm']]
        removed = [s for s in c['shapes'] if s['layer'] == ls['contact'] and any(polygon(s).inside(pt) for pt in points)]
        if len(removed) != copies: raise ValueError('Expected one body contact per unit.')
    else: raise ValueError('Unknown physical fault: '+fault)
    if not removed: raise ValueError('The physical fault selected no shapes.')
    c['shapes'] = [s for s in c['shapes'] if s not in removed]
    return p


def audit_native(path, target, polarity, size):
    """Independently check every native unit, without reducing W to aggregate W."""
    width, length, copies = size
    models = {'gf180mcuC': ('nfet_03v3', 'pfet_03v3'), 'gf180mcuD': ('nfet_03v3', 'pfet_03v3'),
              'ihp-sg13g2': ('sg13_lv_nmos', 'sg13_lv_pmos')}
    expected = models[target][polarity == 'p']
    text = Path(path).read_text(encoding='utf-8')
    lines = [line.split() for line in re.sub(r'\n\s*\+', ' ', text).splitlines() if line.strip() and not line.lstrip().startswith('*')]
    if (len(lines) < 3 or lines[0] != ['.subckt', 'parallel_coupon', 'D', 'G', 'S', 'B']
            or lines[-1] not in (['.ends'], ['.ends', 'parallel_coupon'])):
        raise ValueError('Expected exactly one flat four-terminal native circuit.')
    rows = lines[1:-1]
    if len(rows) != copies: raise ValueError('Native physical unit count differs from schematic m.')
    if len({row[0].lower() for row in rows}) != copies: raise ValueError('Duplicate native instance names.')
    def microns(value):
        return Decimal(value[:-1]) if value.endswith('u') else Decimal(value)*Decimal(1000000)
    for fields in rows:
        if (len(fields) < 8 or not fields[0].lower().startswith('x') or fields[5] != expected
                or fields[2] != 'G' or fields[4] != 'B' or set((fields[1], fields[3])) != {'D', 'S'}):
            raise ValueError('Native unit model or four-terminal connectivity differs.')
        params = dict(v.lower().split('=', 1) for v in fields[6:] if '=' in v)
        if (len(params) != len(fields)-6 or not {'w', 'l'} <= params.keys()
                or params.keys() - {'w', 'l', 'm', 'as', 'ad', 'ps', 'pd'}):
            raise ValueError('Ambiguous or unsupported native device parameters.')
        if (microns(params['w']) != Decimal(str(width)) or microns(params['l']) != Decimal(str(length))
                or Decimal(params.get('m', '1')) != 1):
            raise ValueError('Native per-unit W/L or multiplicity differs.')
    return dict(units=len(rows), model=expected, terminals=['D', 'G', 'S', 'B'],
                width_um=width, length_um=length, sha256=file_digest(path))


def execute(target, polarity, size, output, tools, pilot):
    folder = Path(output)/(target+'-'+polarity+'-m'+str(size[2])); folder.mkdir()
    row = dict(target=target, polarity=polarity, size=size, status='RUNNING', layouts=[], faults=[])
    try:
        tech, identity = load_technology(target); row['package'] = identity
        original = fixture(tech, target, polarity, size)
        save_project(original, folder/'original.icproj'); original = load_project(folder/'original.icproj')
        export_layout(original, folder/'original.gds')
        import klayout.db as db
        for rotation, mirror in ([(0, False)] if pilot else [(r, m) for m in (False, True) for r in (0, 90, 180, 270)]):
            tag = str(rotation)+('-mirror' if mirror else '')
            ly = db.Layout(); ly.read(str(folder/'original.gds'))
            ly.top_cell().transform(db.Trans(rotation//90, mirror, 0, 0)); ly.write(str(folder/(tag+'.gds')))
            p, _ = read_layout(folder/(tag+'.gds')); link_technology(p, original['pdk']); p['cells'][0]['ports'] = ['D', 'G', 'S', 'B']
            export_layout(p, folder/(tag+'.oas')); p, _ = read_layout(folder/(tag+'.oas'))
            link_technology(p, original['pdk']); p['cells'][0]['ports'] = ['D', 'G', 'S', 'B']
            export_layout(p, folder/(tag+'-roundtrip.gds'))
            exchange = compare(folder/(tag+'.gds'), folder/(tag+'-roundtrip.gds'), text_presentation=False)
            dest = folder/('valid-'+tag); report = run(p, p['top'], dest, tools, selected(target, polarity, size))
            if report['status'] != 'passed': raise ValueError(report.get('error', 'Native verification failed'))
            native = audit_native(dest/'lvs-extraction/extracted.spice', target, polarity, size)
            row['layouts'].append(dict(rotation=rotation, mirror=mirror, native=native, exchange=exchange,
                                      report_sha256=file_digest(dest/'report.json')))
        for fault in FAULTS:
            dest = folder/fault; report = run(altered(original, target, fault), original['top'], dest, tools, selected(target, polarity, size, fault))
            if not rejected(report, dest): raise ValueError('Native size/connectivity checking did not detect '+fault)
            row['faults'].append(dict(fault=fault, detected=True, report_sha256=file_digest(dest/'report.json')))
        row['status'] = 'PASS'
    except Exception as e:
        row.update(status='FAIL', error=str(e), traceback=traceback.format_exc())
    (folder/'result.json').write_bytes((json.dumps(row, indent=2)+'\n').encode())
    return row


def inverter(target, counts, output, tools):
    folder = Path(output)/(target+'-inverter-'+str(counts[0])+'-'+str(counts[1])); folder.mkdir()
    row = dict(target=target, counts=counts, status='RUNNING')
    try:
        tech, identity = load_technology(target); row['package'] = identity
        p = fixture(tech, target, 'n', (1, 1, counts[0])); c = p['cells'][0]
        q = fixture(tech, target, 'p', (1, 1, counts[1])); d = q['cells'][0]['devices'][0]; d['name'] = 'M2'; c['devices'].append(d)
        c['ports'] = ['A', 'Y', 'VPWR', 'VGND']; c['name'] = 'parallel_inverter'
        for d in c['devices']:
            supply = 'VGND' if d['kind'] == 'NMOS' else 'VPWR'
            d['nets'] = dict(d='Y', g='A', s=supply, b=supply)
        for key in ('shapes', 'layout_pins', 'layout_ports', 'pdk_layouts'): c[key] = []
        ADAPTERS[target].implementation().generate_inverter(p, c['id'])
        save_project(p, folder/'original.icproj'); p = load_project(folder/'original.icproj')
        n, pm = ('sg13_lv_nmos', 'sg13_lv_pmos') if target == 'ihp-sg13g2' else ('nfet_03v3', 'pfet_03v3')
        text = f'.subckt parallel_inverter A Y VPWR VGND\nX1 Y A VGND VGND {n} w=1u l=1u m={counts[0]}\nX2 Y A VPWR VPWR {pm} w=1u l=1u m={counts[1]}\n.ends parallel_inverter\n'
        result = run(p, p['top'], folder/'valid', tools, reference(text, 'parallel_inverter'))
        if result['status'] != 'passed': raise ValueError(result.get('error', 'Native inverter verification failed'))
        extracted = folder/'valid/lvs-extraction/extracted.spice'
        lines = re.sub(r'\n\s*\+', ' ', extracted.read_text(encoding='utf-8')).splitlines()
        units = [line.split() for line in lines if re.match(r'^\s*X\S+\s', line)]
        if len(units) != sum(counts): raise ValueError('Inverter physical unit count differs.')
        observed = {n: 0, pm: 0}
        for unit in units:
            model = unit[5]; supply = 'VGND' if model == n else 'VPWR'
            if model not in observed or unit[2] != 'A' or unit[4] != supply or set((unit[1], unit[3])) != {'Y', supply}:
                raise ValueError('Inverter native unit terminals differ.')
            params = dict(item.split('=') for item in unit[6:])
            if params['w'] != '1u' or params['l'] != '1u' or params.get('m', '1') != '1':
                raise ValueError('Inverter native unit size differs.')
            observed[model] += 1
        if observed != {n: counts[0], pm: counts[1]}: raise ValueError('Inverter polarity counts differ.')
        wrong = text.replace(f'{n} w=1u l=1u m={counts[0]}', f'{n} w=1u l=1u m={counts[0]+1}')
        result = run(p, p['top'], folder/'wrong-count', tools, reference(wrong, 'parallel_inverter'))
        if not rejected(result, folder/'wrong-count'): raise ValueError('Inverter count fault was not detected.')
        row.update(status='PASS', native_units=observed, native_sha256=file_digest(extracted),
                   report_sha256=file_digest(folder/'valid/report.json'), fault_detected=True,
                   fault_report_sha256=file_digest(folder/'wrong-count/report.json'))
    except Exception as e:
        row.update(status='FAIL', error=str(e), traceback=traceback.format_exc())
    (folder/'result.json').write_bytes((json.dumps(row, indent=2)+'\n').encode())
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'magic', 'netgen'): ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--pilot', action='store_true'); ap.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    a = ap.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), ROOT/'scripts/qualify_standard_mos.py', ROOT/'scripts/qualify_standard_mos_layout.py', *sorted((ROOT/'icstudio').rglob('*.py'))]
    hashes = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in files}
    (out/'source-files.json').write_bytes((json.dumps(hashes, indent=2)+'\n').encode())
    result = dict(status='RUNNING', chunk=7, chunk_complete=False, qualified=False, scope=__doc__, pilot=a.pilot,
                  source_files_sha256=file_digest(out/'source-files.json'), cases=[], inverters=[])
    tools = {n: str(getattr(a, n).resolve(strict=True)) for n in ('magic', 'netgen')}
    result['engines'] = {n: dict(path=p, sha256=file_digest(p)) for n, p in tools.items()}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs = [pool.submit(execute, t, p, s, out, tools, a.pilot) for t in TARGETS for p in ('n', 'p') for s in (sizes(t)[:1] if a.pilot else sizes(t))]
        for job in as_completed(jobs):
            row = job.result(); result['cases'].append(row); print(row['target'], row['polarity'], row['size'], row['status'], row.get('error', ''), flush=True)
            (out/'record.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
        contexts = [pool.submit(inverter, t, counts, out, tools) for t in TARGETS for counts in
                    (((3, 1),) if a.pilot else ((1, 1), (1, 3), (3, 1), (16, 16)))]
        for job in as_completed(contexts):
            row = job.result(); result['inverters'].append(row)
            print(row['target'], 'inverter', row['counts'], row['status'], row.get('error', ''), flush=True)
            (out/'record.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
    result['source_unchanged'] = hashes == {p.relative_to(ROOT).as_posix(): file_digest(p) for p in files}
    result['status'] = 'PASS' if (result['source_unchanged'] and len(result['cases']) == len(jobs)
        and len(result['inverters']) == len(contexts) and all(c['status'] == 'PASS' for c in result['cases']+result['inverters'])) else 'FAIL'
    (out/'record.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
    return int(result['status'] != 'PASS')


if __name__ == '__main__': raise SystemExit(main())
