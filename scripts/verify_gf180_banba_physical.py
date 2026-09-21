"""Run pinned GF180 B DRC/LVS, checked C extraction, and post-C PVT benches.

Distributed RC is attempted and must satisfy the existing conservation validator.
Density and RC failures remain failures: this script never issues signoff or
changes the input layout to satisfy a report. Use a new output directory.
Use --drc-lvs-only to run all three DRC decks and strict LVS without requiring
Magic, ngspice or open_pdks. A successful check is not fabrication signoff.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import clone, file_digest, load_project, scalar
from icstudio.engines import run_deck, tcl_word
from icstudio.klayout_lvs import read_database
from icstudio.pdks import stage_model_deck
from icstudio.testbenches import create, deck, native_subcircuit
from scripts.verify_gf180_banba_pass2 import cell, transient_metrics

PV_COMMIT = '05e7b6adf19edf942969c1c9625f02fd87874f06'
OPEN_PDKS_COMMIT = 'aa3fc215a80d32437b8cca1cb3fdee819d18c4c9'
EXAMPLE = ROOT / 'examples/gf180-banba/layout'
MODELS = {'nfet_03v3': 4, 'pfet_03v3': 4, 'pnp_05p00x05p00': 3,
          'ppolyf_u_1k': 3, 'cap_mim_2f0_m3m4_noshield': 2}


def devices(text):
    """Read only the explicitly supported resolved model calls; fail closed."""
    result = []
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith(('*', '.')):
            continue
        if fields[0][0].upper() == 'C':
            if len(fields) != 4 or not math.isfinite(scalar(fields[3])) or scalar(fields[3]) < 0:
                raise ValueError('Malformed extracted capacitance.')
            continue
        if not fields[0].upper().startswith('X'):
            raise ValueError('Unexpected device in resolved reference: ' + line)
        matches = [(i, value) for i, value in enumerate(fields) if value in MODELS]
        if len(matches) != 1:
            raise ValueError('Unsupported or missing device model: ' + line)
        i, model = matches[0]
        if i != MODELS[model] + 1:
            raise ValueError('Incorrect terminal count: ' + line)
        params = {}
        for field in fields[i+1:]:
            key, value = field.split('=')
            if key in params:
                raise ValueError('Duplicate device parameter.')
            params[key] = scalar(value)
        if any(not math.isfinite(v) for v in params.values()):
            raise ValueError('Nonfinite device parameter.')
        if any(params.get(key, 1) != 1 for key in ('m', 'nf')):
            raise ValueError('Resolve device multiplicity before physical comparison.')
        result.append((fields[0], model, fields[1:i], params))
    if not result:
        raise ValueError('No physical devices found.')
    return result


def cdl(text):
    """Translate model subcircuits to the upstream deck's primitive CDL reader."""
    header = next(line for line in text.splitlines() if line.lower().startswith('.subckt '))
    lines = ['* Resolved schematic; independent of physical extraction', header]
    for name, model, nets, p in devices(text):
        if model.startswith(('nfet', 'pfet')):
            kind, dimensions = 'M', f"w={p['w']:.12g} l={p['l']:.12g}"
        elif model.startswith('pnp'):
            kind, dimensions = 'Q', ''
        elif model.startswith('ppoly'):
            kind, dimensions = 'R', f"w={p['r_width']:.12g} l={p['r_length']:.12g}"
        else:
            kind, dimensions = 'C', f"w={p['c_width']:.12g} l={p['c_length']:.12g}"
        lines.append(' '.join([kind + name[1:], *nets, model, dimensions]).rstrip())
    return '\n'.join(lines + ['.ends ' + header.split()[1], ''])


