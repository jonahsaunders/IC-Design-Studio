"""Independent raw readback of the finite parallel-CMIM saved-bench experiment."""
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex

ROOT = Path(__file__).resolve().parents[1]


def source_files():
    names = {p.relative_to(ROOT).as_posix() for p in (ROOT/'icstudio').glob('*.py')}
    names.update('scripts/'+n+'.py' for n in ('qualify_standard_mos','qualify_ihp_mim_layout',
        'ihp_cmim_boundary_audit','qualify_ihp_cmim_parallel','check_ihp_cmim_parallel',
        'qualify_ihp_cmim_multiplicity','qualify_ihp_cmim_reference'))
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}


def inventory(root):
    require(root.is_dir() and 'tmpuxoell2b' not in root.parts, 'missing/forbidden evidence root')
    for path in (*root.parents, root):
        require(not path.is_symlink() and not path.is_junction(), 'linked evidence root')
    result = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        require('tmpuxoell2b' not in (*dirs, *files), 'forbidden evidence member')
        for name in (*dirs, *files):
            path = Path(folder)/name
            require(not path.is_symlink() and not path.is_junction(), 'linked evidence member')
            if name in files:
                relative = path.relative_to(root).as_posix()
                if relative not in ('report.json', 'verification.json'):
                    require(path.is_file(), 'nonregular evidence member')
                    result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def require(ok, message):
    if not ok: raise ValueError('Parallel CMIM evidence: '+message)


def project_contract(project):
    technology = project['pdk']
    lock = technology['package_lock']
    manifest = {'schema':1, 'family':'ihp-sg13g2', 'id':lock['id'], 'revision':lock['revision'],
                'files':lock['files'], 'technology':{k:v for k,v in technology.items()
                                                   if k not in ('package_root','package_lock')}}
    actual = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',',':'), allow_nan=False).encode()).hexdigest()
    require(actual == '5cb4aca37ed4192eadd82d686a1d5fc97072b018e7c45d21f062333a3361eebd', 'unrelated/changed saved PDK contract')
    dut = next(c for c in project['cells'] if c['id'] == project['top'])
    require(dut['name'] == 'coupon' and dut['ports'] == ['C1','C2'] and not dut.get('layout_instances'), 'saved physical interface/hierarchy')
    for device in dut['devices']:
        require(device['model_ref'] == {'pdk':lock['id'], 'revision':lock['revision'], 'device':'sg13g2_pr/cap_cmim.sym'}, 'unrelated/changed device model reference')
    package = ROOT/'icstudio/assets/pdks/ihp-sg13g2'
    require(all(hashlib.sha256((package/n).read_bytes()).hexdigest() == h for n,h in lock['files'].items()), 'changed pinned package bytes')
    return dut


def number(value):
    match = re.fullmatch(r'([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)([ufpn]?)', value)
    require(match is not None, 'nonliteral number')
    return Decimal(match[1]) * {'': Decimal(1), 'u': Decimal('1e-6'), 'n': Decimal('1e-9'), 'p': Decimal('1e-12'), 'f': Decimal('1e-15')}[match[2]]


def netlist(text, source=False):
    units, graph, names = Counter(), {}, set()
    rows = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(rows[0] == ['.subckt', 'coupon', 'C1', 'C2'] and rows[-1] in (['.ends'], ['.ends', 'coupon']), 'ordered interface')
    for row in rows[1:-1]:
        require(row[0].casefold() not in names, 'duplicate instance')
        names.add(row[0].casefold())
        if row[0].startswith('X'):
            require(row[1:4] == ['C1', 'C2', 'cap_cmim'], 'intrinsic electrode order/model')
            params = {}
            for token in row[4:]:
                key, value = token.split('=')
                require(key not in params, 'duplicate intrinsic parameter')
                params[key] = number(value)
            require(set(params) <= {'w','l','m','mm_ok'} and {'w','l'} <= set(params), 'unknown/missing intrinsic parameter')
            require(params.get('mm_ok', 1) == 1 and (source or 'mm_ok' not in params), 'unexpected mismatch parameter')
            count = params.get('m', Decimal(1))
            require(count > 0 and count == int(count), 'noninteger multiplicity')
            units[params['w'], params['l']] += int(count)
        else:
            require(not source and row[0].startswith('C') and len(row) == 4, 'unknown circuit record')
            pair = tuple(sorted(row[1:3]))
            require(pair not in graph and pair[0] != pair[1] and set(pair) <= {'C1','C2','SUB'}, 'duplicate/unknown capacitance edge')
            graph[pair] = number(row[3])*Decimal('1e18')
    return units, graph


