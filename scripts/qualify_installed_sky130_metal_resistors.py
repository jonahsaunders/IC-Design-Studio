"""Selected electrical checks of fresh installed GUI/export/native resistor inputs.

Source pilots are distinct from installed acceptance. These finite compact-model
checks do not qualify continuous ranges, silicon accuracy or foundry signoff.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from urllib.parse import unquote, urlsplit
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.pdks import model_lines, stage_model_deck
from scripts import installed_metal_resistor_inputs as inputs
from scripts import qualify_sky130_metal_resistors_linked as original

sha,write,require=inputs.sha,inputs.write,inputs.require
ENGINE_SOURCES='docs/qualification/ngspice42-metal-reference'


def execution_identity(out, nonce):
    require(len(nonce)==32 and all(c in '0123456789abcdef' for c in nonce),'Invalid execution nonce.')
    return dict(root=unquote(urlsplit(out.resolve().as_uri()).path),nonce=nonce)


def case_key(row):
    return f'{row["model"]}-g{row["geometry_index"]}-r{row["rotation"]}'


def retain_inputs(binding, spec, out):
    normalized={};faults={}
    for key,row in binding['cases'].items():
        if row['model'] not in spec['experiment']['models']:continue
        normalized[key]={};faults[key]={}
        for kind,source_kind in (('application','reference'),('native','native')):
            source=Path(row['files'][source_kind]);raw=source.read_bytes()
            require(sha(source)==row['hashes'][source_kind],'Fresh GUI/native input changed.')
            retained=out/'original-inputs'/key/(kind+'.spice');retained.parent.mkdir(parents=True,exist_ok=True);retained.write_bytes(raw)
            data,proof=inputs.normalize_top(raw,row['top']);inputs.resistor_tokens(data,row,application=kind=='application')
            target=out/'normalized-inputs'/key/(kind+'.spice');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            normalized[key][kind]=dict(original_path=str(source),original_sha256=sha(source),retained_path=str(retained),
                normalized_path=str(target),normalized_sha256=sha(target),proof=proof)
            if kind=='application':
                for fault in spec['experiment']['faults']:
                    altered,mutation=inputs.fault_copy(data,row,fault)
                    target=out/'fault-inputs'/key/(fault+'.spice');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(altered)
                    faults[key][fault]=dict(path=str(target),sha256=sha(target),source_sha256=proof['normalized_sha256'],proof=mutation)
    require(len(normalized)==24,'Expected all twenty-four current GUI/native inputs.')
    write(out/'normalized-inputs.json',normalized);write(out/'fault-inputs.json',faults)
    return normalized,faults


def deck(spec, case, rows, staged, normalized, faults, execution, folder):
    """Assemble wrappers around retained actual application/native bytes."""
    section=case['section'];temperature=case['temperature_c']
    if case['control']=='wrong-section':
        sections=spec['experiment']['sections'];section=sections[(sections.index(section)+1)%len(sections)]
    if case['control']=='wrong-temperature':temperature+=17
    accuracy='.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear'
    if case['analysis']=='tran':accuracy+=' chgtol=1e-24 trtol=1'
    lines=[original.title(execution,case['name']),staged[section],accuracy,f'.temp {temperature}']
    e=spec['experiment']
    if case['analysis']=='tran':
        pulse=' '.join(format(e[k],'.17g') for k in ('pulse_low_v','pulse_high_v','pulse_delay_s','pulse_edge_s','pulse_edge_s','pulse_width_s','pulse_period_s'))
        lines.append(f'VDRIVE input 0 PULSE({pulse}) AC 1')
    else:lines.append('VDRIVE input 0 DC .0005 AC 1')
    used=set()
    for row in rows:
        tag=row['branch'];lines.append(f'VS_{tag} input in_{tag} DC 0 AC 0')
        if row['kind']=='analytic':
            value=original.resistance(spec,row,case['section'],case['temperature_c'])
            lines.append(f'RC_{tag} in_{tag} out_{tag} {value:.17g}')
        else:
            key=case_key(row);kind=row['kind'];fault=row['fault']
            wrapper=kind+'_'+key.replace('-','_')+('_'+fault.replace('-','_') if fault else '')
            path=Path(faults[key][fault]['path'] if fault else normalized[key][kind]['normalized_path'])
            require(not any(c.isspace() for c in str(path)),'Native include path contains whitespace.')
            if wrapper not in used:
                lines += [f'.subckt {wrapper} a b',f'.include {path.as_posix()}',
                          'X_COUPON a b coupon',f'.ends {wrapper}'];used.add(wrapper)
            for n in range(row['multiplicity']):
                lines.append(f'X_{tag}_{n} in_{tag} out_{tag} {wrapper}')
        lines += [f'RL_{tag} out_{tag} 0 1',f'CL_{tag} out_{tag} 0 1n']
    coefficients=spec['sections'][section]['coefficients']
    lines += [f'VP_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}' for name in coefficients]
    channels=['v(input)']+[v for row in rows for v in
        (f'v(in_{row["branch"]})',f'v(out_{row["branch"]})',f'i(vs_{row["branch"]})')]
    channels += [f'v(par_{name})' for name in coefficients]
    if case['analysis']=='noise':
        lines += ['.control','set filetype=ascii']
        for index,row in enumerate(rows):
            tag=row['branch'];target=(folder/f'noise_{tag}.raw').as_posix()
            lines += [f'echo BEGIN_NOISE_{tag}',f'noise v(out_{tag}) VDRIVE dec 3 1k 10g',
                f'setplot noise{index*2+1}',f'let noise_{tag} = onoise_spectrum',
                f'write {target} frequency noise_{tag}',f'echo END_NOISE_{tag}']
        lines += ['quit 0','.endc']
    else:lines += ['.save '+' '.join(channels),dict(dc='.dc VDRIVE -.001 .001 .0001',ac='.ac dec 3 1k 10g',tran='.tran 20p 21n')[case['analysis']]]
    return '\n'.join([*lines,'.end','']),section,temperature


def execute_case(spec,case,logical,staged,normalized,faults,execution,out,engine,env):
    folder=out/case['name'];folder.mkdir();rows=original.branches(spec,logical,case['analysis'],case['control'])
    text,section,temp=deck(spec,case,rows,staged,normalized,faults,execution,folder)
    (folder/'input.cir').write_text(text,encoding='utf-8',newline='\n')
    command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b']
    if case['analysis']!='noise':command += ['-r',str(folder/'result.raw')]
    command += [str(folder/'input.cir')]
    value={**case,'status':'RUNNING','branches':rows,'actual_section':section,'actual_temperature_c':temp,
        'command':command,'cwd':str(out),'environment':env}
    try:
        proc=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=180)
        log=proc.stdout+proc.stderr;(folder/'console.log').write_text(log,encoding='utf-8')
        require(proc.returncode==0 and 'error' not in log.lower() and 'unknown parameter' not in log.lower(),'Native simulator failed; inspect its log.')
        if case['control']=='positive':value['observation']=original.observe(spec,case,rows,folder,execution)
        else:
            try:original.observe(spec,case,rows,folder,execution)
            except ValueError as exc:value['detected']=str(exc)
            else:raise ValueError('Wrong section/temperature escaped the intended-context check.')
        value.update(status='PASS',returncode=proc.returncode,deck_sha256=sha(folder/'input.cir'),log_sha256=sha(folder/'console.log'))
        if case['analysis']!='noise':value['raw_sha256']=sha(folder/'result.raw')
    except Exception:value.update(status='FAIL',error=traceback.format_exc())
    write(folder/'record.json',value);return value


def run(gui_root,out,expected_commit=None,*,source_pilot=False,source_engine=None,pilot=False,workers=2):
    require(workers in range(1,5),'Select one to four workers.')
    out=inputs.common.gui.unlinked(out).resolve()
    require(not out.exists() and not any(c.isspace() for c in str(out)),
            'Use a fresh absolute output directory without whitespace.')
    out.mkdir(parents=True);started=time.monotonic();execution=execution_identity(out,uuid.uuid4().hex)
    report=dict(schema=1,gate='sky130-metal-installed-electrical-v1',status='RUNNING',mode='source-pilot' if source_pilot else 'installed',
        qualified=False,installed_acceptance=False,full_family=False,chunk_complete=False,release_ready=False,signoff=False,
        installed_electrical_acceptance=False,pilot=pilot,execution=execution,execution_directory=str(out),
        expected_commit=expected_commit,cases=[],scope=__doc__)
    write(out/'qualification.json',report)
    try:
        binding=inputs.bind_gui(gui_root,expected_commit,source_pilot=source_pilot);write(out/'inputs.json',binding)
        installed,spec,mapped=inputs.contracts(binding);write(out/'contract-sources.json',mapped)
        (out/'contract.json').write_bytes((ROOT/installed['source_contract']['path']).read_bytes())
        (out/'installed-contract.json').write_bytes((ROOT/inputs.CONTRACT).read_bytes())
        for name,row in spec['engine_sources'].items():
            path=ROOT/ENGINE_SOURCES/name;require(sha(path)==row['sha256'],'Primitive reference source changed.')
            target=out/'engine-reference'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        sources=inputs.source_files()
        if not source_pilot:inputs.candidate_sources(sources,expected_commit)
        write(out/'source-files.json',sources)
        for name,digest in sources.items():
            target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
            require(sha(target)==digest,'Source changed during capture.')
        package_root=Path(binding['simulation_package']['path']);package=inputs.load(package_root/'package.json')
        package_files={'package.json':sha(package_root/'package.json'),**package['files']}
        for name,digest in package_files.items():
            path=inputs.common.gui.unlinked(package_root/name);require(sha(path)==digest,'Simulation package changed.')
            target=out/'original-package'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        write(out/'package-files.json',package_files)
        normalized,faults=retain_inputs(binding,spec,out)
        normalized_files=inputs.inventory(out/'normalized-inputs');fault_files=inputs.inventory(out/'fault-inputs')
        original_files=inputs.inventory(out/'original-inputs')
        tech=inputs.technology(binding)
        require(tech['simulation'].get('ngspice_compatibility')=='hsa','Unexpected simulator compatibility mode.')
        staged={section:stage_model_deck(tech,'\n'.join(model_lines(tech,section)),out) for section in spec['experiment']['sections']}
        write(out/'selected-model-lines.json',staged)
        staged_files=inputs.inventory(out/'pdk-models');write(out/'staged-model-files.json',staged_files)
        engine=inputs.select_engine(binding,source_engine);env=inputs.native_environment(binding,engine,out)
        before=inputs.runtime(binding,engine,env);write(out/'runtime-before.json',before)
        runtime_files={**before['files'],**{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}}
        original.retain_files(runtime_files,out/'runtime-assets');write(out/'runtime-assets.json',runtime_files)
        logical=original.logical_rows(spec,pilot);selected=original.selection(spec,pilot)
        report.update(inputs_sha256=sha(out/'inputs.json'),gui_execution_id=binding['execution_id'],
            contract_sha256=original.CONTRACT_SHA,installed_contract_sha256=inputs.CONTRACT_SHA,
            contract_sources_sha256=sha(out/'contract-sources.json'),source_files_sha256=sha(out/'source-files.json'),source_root=str(ROOT),
            simulation_package=binding['simulation_package'],logical_rows=logical,selected_cases=[c['name'] for c in selected],
            normalized_inputs_sha256=sha(out/'normalized-inputs.json'),fault_inputs_sha256=sha(out/'fault-inputs.json'),
            runtime_before_sha256=sha(out/'runtime-before.json'))
        write(out/'qualification.json',report)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs=[pool.submit(execute_case,spec,case,logical,staged,normalized,faults,execution,out,engine,env) for case in selected]
            for future in as_completed(jobs):
                value=future.result();report['cases'].append(value);write(out/'qualification.json',report)
                print(value['name'],value['status'],flush=True)
        after=inputs.runtime(binding,engine,env);write(out/'runtime-after.json',after)
        require(before==after,'Native simulator runtime changed.')
        require(sources==inputs.source_files(),'Qualification source changed.')
        require(binding==inputs.bind_gui(gui_root,expected_commit,source_pilot=source_pilot),'Fresh GUI/native prerequisite changed.')
        require(mapped==inputs.contracts(binding)[2],'Contract/package inputs changed.')
        require(all(sha(package_root/n)==d for n,d in package_files.items()),'Original package changed.')
        require(staged_files==inputs.inventory(out/'pdk-models'),'Staged model files changed.')
        require(normalized_files==inputs.inventory(out/'normalized-inputs') and fault_files==inputs.inventory(out/'fault-inputs')
            and original_files==inputs.inventory(out/'original-inputs'),'Retained native/application inputs changed.')
        require(len(report['cases'])==len(selected) and all(c['status']=='PASS' for c in report['cases']),'Electrical acceptance failed.')
        report.update(status='PASS',runtime_after_sha256=sha(out/'runtime-after.json'),
            input_guards=dict(runtime=True,sources=True,gui=True,public_contract=True,simulation_package=True,staged_models=True,retained_inputs=True),
            installed_electrical_acceptance=not source_pilot and not pilot)
    except Exception:report.update(status='FAIL',error=traceback.format_exc(),installed_electrical_acceptance=False)
    report['cases'].sort(key=lambda row:row['name']);report['seconds']=time.monotonic()-started
    write(out/'qualification.json',report);write(out/'manifest.json',inputs.inventory(out,('manifest.json',)))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--expected-commit')
    parser.add_argument('--source-pilot',action='store_true')
    parser.add_argument('--source-engine',type=Path)
    parser.add_argument('--pilot',action='store_true',help='Six selected tt/27C batches only; never full installed acceptance.')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=2)
    args=parser.parse_args()
    report=run(args.gui_root,args.out,args.expected_commit,source_pilot=args.source_pilot,source_engine=args.source_engine,
               pilot=args.pilot,workers=args.workers)
    if report['status']=='PASS':
        from scripts.audit_installed_sky130_metal_resistors import audit
        try:write(args.out/'audit.json',audit(args.out,ROOT))
        except Exception:
            write(args.out/'audit.json',dict(status='FAIL',error=traceback.format_exc(),installed_electrical_acceptance=False))
            raise
    print(json.dumps({k:report.get(k) for k in ('status','mode','installed_electrical_acceptance','seconds','error')},indent=2))
    return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
