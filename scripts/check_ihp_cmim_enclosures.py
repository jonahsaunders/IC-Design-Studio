"""Independently read written masks and native outcomes for the finite enclosure run."""
import argparse
import re
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe_path(path):
    supplied = Path(path).absolute()
    require('tmpuxoell2b' not in supplied.parts, 'Forbidden evidence path.')
    for parent in (*reversed(supplied.parents), supplied):
        require(not parent.is_symlink() and not parent.is_junction(), 'Linked evidence path.')
    return supplied


def sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def text(path):
    return safe_path(path).read_text(encoding='utf-8')


def data(path):
    return json.loads(safe_path(path).read_bytes())


def expected_masks(rule, margin, angle, fault=''):
    import klayout.db as k
    require((rule, margin) in {('MIM.c', 580), ('MIM.c', 600), ('MIM.c', 620),
                               ('MIM.d', 340), ('MIM.d', 360), ('MIM.d', 380)} and angle in (0, 90), 'Unknown geometry.')
    masks = {(36, 0): k.Region(k.Box(-3500, -3500, 3500, 3500)),
             (67, 0): k.Region(k.Box(-4100, -4100, 3500 + margin if rule == 'MIM.c' else 4100, 4100)),
             (126, 0): k.Region(k.Box(-3300, -3300, 3300 if rule == 'MIM.c' else 3580, 3300)),
             (189, 4): k.Region(k.Box(-4100, -4100, 4100, 4100))}
    if rule == 'MIM.c':
        cuts = k.Region()
        for x in (-2520, -1260, 0, 1260, 2520):
            for y in (-2520, -1260, 0, 1260, 2520):
                cuts.insert(k.Box(x-210, y-210, x+210, y+210))
        masks[(129, 0)] = cuts.merged()
    else:
        masks[(125, 0)] = k.Region(k.Box(3500-margin-420, -210, 3500-margin, 210))
    if fault == 'missing-vmim':
        del masks[(129, 0)]
    elif fault in ('missing-topvia', 'wrong-contact-layer'):
        cut = masks.pop((125, 0))
        if fault == 'wrong-contact-layer': masks[(66, 0)] = cut
    elif fault == 'cross-plate-short':
        masks[(126, 0)] += k.Region(k.Box(3100, -820, 4100, 820))
        masks[(125, 0)] += k.Region(k.Box(3590, -210, 4010, 210))
    elif fault not in ('', 'wrong-reference-width', 'swapped-electrodes'):
        raise ValueError('Unknown fault geometry.')
    if angle == 90:
        masks = {key: region.transformed(k.Trans(k.Trans.R90, 0, 0)) for key, region in masks.items()}
    return {key: value.merged() for key, value in masks.items()}


def stream(path):
    import klayout.db as k
    layout = k.Layout(); layout.read(str(safe_path(path))); require(layout.dbu == .001 and len(layout.top_cells()) == 1 and
            layout.top_cell().name == 'coupon', 'Wrong stream unit or top.')
    cell = layout.top_cell(); masks = {}; texts = []
    for index in layout.layer_indexes():
        info = layout.get_info(index); key = (info.layer, info.datatype)
        region = k.Region(cell.begin_shapes_rec(index)).merged()
        if not region.is_empty(): masks[key] = k.Region([p.dup() for p in region.each()])
        it = cell.begin_shapes_rec(index)
        while not it.at_end():
            if it.shape().is_text():
                text = it.shape().text.transformed(it.trans()); texts.append((key, text.string, text.x, text.y))
            it.next()
    return masks, sorted(texts)


def check_stream(path, rule, margin, angle, fault='', extraction_labels=False):
    actual, texts = stream(path); wanted = expected_masks(rule, margin, angle, fault)
    require(set(actual) == set(wanted), 'Written mask layers differ.')
    for key in wanted:
        require((actual[key] ^ wanted[key]).is_empty(), 'Written mask differs: ' + str(key))
    labels = [((126, 2), 'C1', 0, 0), ((67, 2), 'C2', 3600, 0)]
    if fault == 'swapped-electrodes': labels = [((67, 2), 'C1', 3600, 0), ((126, 2), 'C2', 0, 0)]
    if angle == 90: labels = [(layer, name, -y, x) for layer, name, x, y in labels]
    if extraction_labels: labels += [((layer[0], 25), name, x, y) for layer, name, x, y in labels]
    require(texts == sorted(labels), 'Written electrode labels differ.')


