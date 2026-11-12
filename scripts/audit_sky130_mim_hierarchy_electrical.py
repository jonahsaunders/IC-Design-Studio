"""Candidate independent whole-network MiM electrical readback.

The input is retained imported-hierarchy evidence, not regenerated positive
geometry or native devices. This is finite public-model integration, not
direct hierarchical native extraction, calibrated RC or full-family acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys

if '--source' in sys.argv:
    sys.path.insert(0, str(Path(sys.argv[sys.argv.index('--source')+1]).resolve()))
import icstudio
ROOT = Path(icstudio.__file__).resolve().parent.parent
CANDIDATE = Path(__file__).resolve().parents[1]
from scripts.verify_frozen_mim import require, sha, load, inventory
from scripts import audit_sky130_mim_hierarchy as physical
from scripts.audit_sky130_mim_bias_boundaries import read_raw
from scripts.audit_sky130_mim_passive_corners import rc, verify_models
from scripts.audit_sky130_mim_mismatch_aliases import runtime_profile, native_path

PHYSICAL_QUALIFICATION = '069db1ff6115e63c3d16925de68f4d01791ae64f57859a1a7625d4831396778a'
PHYSICAL_MANIFEST = '088cff5586c95ee808b5b6434bc5d4e9dd56d43e60c90f313e33e464cef66ab6'
PHYSICAL_ARCHIVE = '0626cb1d07050768911a6056009e99ac9ce3bcf13d0313b6786195879c434caa'
PHYSICAL_AUDITOR = 'a70f1ea506e8b3edd9a30f2b09cd9acb47f662f5863fabe187e733f1743a9343'
PHYSICAL_ORIGIN = '/var/tmp/icstudio-mim-hierarchy-20261026-v1/full-v1'
MODEL_CONTRACT = 'b324813599a364c83e76e63f583e7b74da50ab8182640a1cb907796a3ce1c209'
CONTRACT_PATH = 'docs/qualification/sky130-mim-hierarchy-electrical-v2.json'
CONTRACT_SHA = 'ebe2c9265f2093d688b5a3673ef557561cdb71a63ed0c4310fecb05780d93b71'
PREDECESSOR_PATH = 'docs/qualification/sky130-mim-hierarchy-electrical-v1.json'
PREDECESSOR_SHA = '090453b72eff9e0d8f9fca40246d8292f8d16e11cfb9a08e5239609ef9b95feb'
PACKAGE_SHA = '840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'
SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
PORTS = ('P1', 'N1', 'P2', 'N2')
PARAMETERS = ('rm3','rm4','rcvia3','rcvia4','tol_m3','tol_m4','camimc','cpmimc','m3_dw','m4_dw',
              'mc_mm_switch','mc_pr_switch')
DELTA=2**-16
# Selected conditioned common modes only. The larger v1 profiles failed their
# fixed return-current bound and remain preserved, not silently qualified here.
PROFILES = {'e1': (1+DELTA,DELTA,-DELTA,-DELTA), 'e2': (DELTA,DELTA,1-DELTA,-DELTA)}
PATHS = ('app','reference','native','cross','missing','width')


def network(path, plate, *, native):
    """Whole original parent and leaf graph, never a replacement positive netlist."""
    if native:
        return physical.native_circuit(Path(path), plate)
    require(Path(path).read_text() == physical.reference_text(plate),
            'Retained hierarchical reference differs from the actual physical comparison input.')
    return dict(sha256=sha(path), top='mim_pair', ordered_ports=list(PORTS),
                leaf='capacitor_leaf', instances=2, model=physical.model(plate), width_um=2, length_um=10, multiplicity=1)


def historical(root):
    """Re-audit the exact archived original, preserving original execution identity."""
    root = Path(root).resolve()
    require(sha(root/'qualification.json') == PHYSICAL_QUALIFICATION and
            sha(root/'manifest.json') == PHYSICAL_MANIFEST, 'Different historical physical acceptance.')
    require(sha(physical.__file__) == PHYSICAL_AUDITOR, 'Different independently reviewed physical reader.')
    result = physical.audit(root, root/'source')
    require(result['original_execution_root'] == PHYSICAL_ORIGIN and result['full_selected_models'] is True and
            result['counts'] == dict(models=2,clean_layouts=4,native_capacitors=8,native_faults=8,exchange_controls=10),
            'Historical physical selection or execution identity differs.')
    inputs = {}
    for plate in (1,2):
        for rotation in (0,90):
            folder = root/f'p{plate}'/f'r{rotation}'/'physical'
            files = dict(reference=folder/'schematic.spice', native=folder/'lvs-extraction/extracted.spice',
                         project=folder/'input.icproj', hierarchy=folder/'original.gds', private_gds=folder/'layout.gds',
                         original_ext=folder/'lvs-extraction/native-original.ext', corrected_ext=folder/'lvs-extraction/mim_pair.ext',
                         orientation=folder/'lvs-extraction/mim-orientation.json')
            network(files['reference'],plate,native=False);network(files['native'],plate,native=True)
            inputs[f'p{plate}-r{rotation}'] = dict(plate=plate,rotation=rotation,top='mim_pair',ports=list(PORTS),
                files={k:str(p) for k,p in files.items()},hashes={k:sha(p) for k,p in files.items()})
    return dict(original_execution_root=PHYSICAL_ORIGIN,archive_sha256=PHYSICAL_ARCHIVE,
                qualification_sha256=PHYSICAL_QUALIFICATION,manifest_sha256=PHYSICAL_MANIFEST,audit=result,cases=inputs)


def source_coefficients(contract, section):
    require(section in SECTIONS, 'Unknown passive section.')
    values = contract['passive_sections'][section]['coefficients']
    require(set(values) == set(PARAMETERS[:-2]) and all(type(v) in (int,float) and math.isfinite(v) for v in values.values()),
            'Public coefficient map differs.')
    return {**values,'mc_mm_switch':0,'mc_pr_switch':0}


def terminal_response(sample, terminal_names, currents, expected_voltage, resistance, capacitance, frequency, *, inactive=False):
    """Independent response/current conservation, including the inactive port."""
    p,n = (sample[name] for name in terminal_names); ip,inn = (sample[name] for name in currents)
    require(max(abs(p-expected_voltage[0]),abs(n-expected_voltage[1])) <= 1e-12, 'Actual port stimulus differs.')
    target_y = 1/complex(resistance,-1/(2*math.pi*frequency*capacitance))
    intended = expected_voltage[0]-expected_voltage[1]
    expected_ip = -target_y*intended
    if inactive:
        require(intended == 0, 'Inactive observation has nonzero differential stimulus.')
        # Same existing relative integration tolerance, referenced to a 1 V
        # active-port current; no divide-by-zero or relative-to-zero acceptance.
        tolerance = abs(target_y)*1e-6
        require(max(abs(ip),abs(inn),abs(ip+inn)) <= tolerance, 'Inactive occurrence carries coupled/leaked current.')
        return dict(i_p_A=[ip.real,ip.imag],i_n_A=[inn.real,inn.imag],off_diagonal_Y_S=[-ip.real,-ip.imag])
    require(intended != 0 and abs(ip+inn) <= abs(expected_ip)*1e-6, 'Active occurrence fails current conservation.')
    y = -ip/(p-n); require(y.real > 0 and y.imag > 0, 'Nonpassive native response.')
    measured_r = (1/y).real; measured_c = -1/(2*math.pi*frequency*(1/y).imag)
    error = max(abs(y/target_y-1),abs(measured_r/resistance-1),abs(measured_c/capacitance-1))
    require(error <= 1e-6, 'Native per-occurrence response differs from public analytical RC.')
    return dict(Y_S=[y.real,y.imag],R_ohm=measured_r,C_F=measured_c,relative_error=error,
                i_p_A=[ip.real,ip.imag],i_n_A=[inn.real,inn.imag])


def current_vector(plate, coefficients, frequency, profile, path):
    """Predict the whole network directly from each explicitly connected branch."""
    require(profile in PROFILES and path in PATHS and frequency > 0, 'Unreviewed stimulus/path.')
    vp1,vn1,vp2,vn2=PROFILES[profile]
    r,c=rc(plate,coefficients);first=1/complex(r,-1/(2*math.pi*frequency*c))
    r2,c2=rc(plate,coefficients,width=3 if path=='width' else 2)
    second=1/complex(r2,-1/(2*math.pi*frequency*c2))
    one=(vp1-vn1)*first
    two=0j if path=='missing' else ((vp1 if path=='cross' else vp2)-vn2)*second
    if path=='cross':return (-one-two,one,0j,two)
    return (-one,one,-two,two)


def sample_observations(sample, plate, coefficients, frequency, profile):
    names={'frequency'}|{f'v(par_{p})' for p in PARAMETERS}
    names|={f'{kind}({prefix}{path}_{node})' for path in PATHS for node in ('p1','n1','p2','n2')
            for kind,prefix in (('v',''),('i','v_'))}
    require(set(sample)==names,'Missing, duplicated or extra whole-network raw channel.')
    require(math.isfinite(sample['frequency'].real) and math.isclose(sample['frequency'].real,frequency,rel_tol=1e-10),'Wrong native frequency grid.')
    for name in PARAMETERS:
        expected=coefficients.get(name,0)
        require(abs(sample[f'v(par_{name})']-expected)<=1e-24+1e-10*abs(expected),'Actual coefficient/switch differs: '+name)
    require(all(math.isfinite(v.real) and math.isfinite(v.imag) for k,v in sample.items() if k!='frequency'), 'Nonfinite electrical observation.')
    r,c=rc(plate,coefficients);one_volt=abs(1/complex(r,-1/(2*math.pi*frequency*c)));results={}
    for path in PATHS:
        voltage=tuple(sample[f'v({path}_{n})'] for n in ('p1','n1','p2','n2'))
        current=tuple(sample[f'i(v_{path}_{n})'] for n in ('p1','n1','p2','n2'))
        require(max(abs(a-b) for a,b in zip(voltage,PROFILES[profile]))<=1e-12,'Actual independent port stimulus differs.')
        intended=current_vector(plate,coefficients,frequency,profile,path)
        error=max(abs(a-b)/one_volt for a,b in zip(current,intended))
        require(error<=1e-6 and abs(sum(current))<=one_volt*1e-6,'Whole-network current vector/cross-response differs.')
        devices={}
        if path in ('app','reference','native'):
            for index in (1,2):
                pair=PROFILES[profile][(index-1)*2:index*2]
                devices[str(index)]=terminal_response(sample,(f'v({path}_p{index})',f'v({path}_n{index})'),
                    (f'i(v_{path}_p{index})',f'i(v_{path}_n{index})'),pair,r,c,frequency,inactive=pair[0]==pair[1])
        positive=current_vector(plate,coefficients,frequency,profile,'native')
        mismatch=max(abs(a-b)/one_volt for a,b in zip(current,positive))
        results[path]=dict(voltages_V=[[v.real,v.imag] for v in voltage],currents_A=[[v.real,v.imag] for v in current],
            current_relative_error=error,positive_current_normalized_difference=mismatch,devices=devices)
    return results


def raw_context(path, title):
    data=Path(path).read_bytes(); header=data.split(b'Values:',1)[0].split(b'Binary:',1)[0].decode().replace('\r\n','\n')
    require(re.findall(r'^Title:[ \t]*(.*)$',header,re.M)==[title], 'Raw output belongs to another execution/context.')
    return read_raw(path,'ac')


def numeric(saved, expected):
    """Do not trust finite, rehashed summaries when they disagree with raw channels."""
    if isinstance(expected,dict):
        require(isinstance(saved,dict) and set(saved)==set(expected), 'Saved observable keys differ.')
        for key,value in expected.items():numeric(saved[key],value)
    elif isinstance(expected,list):
        require(isinstance(saved,list) and len(saved)==len(expected), 'Saved observable count differs.')
        for first,second in zip(saved,expected):numeric(first,second)
    else:
        require(type(saved) in (int,float) and math.isfinite(saved) and math.isclose(saved,expected,rel_tol=1e-8,abs_tol=1e-24),
                'Saved numerical observable differs from native raw data.')


def safe_relative(name):
    path=PurePosixPath(name)
    require(isinstance(name,str) and str(path)==name and not path.is_absolute() and
            not PureWindowsPath(name).drive and '\\' not in name and '..' not in path.parts,
            'Unsafe or noncanonical retained filename.')
    return path


def title(origin,nonce,case,profile):
    payload={'execution_root':origin,'nonce':nonce,'case':case,'profile':profile,'analysis':'ac'}
    return '* icstudio-mim-hierarchy-electrical-v2 '+hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def check_deck(text,case,profile,networks,staged,origin,nonce):
    """Reconstruct literal complete-network wiring without producer helpers."""
    lines=[title(origin,nonce,case['name'],profile),staged,
           '.param mc_mm_switch=0 mc_pr_switch=0','.option tnom=27','.temp 27']
    saves=[]
    for tag in PATHS:
        path=native_path(networks[tag])
        require(path.is_absolute(),'Native network input is relative.')
        lines.extend([f'.subckt whole_{tag} P1 N1 P2 N2',f'.include "{path.as_posix()}"',
                      'Xwhole P1 N1 P2 N2 mim_pair',f'.ends whole_{tag}'])
        for port,voltage in zip(('p1','n1','p2','n2'),PROFILES[profile]):
            lines.append(f'V_{tag}_{port} {tag}_{port} 0 DC 0 AC {voltage:.17g}')
            saves.extend([f'v({tag}_{port})',f'i(v_{tag}_{port})'])
        lines.append('X_'+tag+' '+' '.join(tag+'_'+p for p in ('p1','n1','p2','n2'))+' whole_'+tag)
    for key in PARAMETERS:
        lines.append(f'VPAR_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}')
        saves.append(f'v(par_{key})')
    lines.extend(['.ac dec 1 1k 10G','.save '+' '.join(saves),'.end',''])
    require(text=='\n'.join(lines),'Actual deck differs in whole-network inputs, wiring, stimulus or analysis.')


def fault_bytes(original,plate,kind):
    """Exactly one original occurrence edit, preserving every other byte."""
    require(kind in ('cross','missing','width'),'Unknown native mutation.')
    text=original.decode('utf-8');rows=text.splitlines(keepends=True)
    indices=[i for i,row in enumerate(rows) if re.match(r'^X\S+\s+P2\s+N2\s+',row)]
    require(len(indices)==1,'Ambiguous second native occurrence.')
    i=indices[0];old=rows[i]
    if kind=='missing':rows.pop(i)
    elif kind=='cross':
        m=re.match(r'^X\S+\s+(P2)\s+N2\s+',old)
        rows[i]=old[:m.start(1)]+'P1'+old[m.end(1):]
    else:
        matches=list(re.finditer(r'(?i)\bw\s*=\s*(2)(?=\s|$)',old));require(len(matches)==1,'Ambiguous native width.')
        m=matches[0];rows[i]=old[:m.start(1)]+'3'+old[m.end(1):]
    return ''.join(rows).encode()


def semantic_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]


def application(root,plate,package,old_root,saved):
    folder=root/f'applications/p{plate}';project=load(folder/'schematic.icproj')
    require(len(project['cells'])==2 and len({c['id'] for c in project['cells']})==2,'Application hierarchy cell coverage differs.')
    cells={c['id']:c for c in project['cells']};parent=cells[project['top']]
    require(parent['name']=='mim_pair' and parent['ports']==list(PORTS) and len(parent['devices'])==2,'Application parent interface/count differs.')
    require(all(not project.get(k) for k in ('global_nets','parameters','spice','xschem_exchange')),'Unexpected schematic simulation override.')
    for cell in cells.values():
        require(all(not cell.get(k) for k in ('parameters','spice_parameters','spice_statements','shapes','layout_instances','wires','labels','junctions')),
                'Application contains undeclared geometry/net/parameter overrides.')
    expected_children=[]
    for index,device in enumerate(parent['devices'],1):
        require(device['kind']=='X' and device['name']==f'X{index}' and device['nets']==dict(P=f'P{index}',N=f'N{index}') and
                not device.get('parameters') and not device.get('array') and not device.get('model_ref'), 'Application occurrence mapping differs.')
        expected_children.append(device['cell'])
    require(len(set(expected_children))==1 and expected_children[0]!=project['top'],'Application does not reuse one leaf.')
    child=cells[expected_children[0]]
    require(child['name']=='mim_leaf' and child['ports']==['P','N'] and len(child['devices'])==1,'Application leaf differs.')
    device=child['devices'][0];device_key=f'sky130_fd_pr/cap_mim_m3_{plate}.sym'
    expected_ref=dict(pdk='sky130A',revision=package['revision'],device=device_key)
    require(device['name']=='C1' and device['model_ref']==expected_ref and device['nets']==dict(c0='P',c1='N') and
            device['model_params']==dict(w=2,l=10,mf=1) and not device.get('array') and not device.get('parameters'), 'Application device or parameters differ.')
    tech=project['pdk'];expected_tech=package['technology']
    require(tech['package_lock']=={k:package[k] for k in ('id','revision','files')} and
            {k:v for k,v in tech.items() if k not in ('package_lock','package_root')}==expected_tech,'Application package binding differs.')
    binding=expected_tech['simulation']['catalog'][device_key]
    require(device['kind']==binding['kind'] and device['symbol']['pin_order']==binding['pin_order']==['c0','c1'] and
            binding['model']==physical.model(plate) and binding['emit_parameters']==dict(l='l',m='mf',mf='mf',w='w'), 'Application ABI differs.')
    original_path=old_root/f'p{plate}/leaf.icproj';old=load(original_path)
    oldcell=next(c for c in old['cells'] if c['id']==old['top']);olddevice=oldcell['devices'][0]
    oldbinding=old['pdk']['simulation']['catalog'][device_key]
    oldmap=dict(l='l',m='mf',w='w',**({'mf':'mf'} if plate==1 else {'vm':'mf'}))
    require(oldbinding['emit_parameters']==oldmap and olddevice['model_ref']==dict(expected_ref,revision='9a491f0ebd51a0aa') and
            olddevice['model_params']==device['model_params'] and olddevice['nets']==device['nets'], 'Historical/current counterpart lineage differs.')
    expected_saved=dict(original_leaf_sha256=sha(original_path),old_model_ref=olddevice['model_ref'],new_model_ref=expected_ref,
                        old_binding=oldbinding,current_binding=binding,project_sha256=sha(folder/'schematic.icproj'),
                        application_sha256=sha(folder/'application.spice'),hierarchical_export_sha256=sha(folder/'hierarchical-export.spice'))
    require(saved==expected_saved,'Saved application binding receipt differs from actual project.')
    suffix=physical.model(plate)+' l=10 m=1 mf=1 w=2'
    require(semantic_lines((folder/'application.spice').read_text())==[
        '.subckt mim_pair P1 N1 P2 N2','X_X1_C1 P1 N1 '+suffix,'X_X2_C1 P2 N2 '+suffix,'.ends mim_pair'],
        'Actual complete application export differs from two ordered occurrences.')
    include_lines=[];package_root=native_path(tech['package_root']);require(package_root.is_absolute(),'Relative application package root.')
    for item in expected_tech['simulation']['includes']:
        source=(package_root/safe_relative(item['path'])).as_posix();section=item.get('sections',{}).get('nominal',item.get('section'))
        include_lines.append(f'.lib "{source}" {section}' if section else f'.include "{source}"')
    require(semantic_lines((folder/'hierarchical-export.spice').read_text())==include_lines+[
        '.subckt mim_leaf P N','X_C1 P N '+suffix,'.ends mim_leaf','X1 P1 N1 mim_leaf','X2 P2 N2 mim_leaf','.end'],
        'Actual hierarchical application export differs from saved reused leaf.')
    return folder/'application.spice'


def source_binding(root,report,manifest,reviewed_source):
    sources=load(root/'source-files.json')
    require(sha(root/'source-files.json')==report['source_files_sha256'] and inventory(root/'source')==sources,'Captured base source inventory differs.')
    required={f'scripts/{n}.py' for n in ('audit_sky130_mim_hierarchy','audit_sky130_mim_passive_corners',
        'audit_sky130_mim_bias_boundaries','audit_sky130_mim_mismatch_aliases','installed_mim_inputs','qualify_sky130_mim_passive_corners')}
    required|={'icstudio/catalog.py','icstudio/interchange.py','icstudio/testbenches.py',
               'docs/qualification/sky130-mim-contract-v1.json','docs/qualification/sky130-mim-hierarchy-v1.json'}
    require(required<=sources.keys() and sources['docs/qualification/sky130-mim-contract-v1.json']==MODEL_CONTRACT,'Missing base source/contract closure.')
    for name,digest in sources.items():
        safe_relative(name)
        if reviewed_source is not None:require(sha(Path(reviewed_source)/name)==digest,'Base source differs from reviewed current source: '+name)
    candidates=load(root/'candidate-files.json')
    wanted={'scripts/qualify_sky130_mim_hierarchy_electrical.py','tests/test_sky130_mim_hierarchy_electrical.py','tests/test_sky130_mim_hierarchy_selection.py',CONTRACT_PATH,PREDECESSOR_PATH,
            'scripts/audit_sky130_mim_hierarchy_electrical.py','tests/test_sky130_mim_hierarchy_electrical_audit.py'}
    require(set(candidates)==wanted and sha(root/'candidate-files.json')==report['candidate_files_sha256'] and
            inventory(root/'candidate')=={n:e['sha256'] for n,e in candidates.items()},'Candidate source closure differs.')
    require(candidates[CONTRACT_PATH]['sha256']==CONTRACT_SHA and candidates[PREDECESSOR_PATH]['sha256']==PREDECESSOR_SHA,
            'Candidate or retained failed-profile contract differs.')
    for name in ('scripts/audit_sky130_mim_hierarchy_electrical.py','tests/test_sky130_mim_hierarchy_electrical_audit.py'):
        require(sha(CANDIDATE/name)==candidates[name]['sha256'],'Independent candidate reader was not captured for this execution.')
    return len(sources),len(candidates)


def check_raw(path,case,profile,coefficients,expected_title,saved):
    samples=raw_context(path,expected_title);require(len(samples)==8,'Incomplete frequency sweep.')
    observations=[];detections=dict.fromkeys(('cross','missing','width'),False);maximum=0.0;active=inactive=0
    for i,sample in enumerate(samples):
        f=10**(i+3);paths=sample_observations(sample,case['plate'],coefficients,f,profile);summary={}
        for tag,values in paths.items():
            maximum=max(maximum,values['current_relative_error']/1e-6)
            if tag in detections:detections[tag]|=values['positive_current_normalized_difference']>1e-6
            summary[tag]=dict(voltages=values['voltages_V'],currents=[[-r,-j] for r,j in values['currents_A']])
            active+=sum('Y_S' in d for d in values['devices'].values())
            inactive+=sum('off_diagonal_Y_S' in d for d in values['devices'].values())
        observations.append(dict(frequency_hz=sample['frequency'].real,paths=summary))
    require(set(saved)=={'samples','max_normalized_current_error','detections','observations'} and saved['samples']==8 and
            saved['detections']==detections,'Saved coverage/control detection differs from raw observations.')
    numeric(saved['observations'],observations)
    value=saved['max_normalized_current_error']
    require(type(value) in (int,float) and math.isfinite(value) and math.isclose(value,maximum,rel_tol=1e-7,abs_tol=1e-9),
            'Saved maximum error differs from independently recomputed current errors.')
    return dict(detections=detections,maximum=maximum,active_pair_samples=active,inactive_pair_samples=inactive)


def case_inventory(report):
    require(type(report['pilot']) is bool, 'Selection mode must be explicit.')
    development = report.get('development', False)
    require(type(development) is bool and not (development and report['pilot']), 'Invalid selection mode.')
    full=[dict(name=f'p{p}-r{r}-{s}',plate=p,rotation=r,section=s) for p in (1,2) for r in (0,90) for s in SECTIONS]
    names=report['selected_cases']; full_names=[c['name'] for c in full]
    require(report['full_declared_cases']==full_names and isinstance(names,list) and bool(names) and
            len(names)==len(set(names)) and set(names)<=set(full_names), 'Invalid declared selection.')
    selected=[c for c in full if c['name'] in names]
    require(names==[c['name'] for c in selected], 'Noncanonical selection ordering.')
    if not development:
        expected=[c for c in full if not report['pilot'] or c['rotation']==0 and c['section']=='tt']
        require(selected==expected, 'Non-development coverage differs.')
    require(len(report['cases'])==len(selected) and {r['name'] for r in report['cases']}==set(names), 'Electrical selection incomplete or duplicated.')
    return full, selected


def selection_scope(report):
    full, selected = case_inventory(report)
    development = report.get('development', False)
    return dict(full_declared_selection=len(selected)==len(full),
                development=development, source_integration_acceptance=not development)


def audit(root,physical_root=None,reviewed_source=None):
    root=Path(root).resolve();report=load(root/'qualification.json');manifest=load(root/'manifest.json')
    require(manifest==inventory(root,('manifest.json',)),'Complete electrical evidence inventory differs.')
    require(report['schema']==1 and report['gate']=='sky130-mim-hierarchy-electrical-v2' and report['status']=='PASS' and
            report['mode']=='source-integration' and report['source_integration_acceptance'] is (not report.get('development',False)) and
            all(report.get(k) is False for k in ('qualified','installed','release_ready','signoff','chunk_complete','full_family')) and
            not report.get('error'),'Failed or overclaimed electrical evidence.')
    require(report['guards']==dict(source=True,candidate=True,package=True,models=True,runtime=True,physical=True,networks=True),
            'Missing final source/input/runtime guard.')
    origin=native_path(report['execution_root']);require(origin.is_absolute() and re.fullmatch('[0-9a-f]{32}',report['nonce']), 'Invalid original execution identity.')
    require(report['python']['dont_write_bytecode'] is True and report['python']['pycache_prefix'],'Bytecode isolation guard missing.')
    require(report['contract_sha256']==sha(root/'contract.json')==CONTRACT_SHA,'Unreviewed finite electrical contract.')
    spec=load(root/'contract.json');require(report['scope']==spec['scope'],'Changed qualification scope.')
    source_count,candidate_count=source_binding(root,report,manifest,reviewed_source)
    historical_root=Path(physical_root or report['physical_dependency']['restored_root']).resolve()
    old=historical(historical_root);dependency=report['physical_dependency']
    require(dependency=={**spec['physical_dependency'],'restored_root':dependency['restored_root'],
        'readback_sha256':sha(root/'physical-readback.json'),'original_execution_root':PHYSICAL_ORIGIN} and
        load(root/'physical-readback.json')==old['audit'],'Historical physical readback receipt differs.')
    old_origin=native_path(dependency['restored_root']);require(old_origin.is_absolute(),'Relative original physical restore root.')
    package=load(root/'contract-sources/package')
    require(sha(root/'contract-sources/package')==PACKAGE_SHA and report['simulation_package']==spec['simulation_package'], 'Unreviewed simulation package.')
    # stage_models writes POSIX spelling even when its actual execution root is Windows.
    staged=verify_models(root,{**report,'execution_root':origin.as_posix()},manifest)
    applications={p:application(root,p,package,historical_root,report['applications'][str(p)]) for p in (1,2)}
    before=load(root/'runtime-before.json');after=load(root/'runtime-after.json')
    require(before==after and sha(root/'runtime-before.json')==report['runtime_before_sha256'] and
            sha(root/'runtime-after.json')==report['runtime_after_sha256'],'Runtime identity changed.')
    runtime_profile(root,before,dict(root=report['execution_root']))
    full, selected = case_inventory(report)
    expected_bindings={}
    for case in selected:
        key=f'p{case["plate"]}-r{case["rotation"]}'
        if key in expected_bindings:continue
        oldpaths=old['cases'][key]['files'];original=(Path(oldpaths['native'])).read_bytes()
        expected={}
        for tag in PATHS:
            if tag=='app':path=applications[case['plate']];original_path=origin/f'applications/p{case["plate"]}/application.spice'
            elif tag in ('reference','native'):
                path=Path(oldpaths[tag]);original_path=old_origin/path.relative_to(historical_root).as_posix()
            else:
                path=root/'networks'/key/(tag+'.spice');original_path=origin/'networks'/key/(tag+'.spice')
                require(path.read_bytes()==fault_bytes(original,case['plate'],tag),'Fault copy changed beyond its declared occurrence edit.')
            expected[tag]=dict(path=str(original_path),sha256=sha(path))
        expected_bindings[key]=expected
    require(report['network_bindings']==expected_bindings,'Native/application/reference occurrence binding differs.')
    model_contract=load(root/'source/docs/qualification/sky130-mim-contract-v1.json')
    maximum=0.;active=inactive=detected=0
    by_name={c['name']:c for c in selected}
    for row in report['cases']:
        case=by_name[row['name']];folder=root/case['name'];key=f'p{case["plate"]}-r{case["rotation"]}'
        require(all(row[k]==v for k,v in case.items()) and row['status']=='PASS' and set(row['profiles'])==set(PROFILES) and
                load(folder/'record.json')==row and not row.get('error'),'Case identity/completion differs.')
        combined=dict.fromkeys(('cross','missing','width'),False)
        for profile in PROFILES:
            dest=folder/profile;saved=row['profiles'][profile]
            for name,field in (('input.cir','deck_sha256'),('result.raw','raw_sha256'),('console.log','log_sha256'),('invocation.json','invocation_sha256')):
                require(sha(dest/name)==saved[field],'Native artifact digest differs.')
            invocation=load(dest/'invocation.json')
            command=[before['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',
                     str(origin/case['name']/profile/'result.raw'),str(origin/case['name']/profile/'input.cir')]
            require(invocation==dict(command=command,cwd=str(origin),environment=before['environment'],returncode=0),'Native invocation differs.')
            check_deck((dest/'input.cir').read_text(),case,profile,{t:v['path'] for t,v in expected_bindings[key].items()},
                       staged[case['section']],report['execution_root'],report['nonce'])
            log=(dest/'console.log').read_text().lower();require('error' not in log and 'unknown parameter' not in log and log.strip(),'Native error/empty console.')
            values=check_raw(dest/'result.raw',case,profile,source_coefficients(model_contract,case['section']),
                             title(report['execution_root'],report['nonce'],case['name'],profile),saved['raw'])
            maximum=max(maximum,values['maximum']);active+=values['active_pair_samples'];inactive+=values['inactive_pair_samples']
            for fault in combined:combined[fault]|=values['detections'][fault]
        require(all(combined.values()),'A declared wrong network was not detected by the paired independent excitations.');detected+=len(combined)
    return dict(schema=1,status='PASS',gate=report['gate'],mode=report['mode'],original_execution_root=report['execution_root'],nonce=report['nonce'],
        qualification_sha256=sha(root/'qualification.json'),manifest_sha256=sha(root/'manifest.json'),historical_qualification_sha256=PHYSICAL_QUALIFICATION,
        qualified=False,installed=False,release_ready=False,signoff=False,chunk_complete=False,full_family=False,
        **selection_scope(report),maximum_normalized_current_error=maximum,
        counts=dict(contexts=len(selected),native_ac_runs=2*len(selected),frequency_points=16*len(selected),
                    positive_active_pair_samples=active,positive_inactive_pair_samples=inactive,detected_network_controls=detected,
                    historical_clean_layouts=4,historical_native_capacitors=8,source_files=source_count,candidate_files=candidate_count),
        scope=spec['scope'],source_binding='reviewed current base source' if reviewed_source else 'self-contained base source closure')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--physical',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args();require(a.source.resolve()==ROOT,'Reviewed import source differs.')
    result=audit(a.root,a.physical,a.source);text=json.dumps(result,indent=2)+'\n'
    if a.out:
        require(not a.out.exists() and not a.out.resolve().is_relative_to(a.root.resolve()),'Write audit outside immutable evidence to a new path.')
        a.out.write_text(text,encoding='utf-8')
    print(text,end='')


if __name__=='__main__':main()