def read_native(folder, *, job_name="job"):
    expected = Counter({(Decimal('7e-6'), Decimal('7e-6')): 2})
    raw = folder/job_name/'parasitics/coupon.ext'
    # Discover the actual stage name once; no arbitrary alternate source is accepted.
    require(raw.is_file(), 'missing native PEX raw graph')
    units, graph, locations, ports, nodes = Counter(), {}, set(), {}, set()
    text = raw.read_text(encoding='utf-8')
    metadata = {'version 8.3', 'tech ihp-sg13g2', 'style ngspice()', 'scale 1000 1 1',
        'resistclasses 3000000 67000 110 88 88 88 88 18 11 7000 260000 1360000',
        'parameters cap_rfcmim w=w l=l', 'parameters cap_cmim w=w l=l'}
    timestamps = 0
    for line in text.splitlines():
        row = shlex.split(line)
        if not row: continue
        if line in metadata:
            metadata.remove(line)
        elif row[0] == 'timestamp' and len(row) == 2 and re.fullmatch('[0-9]+', row[1]):
            timestamps += 1
        elif row[0] == 'port':
            require(len(row) == 8 and row[1] in ('C1','C2') and row[1] not in ports and
                    row[-1] == {'C1':'m6','C2':'m5'}[row[1]] and all(re.fullmatch('-?[0-9]+',v) for v in row[2:7]), 'raw port')
            ports[row[1]] = int(row[2])
        elif row[0] == 'device':
            require(len(row) == 16 and row[1:3] == ['csubckt','cap_cmim'] and row[10] == 'C1' and row[13] == 'C2', 'raw intrinsic order/model')
            location = tuple(int(v) for v in row[3:7])
            require(location not in locations, 'duplicate native intrinsic location')
            locations.add(location)
            dims = tuple(Decimal(v.split('=')[1])*Decimal('1e-8') for v in row[7:9])
            require(row[7].startswith('w=') and row[8].startswith('l='), 'raw dimension fields')
            units[dims] += 1
        elif row[0] in ('node', 'substrate'):
            require(len(row) == 31 and row[1] in ('C1','C2','SUB') and row[1] not in nodes and
                    row[0] == ('substrate' if row[1] == 'SUB' else 'node') and
                    row[6] == {'C1':'m6','C2':'m5','SUB':'space'}[row[1]] and number(row[2]) == 0 and
                    all(re.fullmatch('-?[0-9]+',v) for v in [*row[4:6],*row[7:]]), 'raw node/substrate')
            nodes.add(row[1])
            if row[1] == 'SUB': require(number(row[3]) == 0, 'nonzero substrate capacitance')
            else: graph[tuple(sorted((row[1],'SUB')))] = number(row[3])
        elif row[0] == 'cap':
            require(set(row[1:3]) == {'C1','C2'} and ('C1','C2') not in graph, 'raw coupling')
            graph['C1','C2'] = Decimal(row[3])
        else:
            require(False, 'unknown raw record')
    require(not metadata and timestamps == 1 and ports == {'C1':1,'C2':2} and nodes == {'C1','C2','SUB'}, 'incomplete raw metadata/ports/substrate')
    require(units == expected and set(graph) == {('C1','C2'),('C1','SUB'),('C2','SUB')} and min(graph.values()) >= 1, 'raw intrinsic multiset or complete graph')
    original_units, original = netlist((raw.parent/'extracted.spice').read_text(encoding='utf-8'))
    flat_units, flat = netlist((raw.parent/'extracted-flat.spice').read_text(encoding='utf-8'))
    require(original_units == flat_units == expected, 'export intrinsic multiset')
    require(set(flat) == set(graph), 'missing/extra exported edge')
    require(all(abs(flat[e]-v) <= Decimal('.005')+v*Decimal('2e-7') for e,v in graph.items()), 'changed exported edge')
    require(('C1','SUB') not in original and abs(original['C2','SUB']-graph['C1','SUB']-graph['C2','SUB']) < Decimal('.02'), 'original writer defect not retained')
    evidence = json.loads((raw.parent/'cmim-capacitance.json').read_text(encoding='utf-8'))
    require(evidence['schema'] == 2 and evidence['multiplicity'] == 2 and
            evidence['intrinsic_units'] == [{'width_m':'0.000007','length_m':'0.000007','multiplicity':2}], 'application intrinsic receipt')
    require({tuple(row['nodes']):Decimal(row['raw']) for row in evidence['edges_af']} == graph, 'application raw receipt')
    return {'intrinsic_units': 2, 'raw_edges_af': [{'nodes':list(e),'value':str(v)} for e,v in sorted(graph.items())]}