def categories(path):
    root = ET.fromstring(safe_path(path).read_bytes()); items = root.findall('./items/item')
    require(all(i.findtext('cell') == 'coupon' and i.findtext('multiplicity') == '1' for i in items), 'Finding cell differs.')
    return sorted(i.findtext('category').strip("'\"") for i in items)


def reference_device(text, prefix, width):
    lines = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(lines) == 3 and [s.lower() for s in lines[0][:2]] == ['.subckt', 'coupon'] and
            lines[0][2:] == ['C1', 'C2'] and [s.lower() for s in lines[-1]] == ['.ends', 'coupon'] and
            len(lines[1]) >= 5, 'Unexpected reference structure or directive.')
    row = lines[1]; require(row[:4] == [prefix, 'C1', 'C2', 'cap_cmim'], 'Reference model or ordered terminals differ.')
    values = {}
    for token in row[4:]:
        require(token.count('=') == 1, 'Malformed reference parameter.')
        name, value = token.split('='); name = name.lower()
        require(name not in values, 'Duplicated reference parameter.')
        try: number = Decimal(value)
        except InvalidOperation as exc: raise ValueError('Nonliteral reference parameter.') from exc
        require(number.is_finite(), 'Nonfinite reference parameter.'); values[name] = number
    expected = {'w': Decimal(width), 'l': Decimal('7e-6'), 'm': Decimal(1)}
    if prefix == 'X_C1': expected['mm_ok'] = Decimal(1)
    else: expected.update(a=Decimal(width)*Decimal('7e-6'), p=2*(Decimal(width)+Decimal('7e-6')))
    require(values == expected, 'Reference parameter values differ.')


def extraction_command(command, settings, executable):
    require(isinstance(command, list) and len(command) >= 4 and command[:3] == [executable, '-b', '-r'],
            'Extraction command executable differs.')
    args = command[4:]
    require(len(args) % 2 == 0 and all(args[i] == '-rd' for i in range(0, len(args), 2)), 'Malformed extraction arguments.')
    pairs = [args[i].split('=', 1) for i in range(1, len(args), 2)]
    require(all(len(pair) == 2 for pair in pairs) and len({pair[0] for pair in pairs}) == len(pairs), 'Duplicate extraction setting.')
    opts = dict(pairs)
    expected = {'topcell': 'coupon', 'run_mode': 'flat', 'net_only': 'true', 'top_lvl_pins': 'true',
                'no_simplify': 'true', 'combine_devices': 'false', 'purge': 'false', 'purge_nets': 'false',
                'purge_devices': 'false', 'implicit_nets': '', 'disable_tap_extraction': 'false'}
    require(set(opts) == set(expected) | {'input', 'report', 'target_netlist', 'log'} and
            all(opts.get(key) == value for key, value in expected.items()) and (settings is None or opts == settings),
            'Extraction options differ from the unfiltered route.')
    input_path = opts['input'].replace('\\', '/')
    require(input_path.endswith('/lvs-extraction/labels.gds') and '/../' not in input_path, 'Extraction input path differs.')
    root = input_path[:-len('/labels.gds')]
    require(command[3].replace('\\', '/') == root+'/deck/sg13g2.lvs' and
            all(opts[key].replace('\\', '/') == root+'/'+name for key, name in
                (('report', 'extraction.lvsdb'), ('target_netlist', 'native.cir'), ('log', 'native.log'))),
            'Extraction output or deck path differs.')
    return opts


def check_decks(flow, report, expected):
    result = data(flow/'drc/result.json')
    require(type(result.get('schema')) is int and result['schema'] == 2 and result['top'] == 'coupon' and
            result['source_commit'] == '5e6d592e4002946a4616f798c357f0f3c06cf3b6' and
            result['source_lock_sha256'] == '31601ee4ca33750dd2f580f6a8fc519bb5dbe99d504e72759fd97d538f4f3863' and
            result['input_sha256'] == sha(flow/'original.gds') and
            [r['name'] for r in result['decks']] == ['main', 'maximal', 'metal-spacing'], 'DRC identity differs.')
    names = ('main', 'maximal', 'metal-spacing')
    entries = ('ihp-sg13g2.drc', 'rule_decks/sg13g2_maximal.drc', 'metal-spacing/check.drc')
    for row, name, entry, expected_categories in zip(result['decks'], names, entries, expected):
        require(row['entry'] == entry and row['report'] == name+'/findings.lyrdb', 'DRC report path differs.')
        path = flow/'drc'/row['report']; found = categories(path)
        require(sha(path) == row['report_sha256'] and type(row['violations']) is int and
                row['violations'] == len(found) and found == expected_categories, 'Raw DRC categories differ.')
    extra = result['decks'][2]
    require(extra['recipe_sha256'] == '24adf2591231b27e5ed40c9ad86a5626f9e102b0ed8f3fc7728fe7843b3a29e0' and
            sha(flow/'drc/metal-spacing/check.drc') == extra['recipe_sha256'], 'Supplemental recipe differs.')
    require(type(result['violations']) is int and result['violations'] == sum(d['violations'] for d in result['decks']) and
            type(report['drc_count']) is int and report['drc_count'] == result['violations'], 'Total findings differ.')


