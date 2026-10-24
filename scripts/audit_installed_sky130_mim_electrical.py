"""Independent live readback of the installed/source MiM electrical evidence.

No producer acceptance function is imported. Native raw parsing and the older
independent model-closure validator are reused; runtime provenance is new.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import installed_mim_inputs as inputs
from scripts.audit_sky130_mim_bias_boundaries import read_raw
from scripts.audit_sky130_mim_passive_corners import verify_models

require, sha, load = inputs.require, inputs.sha, inputs.load
SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
BRANCHES = ('schematic', 'extracted', 'independent')
PARAMETERS = ('rm3', 'rm4', 'rcvia3', 'rcvia4', 'tol_m3', 'tol_m4', 'camimc', 'cpmimc', 'm3_dw', 'm4_dw',
              'mc_mm_switch', 'mc_pr_switch')


def case_name(plate, section, rotation, bias):
    return f'p{plate}-{section}-r{rotation}-b'+{-5:'m5', 0:'0', 5:'p5'}[bias]


def case_inventory(report):
    require(type(report.get('pilot')) is bool, 'Pilot/full selection is absent.')
    expected = [(p,s,r,b) for p in (1,2) for s in (('tt',) if report['pilot'] else SECTIONS)
                for r in (0,90) for b in ((0,) if report['pilot'] else (-5,0,5))]
    names = [case_name(*v) for v in expected]
    require(report.get('selected_cases') == names and len(report.get('cases', [])) == len(expected) and
            {r['name'] for r in report['cases']} == set(names), 'Missing, duplicated or unexpected electrical context.')
    for row in report['cases']:
        context = (row['plate'], row['section'], row['rotation'], row['bias_V'])
        require(not any(isinstance(v, bool) for v in context) and context in expected and
                row['name'] == case_name(*context), 'Case label differs from its declared context.')
    return expected


def execution_title(identity, case, analysis, fault=None):
    token = hashlib.sha256(json.dumps(dict(identity=identity, case=case, analysis=analysis, fault=fault or 'positive'),
                                      sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return '* icstudio-installed-mim-v1 '+token


def observed(path, analysis, coefficients):
    rows = read_raw(path, analysis)
    names = {f'{kind}({terminal}_{key})' for key in BRANCHES for kind, terminal in (('v','p'),('v','n'),('i','vp'),('i','vn'))}
    names |= {'v(par_'+key+')' for key in PARAMETERS}
    if analysis == 'ac':
        names.add('frequency')
    for row in rows:
        require(set(row) == names, 'Native channel coverage differs.')
        for key in PARAMETERS:
            expected = coefficients.get(key, 0)
            require(abs(row['v(par_'+key+')']-expected) <= 1e-24+1e-10*abs(expected), 'Native coefficient/switch differs: '+key)
    return rows


def op(path, coefficients, p, n=0):
    row = observed(path, 'op', coefficients)[0]; result = {}
    for key in BRANCHES:
        vp,vn,ip,inn = (row[f'v(p_{key})'],row[f'v(n_{key})'],row[f'i(vp_{key})'],row[f'i(vn_{key})'])
        require(max(abs(vp-p), abs(vn-n), abs((vp-vn)-(p-n))) <= 1e-9, 'Native terminal bias differs.')
        require(max(abs(ip), abs(inn), abs(ip+inn)) <= 1e-12, 'Ideal-model DC current/KCL differs.')
        result[key] = dict(p_V=vp.real,n_V=vn.real,differential_V=(vp-vn).real,i_p_A=ip.real,i_n_A=inn.real)
    return result


def ac(path, coefficients, plate):
    metal = str(plate+2); delta = (coefficients['m'+metal+'_dw']+coefficients['tol_m'+metal])*1e6
    width, length = 2+delta, 10+delta
    resistance = coefficients['rm'+metal]*length/width + coefficients['rcvia'+metal]*(.56 if plate == 1 else .73)**2/(width*length)
    capacitance = coefficients['camimc']*width*length + 2*coefficients['cpmimc']*(width+length)
    require(all(math.isfinite(v) and v > 0 for v in (width,length,resistance,capacitance)), 'Invalid source-fixed RC target.')
    results = []
    for i,row in enumerate(observed(path, 'ac', coefficients)):
        f = row['frequency'].real
        require(math.isclose(f, 1e3*10**i, rel_tol=1e-12), 'Native frequency grid differs.')
        target = 1/complex(resistance, -1/(2*math.pi*f*capacitance)); branches = {}
        for key in BRANCHES:
            vp,vn,ip,inn = row[f'v(p_{key})'],row[f'v(n_{key})'],row[f'i(vp_{key})'],row[f'i(vn_{key})']
            require(abs(vp-1) <= 1e-12 and abs(vn) <= 1e-12, 'Native AC stimulus differs.')
            y = -ip/(vp-vn)
            require(y.real > 0 and y.imag > 0 and abs((ip+inn)/y) <= 1e-6, 'Native response is nonpassive or fails KCL.')
            r = (1/y).real; c = -1/(2*math.pi*f*(1/y).imag)
            error = max(abs(y/target-1),abs(r/resistance-1),abs(c/capacitance-1))
            require(error <= 1e-6, 'Native response differs from source-fixed analytical RC.')
            branches[key] = dict(Y_S=[y.real,y.imag],R_ohm=r,C_F=c,relative_error=error)
        reference = complex(*branches['independent']['Y_S'])
        require(all(abs(complex(*v['Y_S'])/reference-1) <= 1e-6 for v in branches.values()), 'Comparison branches differ.')
        results.append(dict(frequency_Hz=f,paths=branches))
    return dict(expected_R_ohm=resistance,expected_C_F=capacitance,samples=results)


def numeric(actual, expected, absolute=1e-24):
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected), 'Saved observable keys differ.')
        for key in expected:
            numeric(actual[key], expected[key], 1e-12 if key=='relative_error' else absolute)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), 'Saved observable count differs.')
        for a,e in zip(actual,expected):
            numeric(a,e,absolute)
    else:
        require(isinstance(actual,(int,float)) and not isinstance(actual,bool) and math.isfinite(actual) and
                math.isclose(actual,expected,rel_tol=1e-8,abs_tol=absolute), 'Saved numerical observable differs.')


def applied(bias, fault):
    require(fault in (None,'missing-bias','sign-reversed','clamped-bias','displaced-ground'), 'Unexpected bias control.')
    require(not fault or bias != 0 or fault == 'displaced-ground', 'Inapplicable zero-bias control.')
    high = 0 if fault == 'missing-bias' else -bias if fault == 'sign-reversed' else math.copysign(4.99,bias) if fault == 'clamped-bias' else bias
    return high, .5 if fault == 'displaced-ground' else 0


def check_deck(path, reference, native, staged, plate, bias, analysis, title, fault=None):
    """An independent literal contract prevents hidden/shunted extra branches."""
    high,low = applied(bias,fault)
    expected = title+'\n'+staged+'\n.param mc_mm_switch=0 mc_pr_switch=0\n.option tnom=27\n.temp 27\n'
    expected += reference+'\n'+f'.subckt independent P N\nX1 P N sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10 m=1\n.ends independent\n'
    expected += '.include '+Path(native).as_posix()+'\n'
    for key in BRANCHES:
        dc = '' if fault == 'missing-bias' else f'DC {high:g} '
        expected += f'VP_{key} p_{key} 0 {dc}AC 1\nVN_{key} n_{key} 0 DC {low:g} AC 0\n'
        expected += f'X_{key} p_{key} n_{key} '+('device_coupon' if key == 'extracted' else key)+'\n'
    for key in PARAMETERS:
        expected += f'VPAR_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}\n'
    saves = [f'{kind}({terminal}_{key})' for key in BRANCHES for kind,terminal in (('v','p'),('v','n'),('i','vp'),('i','vn'))]
    saves += ['v(par_'+key+')' for key in PARAMETERS]
    expected += ('.op\n' if analysis == 'op' else '.ac dec 1 1k 10G\n')+'.save '+' '.join(saves)+'\n.end\n'
    require(path.read_text() == expected, 'Executed circuit/directives differ from the independent deck contract.')


def check_execution(folder, saved, analysis, runtime, title):
    deck,raw,log = folder/'probe.cir',folder/'probe.raw',folder/'console.log'
    expected_command = [runtime['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(raw),str(deck)]
    require(saved.get('status') == 'PASS' and type(saved.get('returncode')) is int and saved.get('returncode') == 0 and saved.get('command') == expected_command and
            saved.get('cwd') == str(folder) and saved.get('environment') == runtime['environment'], 'Executed engine/context differs.')
    require(saved['deck_sha256'] == sha(deck) and saved['raw_sha256'] == sha(raw) and saved['log_sha256'] == sha(log), 'Native output binding differs.')
    header = raw.read_bytes().split(b'Values:',1)[0].split(b'Binary:',1)[0].decode().replace('\r\n','\n')
    require(re.findall(r'^Title:[ \t]*(.*)$',header,re.M) == [title], 'Stale/substituted raw context identity.')
    console = log.read_text(errors='replace')
    require(not re.search(r'(?im)^\s*(?:fatal error|error(?:\s|:))|unknown subckt|unknown parameter|singular matrix|timestep too small',console), 'Native console reports an error.')
    require(re.findall(r'No\. of Data Rows\s*:\s*(\d+)',console) == [('1' if analysis == 'op' else '8')], 'Native execution completion count differs.')


def staged_models(root, report, manifest):
    # SPICE includes always use slash-separated paths, while subprocess cwd and
    # arguments preserve native OS spelling. This is a model-only translation.
    return verify_models(root,{**report,'execution_root':root.as_posix()},manifest)


def audit(root):
    root = inputs.gui.unlinked(root).resolve(); manifest = load(root/'manifest.json')
    require(manifest == inputs.inventory(root, ('manifest.json','audit.json')), 'Evidence inventory changed or is incomplete.')
    report = load(root/'qualification.json')
    require(report.get('schema') == 1 and report.get('status') == 'PASS' and report.get('gate') == 'mim-installed-electrical60' and
            report.get('mode') in ('source-pilot','installed') and report.get('execution_root') == str(root), 'Electrical report is incomplete or relocated.')
    require(all(report.get(k) is False for k in ('qualified','release_ready','signoff','full_mim_installed')), 'Report exceeds the selected scope.')
    require(report.get('input_guards') == dict(runtime=True,sources=True,gui=True,public_contract=True,staged_models=True), 'Missing input guards.')
    case_inventory(report)
    require(report.get('installed_electrical_acceptance') is (report['mode']=='installed' and not report['pilot']), 'Installed/source claim differs.')
    binding = load(root/'inputs.json')
    require(sha(root/'inputs.json') == report['inputs_sha256'] and binding['mode'] == report['mode'] and
            binding['expected_commit'] == report['expected_commit'], 'Input receipt differs.')
    actual = inputs.bind_gui(binding['supplied_root'],binding['expected_commit'],source_pilot=binding['mode']=='source-pilot')
    require(actual == binding, 'Original GUI/native/bundle prerequisites no longer re-audit.')
    contract,mapped = inputs.contracts(binding)
    require(mapped == load(root/'mapped-sources.json') and sha(root/'contract.json') == report['contract_sha256'] == inputs.CONTRACT_SHA and
            sha(root/'bias-contract.json') == report['source_map_sha256'] == inputs.MAP_SHA, 'Reviewed source contracts differ.')
    source_files = load(root/'source-files.json')
    require(sha(root/'source-files.json') == report['source_files_sha256'] and source_files == inputs.source_files(), 'Electrical producer/checker source changed.')
    for name,digest in source_files.items():
        require(sha(inputs.gui.confined(root/'source',name)) == digest, 'Retained checker source differs.')
    if binding['mode']=='installed':
        inputs.candidate_sources(source_files,binding['expected_commit'])
    runtime = load(root/'runtime-before.json')
    require(sha(root/'runtime-before.json') == report['runtime_before_sha256'] and sha(root/'runtime-after.json') == report['runtime_after_sha256'] and
            runtime == load(root/'runtime-after.json'), 'Simulator runtime changed.')
    engine = inputs.select_engine(binding,Path(runtime['engine']) if binding['mode']=='source-pilot' else None)
    env = inputs.native_environment(binding,engine,root)
    require(env == runtime['environment'] and inputs.runtime(binding,engine,env) == runtime, 'Live simulator/configuration/dependencies differ.')
    require(re.fullmatch('[0-9a-f]{32}',report['execution_id']), 'Missing electrical execution identity.')
    identity = dict(execution_root=str(root),execution_id=report['execution_id'],gui_execution_id=binding['execution_id'],
                    inputs_sha256=sha(root/'inputs.json'),engine_sha256=sha(engine))
    require(report['context_identity'] == identity, 'Electrical context identity differs.')
    staged = staged_models(root,report,manifest)
    for key,case in binding['cases'].items():
        for kind,path in case['files'].items():
            require(sha(root/'gui-inputs'/key/(kind+Path(path).suffix)) == case['hashes'][kind], 'Copied GUI/native input differs.')
        for kind,filename,top in (('native','extracted.spice','device_coupon'),('reference','schematic.spice','schematic')):
            text = Path(case['files'][kind]).read_text()
            inputs.gui.circuit(text,case['top'],case['plate'],extracted=kind=='native')
            expected = re.sub(r'(?m)^(\.subckt|\.ends) '+re.escape(case['top'])+r'\b',lambda m:m[1]+' '+top,text)
            require((root/'normalized'/key/filename).read_text() == expected, 'Derived input changed beyond the top-name normalization.')
    domains = report['domain_controls']
    require([v['request'] for v in domains] == ['-5.001','5.001','nan','inf','-inf'] and all(v['status']=='REJECTED' and v['error'] for v in domains), 'Domain rejection coverage differs.')
    responses = {}; fault_count = 0
    for row in report['cases']:
        p,s,r,b = row['plate'],row['section'],row['rotation'],row['bias_V']; key = f'p{p}-r{r}'
        folder = root/row['name']; original = binding['cases'][key]; native = root/'normalized'/key/'extracted.spice'
        require(row['status']=='PASS' and load(folder/'record.json') == row and row['gui_case']==key and
                row['gui_job_id']==original['job_id'] and row['native_original_sha256']==original['hashes']['native'] and
                row['native_path']==str(native) and row['native_sha256']==sha(native), 'Case is bound to another GUI/native input.')
        coefficients = contract['passive_sections'][s]['coefficients']; reference = (root/'normalized'/key/'schematic.spice').read_text()
        require(set(row['analyses']) == {'op','ac'}, 'Positive analysis coverage differs.')
        for analysis in ('op','ac'):
            saved = row['analyses'][analysis]; dest = folder/analysis; title = execution_title(identity,row['name'],analysis)
            check_execution(dest,saved,analysis,runtime,title)
            check_deck(dest/'probe.cir',reference,native,staged[s],p,b,analysis,title)
            numeric(saved['coefficients'],{k:coefficients.get(k,0) for k in PARAMETERS})
            if analysis=='op':
                numeric(saved['paths'],op(dest/'probe.raw',coefficients,b))
            else:
                derived = ac(dest/'probe.raw',coefficients,p)
                for field,value in derived.items():
                    numeric(saved[field],value)
                responses[(p,s,r,b)] = derived['samples']
        expected_faults = (['missing-bias','sign-reversed','clamped-bias'] if b else [])+['displaced-ground']
        require([v.get('fault') for v in row['controls']] == expected_faults, 'Fault control coverage differs.')
        for saved in row['controls']:
            fault = saved['fault']; high,low = applied(b,fault); dest = folder/'controls'/fault
            title = execution_title(identity,row['name'],'op',fault)
            require(saved.get('detected') is True and saved['intended_bias_V']==b and saved['applied_bias_V']==high and
                    saved['applied_ground_V']==low and bool(saved['rejection']), 'Fault claim differs.')
            check_execution(dest,saved,'op',runtime,title); check_deck(dest/'probe.cir',reference,native,staged[s],p,b,'op',title,fault)
            numeric(saved['paths'],op(dest/'probe.raw',coefficients,high,low))
            numeric(saved['coefficients'],{k:coefficients.get(k,0) for k in PARAMETERS})
            try:
                op(dest/'probe.raw',coefficients,b)
            except ValueError as error:
                require(str(error)=='Native terminal bias differs.', 'Bias control failed for an unrelated reason.')
            else:
                raise ValueError('Declared fault actually passed the intended bias.')
            fault_count += 1
    comparisons = 0
    for (p,s,r,b),values in responses.items():
        require((p,s,r,0) in responses, 'Missing zero-bias reference.')
        if b == 0:
            continue
        for current,zero in zip(values,responses[(p,s,r,0)]):
            for key in BRANCHES:
                a,z = current['paths'][key],zero['paths'][key]
                require(max(abs(complex(*a['Y_S'])/complex(*z['Y_S'])-1),abs(a['R_ohm']/z['R_ohm']-1),abs(a['C_F']/z['C_F']-1)) <= 1e-6,
                        'Linear-model response differs from the matching zero-bias context.')
        comparisons += 1
    counts = dict(contexts=len(responses),ac_samples=8*len(responses),op_points=len(responses),bias_faults=fault_count,
                  domain_rejections=5,bias_invariance_contexts=comparisons,fresh_gui_native_inputs=4)
    require(counts == (dict(contexts=4,ac_samples=32,op_points=4,bias_faults=4,domain_rejections=5,bias_invariance_contexts=0,fresh_gui_native_inputs=4) if report['pilot'] else
            dict(contexts=60,ac_samples=480,op_points=60,bias_faults=180,domain_rejections=5,bias_invariance_contexts=40,fresh_gui_native_inputs=4)), 'Required totals differ.')
    return dict(schema=1,status='PASS',mode=report['mode'],installed_electrical_acceptance=report['installed_electrical_acceptance'],
                full_mim_installed=False,qualified=False,signoff=False,counts=counts,qualification_sha256=sha(root/'qualification.json'),
                inputs_sha256=sha(root/'inputs.json'),runtime_check='live_actual_engine_configuration_and_dependencies',audit_sha256=sha(__file__))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True); a = parser.parse_args()
    result = audit(a.root); inputs.write(a.out,result); print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
