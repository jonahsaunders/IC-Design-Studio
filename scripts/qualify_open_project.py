"""Reproduce the pinned overvoltage import, simulation and physical comparison.

The default gate checks import fidelity. --require-consistent additionally
requires the external design's source and layout to pass LVS. Neither outcome
is a foundry signoff statement. Source files are never modified.
"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import atomic_write, file_digest, save_project, load_project, clone
from icstudio.engines import execute, netgen_lvs, require_lvs_match, tcl_word, parse_raw
from icstudio.native_analysis import circuit_text


def normalized_diodes(text, reference=False, physical_units=True):
    """Documented bridge for this locked legacy source; never change wiring.

The checked-in netlist uses XD while the supplied lvsdiode symbol uses D.
The bundled diode model declares a 1e12 area scale. LVS uses square microns.
The PDK setup already excludes perim; do not discard any other property.
"""
    count = 0
    def convert(match):
        nonlocal count
        count += 1
        area = float(match['area']) * (1e-12 if physical_units else 1)
        return 'D' + match['name'] + match['body'] + ' area=' + format(area, '.12g')
    prefix = 'XD' if reference else 'D'
    pattern = (r'(?m)^' + prefix + r'(?P<name>\S+)(?P<body>\s+\S+\s+\S+\s+sky130_fd_pr__diode_pw2nd_05v5)'
               r'\s+area=(?P<area>\S+)' + (r'\s+perim=\S+' if reference else '') + r'\s*$')
    result = re.sub(pattern, convert, text)
    if count != 17: raise ValueError('Legacy diode bridge expected exactly 17 declarations; inspect the new source.')
    return result


def geometry_equal(first, second):
    """Compare every cell/layer region, text and placement without Studio sidecars."""
    import klayout.db as db
    layouts = []
    for path in (first, second):
        ly = db.Layout(); ly.read(str(path)); layouts.append(ly)
    a, b = layouts
    if a.dbu != b.dbu: raise ValueError('Layout database units changed.')
    if {c.name for c in a.each_cell()} != {c.name for c in b.each_cell()}: raise ValueError('Layout cell set changed.')
    layers = {(ly.get_info(i).layer, ly.get_info(i).datatype) for ly in layouts for i in ly.layer_indexes()}
    checked = 0
    for c in a.each_cell():
        other = b.cell(c.name)
        def instances(cell, ly):
            return sorted((ly.cell(i.cell_index).name, str(i.cplx_trans), i.na, i.nb, str(i.a), str(i.b)) for i in cell.each_inst())
        if instances(c, a) != instances(other, b): raise ValueError('Placements changed in ' + c.name)
        for pair in layers:
            ia, ib = a.find_layer(*pair), b.find_layer(*pair)
            ra = db.Region(c.shapes(ia)) if ia is not None else db.Region()
            rb = db.Region(other.shapes(ib)) if ib is not None else db.Region()
            if not (ra ^ rb).is_empty(): raise ValueError('Geometry changed: ' + c.name + ' / ' + str(pair))
            def labels(cell, index):
                return sorted(str(s.text) for s in cell.shapes(index).each() if s.is_text()) if index is not None else []
            if labels(c, ia) != labels(other, ib): raise ValueError('Layout text changed: ' + c.name)
            checked += 1
    return dict(status='passed', cells=a.cells(), cell_layers=checked,
                checks=['region XOR', 'text and text transforms', 'hierarchy and array transforms'])


def simulations(project, reference, executable, output, compatibility='hsa'):
    from icstudio.native_spice import netlist
    from icstudio.spice_program import read_plot
    top = next(c for c in project['cells'] if c['id'] == project['top'])
    text = circuit_text(netlist(project, output / 'native-deck'))
    split = text.lower().index('.subckt ')
    native = '.subckt ' + top['name'] + ' ' + ' '.join(top['ports']) + '\n' + text[:split] + '.ends ' + top['name'] + '\n' + text[split:]
    other = circuit_text(normalized_diodes(reference, True, False))
    models = ROOT / 'icstudio/assets/pdks/sky130A/libs.tech/ngspice/sky130.lib.spice'
    results = []
    for code in range(16):
        waves = []
        for kind, circuit in (('native', native), ('reference', other)):
            sub = re.search(r'(?im)^\.subckt\s+' + re.escape(top['name']) + r'\s+([^\n]+)', circuit)
            ports = ['0' if p in ('avss', 'dvss') else p.replace('[', '_').replace(']', '') for p in sub[1].split()]
            folder = output / f'{code:02d}-{kind}'; folder.mkdir(parents=True)
            deck = '* Pinned detector DC functional sweep\n.lib "' + str(models) + '" tt\n' + circuit
            deck += '\nXDUT ' + ' '.join(ports) + ' ' + top['name']
            deck += '\nVavdd avdd 0 3\nVdvdd dvdd 0 1.8\nVena ena 0 1.8\nVbg vbg 0 1.2\nIbias avdd ibias 600n\nRload ovout 0 1meg\n'
            deck += ''.join(f'Vbit{i} vtrip_{i} 0 {1.8 if code & (1 << i) else 0}\n' for i in range(4))
            deck += '.temp 27\n.dc Vavdd 3 6 .01\n.save v(ovout)\n.end\n'
            command=[executable, '-n', '-D', 'filetype=ascii']
            if compatibility=='hsa':command += ['-D', 'ngbehavior=hsa']
            if compatibility=='hsa':
                from icstudio.dc_startup import seed_deck
                deck=seed_deck(deck,lambda raw,deck:command+['-b','-r',str(raw),str(deck)],folder)
            atomic_write(folder / 'input.cir', deck)
            command += ['-b', '-r', str(folder / 'output.raw'), str(folder / 'input.cir')]
            try: log = execute(command, folder, timeout=120)
            except Exception as exc:
                atomic_write(folder / 'engine-error.log', str(exc)); raise
            atomic_write(folder / 'engine.log', log)
            if re.search(r'(?im)^\s*error|unknown subckt|timestep too small|singular matrix', log): raise ValueError('Simulation diagnostic: ' + str(folder))
            plot = read_plot(folder / 'output.raw')
            if plot['plot_kind'] != 'dc' or len(plot['x']) != 301 or 'ovout' not in plot['traces']: raise ValueError('Incomplete functional sweep.')
            rows = list(zip(plot['x'], plot['traces']['ovout']))
            if not all(math.isfinite(v) for row in rows for v in row): raise ValueError('Nonfinite functional sweep.')
            if rows[0][1] > .2 or rows[-1][1] < 1.6: raise ValueError('Detector did not switch across the supply sweep.')
            waves.append(rows)
        error = max(abs(a[1] - b[1]) for a, b in zip(*waves))
        # Compare within the solver's default 0.1% relative accuracy, with
        # a 2 µV floor near zero. A rail transition must occur on the same step.
        if any(abs(a[1]-b[1])>max(2e-6,1e-3*abs(b[1])) for a,b in zip(*waves)):
            raise ValueError(f'Code {code}: waveform differs beyond the declared solver tolerance ({error:g} V peak).')
        trip = next(row[0] for row in waves[0] if row[1] >= .9)
        reference_trip = next(row[0] for row in waves[1] if row[1] >= .9)
        if abs(trip-reference_trip)>1e-8:raise ValueError('Detector trip steps differ from the reference.')
        results.append(dict(code=code, trip_voltage=trip, max_reference_error=error, status='passed'))
        atomic_write(output / 'completed-codes.json', json.dumps(results, indent=2))
    if any(b['trip_voltage'] <= a['trip_voltage'] for a, b in zip(results, results[1:])):
        raise ValueError('Trip thresholds are not strictly increasing.')
    return dict(status='passed', compatibility=compatibility, dc_startup=compatibility=='hsa', corner='tt', temperature=27, dvdd=1.8, vbg=1.2,
                ibias=6e-7, supply_step=.01, tolerance=dict(relative=1e-3,absolute_voltage=2e-6,trip='same 10 mV step'), codes=results,
                scope='Emitted-deck comparison in the declared compatibility mode; excludes transient timing, hysteresis, PVT and extracted simulation.')


def qualify(args):
    from icstudio.native_migration import review_path
    from icstudio.native_spice import netlist
    from icstudio.interchange import export_layout
    from icstudio.layout_attach import attach, matching_cells
    from icstudio.engines import magic_import
    from icstudio.external_tools import extraction_commands
    source = args.source.resolve(); out = args.out.resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('Choose an empty output directory.')
    out.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / 'examples/open-projects/overvoltage-lock.json').read_text())
    report = dict(schema=1, status='running', import_regression='running', source={k:v for k,v in lock.items() if k != 'files'}, checks={})
    def publish(): atomic_write(out / 'qualification.json', json.dumps(report, indent=2) + '\n')
    publish()
    try:
        for relative, expected in lock['files'].items():
            path = (source / relative).resolve()
            if not path.is_relative_to(source) or file_digest(path) != expected: raise ValueError('Pinned source differs: ' + relative)
        report['verified_source_files'] = len(lock['files'])
        top = lock['top']; tech = args.pdk.resolve() / 'libs.tech/magic/sky130A.tech'; setup = args.pdk.resolve() / 'libs.tech/netgen/sky130A_setup.tcl'
        report['tools'] = {k: execute([getattr(args,k), '--version' if k != 'netgen' else '-batch'], out, timeout=30)[:1500] for k in ('magic', 'netgen', 'ngspice')}
        from scripts.prepare_open_project_technology import prepare
        tech, correction = prepare(tech, out / 'technology')
        report['process'] = dict(technology_sha256=file_digest(tech), setup_sha256=file_digest(setup), correction=correction)
        result = review_path(source / 'xschem' / (top + '.sch'), libraries=[source / 'xschem'])
        atomic_write(out / 'migration.json', json.dumps({k:v for k,v in result.items() if k != 'candidate'}, indent=2))
        p = result['candidate']
        if p is None: raise ValueError('Schematic migration has no native candidate.')
        save_project(p, out / 'schematic.icproj'); p = load_project(out / 'schematic.icproj')
        raw = netlist(p, out / 'native', mode='lvs')
        ref = (source / 'netlist/schematic' / (top + '.spice')).read_text()
        atomic_write(out / 'native-lvs.spice', normalized_diodes(raw))
        atomic_write(out / 'reference-lvs.spice', normalized_diodes(ref, True))
        report['normalization'] = ['Legacy XD diode notation mapped to D for the 17 locked declarations.',
            'Diode simulation area scaled by 1e-12 into square microns for LVS only.',
            'Perimeter excluded by the pinned PDK policy; Magic pj treated as perim. Connectivity and MOS/resistor parameters unchanged.']
        atomic_write(out / 'setup.tcl', 'source ' + tcl_word(setup) + '\nforeach c {1 2} {\nproperty "-circuit$c sky130_fd_pr__diode_pw2nd_05v5" delete pj\n}\n')
        def compare(name, other, schematic=None):
            log = netgen_lvs(args.netgen, schematic or out / 'native-lvs.spice', top, other, top, out / 'setup.tcl', out / name)
            if not (out / name / 'lvs.log').is_file(): raise ValueError('Netgen produced no comparison report: ' + name)
            try: require_lvs_match(log); status = 'passed'
            except ValueError:
                if not re.search(r'Netlists do not match|Circuits do not match|Property errors|disconnected node:|\(no matching pin\)|failed pin matching', log, re.I):
                    raise ValueError('Netgen did not finish a recognizable comparison: ' + name)
                status = 'failed'
            return dict(status=status, report=name + '/lvs.log')
        report['checks']['schematic_reference'] = compare('schematic-reference', out / 'reference-lvs.spice')
        if report['checks']['schematic_reference']['status'] != 'passed': raise ValueError('Schematic import differs electrically from the reference.')
        from icstudio.interchange import export_xschem
        export_xschem(p, out / 'xschem-roundtrip')
        reopened = review_path(out / 'xschem-roundtrip' / (top + '.sch'))['candidate']
        if reopened is None: raise ValueError('The exported schematic cannot be reimported.')
        atomic_write(out / 'roundtrip-lvs.spice', normalized_diodes(netlist(reopened, out / 'reimported', mode='lvs')))
        report['checks']['schematic_roundtrip'] = compare('schematic-roundtrip', out / 'roundtrip-lvs.spice')
        if report['checks']['schematic_roundtrip']['status'] != 'passed': raise ValueError('Electrical connectivity changed on schematic round trip.')
        layout = load_project(magic_import(args.magic, source / 'mag' / (top + '.mag'), tech, out / 'magic-import'))
        combined = attach(p, layout, matching_cells(p, layout))
        save_project(combined, out / 'overvoltage.icproj')
        export_layout(load_project(out / 'overvoltage.icproj'), out / 'roundtrip.gds')
        # Export the layout-only native project as well: added schematic-only
        # cells are expected in the combined project, but not in the geometry test.
        export_layout(layout, out / 'geometry-roundtrip.gds')
        report['checks']['layout_geometry'] = geometry_equal(out / 'magic-import/imported.gds', out / 'geometry-roundtrip.gds')
        report['cells'] = dict(schematic=len(p['cells']), layout=len(layout['cells']), attached=len(combined['layout_attachment']['cells']))
        publish()
        report['checks']['simulation'] = simulations(p, ref, args.ngspice, out / 'simulation', args.compatibility)
        publish()
        from scripts.open_project_bench import create
        from icstudio.engines import run_ngspice
        bench = create(combined, out)
        bench_run = out / 'bench-simulation'; bench_run.mkdir()
        result = run_ngspice(bench, bench['top'], bench['analysis'], args.ngspice, bench_run)
        from icstudio.spice_program import read_plot
        reference_wave = read_plot(out / 'simulation/00-reference/output.raw')['traces']['ovout']
        actual = result['traces']['ovout']
        if len(actual) != 301 or any(not math.isfinite(a) or abs(a-b)>max(2e-6,1e-3*abs(b)) for a,b in zip(actual,reference_wave)):
            raise ValueError('The saved desktop testbench differs from the reference sweep.')
        report['checks']['desktop_testbench'] = dict(status='passed', project='overvoltage-bench.icproj',
            compatibility='hsa', dc_startup=True, points=len(actual), code=0,
            max_reference_error=max(abs(a-b) for a,b in zip(actual,reference_wave)),
            scope='Saved/reopened project through the app graphical-analysis engine; both DUT views and model closure embedded.')
        publish()
        native = out / 'source-layout'; shutil.copytree(source / 'mag', native)
        script = 'load ' + tcl_word(top) + '\nselect top cell\n' + extraction_commands('lvs', {'hierarchy': False})[0] + 'ext2spice\nquit -noprompt\n'
        atomic_write(native / 'extract.tcl', script)
        atomic_write(native / 'extraction.log', execute([args.magic, '-dnull', '-noconsole', '-T', str(tech)], native, input_text=script))
        report['checks']['layout_schematic_lvs'] = compare('layout-schematic', native / (top + '.spice'))
        report['checks']['layout_schematic_lvs']['extraction'] = 'Full circuit, hierarchy off; all device properties and top pins compared.'
        # Compare faults with the same independently extracted physical circuit.
        # This proves flattening and the extraction correction do not mask real
        # child wiring, external interface or resistor dimension defects.
        original = (out / 'native-lvs.spice').read_text()
        faults = {
            'enable_open': (' ena ', ' disconnected_enable '),
            'child_pin': ('x4 avdd dvdd vtrip[3] A NotA avss dvss level_shifter',
                          'x4 avdd dvdd vtrip[3] A NotA dvdd dvss level_shifter'),
            'resistor_length': ('res_xhigh_po_1p41 L=14.1 ', 'res_xhigh_po_1p41 L=13.94 '),
        }
        for name, (before, after) in faults.items():
            if before not in original: raise ValueError('Fault target changed: ' + name)
            broken = out / (name + '.spice')
            atomic_write(broken, original.replace(before, after, 1))
            finding = compare('fault-' + name, native / (top + '.spice'), broken)
            if finding['status'] != 'failed': raise ValueError('LVS missed the deliberate ' + name)
            finding.update(status='passed', observed_lvs='failed')
            report['checks']['fault_' + name] = finding
        report['import_regression'] = 'passed'
        report['status'] = 'passed' if report['checks']['layout_schematic_lvs']['status'] == 'passed' else 'needs_attention'
    except Exception as exc:
        report.update(status='failed', import_regression='failed', error=str(exc), traceback=traceback.format_exc())
    publish()
    print(json.dumps(dict(status=report['status'], import_regression=report['import_regression'], report=str(out / 'qualification.json')), indent=2))
    return 0 if report['import_regression'] == 'passed' and (not args.require_consistent or report['status'] == 'passed') else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'pdk', 'out'): ap.add_argument('--' + key, type=Path, required=True)
    for key in ('magic', 'netgen', 'ngspice'): ap.add_argument('--' + key, default=shutil.which(key), required=not shutil.which(key))
    ap.add_argument('--require-consistent', action='store_true')
    ap.add_argument('--compatibility', choices=('native','hsa'), default='hsa',
                    help='Explicit ngspice mode. HSA uses first-point DC startup; native is retained for independent comparison.')
    return qualify(ap.parse_args())


if __name__ == '__main__': raise SystemExit(main())
