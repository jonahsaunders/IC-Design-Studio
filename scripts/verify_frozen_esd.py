"""Independent reader/reference execution for the opt-in ESD desktop probe.

Source runs remain development evidence. Installed provenance requires a
separately supplied clean candidate and exact installed executable identity.
No default promotion, ESD ratings or full family qualification is inferred.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if (ROOT/'icstudio').is_dir(): sys.path.insert(0,str(ROOT))
if '--source' in sys.argv: sys.path.insert(0,str(Path(sys.argv[sys.argv.index('--source')+1]).resolve()))
from scripts import audit_sky130_esd_nvt as raw_audit
from scripts.verify_frozen_mim import load, unlinked, relative, inventory
from scripts import installed_mim_inputs as runtime_inputs

BASE = '840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'
OPTIONAL = raw_audit.PACKAGE
KEY = 'sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym'
CONDITIONS = tuple((c,t,'dc') for c in ('nominal','ss','ff','sf','fs') for t in (0,27,85)) + tuple(('nominal',27,p) for p in 'dgsb')
require = raw_audit.require
sha = raw_audit.sha


def write(path, value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def same_project(actual, expected, message):
    require(actual == expected,message)


def finite(value):
    if isinstance(value,dict):
        for child in value.values(): finite(child)
    elif isinstance(value,list):
        for child in value: finite(child)
    elif isinstance(value,float):
        require(math.isfinite(value),'Nonfinite result or evidence number.')


def inside(root, name):
    path = unlinked(Path(root)/relative(name))
    require(path.resolve().is_relative_to(Path(root).resolve()),'Evidence escaped root.')
    return path


def original_file(root, original_root, value):
    """Locate a retained original path in a relocated evidence tree."""
    origin,path = map(raw_audit.native_path,(original_root,value))
    require(origin.is_absolute() and path.is_absolute(),'Original paths must be absolute.')
    try: name = path.relative_to(origin).as_posix()
    except ValueError as exc: raise ValueError('Original path escaped execution root.') from exc
    return inside(root,name)


def external_file(original, expected):
    """Only the trusted caller can remap an archived executable/runtime file."""
    path = expected.get('artifact_paths',{}).get(original,original)
    return unlinked(path)


def producer_inventory(root, expected):
    path = inside(root,'producer-manifest.json')
    require(sha(path) == expected['producer_manifest_sha256'],'Trusted producer manifest differs.')
    manifest = load(path)
    require(set(manifest) == {'schema','execution_id','files'} and manifest['schema'] == 1
            and manifest['execution_id'] == expected['execution_id'],'Producer manifest identity differs.')
    require(manifest['files'] == inventory(root,('producer-manifest.json',)),
            'Producer evidence changed after capture.')
    require(manifest['files'].get('report.json') == expected['report_sha256'],
            'Producer report is not in the immutable manifest.')
    return manifest


def runtime_files(profile, expected):
    require(profile['engine'] == expected['engine'] and profile['sha256'] == expected['engine_sha256'],
            'Runtime engine differs from externally selected engine.')
    require(profile['files'].get(profile['engine']) == profile['sha256'],'Runtime omits executable.')
    for original,value in profile['files'].items():
        require(raw_audit.native_path(original).is_absolute() and sha(external_file(original,expected)) == value,
                'Runtime file changed: '+original)
    for original,row in profile['elf_dependencies'].items():
        # Loader-selected ELF aliases may legitimately be symlinks. Their exact
        # resolved target is authenticated; evidence/package paths remain unlinked.
        if original not in expected.get('artifact_paths',{}) and row['resolved'] not in expected.get('artifact_paths',{}):
            require(str(Path(original).resolve()) == row['resolved'],'ELF loader target changed.')
        require(sha(external_file(row['resolved'],expected)) == row['sha256'],'ELF dependency changed.')


def environment_shape(env, mode, resource_root, environment_root):
    allowed = {'LANG','LC_ALL','TZ','HOME','USERPROFILE','TMP','TEMP','PATH','SystemRoot','WINDIR','SPICE_SCRIPTS','LD_LIBRARY_PATH'}
    origin = raw_audit.native_path(environment_root)
    require(set(env) <= allowed and env.get('LANG') == env.get('LC_ALL') == 'C' and env.get('TZ') == 'UTC',
            'Unreviewed native environment keys or locale.')
    require(env.get('HOME') == env.get('USERPROFILE') == str(origin/'empty-home') and
            env.get('TMP') == env.get('TEMP') == str(origin/'temporary'),'Native temporary environment escaped owned root.')
    require(bool(env.get('PATH')) and bool(env.get('SPICE_SCRIPTS')),'Missing explicit runtime search/initializer path.')
    if 'LD_LIBRARY_PATH' in env:
        require(mode == 'installed' and env['LD_LIBRARY_PATH'] == resource_root,'Unreviewed runtime library override.')


def runtime_equivalent(first, second):
    # Reference runs have their own empty home/temp directories. Every executable,
    # config, library, loader result and version byte remains identical.
    require({k:v for k,v in first.items() if k != 'environment'} ==
            {k:v for k,v in second.items() if k != 'environment'},'Reference runtime differs from reviewed producer runtime.')


def header(root, expected):
    producer_inventory(root,expected)
    report = load(inside(root,'report.json')); finite(report)
    require(sha(root/'report.json') == expected['report_sha256'] and
            report['execution_id'] == expected['execution_id'] and
            re.fullmatch('[0-9a-f]{32}',report['execution_id']),'Externally selected report/nonce differs.')
    require(report['schema'] == 'esd-desktop-probe-v1' and report['status'] == 'PASS' and
            not report.get('error') and not report.get('source_error') and not report['errors'],'Probe failed.')
    require(all(report[k] is False for k in ('qualified','default_promoted','chunk_complete','installed_acceptance')),
            'Probe overstates acceptance.')
    require(report['package_sha256'] == OPTIONAL and report['base_sha256'] == BASE,'Wrong package selection.')
    for key in ('executable','executable_sha256','engine','engine_sha256','resource_root','runtime'):
        require(report[key] == expected[key],'Externally selected input differs: '+key)
    require(report['engine_sha256'] in raw_audit.ENGINES,'Unreviewed engine profile.')
    for field in ('executable','engine'):
        require(raw_audit.native_path(report[field]).is_absolute() and
                sha(external_file(report[field],expected)) == expected[field+'_sha256'],'Executable bytes changed.')
    require(report['native_environment'] == expected['native_environment'] and
            report['native_runtime_before'] == report['native_runtime_after'] == expected['native_runtime'] and
            expected['native_runtime']['environment'] == expected['native_environment'],'Native runtime/environment changed.')
    environment_shape(report['native_environment'],expected['mode'],report['resource_root'],
                      str(raw_audit.native_path(report['execution_root'])/'native-environment'))
    runtime_files(expected['native_runtime'],expected)
    for original,value in expected['reader_files'].items():
        require(sha(unlinked(original)) == value,'Reviewed reader/helper bytes changed: '+original)
    required = (Path(__file__).resolve(),Path(raw_audit.__file__).resolve(),
                Path(runtime_inputs.__file__).resolve(),Path(sys.modules['scripts.verify_frozen_mim'].__file__).resolve())
    require(all(str(p) in expected['reader_files'] for p in required),'Incomplete externally reviewed reader closure.')
    resource = raw_audit.native_path(report['resource_root'])
    collection = str(resource/'icstudio/assets/pdks/collection.json')
    require(report['collection_sha256'] == sha(external_file(collection,expected)) == expected['collection_sha256'], 'Bundled collection changed.')
    if expected['mode'] == 'installed':
        require(report['frozen'] is True and report['source_files'] == {} and report['build']['frozen'] is True and
                report['build']['dirty'] is False and re.fullmatch('[0-9a-f]{40}',expected['commit']) and
                report['build']['commit'] == expected['commit'],'Installed candidate differs.')
        require(raw_audit.native_path(report['engine']).parent == resource/'icstudio/assets/runtime/ngspice',
                'Installed engine escaped selected bundle.')
        require(expected['runtime']['manifest_sha256'] is not None,'Installed runtime manifest absent.')
        require('icstudio/esd_desktop_probe.py' in expected['candidate_sources'],'Probe absent from reviewed candidate sources.')
        # Source identity comes from Git objects at the requested immutable commit,
        # not current working-tree files or a claim inside the probe report.
        # One binary-safe Git batch preserves the same exact per-blob checks
        # without launching a Git process for every application source file.
        runtime_inputs.candidate_sources(expected['candidate_sources'],expected['commit'])
    else:
        require(expected['mode'] == 'source' and report['frozen'] is False and report['build']['frozen'] is False and expected['sources'] and
                report['source_files'] == expected['sources'],'Source development identity differs.')
    engine_dir = raw_audit.native_path(report['engine']).parent
    if expected['runtime']['manifest_sha256'] is not None:
        require(sha(external_file(str(engine_dir/'runtime-manifest.json'),expected)) == expected['runtime']['manifest_sha256'],
                'Shipped runtime manifest changed.')
    for name,value in expected['runtime']['files'].items():
        require(sha(external_file(str(engine_dir/relative(name)),expected)) == value,'Shipped support file changed.')
    require(report['conditions'] == [list(c) for c in CONDITIONS],'Incomplete condition selection.')
    return report


def package_at(path, expected):
    path = unlinked(path).resolve()
    require(sha(path/'package.json') == expected,'Unexpected package identity.')
    package = load(path/'package.json')
    for name,value in package['files'].items():
        child = unlinked(path/relative(name))
        require(child.is_file() and child.resolve().is_relative_to(path) and sha(child) == value,'Package asset mismatch.')
    return package


def project_file(root, row, name='project', origin=None):
    path = original_file(root,origin,row[name]) if origin else unlinked(row[name]).resolve()
    require(path.resolve().is_relative_to(root) and path.is_file(),'Missing or external lifecycle file.')
    if name == 'project': require(sha(path) == row['project_sha256'],'Changed lifecycle project.')
    return path


def technology(project, package):
    tech = copy.deepcopy(project['pdk'])
    root = raw_audit.native_path(tech.pop('package_root'))
    lock = tech.pop('package_lock')
    require(tech == package['technology'],'Selected technology differs from exact package.')
    require(lock == {**{k:package[k] for k in ('id','revision','files')},'manifest_hash':digest(package)},'Selected package lock differs.')
    return root


def exports(root, report, row, project, package, esd=False):
    def statements(field):
        return [shlex.split(line) for line in project_file(root,row,field,report['execution_root']).read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('*')]
    cell = project['cells'][0]
    expected = []
    if esd:
        for i in range(6):
            length,copies = (.9,2.,4.)[i//2],(1,3)[i%2]
            expected.append((f'X_Dq{i}',[f'q{i}{p}' for p in 'dgsb'],raw_audit.MODEL,
                             dict(w=10.,l=length,nf=1.,ad=2.9,**{'as':2.9},pd=20.58,ps=20.58,
                                  nrd=.029,nrs=.029,sa=0.,sb=0.,sd=0.,m=copies,mult=copies)))
    else:
        for i in range(2):
            expected.append((f'X_C{i+1}',['P','N'],f'sky130_fd_pr__cap_mim_m3_{i+1}',
                             dict(w=2+i,l=10,m=2+2*i,mf=2+2*i)))
    def devices(rows):
        require(len(rows) == len(expected),'Export device count differs.')
        for tokens,(name,nodes,model,parameters) in zip(rows,expected):
            prefix = [name,*nodes,model]
            require(tokens[:len(prefix)] == prefix,'Export terminal/model order differs.')
            pairs = [s.split('=') for s in tokens[len(prefix):]]
            require(all(len(p) == 2 for p in pairs) and len({p[0] for p in pairs}) == len(pairs),
                    'Export parameter syntax/duplicates differ.')
            require({k:float(v) for k,v in pairs} == parameters,'Export geometry/multiplicity differs.')
    reference = statements('reference')
    require(reference[0] == ['.subckt',cell['name'],*cell['ports']] and
            reference[-1] == ['.ends',cell['name']],'Native reference wrapper differs.')
    devices(reference[1:-1])
    schematic = statements('schematic'); includes = []
    origin = raw_audit.native_path(project['pdk']['package_root'])
    for item in package['technology']['simulation']['includes']:
        section = item.get('sections',{}).get('nominal',item.get('section'))
        path = (origin/item['path']).as_posix()
        includes.append(['.lib',path,section] if section else ['.include',path])
    require(schematic[:len(includes)] == includes and
            schematic[-3:] == [['.temp','27'],['.tran','2e-07','0.0001'],['.end']],
            'Export model include/default-analysis selection differs.')
    devices(schematic[len(includes):-3])


def lifecycle(root, report, optional):
    origin = report['execution_root']
    base = load(root/'base-package.json')
    require(sha(root/'base-package.json') == BASE and sha(root/'optional-package.json') == OPTIONAL,'Captured package identities differ.')
    require(load(root/'optional-package.json') == optional and load(root/'registry-package.json') == optional,'Registry semantic identity differs.')
    old = []
    for field in ('old_before','old_after'):
        project = load(project_file(root,report[field],origin=origin))
        old_original = technology(project,base)
        require(old_original.name == report['registry']['old_key'] and old_original.is_relative_to(raw_audit.native_path(origin)/'profile'),
                'Historical registry location differs.')
        old_root = original_file(root,origin,str(old_original))
        require(load(old_root/'package.json') == base,'Historical registry manifest changed.')
        for name,value in base['files'].items(): require(sha(inside(old_root,name)) == value,'Historical registry asset changed.')
        require(project['pdk']['simulation']['catalog'][KEY]['unavailable'],'Historical binding availability changed.')
        require(len(project['cells']) == 1 and project['top'] == project['cells'][0]['id'],'Historical top differs.')
        devices = project['cells'][0]['devices']
        require(len(devices) == 2 and [d['name'] for d in devices] == ['C1','C2'],'Historical MiM fixture differs.')
        for i,d in enumerate(devices):
            require(d['model_ref'] == dict(pdk='sky130A',revision=base['revision'],device=f'sky130_fd_pr/cap_mim_m3_{i+1}.sym')
                    and d['nets'] == {'c0':'P','c1':'N'} and
                    {k:float(d['model_params'][k]) for k in ('w','l','mf')} == dict(w=2+i,l=10,mf=2+2*i),
                    'Historical model or edited parameters differ.')
        old.append(project)
        exports(root,report,report[field],project,base)
    require(old[0] == old[1],'Historical project changed after optional install.')
    for field in ('schematic','reference'):
        require(project_file(root,report['old_before'],field,origin).read_bytes() == project_file(root,report['old_after'],field,origin).read_bytes(),
                'Historical exported circuit changed.')
    selected = load(project_file(root,report['selected'],origin=origin))
    current = technology(selected,optional)
    require(current == raw_audit.native_path(report['registry']['current_root']) and current.name == report['registry']['current_key']
            and current.is_relative_to(raw_audit.native_path(origin)/'profile'),'Selected GUI registry differs.')
    current = original_file(root,origin,str(current))
    require(load(current/'package.json') == optional,'Actual registry differs from optional package.')
    for name,value in optional['files'].items():
        require(sha(unlinked(current/relative(name))) == value,'Registry asset changed.')
    require(len(selected['cells']) == 1 and selected['top'] == selected['cells'][0]['id'],'Selected top/cell differs.')
    cell = selected['cells'][0]
    require(not any(cell.get(k) for k in ('wires','shapes','labels','junctions','ports')),'Unexpected selected geometry/connectivity.')
    require(len(cell['devices']) == 6,'Expected six GUI ESD specimens.')
    require(set(selected) == {'schema','id','name','revision','top','created','modified','pdk','cells','analysis','waivers'}
            and not selected['waivers'],'Unexpected project override.')
    require(len(report['bindings']) == 6,'Missing or duplicate GUI binding receipts.')
    for i,d in enumerate(cell['devices']):
        require(d['name'] == 'Dq'+str(i) and d['kind'] == 'NMOS' and d['rotation'] == 0
                and d['model_ref'] == dict(pdk='sky130A',revision=optional['revision'],device=KEY)
                and d['nets'] == d['net_labels'] == {p:'q'+str(i)+p for p in 'dgsb'},'Selected ESD identity/connectivity differs.')
        require(d['params']['w'] == '10u' and float(d['params']['l'].removesuffix('u')) == (.9,2,4)[i//2]
                and float(d['model_params']['nf']) == 1 and float(d['model_params']['mult']) == (1,3)[i%2],
                'Selected bin or multiplicity differs.')
        binding = report['bindings'][i]
        require(binding['device_id'] == d['id'] and binding['name'] == d['name'] and
                binding['model_ref'] == d['model_ref'] and binding['model'] == raw_audit.MODEL,
                'GUI binding receipt differs from saved device.')
        required_values = dict(w=10.,l=(.9,2.,4.)[i//2],nf=1.,mult=(1,3)[i%2])
        require(all(binding['values'].get(k) == v for k,v in required_values.items()),'Resolved GUI binding values differ.')
    exports(root,report,report['selected'],selected,optional,True)
    return selected


def derived_project(actual, selected, drive, role, title):
    require(len(actual['cells']) == 1,'Electrical project has extra cells.')
    actual_copy = copy.deepcopy(actual)
    sources = actual_copy['cells'][0]['devices'][6:]
    require(len(sources) == 25,'Unexpected electrical harness size.')
    devices = actual_copy['cells'][0]['devices'][:6]
    expected = copy.deepcopy(selected)
    expected['name'] = title
    for i,d in enumerate(expected['cells'][0]['devices']):
        if role == 'wrong-multiplicity': d['model_params']['mult'] = str(float(d['model_params']['mult'])*2)
        elif role == 'wrong-gate': d['nets']['g'] = d['nets']['s']; d['net_labels']['g'] = d['net_labels']['s']
        elif role == 'wrong-body': d['nets']['b'] = d['nets']['s']; d['net_labels']['b'] = d['net_labels']['s']
        elif role == 'wrong-length': d['params']['l'] = '2u' if i//2 == 2 else '4u'
    actual_copy['cells'][0]['devices'] = devices
    same_project(actual_copy,expected,'Electrical project did not derive from the saved GUI graph.')
    names = ['VG']+['Vq'+str(i)+p for i in range(6) for p in 'dgsb']
    require([s['name'] for s in sources] == names and len({s['id'] for s in sources+devices}) == 31,'Source identities differ.')
    for i,s in enumerate(sources):
        if i == 0:
            nodes,value,ac = {'p':'sweep','n':'0'},.8,0
        else:
            index,pin = divmod(i-1,4)
            terminal = 'dgsb'[pin]
            nodes = {'p':'q'+str(index)+terminal,'n':'sweep' if terminal == 'g' else '0'}
            value,ac = (.6,0,0,-.15)[pin],int(terminal == drive)
        require(s['kind'] == 'V' and s['nets'] == s['net_labels'] == nodes and float(s['value']) == value
                and s['source']['type'] == 'dc' and float(s['source']['ac']) == ac
                and s['x'] == (i%8)*300 and s['y'] == 1500+(i//8)*300 and s['rotation'] == 0,
                'Electrical harness differs from the declared sources.')


def title_for(report, case, role, revision=None):
    title = f"icstudio-esd-nvt-v2 {report['execution_id']} {case} {role}"
    return '* '+title if role == 'independent' else '* IC Design Studio / '+title+' / revision '+str(revision)


def execution(folder, report, case, role, revision, reference_report=None):
    record = load(folder/'execution-receipt.json')
    require(record.get('schema') == 1 and record.get('status') == 'PASS' and not record.get('error')
            and record['execution_id'] == report['execution_id'] and record['case'] == case and record['role'] == role,
            'Execution identity/status differs.')
    independent = role == 'independent'
    deck_name,raw_name = ('reference.cir','deck.raw') if independent else ('input.cir','result.raw')
    owner = reference_report if independent else report
    origin = raw_audit.native_path(owner['execution_root'])/'native'/case/role
    require(record['command'] == [report['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(origin/raw_name),str(origin/deck_name)]
            and record['cwd'] == str(origin) and record['engine_sha256'] == report['engine_sha256']
            and record['deck_filename'] == deck_name and record['raw_filename'] == raw_name,'Native command or engine differs.')
    require(record['environment'] == owner['native_environment'],'Native execution environment differs.')
    require(record['timeout_seconds'] == 180 and type(record['elapsed_seconds']) in (int,float)
            and math.isfinite(record['elapsed_seconds']) and record['elapsed_seconds'] >= 0,'Execution timing invalid.')
    start,end = (datetime.fromisoformat(record[k]) for k in ('started_utc','ended_utc'))
    require(start.utcoffset() == end.utcoffset() == timezone.utc.utcoffset(None) and start <= end
            and abs((end-start).total_seconds()-record['elapsed_seconds']) < 1,'Execution interval differs.')
    for filename,key in ((deck_name,'deck_sha256'),(raw_name,'raw_sha256'),('engine.log','log_sha256')):
        require(sha(folder/filename) == record[key],'Captured native artifact differs.')
    title = title_for(report,case,role,revision)
    require((folder/deck_name).read_text().splitlines()[0] == title,'Executed deck title differs.')
    return title


def references(root, package_path, reference_out, expected):
    """Run literal references using exactly the engine captured by the probe."""
    root = unlinked(root).resolve(); reference_out = unlinked(reference_out).resolve()
    require(not reference_out.exists() and not reference_out.is_relative_to(root) and not root.is_relative_to(reference_out),
            'References need a fresh separate evidence root.')
    report = header(root,expected)
    engine = unlinked(report['engine']).resolve()
    require(sha(engine) == report['engine_sha256'],'Captured engine changed before reference execution.')
    files = package_at(package_path,OPTIONAL)['files']
    reference_out.mkdir(parents=True)
    binding = dict(mode='installed' if expected['mode'] == 'installed' else 'source-pilot',resource_root=expected['resource_root'])
    env = runtime_inputs.native_environment(binding,engine,reference_out)
    before = runtime_inputs.runtime(binding,engine,env)
    runtime_equivalent(before,expected['native_runtime'])
    reference_report = dict(schema='esd-reference-v1',status='RUNNING',execution_id=report['execution_id'],
                            execution_root=str(reference_out),producer_report_sha256=expected['report_sha256'],
                            producer_manifest_sha256=expected['producer_manifest_sha256'],engine=report['engine'],
                            engine_sha256=report['engine_sha256'],native_environment=env,native_runtime_before=before,cases=[])
    write(reference_out/'report.json',reference_report)
    for corner,temp,drive in CONDITIONS:
        case = f'{corner}-{temp}-{drive}'
        app = root/'native'/case/'application'
        inverse = raw_audit.staged_models(app,Path(package_path),files)
        ref = reference_out/'native'/case/'independent'
        ref.mkdir(parents=True,exist_ok=False)
        shutil.copyfile(app/'pdk-model-files.json',ref/'pdk-model-files.json')
        for name in inverse.values():
            (ref/name).parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(app/name,ref/name)
        lines = [title_for(report,case,'independent'),'.lib '+inverse['libs.tech/ngspice/sky130.lib.spice']+' '+('tt' if corner == 'nominal' else corner)]
        for rel in ('libs.tech/ngspice/icstudio-parallel-varactors.spice','libs.tech/ngspice/icstudio-rf-ps2nw/library.spice',
                    'libs.tech/ngspice/icstudio-esd-nvt/'+raw_audit.MODEL+'.pm3.spice'):
            lines.append('.include '+inverse[rel])
        lines.append('VG sweep 0 .8 AC 0')
        for i in range(6):
            for pin,value in zip('dgsb',(.6,0.,0.,-.15)):
                lines.append(f'Vq{i}{pin} q{i}{pin} '+('sweep' if pin == 'g' else '0')+f' DC {value:g} AC {int(pin == drive)}')
            length,copies = (.9,2,4)[i//2],(1,3)[i%2]
            lines.append(f'Xq{i} '+' '.join(f'q{i}{p}' for p in 'dgsb')+' '+raw_audit.MODEL+
                         f' w=10 l={length:g} nf=1 ad=2.9 as=2.9 pd=20.58 ps=20.58 nrd=.029 nrs=.029 sa=0 sb=0 sd=0 m={copies} mult={copies}')
        lines += [f'.temp {temp}', '.dc VG 0 1.2 .03' if drive == 'dc' else '.ac dec 5 1k 1g','.end','']
        deck,raw = ref/'reference.cir',ref/'deck.raw'
        deck.write_text('\n'.join(lines),encoding='utf-8')
        command = [str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(raw),str(deck)]
        record = dict(schema=1,execution_id=report['execution_id'],case=case,role='independent',cwd=str(ref),command=command,
                      engine_sha256=sha(engine),deck_filename=deck.name,deck_sha256=sha(deck),raw_filename=raw.name,
                      started_utc=datetime.now(timezone.utc).isoformat(),timeout_seconds=180,status='RUNNING',environment=env)
        write(ref/'execution-receipt.json',record)
        start = time.monotonic()
        try:
            result = subprocess.run(command,cwd=ref,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
            (ref/'engine.log').write_bytes(result.stdout)
            require(result.returncode == 0 and raw.is_file(),'Independent native reference failed.')
            require(sha(deck) == record['deck_sha256'] and sha(engine) == record['engine_sha256'],'Reference inputs changed.')
            record.update(status='PASS',raw_sha256=sha(raw),log_sha256=sha(ref/'engine.log'))
        except Exception as exc:
            record.update(status='FAIL',error=repr(exc))
            reference_report.update(status='FAIL',error=repr(exc))
            write(reference_out/'report.json',reference_report)
            raise
        finally:
            record.update(ended_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-start)
            write(ref/'execution-receipt.json',record)
        reference_report['cases'].append([corner,temp,drive])
        write(reference_out/'report.json',reference_report)
    require(sha(engine) == report['engine_sha256'],'Engine changed during reference execution.')
    after = runtime_inputs.runtime(binding,engine,env)
    require(after == before,'Runtime changed during reference execution.')
    producer_inventory(root,expected)
    reference_report.update(status='PASS',native_runtime_after=after)
    write(reference_out/'report.json',reference_report)
    manifest = dict(schema=1,execution_id=report['execution_id'],files=inventory(reference_out))
    write(reference_out/'reference-manifest.json',manifest)
    return dict(status='PASS',reference_root=str(reference_out),reference_manifest_sha256=sha(reference_out/'reference-manifest.json'),
                producer_manifest_sha256=expected['producer_manifest_sha256'],native_executions=19)


def check_reference(root, expected, expected_manifest):
    require(sha(inside(root,'reference-manifest.json')) == expected_manifest,'Trusted reference manifest differs.')
    manifest = load(root/'reference-manifest.json')
    require(set(manifest) == {'schema','execution_id','files'} and manifest['schema'] == 1 and
            manifest['execution_id'] == expected['execution_id'] and
            manifest['files'] == inventory(root,('reference-manifest.json',)),'Reference evidence changed.')
    report = load(root/'report.json'); finite(report)
    require(report['schema'] == 'esd-reference-v1' and report['status'] == 'PASS' and not report.get('error') and
            report['execution_id'] == expected['execution_id'] and report['producer_report_sha256'] == expected['report_sha256'] and
            report['producer_manifest_sha256'] == expected['producer_manifest_sha256'] and
            report['engine'] == expected['engine'] and report['engine_sha256'] == expected['engine_sha256'] and
            report['cases'] == [list(c) for c in CONDITIONS],'Reference selection/provenance differs.')
    require(report['native_runtime_before'] == report['native_runtime_after'] and
            report['native_runtime_before']['environment'] == report['native_environment'],'Reference runtime changed.')
    runtime_equivalent(report['native_runtime_before'],expected['native_runtime'])
    # Independently constrain the only permitted environment differences.
    env = dict(expected['native_environment']); origin = raw_audit.native_path(report['execution_root'])
    env.update(HOME=str(origin/'empty-home'),USERPROFILE=str(origin/'empty-home'),
               TMP=str(origin/'temporary'),TEMP=str(origin/'temporary'))
    require(report['native_environment'] == env,'Reference environment contains an override.')
    return report


def numbers_match(actual, wanted, message):
    if isinstance(wanted,dict):
        require(isinstance(actual,dict) and actual.keys() == wanted.keys(),message+' keys')
        for name,value in wanted.items(): numbers_match(actual[name],value,message+'/'+name)
    elif isinstance(wanted,list):
        require(isinstance(actual,list) and len(actual) == len(wanted),message+' samples')
        for a,b in zip(actual,wanted): numbers_match(a,b,message)
    else:
        require(type(actual) in (int,float) and math.isfinite(actual) and
                abs(actual-wanted) <= 1e-30+1e-12*abs(wanted),message)


def application_result(folder, project, data, corner, temp, drive, engine_hash):
    """Independently reconstruct every displayed voltage/current vector from raw."""
    result = load(folder/'comparison-result.json'); finite(result)
    typ = 'dc' if drive == 'dc' else 'ac'
    settings = dict(type=typ,corner=corner,temperature=temp,source='VG',dc_start='0',dc_stop='1.2',dc_step='.03',start='1k',end='1g',points=5)
    require(result['schema'] == 1 and result['engine'] == 'ngspice (installed executable)' and
            result['engine_hash'] == engine_hash and result['project_id'] == project['id'] and
            result['revision'] == project['revision'] and result['cell_id'] == project['top'] and
            result['design_hash'] == digest({k:v for k,v in project.items() if k not in ('waivers','modified','native_migration')}) and
            result['pdk_hash'] == digest(project['pdk']) and result['rule_hash'] == digest(project['pdk']['layers']) and
            result['settings'] == settings,'Application result provenance/settings differ.')
    require(result['log'] == (folder/'engine.log').read_text(),'Application log differs from native log.')
    aliases = {d['name'].lower():d['name'] for d in project['cells'][0]['devices'][6:]}
    traces,phase,currents,current_phase = {},{},{},{}
    for name,values in data.items():
        if name.startswith('v(') and name.endswith(')') and not name.startswith('v(@'):
            key = name[2:-1]
            traces[key] = [v.real for v in values] if typ == 'dc' else [abs(v) for v in values]
            if typ == 'ac': phase[key] = [math.degrees(math.atan2(v.imag,v.real)) for v in values]
        elif (name.startswith('i(') and name.endswith(')')) or name.endswith('#branch'):
            key = name[2:-1] if name.startswith('i(') else name[:-7]
            key = aliases.get(key,key)
            currents[key] = [v.real for v in values] if typ == 'dc' else [abs(v) for v in values]
            if typ == 'ac': current_phase[key] = [math.degrees(math.atan2(v.imag,v.real)) for v in values]
    for key,wanted in dict(traces=traces,phase=phase,currents=currents,current_phase=current_phase).items():
        numbers_match(result[key],wanted,'Application '+key+' differs from native raw')
    scale = data['v(v-sweep)' if typ == 'dc' else 'frequency']
    numbers_match(result['x'],[v.real for v in scale],'Application domain differs from native raw')
    require(result['x_label'] == ('Source value' if typ == 'dc' else 'Frequency (Hz)') and
            result['y_label'] == ('Voltage (V)' if typ == 'dc' else 'Voltage magnitude (V)') and
            all(result[key] == {} for key in ('operating_point','device_operating_point','operating_currents')),
            'Application result shape differs from selected analysis.')


def current_balance(data):
    for i in range(6):
        for currents in zip(*(data[f'i(vq{i}{p})'] for p in 'dgsb')):
            require(abs(sum(currents)) <= 1e-11+1e-6*max(map(abs,currents)),
                    'Application or reference terminal current conservation failed.')


def audit(root, package_path, reference_root, expected, reference_manifest_sha256):
    root = unlinked(root).resolve()
    reference_root = unlinked(reference_root).resolve()
    require(not reference_root.is_relative_to(root) and not root.is_relative_to(reference_root),'Reference and producer roots overlap.')
    report = header(root,expected)
    reference_report = check_reference(reference_root,expected,reference_manifest_sha256)
    package = package_at(package_path,OPTIONAL)
    selected = lifecycle(root,report,package)
    worst = 0.
    require(len(report['cases']) == len(CONDITIONS),'Missing native cases.')
    for index,(corner,temp,drive) in enumerate(CONDITIONS):
        case = f'{corner}-{temp}-{drive}'
        roles = ('application',*raw_audit.FAULTS) if drive == 'dc' else ('application',)
        require(report['cases'][index] == dict(corner=corner,temperature_c=temp,drive=drive,roles=list(roles)),'Case order/roles differ.')
        data = {}
        for role in (*roles,'independent'):
            folder = (reference_root if role == 'independent' else root)/'native'/case/role
            raw_audit.deck(folder,Path(package_path),package['files'],corner,temp,drive,role)
            if role != 'independent':
                project = load(folder/'input.icproj')
                derived_project(project,selected,drive,role,f"icstudio-esd-nvt-v2 {report['execution_id']} {case} {role}")
            title = execution(folder,report,case,role,selected['revision'],reference_report)
            log = (folder/'engine.log').read_text()
            require(f'TEMP = {temp:.6f}' in log and 'TNOM = 27.000000' in log and 'Total analysis time' in log,'Native condition not exercised.')
            data[role],domain = raw_audit.raw(folder/('deck.raw' if role == 'independent' else 'result.raw'),drive,
                                            raw_audit.ENGINES[report['engine_sha256']],title)
            current_balance(data[role])
            if role != 'independent': application_result(folder,project,data[role],corner,temp,drive,report['engine_sha256'])
        worst = max(worst,*raw_audit.compare(data['application'],data['independent'],domain,drive,True))
        for role in roles[1:]: raw_audit.compare(data[role],data['independent'],domain,drive,False)
    producer_inventory(root,expected)
    return dict(status='PASS',mode=expected['mode'],installed_acceptance=expected['mode'] == 'installed',
                cases=19,native_executions=98,devices=6,fault_device_instances=360,maximum_normalized_error=worst,
                qualified=False,default_promoted=False,chunk_complete=False,report_sha256=expected['report_sha256'],
                producer_manifest_sha256=expected['producer_manifest_sha256'],reference_manifest_sha256=reference_manifest_sha256,
                reader_sha256=sha(__file__),original_execution_root=report['execution_root'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('references','audit'))
    parser.add_argument('--source',type=Path)
    for name in ('root','package','references','expected','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--reference-manifest-sha256')
    args = parser.parse_args()
    require(sha(unlinked(args.expected)) == args.expected_sha256,'Trusted expected-input file changed.')
    expected = load(args.expected)
    out = unlinked(args.output).resolve()
    require(not out.exists() and not out.is_relative_to(args.root.resolve()) and
            not out.is_relative_to(args.references.resolve()),'Write a new audit receipt outside immutable evidence.')
    if args.action == 'references': result = references(args.root,args.package,args.references,expected)
    else:
        require(re.fullmatch('[0-9a-f]{64}',args.reference_manifest_sha256 or ''),'Trusted reference-manifest hash required.')
        result = audit(args.root,args.package,args.references,expected,args.reference_manifest_sha256)
    write(out,result);print(json.dumps(result,indent=2))


if __name__ == '__main__': main()