def check_extracted(reference, extracted):
    """Named-net/device/dimension bijection before allowing extracted simulation.

    MOS source/drain and resistor end terminals are interchangeable. MOS junction
    geometry is intentionally extracted, not forced to schematic defaults.
    """
    def signatures(text):
        rows = []
        for _, model, terminals, p in devices(text):
            nets = [n.casefold() for n in terminals]
            if model.startswith(('nfet', 'pfet')):
                nets = [*sorted([nets[0], nets[2]]), nets[1], nets[3]]
                sizes = [p['w'], p['l']]
            elif model.startswith('ppoly'):
                nets = [*sorted(nets[:2]), nets[2]]
                sizes = [p['r_width'], p['r_length']]
            elif model.startswith('cap'):
                sizes = sorted([p['c_width'], p['c_length']])
            else:
                sizes = []
            # The physical grid is 5 nm; retain dimensions to 0.001 nm.
            rows.append((model, tuple(nets), tuple(round(v * 1e12) for v in sizes)))
        return Counter(rows)
    if signatures(reference) != signatures(extracted):
        raise ValueError('Extracted device, terminal or dimension mismatch.')
    ports = lambda text: next(line.split()[2:] for line in text.splitlines()
                             if line.lower().startswith('.subckt '))
    if Counter(ports(reference)) != Counter(ports(extracted)):
        raise ValueError('Extracted ports differ from the schematic.')
    caps = [line.split() for line in extracted.splitlines() if line.startswith('C')]
    return dict(status='passed', devices=len(devices(extracted)), capacitances=len(caps),
                total_capacitance_f=sum(scalar(row[3]) for row in caps), ports=ports(extracted))


def fix_pnp_technology(text):
    """Use emitter area for PNP selection while retaining C/B/E model pin order.

    Upstream incorrectly treats the emitter as substrate, then tests absent a2.
    MSUBCKT emits terminal2/base/terminal1: declare emitter, collector explicitly.
    Retain all four bounded model choices; do not hard-code the expected model.
    """
    pattern = (r'(device msubcircuit pnp_\S+ pnp) pwell,space/w \*pdiff error '
               r'a2>([\d.]+) a2<([\d.]+)')
    fixed, count = re.subn(pattern, r'\1 *pdiff pwell,space/w a1>\2 a1<\3', text)
    if count != 4:
        raise ValueError('Pinned PNP technology declarations changed.')
    return fixed


def command(args, folder, name, env=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (name + '.command.json')).write_text(json.dumps(list(map(str, args)), indent=2)+'\n')
    with (folder / (name + '.log')).open('w') as log:
        run = subprocess.run(list(map(str, args)), cwd=folder, env=env,
                             stdout=log, stderr=subprocess.STDOUT, timeout=900)
    return run.returncode


def locked_checkout(path, expected):
    revision = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(path), 'diff', 'HEAD', '--'], text=True)
    if revision != expected or dirty:
        raise ValueError('Use the clean pinned upstream checkout: ' + str(path))


def drc_results(directory, stem, exit_code):
    """Require complete reports and successful execution, not just no markers."""
    reports = {}
    for deck in ('main', 'density', 'antenna'):
        path = directory / f'{stem}_{deck}.lyrdb'
        if not path.is_file():
            raise ValueError('Incomplete DRC/antenna/density output: missing ' + path.name)
        root = ET.parse(path).getroot()
        if root.tag != 'report-database' or root.find('items') is None or root.find('categories') is None:
            raise ValueError('Malformed DRC report: ' + path.name)
        counts = Counter()
        for item in root.findall('./items/item'):
            category = (item.findtext('category') or '').strip("'")
            if not category:
                raise ValueError('DRC marker has no category: ' + path.name)
            counts[category] += 1
        reports[path.name] = dict(items=sum(counts.values()), rules=dict(counts))
    return dict(exit_code=exit_code, passed=exit_code == 0 and not any(
        row['items'] for row in reports.values()), reports=reports)


def drc_remaining(result):
    rules = sorted({rule for data in result['reports'].values() for rule in data['rules']})
    remaining = ['DRC closure: ' + ', '.join(rules) + '.'] if rules else []
    if result['exit_code'] and not rules:
        remaining.append('DRC engine failed despite empty reports; inspect drc.log.')
    return remaining