def currents(folder, graph, *, job_name="job"):
    """Read actual ASCII complex vectors, then independently solve this circuit."""
    text = (folder/job_name/'post-layout/deck.raw').read_text(encoding='utf-8')
    require('Flags: complex\n' in text and 'No. Variables: 3\n' in text and
            re.search(r'No\. Points: 3\s*\n', text), 'native AC dimensions')
    header, body = text.split('Values:\n')
    require(re.findall(r'^\s*[0-9]+\s+(\S+)\s+\S+', header.split('Variables:\n')[1], re.M) ==
            ['frequency','v(vin)','i(vin)'], 'native AC vector names')
    rows = [r.split() for r in body.splitlines() if r.strip()]
    require(len(rows) == 9, 'native AC sample count')
    # The exported capacitor values have five fractional SI digits. Use the
    # independently parsed actual simulation deck for its numerical prediction.
    _, flat = netlist((folder/job_name/'parasitics/extracted-flat.spice').read_text(encoding='utf-8'))
    edges = {e:float(v)*1e-18 for e,v in flat.items()}
    extra = edges['C1','C2'] + edges['C1','SUB']*edges['C2','SUB']/(edges['C1','SUB']+edges['C2','SUB'])
    model = ROOT/'icstudio/assets/pdks/ihp-sg13g2/libs.tech/ngspice/models'
    text = (model/'capacitors_mod.lib').read_text(encoding='utf-8')
    resistance = float(re.search(r'^R1 PLUS 1 r=([0-9.]+)m$', text, re.M)[1])*1e-3
    fringe = float(re.search(r'^\.model cmim_core C .*CJSW=([0-9.Ee+-]+)', text, re.M)[1])
    nominal = (model/'cornerCAP.lib').read_text(encoding='utf-8').split('.LIB cap_typ\n',1)[1].split('.ENDL cap_typ',1)[0]
    area = float(re.search(r'^\.param cap_carea = ([0-9.Ee+-]+)$', nominal, re.M)[1])
    capacitance = 49*area+28*fringe
    errors = []
    for i in range(3):
        require(len(rows[i*3]) == 2 and rows[i*3][0] == str(i) and len(rows[i*3+1]) == len(rows[i*3+2]) == 1, 'native AC sample index')
        f = float(rows[i*3][1].split(',')[0])
        voltage, current = (complex(*map(float, r[-1].split(','))) for r in rows[i*3+1:i*3+3])
        require(all(math.isfinite(v) for v in (f, voltage.real, voltage.imag, current.real, current.imag)) and
                abs(f/(1e5*10**(i/2))-1) < 1e-12 and abs(voltage-1) < 1e-12, 'nonfinite/wrong AC stimulus')
        omega = 2*math.pi*f
        expected = -(2/(resistance+1/(1j*omega*capacitance))+1j*omega*extra)
        errors.append(abs(current-expected)/abs(expected))
    require(max(errors) < 1e-7, 'native AC differs from independent finite linear circuit')
    return {'samples':3, 'maximum_relative_current_error':max(errors)}


