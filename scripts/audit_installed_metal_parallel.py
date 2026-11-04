"""Independent live readback of actual installed parallel-array DC/AC evidence.

No producer acceptance code or regenerated positive device is used. Original
GUI references and unmerged native arrays remain bound to the same candidate,
application, queued jobs and execution nonce. Source pilots stay separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import installed_metal_parallel_inputs as inputs
from scripts import verify_frozen_metal_parallel as gui
from scripts import audit_sky130_metal_resistor_parallel as raw
from scripts.audit_installed_sky130_metal_resistors import normalized_original,execution_identity
from scripts.audit_sky130_metal_resistors_linked import compare_summary

require,sha,load=gui.require,gui.sha,gui.load
COUNTS=dict(fresh_gui_native_inputs=30,electrical_contexts=30,electrical_analyses=60,electrical_path_samples=3870)


def context_title(execution,gui_nonce,case,analysis):
    value=dict(execution_root=execution['root'],execution_nonce=execution['nonce'],gui_execution_id=gui_nonce,case=case,analysis=analysis)
    return '* icstudio-installed-metal-parallel-v1 '+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def input_copies(root,binding):
    normalized=load(root/'normalized-inputs.json');require(list(binding['cases'])==list(inputs.CASES) and set(normalized)==set(inputs.CASES),
        'Incomplete actual GUI/native array input selection.')
    inventories={'original-inputs':{},'normalized-inputs':{}}
    for name in inputs.CASES:
        row=binding['cases'][name]
        require(set(normalized[name])=={'application','native'},'Missing/extra array input path.')
        for kind,key in (('application','reference'),('native','native')):
            actual=gui.unlinked(row['files'][key]).resolve();data=actual.read_bytes()
            require(sha(actual)==row['hashes'][key],'Fresh original array input changed.')
            gui.circuit(data.decode('utf-8'),row['top'],row['model'],row['multiplicity'],extracted=kind=='native')
            retained=root/'original-inputs'/name/(kind+'.spice');target=root/'normalized-inputs'/name/(kind+'.spice')
            require(retained.read_bytes()==data,'Retained original array input was replaced.')
            value,proof=normalized_original(data,row['top'])
            require(target.read_bytes()==value,'Array normalization changed more than the exact top-name tokens.')
            gui.circuit(value.decode('utf-8'),'coupon',row['model'],row['multiplicity'],extracted=kind=='native')
            require(normalized[name][kind]==dict(original_path=str(actual),original_sha256=sha(actual),retained_path=str(retained),
                normalized_path=str(target),normalized_sha256=sha(target),proof=proof),'Array normalization receipt differs from original bytes.')
            inventories['original-inputs'][name+'/'+kind+'.spice']=sha(retained)
            inventories['normalized-inputs'][name+'/'+kind+'.spice']=sha(target)
    for name,expected in inventories.items():require(gui.inventory(root/name)==expected,'Unexpected original/normalized array files.')
    return normalized


def check_deck(root,row,case,analysis,selected,normalized,execution,gui_nonce):
    require(case in inputs.CASES and analysis in ('dc','ac'),'Unknown installed array electrical case.')
    title=context_title(execution,gui_nonce,case,analysis)
    lines=[title,selected['tt'],'.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear','.temp 27','VDRIVE input 0 DC .0005 AC 1']
    for kind,wrapper in (('application','app_wrapper'),('native','native_wrapper')):
        path=Path(normalized[kind]['normalized_path'])
        require(path==root/'normalized-inputs'/case/(kind+'.spice') and not any(c.isspace() for c in str(path)),
                'Actual array include path differs from its retained input.')
        lines += [f'.subckt {wrapper} a b','.include '+path.as_posix(),'X_BODY a b coupon',f'.ends {wrapper}']
    resistance=raw.model_resistance(2,5,row['multiplicity'],27.,raw.FIXED[row['model']],scale=1e-6)
    for tag,body in (('a','XA in_a out_a app_wrapper'),('n','XN in_n out_n native_wrapper'),('c',f'RC in_c out_c {resistance:.17g}')):
        lines += [f'VS_{tag} input in_{tag} DC 0 AC 0',body,f'RL_{tag} out_{tag} 0 1',f'CL_{tag} out_{tag} 0 1n']
    lines += [f'VP_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}' for key in raw.COEFFICIENTS]
    names=['v(input)',*[v for tag in ('a','n','c') for v in (f'v(in_{tag})',f'v(out_{tag})',f'i(vs_{tag})')],
        *['v(par_'+key+')' for key in raw.COEFFICIENTS]]
    lines += ['.save '+' '.join(names),'.dc VDRIVE -.001 .001 .0001' if analysis=='dc' else '.ac dec 3 1k 10g','.end']
    path=root/'electrical'/(case+'-'+analysis)/'input.cir'
    require(path.read_text()=='\n'.join(lines)+'\n','Installed array deck changed input, multiplier, model, operating context or stimulus.')
    return title


def runtime_binding(root,report,binding,installed):
    before=load(root/'runtime-before.json')
    require(before==load(root/'runtime-after.json') and all(sha(root/f'runtime-{v}.json')==report[f'runtime_{v}_sha256'] for v in ('before','after')),
            'Array simulator runtime changed or receipt differs.')
    require(before['platform']==sys.platform and before['platform'] in installed['runtime_profiles'] and
            before['sha256']==installed['runtime_profiles'][before['platform']]['sha256'],'Unreviewed selected array simulator profile.')
    engine=inputs.select_engine(binding,Path(before['engine']) if binding['mode']=='source-pilot' else None)
    environment=inputs.native_environment(binding,engine,root)
    require(before['environment']==environment and inputs.runtime(binding,engine,environment)==before,
            'Live selected simulator/configuration/dependency closure differs.')
    assets={**before['files'],**{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}}
    require(load(root/'runtime-assets.json')==assets and gui.inventory(root/'runtime-assets')=={d:d for d in set(assets.values())},
            'Captured actual array runtime closure differs.')
    return before


def audit(root,reviewed_source=None):
    root=gui.unlinked(root).resolve();report=load(root/'qualification.json');manifest=load(root/'manifest.json')
    require(manifest==gui.inventory(root,('manifest.json','audit.json')),'Complete installed array electrical inventory differs.')
    require(report.get('schema')==1 and report.get('gate')=='sky130-metal-parallel-installed-electrical-v1' and report.get('status')=='PASS' and
            report.get('mode') in ('source-pilot','installed') and report.get('pilot') is False and not report.get('error') and
            all(report.get(k) is False for k in ('qualified','installed_acceptance','full_family','chunk_complete','release_ready','signoff')),
            'Incomplete or overclaimed installed-array electrical result.')
    require(report['installed_electrical_acceptance'] is (report['mode']=='installed') and report.get('input_guards')==dict(
        runtime=True,sources=True,gui=True,public_contract=True,simulation_package=True,staged_models=True,retained_inputs=True),
        'Array installed claim or final input guards differ.')
    execution=execution_identity(root,report);binding=load(root/'inputs.json')
    require(sha(root/'inputs.json')==report['inputs_sha256'] and binding['mode']==report['mode'] and
            binding['expected_commit']==report['expected_commit'] and binding['execution_id']==report['gui_execution_id'],
            'Array GUI prerequisite receipt differs.')
    require(inputs.bind_gui(binding['supplied_root'],binding['expected_commit'],source_pilot=binding['mode']=='source-pilot')==binding,
            'Fresh array GUI/native prerequisite no longer independently audits.')
    installed,spec,mapped=inputs.contracts(binding)
    require(sha(root/'installed-contract.json')==report['installed_contract_sha256']==inputs.CONTRACT_SHA and
            sha(root/'contract.json')==report['contract_sha256']==installed['source_contract']['sha256']==raw.CONTRACT_SHA and
            load(root/'contract-sources.json')==mapped and sha(root/'contract-sources.json')==report['contract_sources_sha256'],
            'Exact public array contract/source bindings differ.')
    sources=load(root/'source-files.json');require(sha(root/'source-files.json')==report['source_files_sha256'] and
            gui.inventory(root/'source')==sources==inputs.source_files(),'Captured/executing array source closure differs.')
    if reviewed_source is not None:require(all(sha(gui.confined(reviewed_source,n))==d for n,d in sources.items()),'Array source differs from independently reviewed files.')
    if binding['mode']=='installed':inputs.candidate_sources(sources,binding['expected_commit'])
    for name,value in spec['engine_sources'].items():
        path=gui.confined(root/'engine-reference',name)
        require(sha(path)==value['sha256'] and path.stat().st_size==value['bytes'],'Primitive source/reference notice differs.')
    require(report['simulation_package']==binding['simulation_package'],'Declared selected simulation package differs.')
    _,selected=raw.model_closure(root,manifest)
    require(sha(root/'original-package/package.json')==binding['simulation_package']['manifest_sha256'] and
            sha(root/'normalized-inputs.json')==report['normalized_inputs_sha256'],'Retained package/input identities differ.')
    normalized=input_copies(root,binding);runtime=runtime_binding(root,report,binding,installed)
    expected=[(key,analysis) for key in inputs.CASES for analysis in ('dc','ac')]
    names=[key+'-'+analysis for key,analysis in expected]
    require(report['selected_cases']==names and [v['name'] for v in report['cases']]==sorted(names),'Missing/duplicate/reordered array electrical cases.')
    cases={v['name']:v for v in report['cases']};samples=0;maximum={'dc':0.,'ac':0.}
    for key,analysis in expected:
        name=key+'-'+analysis;saved=cases[name];row=binding['cases'][key];folder=root/'electrical'/name
        require(load(folder/'record.json')==saved and saved['case']==key and saved['analysis']==analysis and
            all(saved[k]==row[k] for k in ('model','width_um','length_um','multiplicity','rotation')) and saved['status']=='PASS' and
            type(saved['returncode']) is int and saved['returncode']==0 and not saved.get('error'),'Array analysis receipt/selection differs.')
        argv=[runtime['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(folder/'input.cir')]
        require(saved['command']==argv and saved['cwd']==str(root) and saved['environment']==runtime['environment'],
            'Actual array analysis command/runtime/environment differs.')
        require(all(saved[k+'_sha256']==sha(folder/path) for k,path in (('deck','input.cir'),('raw','result.raw'),('log','console.log'))),
            'Native array deck/raw/log binding differs.')
        require(not re.search(r'error|unknown parameter|unknown subckt|singular matrix|timestep too small',(folder/'console.log').read_text(),re.I),
            'Native array analysis reported an error.')
        title=check_deck(root,row,key,analysis,selected,normalized[key],execution,binding['execution_id'])
        observed=raw.electrical_observation(folder/'result.raw',title,analysis,row['model'],2,5,row['multiplicity'])
        compare_summary(saved['observation'],observed);samples+=3*observed['samples']
        maximum[analysis]=max(maximum[analysis],*[v[k] for v in observed['branches'].values() for k in
            ('maximum_normalized_error','current_normalized_error','kcl_normalized_error')])
    counts=dict(fresh_gui_native_inputs=len(binding['cases']),electrical_contexts=len(cases)//2,electrical_analyses=len(cases),electrical_path_samples=samples)
    require(counts==COUNTS,'Installed array DC/AC coverage differs.')
    return dict(schema=1,status='PASS',mode=report['mode'],expected_commit=report['expected_commit'],gui_execution_id=binding['execution_id'],
        installed_electrical_acceptance=report['installed_electrical_acceptance'],qualified=False,signoff=False,full_family=False,chunk_complete=False,
        release_ready=False,qualification_sha256=sha(root/'qualification.json'),inputs_sha256=sha(root/'inputs.json'),manifest_sha256=sha(root/'manifest.json'),
        counts=counts,maximum_normalized_errors=maximum,runtime_check='live actual selected engine/configuration/dependencies and retained bytes',
        source_binding='all captured files compared to reviewed source' if reviewed_source is not None else 'captured and current source closure')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--reviewed-source',type=Path);ap.add_argument('--out',type=Path)
    args=ap.parse_args();result=audit(args.root,args.reviewed_source)
    if args.out:require(not args.out.exists(),'Choose a fresh independent audit receipt.');inputs.write(args.out,result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