def magic_script(p, technology, gds):
    lines = ['drc off', 'tech load '+tcl_word(technology), 'scalegrid 1 10',
             'gds read '+tcl_word(gds), 'load banba_layout', 'select top cell']
    physical = cell(p, 'banba_layout')
    by_id = {device['id']: device for device in physical['devices']}
    seen = set(physical['ports'])
    for pin in physical['layout_pins']:
        net = by_id[pin['device_id']]['nets'][pin['pin']].replace('/', '_')
        if net in seen:
            continue
        seen.add(net)
        x, y = [v/1000 for v in pin['point']]
        lines += [f'box values {x}um {y}um {x}um {y}um',
                  f'label {tcl_word(net)} center {pin["layer"].removeprefix("banba_")}']
    return '\n'.join(lines)+'\n'


def simulate(p, extracted, executable, output, ports):
    summary = dict(scope='C-only extraction, measured MOS junction geometry; no distributed wire R.',
                   load_f=5e-12, pvt=[], nominal={})

    def run(corner, temperature, supply, ramp=None, label='nominal'):
        q = clone(p); q['parameters']['vdd'] = str(supply)
        # The diagnostic replaces a DC source with the requested supply ramp.
        bench = create(q, cell(q, 'tb_dc')['id'])
        settings = dict(q['analysis'], type='op', corner=corner, temperature=temperature)
        if ramp:
            slow = ramp == '1m'
            settings.update(type='tran', step='500n' if slow else '100n', stop='2m' if slow else '500u')
            settings['diagnostic'] = dict(kind='startup', source='VDD', output='VREF', initial_node='VREF',
                initial_voltage='0', ramp=ramp, supply=str(supply), supply_from_source=False, stop=settings['stop'],
                minimum='.57', maximum='.63', tail_fraction='.2')
        bench.update(analysis=settings, probes=['VREF'],
                     measurements=[dict(name='supply', kind='current', source='VDD')])
        folder = output / label / ('op' if ramp is None else 'ramp-'+ramp)
        folder.mkdir(parents=True)
        text = stage_model_deck(q['pdk'], deck(q, bench, extracted, ports=ports), folder)
        (folder/'input.cir').write_text(text)
        run_settings = dict(deck=str(folder/'input.cir'), analysis=settings)
        retry_reason = None
        try:
            r = run_deck(q, bench['bench_cell'], run_settings, str(executable), folder)
        except ValueError as error:
            # Retain an incomplete raw file. Retry the identical deck once;
            # never repair headers, loosen tolerances, or accept partial traces.
            if not str(error).startswith(('Unsupported raw-file dimensions', 'Incomplete or malformed raw-file')):
                raise
            retry_reason = str(error)
            retry = folder/'retry'; retry.mkdir()
            (retry/'reason.txt').write_text(retry_reason+'\n')
            r = run_deck(q, bench['bench_cell'], run_settings, str(executable), retry)
        if ramp and (not r['x'] or not math.isclose(r['x'][-1], scalar(settings['stop']), rel_tol=1e-9)):
            raise ValueError('Transient did not reach its requested stop time.')
        if not ramp:
            return dict(vref=r['traces']['vref'][-1], supply_current=-r['currents']['vdd'][-1], retry_reason=retry_reason)
        m = transient_metrics(r, tolerance=.03)
        limit = .00125 if ramp == '1m' else .00025
        m.update(ramp=ramp, settling_limit_seconds=limit, retry_reason=retry_reason)
        m['passed'] = (.57 <= m['final_vref'] <= .63 and m['peak_vref'] <= .75 and
            m['settling_seconds'] is not None and m['settling_seconds'] <= limit and
            m['tail_peak_to_peak'] < .0006)
        return m

    summary['nominal'] = run('nominal', 27, 3.3)
    def case(values):
        corner, temperature, supply = values
        label = f'{corner}-{temperature}-{supply}'
        row = dict(corner=corner, temperature=temperature, supply=supply,
                   **run(corner, temperature, supply, label=label))
        row['ramps'] = [run(corner, temperature, supply, ramp, label) for ramp in ['100n', '10u', '1m']]
        row['passed'] = (.57 <= row['vref'] <= .63 and 0 <= row['supply_current'] <= 70e-6
                         and all(r['passed'] for r in row['ramps']))
        return row

    cases = [(corner, temperature, supply) for corner in ['nominal', 'ff', 'ss', 'fs', 'sf']
             for temperature in [-40, 125] for supply in [2.7, 3.6]]
    # Each worker owns a project copy and separate model/deck/output directories.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(case, cases):
            summary['pvt'].append(row)
            print(row['corner'], row['temperature'], row['supply'],
                  'PASS' if row['passed'] else 'FAIL', flush=True)
            (output/'simulation.json').write_text(json.dumps(summary, indent=2)+'\n')
    summary['passed'] = all(row['passed'] for row in summary['pvt'])
    (output/'simulation.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def verify(a):
    output = a.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Choose an empty output directory.')
    locked_checkout(a.pv, PV_COMMIT)
    if not a.drc_lvs_only:
        locked_checkout(a.open_pdks, OPEN_PDKS_COMMIT)
    p = load_project(EXAMPLE/'banba-layout.icproj')
    reference = native_subcircuit(p, cell(p, 'banba_layout')['id'])
    (output/'schematic.spice').write_text(reference)
    (output/'schematic.cdl').write_text(cdl(reference))
    env = dict(os.environ, PATH=str(a.klayout.parent)+os.pathsep+os.environ['PATH'])
    gds = EXAMPLE/'banba-layout.gds'
    report = dict(schema=1, project_sha256=file_digest(EXAMPLE/'banba-layout.icproj'),
        gds_sha256=file_digest(gds), variant='B: 4LM, MIM B 2fF, top metal 11K',
        pv_commit=PV_COMMIT, signoff=False, passed=False,
        scope='drc-lvs' if a.drc_lvs_only else 'drc-lvs-extraction-simulation')
    if not a.drc_lvs_only:
        report['open_pdks_commit'] = OPEN_PDKS_COMMIT
    report['tools'] = {}
    engines = [('klayout', a.klayout, ['-b', '-v'])]
    if not a.drc_lvs_only:
        engines += [('magic', a.magic, ['--version']), ('ngspice', a.ngspice, ['--version'])]
    for name, executable, args in engines:
        if command([executable, *args], output, name+'-version'):
            raise ValueError(name + ' version probe failed; inspect its log.')
        report['tools'][name] = dict(launcher_sha256=file_digest(executable),
                                     version_log=(output/(name+'-version.log')).read_text())
    rc = command([sys.executable, a.pv/'klayout/drc/run_drc.py', '--path='+str(gds), '--variant=B',
        '--topcell=banba_layout', '--run_dir='+str(output/'drc'), '--thr=2', '--density', '--antenna'], output, 'drc', env)
    report['drc'] = drc_results(output/'drc', gds.stem, rc)
    report['remaining'] = drc_remaining(report['drc']) + ['Strict LVS has not completed.']
    (output/'physical-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    rc = command([sys.executable, a.pv/'klayout/lvs/run_lvs.py', '--layout='+str(gds),
        '--netlist='+str(output/'schematic.cdl'), '--variant=B', '--topcell=banba_layout',
        '--run_dir='+str(output/'lvs'), '--lvs_sub=VSS', '--run_mode=flat', '--thr=2',
        '--net_only', '--top_lvl_pins'], output, 'lvs', env)
    comparison = read_database(output/'lvs/banba-layout.lvsdb')
    counts = Counter(row['kind'] for row in comparison['rows'])
    passed = (rc == 0 and comparison['matched'] and all(row['status'] == 'Match' for row in comparison['rows'])
              and counts['device'] == len(devices(reference)))
    report['lvs'] = dict(exit_code=rc, passed=passed, pairs=dict(counts), circuits=comparison['circuits'])
    report['remaining'] = drc_remaining(report['drc']) + ([] if passed else ['Strict LVS failed.'])
    if a.drc_lvs_only:
        report['passed'] = report['drc']['passed'] and passed
        (output/'physical-verification.json').write_text(json.dumps(report, indent=2)+'\n')
        return report
    (output/'physical-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    if not passed:
        raise ValueError('Strict LVS failed; extracted simulation refused.')
    technology = output/'gf180mcuB.tech'
    rc = command([sys.executable, a.open_pdks/'common/preproc.py', a.open_pdks/'gf180mcu/magic/gf180mcu.tech',
        technology, '-DTECHNAME=gf180mcuB', '-DREVISION='+OPEN_PDKS_COMMIT, '-DMETALS4', '-DMIM',
        '-DTHICKMET1P1', '-DHRPOLY1K', '-DMAGIC_CURRENT=8.3'], output, 'technology')
    if rc:
        raise ValueError('Technology preprocessing failed.')
    technology.write_text(fix_pnp_technology(technology.read_text()))
    report['technology_sha256'] = file_digest(technology)
    prefix = magic_script(p, technology, gds)
    folder = output/'extraction'; folder.mkdir()
    script = prefix + ('extract do local\nextract all\next2spice lvs\next2spice merge none\n'
        'ext2spice cthresh 0\next2spice -o extracted-c.spice\nsave banba_layout\nquit -noprompt\n')
    (folder/'capacitance.tcl').write_text(script)
    rc = command([a.magic, '-dnull', '-noconsole', 'capacitance.tcl'], folder, 'capacitance')
    log = (folder/'capacitance.log').read_text()
    # Magic's GDS undo notice does not describe geometry or extraction failure.
    log = log.replace("Warning: Calma reading is not undoable!  I hope that's OK.", '')
    if rc or re.search(r"error|warning|do not match|missing|couldn't load|unknown command", log, re.I):
        raise ValueError('Capacitance extraction raised an error or warning; inspect its log.')
    report['capacitance'] = check_extracted(reference, (folder/'extracted-c.spice').read_text())
    report['capacitance']['sha256'] = file_digest(folder/'extracted-c.spice')
    (output/'physical-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    # Isolate ext2sim from extresist: retained process state otherwise crashes on PNPs.
    (folder/'prepare-rc.tcl').write_text(prefix+'ext2sim labels on\next2sim\nquit -noprompt\n')
    (folder/'resistance.tcl').write_text(prefix+'extresist simplify off\nextresist all\nquit -noprompt\n')
    try:
        for phase in ['prepare-rc', 'resistance']:
            phase_code = command([a.magic, '-dnull', '-noconsole', phase+'.tcl'], folder, phase)
            if phase_code:
                raise ValueError(f'Magic failed during {phase} (exit {phase_code}).')
        from icstudio.magic_rc import normalize
        normalize(folder, 'banba_layout')
        # No RC qualification until terminal preservation and C finalization run.
        report['rc'] = dict(status='unqualified', reason='Normalization completed; RC electrical and terminal checks still required.')
    except (ValueError, RuntimeError) as error:
        report['rc'] = dict(status='blocked', reason=str(error))
    resistance_log = folder/'resistance.log'
    report['rc']['diagnostics'] = [line for line in (resistance_log.read_text() if resistance_log.exists() else '').splitlines()
                                    if re.search(r'warning|missing|error|Nets extracted|Nets output', line, re.I)
                                    and 'Calma reading is not undoable' not in line]
    (output/'physical-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    report['simulation'] = simulate(p, folder/'extracted-c.spice', a.ngspice,
                                     output/'simulation', report['capacitance']['ports'])
    report['remaining'] = drc_remaining(report['drc']) + [
        'Complete, terminal-verified distributed RC extraction and post-RC electrical qualification.']
    if not report['simulation']['passed']:
        report['remaining'].append('Failed C-only electrical requirements; inspect simulation rows.')
    (output/'physical-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drc-lvs-only', action='store_true',
                        help='Run geometry, density, antenna and strict LVS; no extraction or simulation.')
    for name in ['pv', 'klayout', 'out']:
        parser.add_argument('--'+name, type=lambda s: Path(s).resolve(), required=True)
    for name in ['open-pdks', 'magic', 'ngspice']:
        parser.add_argument('--'+name, type=lambda s: Path(s).resolve())
    args = parser.parse_args(argv)
    if not args.drc_lvs_only:
        missing = [name for name in ['open-pdks', 'magic', 'ngspice'] if getattr(args, name.replace('-', '_')) is None]
        if missing:
            parser.error('Full verification requires ' + ', '.join('--'+name for name in missing))
    result = verify(args)
    print(json.dumps({key: result[key] for key in
        ['scope', 'passed', 'signoff', 'drc', 'lvs', 'capacitance', 'rc', 'remaining'] if key in result}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