def check_reference(folder, flow, report, width):
    project = data(folder/'catalog.icproj'); cells = project['cells']
    require(len(cells) == 1 and len(cells[0]['devices']) == 1 and project['pdk']['package_lock']['id'] == 'ihp-sg13g2' and
            project['pdk']['package_lock']['revision'] == 'cfb96b74cf33877e', 'Catalog project/package differs.')
    device = cells[0]['devices'][0]
    require(device['kind'] == 'PDK' and device['name'] == 'C1' and device['nets'] == {'c0':'C1','c1':'C2'} and
            device['model_ref'] == {'pdk':'ihp-sg13g2','revision':'cfb96b74cf33877e','device':'sg13g2_pr/cap_cmim.sym'} and
            'native_spice' not in device, 'Ordinary catalog device differs.')
    params = device['model_params']
    require(set(params) == {'w','l','m','mm_ok'} and Decimal(str(params['w'])) == Decimal(width) and
            Decimal(str(params['l'])) == Decimal('7e-6') and type(params['m']) is int and params['m'] == 1 and
            type(params['mm_ok']) is int and params['mm_ok'] == 1, 'Saved catalog parameters differ.')
    reference = text(folder/'captured-reference.spice'); projected = text(flow/'schematic-lvs.spice')
    require(text(flow/'schematic.spice') == reference, 'Captured reference was substituted.')
    reference_device(reference, 'X_C1', width); reference_device(projected, 'CX_C1', width)
    proof = report['reference_defaults']; require(len(proof) == 1 and proof[0]['instance'] == 'X_C1' and
            proof[0]['physical_instance'] == 'CX_C1' and proof[0]['changed'] is True, 'Projection receipt differs.')
    proof = proof[0]['proof']
    require(proof['source'] == 'libs.tech/xschem/sg13g2_pr/cap_cmim.sym' and
            proof['sha256'] == 'b11c811ee178d260c4b7afcaa8c123f8a6c8c108dde1a119c91aa4386d24e20b' and
            proof['model_source'] == 'libs.tech/ngspice/models/capacitors_mod.lib' and
            proof['model_sha256'] == 'ff9eb4cc9fdccc0645d9db0bd37e25e9fee2a633765910a7f55ac2084c49695f' and
            proof['geometry_reader'] == 'rule_decks/custom_reader.lvs' and
            proof['geometry_reader_sha256'] == 'c71b6713d8a62055d3d8e9e75a7f5f78140001bf76e3fa573b9883fab5e49f06',
            'Projection source identity differs.')


