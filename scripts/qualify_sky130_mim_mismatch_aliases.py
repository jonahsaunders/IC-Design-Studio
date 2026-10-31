"""Finite source-only integration of actual SKY130 MiM mismatch library aliases.

Four deterministic replicas per model do not calibrate distributions/correlations.
No physical, installed, complete-family or manufacturing acceptance is claimed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import parse_raw
from icstudio.interchange import spice
from icstudio.model import clone, example, save_project
from icstudio.pdks import model_lines, stage_model_deck
from scripts import installed_mim_inputs as identity

CONTRACT = 'docs/qualification/sky130-mim-mismatch-aliases-v1.json'
CONTRACT_SHA = 'b31cff4a8fbbd844a759f16ec7a61c34c590a76ed330c31f325a0d182259a400'
SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
PARAMETERS = ('rm3','rm4','rcvia3','rcvia4','tol_m3','tol_m4','camimc','cpmimc','m3_dw','m4_dw','mc_mm_switch','mc_pr_switch')
sha, require, write = identity.sha, identity.require, identity.write


def contract():
    path = ROOT/CONTRACT
    require(sha(path) == CONTRACT_SHA, 'Mismatch alias contract changed.')
    result = json.loads(path.read_bytes())
    original = result['original_contract']
    require(sha(ROOT/original['path']) == original['sha256'], 'Original MiM contract changed.')
    return result


def rows():
    return [dict(tag=f'p{plate}t{trial}', plate=plate,
                 model=f'sky130_fd_pr__cap_mim_m3_{plate}',
                 key=f'sky130_fd_pr/cap_mim_m3_{plate}.sym')
            for plate in (1, 2) for trial in range(4)]


def selection(pilot=False):
    result = []
    for section in SECTIONS[:1] if pilot else SECTIONS:
        for multiplier in (1, 4):
            for variant in ('application-alias', 'literal-alias', 'application-base'):
                result.append(dict(section=section, multiplier=multiplier, variant=variant))
        for variant in ('wrong-alias', 'wrong-mf', 'missing-m'):
            result.append(dict(section=section, multiplier=1 if variant == 'wrong-alias' else 4, variant=variant))
    for item in result:
        section = item['section']
        actual = SECTIONS[(SECTIONS.index(section)+1) % len(SECTIONS)] if item['variant']=='wrong-alias' else section
        item.update(name=f'{section}-m{item["multiplier"]}-{item["variant"]}',
                    actual_section=actual+('' if item['variant']=='application-base' else '_mm'))
    return result


def fixture(tech, multiplier):
    project = example('empty'); project['pdk'] = clone(tech)
    for row in rows():
        device = create_device(tech, row['key'], row['tag'])
        device['model_params'].update(w=2, l=10, mf=multiplier)
        device['nets'] = dict(c0=row['tag'], c1='0')
        project['cells'][0]['devices'].append(device)
    return project


def title(execution, case):
    token = hashlib.sha256(json.dumps(dict(execution=execution, case=case), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return '* icstudio-mim-mismatch-v1 '+token


def deck(case, staged, application_calls, execution):
    variant, multiplier = case['variant'], case['multiplier']
    if variant.startswith('application') or variant == 'wrong-alias':
        calls = application_calls[multiplier]
    else:
        mf = 1 if variant == 'wrong-mf' else multiplier
        count = '' if variant == 'missing-m' else f' m={multiplier}'
        calls = [f'X_{r["tag"]} {r["tag"]} 0 {r["model"]} w=2 l=10 mf={mf}{count}' for r in rows()]
    lines = [title(execution, case['name']), staged[case['actual_section']],
             '.option seed=20261024 tnom=27', '.temp 27']
    lines += [f'V{r["tag"]} {r["tag"]} 0 DC 0 AC 1' for r in rows()]
    lines += calls
    lines += [f'Vpar_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}' for name in PARAMETERS]
    channels = [v for r in rows() for v in (f'v({r["tag"]})', f'i(v{r["tag"]})')]
    channels += [f'v(par_{name})' for name in PARAMETERS]
    lines += ['.save '+' '.join(channels), '.ac dec 1 1k 100k', '.end', '']
    return '\n'.join(lines)


def expected_parameters(section, spec):
    base = section.removesuffix('_mm')
    return {**spec['sections'][base]['coefficients'], 'mc_mm_switch':int(section.endswith('_mm')), 'mc_pr_switch':0}


def check_parameters(actual, section, spec):
    expected = expected_parameters(section, spec)
    require(set(actual) == set(expected), 'Incomplete effective coefficient probes.')
    for name, value in expected.items():
        tolerance = spec['tolerances']['coefficient_absolute']+abs(value)*spec['tolerances']['coefficient_relative']
        require(math.isfinite(actual[name]) and abs(actual[name]-value) <= tolerance,
                'Effective source coefficient differs: '+name)


def analytical(plate, parameters):
    metal = plate+2
    w = 2+1e6*(parameters[f'm{metal}_dw']+parameters[f'tol_m{metal}'])
    l = 10+1e6*(parameters[f'm{metal}_dw']+parameters[f'tol_m{metal}'])
    capacitance = parameters['camimc']*w*l+2*parameters['cpmimc']*(w+l)
    pitch = .56 if plate == 1 else .73
    resistance = parameters[f'rm{metal}']*l/w+parameters[f'rcvia{metal}']*pitch*pitch/(w*l)
    return resistance, capacitance


def raw_values(path, expected_title, section, spec, multiplier):
    headers = path.read_bytes().split(b'Variables:', 1)[0].decode('ascii')
    titles = [line.partition(':')[2].strip() for line in headers.splitlines() if line.lower().startswith('title:')]
    require(titles == [expected_title.lower()], 'Raw output belongs to another execution/case.')
    for key,value in (('plotname','AC Analysis'),('flags','complex')):
        require([line.partition(':')[2].strip() for line in headers.splitlines() if line.lower().startswith(key+':')]==[value],
                'Expected one complex AC analysis.')
    names, data, complex_data = parse_raw(path)
    expected_names = {'frequency', *[v for r in rows() for v in (f'v({r["tag"]})', f'i(v{r["tag"]})')],
                      *[f'v(par_{name})' for name in PARAMETERS]}
    require(complex_data and len(data)==3 and len(names)==len(set(names)) and set(names)==expected_names,
            'Expected exact three-point AC channels.')
    values = {}; coefficients = None
    for index, (sample, frequency) in enumerate(zip(data, spec['experiment']['frequencies_hz'])):
        actual_frequency = sample[names.index('frequency')].real
        require(math.isfinite(actual_frequency) and abs(actual_frequency/frequency-1)<=spec['tolerances']['frequency_relative'],
                'Unexpected frequency sample.')
        # ngspice does not initialize the unused imaginary frequency slot.
        require(all(math.isfinite(value.real) and math.isfinite(value.imag) for name,value in zip(names,sample) if name!='frequency'),
                'Nonfinite physical sample or coefficient.')
        probes = {key:sample[names.index('v(par_'+key+')')] for key in PARAMETERS}
        require(all(v.imag==0 for v in probes.values()), 'Coefficient probes have a phase.')
        params = {key:value.real for key,value in probes.items()}
        check_parameters(params, section, spec)
        require(coefficients is None or coefficients==params, 'Coefficient probes changed with frequency.')
        coefficients = params
        for row in rows():
            voltage = sample[names.index('v('+row['tag']+')')]
            current = sample[names.index('i(v'+row['tag']+')')]
            require(abs(voltage-1)<=spec['tolerances']['absolute_applied_voltage'] and current!=0, 'Wrong AC normalization or missing current.')
            impedance = voltage/-current
            require(impedance.imag<0, 'Noncapacitive terminal response.')
            resistance, capacitance = impedance.real, -1/(2*math.pi*frequency*impedance.imag)
            require(math.isfinite(resistance) and math.isfinite(capacitance) and resistance>0 and capacitance>0, 'Invalid series RC.')
            values.setdefault(row['tag'], []).append(dict(frequency_Hz=frequency, resistance_ohm=resistance, capacitance_F=capacitance))
    for row in rows():
        samples = values[row['tag']]
        require(max(s['capacitance_F'] for s in samples)/min(s['capacitance_F'] for s in samples)-1<=1e-8,
                'Capacitance differs across selected frequencies.')
        resistance, capacitance = analytical(row['plate'], coefficients)
        for sample in samples:
            require(abs(sample['resistance_ohm']/(resistance/multiplier)-1)<=spec['tolerances']['relative_analytical_rc'], 'Series resistance differs from source law.')
            if not section.endswith('_mm'):
                require(abs(sample['capacitance_F']/(capacitance*multiplier)-1)<=spec['tolerances']['relative_analytical_rc'], 'Base capacitance differs from source law.')
    return dict(coefficients=coefficients, samples=values, capacitances_F={key:value[0]['capacitance_F'] for key,value in values.items()})


def comparisons(results, selected_sections, spec):
    out = []
    for section in selected_sections:
        result = lambda m, variant: results[f'{section}-m{m}-{variant}']
        cap = lambda m, variant: result(m, variant)['raw']['capacitances_F']
        base, unit = cap(1,'application-base'), cap(1,'application-alias')
        deltas = {name:unit[name]/base[name]-1 for name in base}
        for plate in (1,2):
            selected = [value for name,value in deltas.items() if name.startswith(f'p{plate}')]
            require(max(abs(v) for v in selected)>spec['tolerances']['minimum_max_fractional_mismatch'], 'Mismatch selection produced no detectable variation.')
        mapping = scaling = nominal = 0
        for m in (1,4):
            app, literal, deterministic = cap(m,'application-alias'), cap(m,'literal-alias'), cap(m,'application-base')
            mapping=max(mapping,max(abs(app[k]/literal[k]-1) for k in base))
            scaling=max(scaling,max(abs(app[k]/(m*base[k])-1-deltas[k]/math.sqrt(m)) for k in base))
            nominal=max(nominal,max(abs(deterministic[k]/(m*base[k])-1) for k in base))
        require(mapping<=spec['tolerances']['relative_mapping'] and scaling<=spec['tolerances']['absolute_fractional_mf_scaling'] and nominal<=spec['tolerances']['relative_base_scaling'],
                'Application mapping or paired MF law differs.')
        rejected = []
        for key, actual in (('wrong-alias',result(1,'wrong-alias')),('disabled-mismatch',result(1,'application-base'))):
            try: check_parameters(actual['raw']['coefficients'], section+'_mm', spec)
            except ValueError: rejected.append(key)
            else: raise ValueError('A wrong library selection escaped its intended-section check.')
        for key in ('wrong-mf','missing-m'):
            wrong, correct = cap(4,key), cap(4,'application-alias')
            require(all(abs(wrong[name]/correct[name]-1)>spec['tolerances']['relative_mapping'] for name in base), 'An incorrect MF/m binding escaped detection.')
            rejected.append(key)
        out.append(dict(section=section, max_relative_mapping=mapping, max_absolute_fractional_mf_scaling=scaling,
                        max_relative_base_scaling=nominal, unit_fractional_deltas=deltas, detected_controls=rejected))
    return out


def source_files():
    paths = {Path(__file__), ROOT/CONTRACT, ROOT/'docs/qualification/sky130-mim-contract-v1.json',
             ROOT/'tests/test_sky130_mim_mismatch_aliases.py'}
    paths.update(ROOT/name for name in ('scripts/audit_sky130_mim_mismatch_aliases.py',
        'tests/test_sky130_mim_mismatch_alias_audit.py'))
    paths.update(Path(module.__file__).resolve() for module in list(sys.modules.values())
                 if getattr(module,'__file__',None) and Path(module.__file__).suffix=='.py' and Path(module.__file__).resolve().is_relative_to(ROOT))
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)}


def scope_check(value):
    require(value.get('mode')=='source-integration' and all(value.get(k) is False for k in
        ('qualified','installed_acceptance','full_mim_installed','chunk_complete','release_ready','signoff')),
        'Source integration cannot claim installed or complete family acceptance.')


def run(out, engine, *, pilot=False, workers=2):
    require(workers in range(1,5), 'Select one to four workers.')
    require(sys.dont_write_bytecode and sys.pycache_prefix and not Path(sys.pycache_prefix).exists(),
            'Run with -B and a fresh nonexistent -X pycache_prefix for exact source execution.')
    out = identity.gui.unlinked(out).resolve()
    require(not out.exists() and not any(c.isspace() for c in str(out)), 'Use a fresh output directory without whitespace.')
    out.mkdir(parents=True)
    started = time.monotonic()
    execution = dict(root=str(out), nonce=uuid.uuid4().hex)
    report = dict(schema=1, gate='sky130-mim-mismatch-aliases-v1', status='RUNNING', mode='source-integration',
        qualified=False, installed_acceptance=False, full_mim_installed=False, chunk_complete=False, release_ready=False,
        signoff=False, source_integration_acceptance=False, execution=execution, pilot=pilot, cases=[], scope=__doc__)
    scope_check(report)
    try:
        spec = contract(); (out/'contract.json').write_bytes((ROOT/CONTRACT).read_bytes())
        package_root = ROOT/spec['package']['path']; package = json.loads((package_root/'package.json').read_bytes())
        require(sha(package_root/'package.json')==spec['package']['manifest_sha256'] and package['revision']==spec['package']['revision'], 'Unreviewed simulation package.')
        tech=clone(package['technology']); tech.update(package_root=str(package_root),package_lock={k:package[k] for k in ('id','revision','files')})
        package_files={'package.json':sha(package_root/'package.json'),**package['files']}
        for name,digest in package_files.items():
            p=identity.gui.unlinked(package_root/name).resolve()
            require(p.is_relative_to(package_root.resolve()) and sha(p)==digest, 'Package asset changed.')
            target=out/'original-package'/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(p.read_bytes())
        write(out/'package-files.json', package_files)
        staged={}
        for section in [v for s in SECTIONS for v in (s,s+'_mm')]:
            staged[section]=stage_model_deck(tech, '\n'.join(model_lines(tech,section)), out)
        write(out/'selected-model-lines.json',staged)
        staged_files=identity.inventory(out/'pdk-models')
        write(out/'staged-model-files.json',staged_files)
        application={}
        for m in (1,4):
            project=fixture(tech,m); save_project(project,out/f'project-m{m}.icproj')
            application[m]=[line for line in spice(project).splitlines() if line.startswith('X_')]
            require(len(application[m])==len(rows()), 'Application export lost an instance.')
            (out/f'application-m{m}.spice').write_text('\n'.join(application[m])+'\n',encoding='utf-8')
        engine=identity.checked_path(engine)
        binding=dict(mode='source-pilot')
        env=identity.native_environment(binding,engine,out)
        before=identity.runtime(binding,engine,env); write(out/'runtime-before.json',before)
        runtime_assets={}
        for name,digest in {**before['files'],**{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}}.items():
            target=out/'runtime-assets'/digest; target.parent.mkdir(exist_ok=True)
            if not target.exists(): target.write_bytes(Path(name).read_bytes())
            require(sha(target)==digest,'Runtime changed while retaining it.'); runtime_assets[name]=digest
        write(out/'runtime-assets.json',runtime_assets)
        sources=source_files(); write(out/'source-files.json',sources)
        for name,digest in sources.items():
            p=out/'source'/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes((ROOT/name).read_bytes())
            require(sha(p)==digest,'Source changed during capture.')
        selected=selection(pilot)
        report.update(selected_cases=[c['name'] for c in selected],contract_sha256=CONTRACT_SHA,
            package=spec['package'],source_files_sha256=sha(out/'source-files.json'),
            runtime_before_sha256=sha(out/'runtime-before.json'),source_root=str(ROOT),
            python=dict(executable=sys.executable,sha256=sha(Path(sys.executable)),version=sys.version,
                        pycache_prefix=sys.pycache_prefix,dont_write_bytecode=sys.dont_write_bytecode))
        write(out/'qualification.json',report)
        def one(case):
            folder=out/case['name']; folder.mkdir()
            text=deck(case,staged,application,execution); (folder/'input.cir').write_text(text,encoding='utf-8',newline='\n')
            command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(folder/'input.cir')]
            record={**case,'status':'RUNNING','command':command,'cwd':str(out),'environment':env}
            try:
                proc=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=120)
                log=proc.stdout+proc.stderr; (folder/'console.log').write_text(log,encoding='utf-8')
                require(proc.returncode==0 and 'error' not in log.lower() and 'unknown parameter' not in log.lower(), 'Native simulator failed; inspect retained log.')
                effective_count=1 if case['variant']=='missing-m' else case['multiplier']
                record['raw']=raw_values(folder/'result.raw',title(execution,case['name']),case['actual_section'],spec,effective_count)
                record.update(status='PASS',returncode=proc.returncode,raw_sha256=sha(folder/'result.raw'),deck_sha256=sha(folder/'input.cir'),log_sha256=sha(folder/'console.log'))
            except Exception: record.update(status='FAIL',error=traceback.format_exc())
            write(folder/'record.json',record)
            return record
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(one,c) for c in selected]):
                value=future.result(); report['cases'].append(value); write(out/'qualification.json',report)
                print(value['name'],value['status'],flush=True)
        require(len(report['cases'])==len(selected) and all(c['status']=='PASS' for c in report['cases']), 'Native cases failed.')
        report['comparisons']=comparisons({c['name']:c for c in report['cases']},SECTIONS[:1] if pilot else SECTIONS,spec)
        after=identity.runtime(binding,engine,env); write(out/'runtime-after.json',after)
        require(before==after,'Simulator runtime changed during execution.')
        require(all(sha(ROOT/n)==d for n,d in sources.items()),'Captured source changed during execution.')
        require(all(sha(package_root/n)==d for n,d in package_files.items()),'Original package changed during execution.')
        require(staged_files==identity.inventory(out/'pdk-models'),'Staged models changed during execution.')
        report.update(status='PASS',source_integration_acceptance=True,runtime_after_sha256=sha(out/'runtime-after.json'),
            guards=dict(source=True,package=True,staged_models=True,runtime=True))
    except Exception: report.update(status='FAIL',error=traceback.format_exc())
    report['cases'].sort(key=lambda c:c['name']); report['seconds']=time.monotonic()-started
    scope_check(report); write(out/'qualification.json',report)
    write(out/'manifest.json',identity.inventory(out,('manifest.json',)))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ngspice',type=Path,required=True)
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    report=run(args.out,args.ngspice,pilot=args.pilot,workers=args.workers)
    print(json.dumps({k:report[k] for k in ('status','seconds','source_integration_acceptance')},indent=2))
    if report['status']!='PASS': raise SystemExit(1)


if __name__=='__main__': main()