def verify(root):
    root = Path(root).absolute()
    report = json.loads((root/'report.json').read_text(encoding='utf-8'))
    require(report['status'] == 'OBSERVED' and report['qualified'] is False and report['installed_acceptance'] is False, 'invalid outcome/expanded scope')
    require(report['source_files'] == source_files(), 'changed/incomplete source identity')
    files = inventory(root)
    require(bool(files) and report['files'] == files, 'changed/incomplete evidence inventory')
    positives = ('m2-0','pair-0','m2-90','pair-90')
    negatives = ('m1-0','m3-0','wrong-width-0')
    require([r['name'] for r in report['cases']] == [*positives,*negatives], 'finite case selection')
    results = []
    for name in (*positives,*negatives):
        folder = root/name
        actual = json.loads((folder/'job/report.json').read_text(encoding='utf-8'))
        project = json.loads((folder/'project.icproj').read_text(encoding='utf-8'))
        require(project == json.loads((folder/'job/input.icproj').read_text(encoding='utf-8')), 'saved/current project differs')
        captured = (folder/'captured.spice').read_text(encoding='utf-8')
        require(captured == (folder/'job/schematic.spice').read_text(encoding='utf-8'), 'captured/actual source differs')
        dut = project_contract(project)
        expected_rows = {}
        for device in dut['devices']:
            require(device['kind'] == 'PDK' and device['model_ref']['device'] == 'sg13g2_pr/cap_cmim.sym' and
                    device['nets'] == {'c0':'C1','c1':'C2'} and not device.get('native_spice') and not device.get('array'), 'ordinary saved device')
            key = 'X_'+device['name']
            require(key.casefold() not in {k.casefold() for k in expected_rows}, 'duplicate saved device')
            expected_rows[key] = {k:number(str(device['model_params'][k])) for k in ('w','l','m','mm_ok')}
        actual_rows = {row.split()[0]:{k:number(v) for k,v in (s.split('=') for s in row.split()[4:])}
                       for row in captured.splitlines() if row.startswith('X')}
        require(actual_rows == expected_rows, 'saved project/captured device parameters differ')
        for relative, digest in actual['provenance']['files'].items():
            require(files.get(name+'/job/'+relative) == digest, 'changed native provenance input')
        stages = {r['name']:r['status'] for r in actual['stages']}
        if name in positives:
            require(actual['status'] == 'passed' and all(v == 'passed' for v in stages.values()) and
                    {'preflight','schematic_simulation','drc','lvs','capacitance_extraction','post_layout_simulation','integrity'} <= stages.keys(), 'positive saved-bench stage')
            require(netlist((folder/'captured.spice').read_text(encoding='utf-8'), True)[0] == Counter({(Decimal('7e-6'),Decimal('7e-6')):2}), 'captured ordinary source')
            require('Final result: Circuits match uniquely.' in (folder/'job/lvs/lvs.log').read_text(encoding='utf-8'), 'native LVS result')
            proof = json.loads((folder/'job/parasitics/cmim-capacitance.json').read_text(encoding='utf-8'))
            require(proof['source_sha256'] == files[name+'/job/schematic.spice'] and
                    all(files.get(name+'/job/parasitics/'+n) == h for n,h in proof['files'].items()), 'graph source/file provenance')
            native = read_native(folder)
            results.append({'name':name, **native, **currents(folder, native)})
        else:
            require(actual['status'] == 'failed' and stages.get('lvs') == 'failed' and stages.get('capacitance_extraction') == 'not_run', 'intrinsic fault escaped LVS')
            require('Property errors were found.' in (folder/'job/lvs/lvs.log').read_text(encoding='utf-8'), 'native LVS fault evidence')
    return {'status':'PASS','qualified':False,'installed_acceptance':False,'positive_cases':len(positives),
            'native_lvs_faults':len(negatives),'files_verified':len(report['files']),'cases':results}