def audit_case(folder, rule, margin, angle):
    folder = Path(folder); flow = folder / 'job/physical-flow'
    for path in (folder/'selected.oas', flow/'original.gds', flow/'layout.gds'):
        check_stream(path, rule, margin, angle)
    check_stream(flow/'lvs-extraction/labels.gds', rule, margin, angle, extraction_labels=True)
    report = data(flow/'report.json')
    require([r['name'] for r in report['stages']] == ['preflight','layout_export','drc','lvs_extraction','lvs','integrity'], 'Case stages differ.')
    stage_rows = {r['name']: r for r in report['stages']}
    stages = {name: row['status'] for name, row in stage_rows.items()}
    below = margin == (580 if rule == 'MIM.c' else 340)
    require(all(stages[n] == 'passed' for n in ('preflight', 'layout_export', 'lvs_extraction', 'lvs', 'integrity')) and
            stages['drc'] == ('failed' if below else 'passed'), 'Unexpected native stage.')
    extraction = stage_rows['lvs_extraction']['evidence']; mapping = extraction['label_mapping']
    require(mapping['source_sha256'] == sha(flow/'original.gds') and mapping['sha256'] == sha(flow/'lvs-extraction/labels.gds') and
            extraction['native_sha256'] == sha(flow/'lvs-extraction/native.cir'), 'Extraction input or native output identity differs.')
    command = data(flow/'lvs-extraction/command.json')
    extraction_command(command, extraction['settings'], stage_rows['preflight']['evidence']['tools']['klayout']['path'])
    check_decks(flow, report, [[rule] if below else [], [], []])
    raw = [line.split() for line in text(flow/'lvs-extraction/native.cir').splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(raw) == 3 and raw[0][:2] == ['.SUBCKT', 'coupon'] and set(raw[0][2:]) == {'C1', 'C2'} and
            raw[-1] == ['.ENDS', 'coupon'] and len(raw[1]) == 9 and raw[1][0].startswith('C') and
            raw[1][1:] == ['C1', 'C2', 'cap_cmim', 'w=7u', 'l=7u', 'A=49p', 'P=28u', 'm=1'], 'Extracted capacitor differs.')
    console = text(flow/'lvs-extraction/console.log')
    for term in ('NET_ONLY enabled', 'LVS Total Run time', '[layout_netlist] simplify: SKIPPED',
                 '[layout_netlist] combine_devices: SKIPPED', '[layout_netlist] purge: SKIPPED',
                 '[layout_netlist] purge_nets: SKIPPED', '[layout_netlist] purge_devices: SKIPPED'):
        require(term in console, 'Incomplete unfiltered extraction.')
    lvs = text(flow/'lvs/lvs.log')
    require('Final result: Circuits match uniquely.' in lvs and 'Cell pin lists are equivalent.' in lvs and 'Property errors' not in lvs, 'Strict LVS differs.')
    check_reference(folder, flow, report, '7e-6')
    return dict(rule=rule, margin_nm=margin, rotation=angle, raw_device_count=1, strict_lvs='passed',
                findings=[rule] if below else [])


def audit_fault(folder, name):
    expected_faults = ('missing-vmim', 'missing-topvia', 'wrong-contact-layer', 'cross-plate-short',
                       'wrong-reference-width', 'swapped-electrodes')
    require(name in expected_faults, 'Unknown fault.')
    folder = Path(folder); flow = folder/'job/physical-flow'
    rule, margin = ('MIM.c', 600) if name == 'missing-vmim' else ('MIM.d', 360)
    for path in (folder/'selected.oas', flow/'original.gds', flow/'layout.gds'):
        check_stream(path, rule, margin, 0, name)
    check_stream(flow/'lvs-extraction/labels.gds', rule, margin, 0, name, extraction_labels=True)
    report = data(flow/'report.json'); rows = report['stages']
    require([r['name'] for r in rows] == ['preflight','layout_export','drc','lvs_extraction','lvs','integrity'], 'Fault stages differ.')
    stages = {r['name']: r['status'] for r in rows}; guarded = name in expected_faults[:4]
    require(stages == dict(preflight='passed', layout_export='passed', drc='failed' if guarded else 'passed',
                           lvs_extraction='failed' if guarded else 'passed', lvs='not_run' if guarded else 'failed',
                           integrity='not_run' if guarded else 'passed'), 'Fault stage outcome differs.')
    expected_drc = ([[], ['MIM.h'], []] if name in ('missing-vmim','missing-topvia') else
                    [['V4.a','V4.a'], ['MIM.h'], []] if name == 'wrong-contact-layer' else
                    [['TV1.c','TV1.d'], [], []] if name == 'cross-plate-short' else [[],[],[]])
    check_decks(flow, report, expected_drc)
    if guarded:
        require(rows[3].get('error') == 'IHP extracted port names differ from the schematic.' and
                not safe_path(flow/'lvs/lvs.log').exists(), 'Specific pre-LVS port guard differs.')
    command = data(flow/'lvs-extraction/command.json')
    opts = extraction_command(command, None, rows[0]['evidence']['tools']['klayout']['path'])
    require(opts['input'].replace('\\','/').endswith('/fault-'+name+'/job/physical-flow/lvs-extraction/labels.gds'),
            'Fault extraction input case differs.')
    console = text(flow/'lvs-extraction/console.log')
    for term in ('NET_ONLY enabled', 'LVS Total Run time', '[layout_netlist] simplify: SKIPPED',
                 '[layout_netlist] combine_devices: SKIPPED', '[layout_netlist] purge: SKIPPED',
                 '[layout_netlist] purge_nets: SKIPPED', '[layout_netlist] purge_devices: SKIPPED'):
        require(term in console, 'Incomplete fault extraction.')
    raw = [line.split() for line in text(flow/'lvs-extraction/native.cir').splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(raw) == 3 and raw[0][:2] == ['.SUBCKT','coupon'] and raw[-1] == ['.ENDS','coupon'] and
            len(raw[1]) == 9 and raw[1][0].startswith('C') and
            raw[1][3:] == ['cap_cmim','w=7u','l=7u','A=49p','P=28u','m=1'], 'Fault native unit differs.')
    unit = raw[1]
    if name in ('missing-vmim','missing-topvia','wrong-contact-layer'):
        require(raw[0][2:] == ['C2'] and re.fullmatch(r'\\?\$\d+', unit[1]) and unit[2] == 'C2', 'Missing contact topology differs.')
    elif name == 'cross-plate-short':
        require(raw[0][2:] == ['C1|C2'] and unit[1:3] == ['C1|C2','C1|C2'], 'Short topology differs.')
    else:
        require(set(raw[0][2:]) == {'C1','C2'} and unit[1:3] == (['C2','C1'] if name == 'swapped-electrodes' else ['C1','C2']), 'Fault terminal mapping differs.')
        log = text(flow/'lvs/lvs.log')
        if name == 'wrong-reference-width':
            require('Property errors were found.' in log and all(v in log for v in ('5.04e-11','4.9e-11','2.84e-05','2.8e-05')), 'Wrong-width property failure differs.')
        else:
            require('Final result: Top level cell failed pin matching.' in log and log.count('**Mismatch**') == 2, 'Electrode pin failure differs.')
    check_reference(folder, flow, report, '7.2e-6' if name == 'wrong-reference-width' else '7e-6')
    return dict(fault=name, raw_topology_verified=True, lvs='not_run' if guarded else 'failed', findings=expected_drc)


def selection(report):
    require(type(report.get('schema')) is int and report['schema'] == 1 and report.get('status') == 'OBSERVED_FULL_SELECTION' and report.get('pilot') is False, 'Full selection is required.')
    expected = [(r, m, a) for r, values in (('MIM.c', (580,600,620)), ('MIM.d',(340,360,380))) for m in values for a in (0,90)]
    require([(x['rule'], x['margin_nm'], x['rotation']) for x in report['cases']] == expected and
            all(type(x['margin_nm']) is int and type(x['rotation']) is int for x in report['cases']), 'Case selection differs.')
    faults = ('missing-vmim', 'missing-topvia', 'wrong-contact-layer', 'cross-plate-short', 'wrong-reference-width', 'swapped-electrodes')
    require([x['fault'] for x in report['faults']] == list(faults), 'Fault selection differs.')
    return expected, faults


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('output', type=Path)
    args = parser.parse_args(); supplied = args.output.absolute()
    require('tmpuxoell2b' not in supplied.parts, 'Forbidden evidence path.')
    for parent in (*reversed(supplied.parents), supplied):
        require(not parent.is_symlink() and not parent.is_junction(), 'Linked evidence ancestor.')
    root = supplied.resolve(); require('tmpuxoell2b' not in root.parts, 'Forbidden resolved evidence path.')
    report = data(root/'report.json')
    expected, faults = selection(report)
    contract_path = Path(__file__).resolve().parents[1]/'docs/qualification/ihp-cmim-enclosures-v1.json'
    contract_hash = '8f82d1ba570a7e831a55e751700b04d9f3e35a0bc007acdf7639c223dfda501b'
    require(sha(contract_path) == report['source_contract_sha256'] == contract_hash and
            all(report['source_files'].get(k) == v for k, v in data(contract_path)['source_sha256'].items()), 'Source contract binding differs.')
    results = [audit_case(root/f'{rule}-{margin}-{angle}', rule, margin, angle) for rule, margin, angle in expected]
    fault_results = [audit_fault(root/('fault-'+name), name) for name in faults]
    print(json.dumps(dict(status='PASS_FULL_SELECTION_READBACK', cases=results, faults=fault_results, fault_controls_audited=True,
                          qualified=False, installed_acceptance=False), indent=2))


if __name__ == '__main__':
    main()
