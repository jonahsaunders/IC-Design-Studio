"""Bounded public SKY130 DRC on four independently verified GUI MiM exports.

This is a local public block-geometry subgate, not complete-chip, density,
antenna, electrical, device-envelope or foundry qualification. Source pilots
cannot qualify an installed candidate.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import installed_mim_inputs as inputs
from scripts import verify_frozen_mim as gui
from icstudio.digital_sky130_native import FLAGS, SCOPE, REVISION, DECK_SHA256, LICENSE_SHA256, CATEGORIES_SHA256

require, sha, load, write = inputs.require, inputs.sha, inputs.load, inputs.write
ASSETS = dict(zip(('sky130A_mr.drc', 'GPL-3.0.txt', 'categories.json'),
                 (DECK_SHA256, LICENSE_SHA256, CATEGORIES_SHA256)))
CASES = ('p1-r0', 'p1-r90', 'p2-r0', 'p2-r90')
FAULT = 'p2-r90-narrow-metal'
RELEASE = 'release 2026.03.30_01.00'


def sources():
    paths = [ROOT/'scripts'/n for n in ('qualify_installed_sky130_mim_public_drc.py',
        'installed_mim_inputs.py', 'verify_frozen_mim.py', 'audit_sky130_mim_physical_case.py',
        'audit_sky130_mim_orientation.py')]
    paths += [p for p in (ROOT/'icstudio').glob('*.py') if p.name != 'build_info.py']
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def assets(binding):
    root = gui.unlinked(Path(binding['resource_root'])/'icstudio/assets/verification/sky130')
    result = {}
    for name, expected in ASSETS.items():
        path = inputs.checked_path(root/name)
        require(sha(path) == expected, 'Bundled public source changed: '+name)
        if binding['mode'] == 'installed':
            require(hashlib.sha256(gui.git_blob(binding['expected_commit'],
                'icstudio/assets/verification/sky130/'+name)).hexdigest() == expected,
                'Public source is outside the installed candidate.')
        result[name] = dict(path=str(path), sha256=expected)
    return result


def runtime(binding, source_engine=None):
    if binding['mode'] == 'installed':
        require(source_engine is None, 'Installed acceptance cannot override its included engine.')
        report = load(Path(binding['gui_root'])/'report.json')
        selected = report['managed_runtime_before']['runtime']
        require(selected == report['managed_runtime_after']['runtime'], 'GUI runtime changed.')
        root = Path(selected['root'])
        records = load(Path(binding['gui_root'])/'runtime/before/files.json')
        manifest = load(Path(binding['gui_root'])/'runtime/before/payload-manifest.json')
        require(sha(root/'opt/icstudio/files.json') == manifest['files_sha256'] and
                load(root/'opt/icstudio/files.json') == records and
                load(root/'opt/icstudio/runtime.json')['files_sha256'] == manifest['files_sha256'],
                'Included runtime inventory changed.')
        require(selected['kind'] == ('wsl' if os.name == 'nt' else 'linux'), 'Wrong included runtime platform.')
    else:
        require(source_engine is not None and sys.platform == 'linux',
                'Source bring-up requires an explicit existing Linux runtime KLayout.')
        engine = gui.unlinked(source_engine).absolute()
        require(engine.parts[-4:] == ('opt', 'icstudio', 'bin', 'klayout'),
                'Source pilot must select the existing recorded runtime launcher.')
        root = engine.parents[3]
        selected = dict(kind='linux', root=str(root), scope='Explicit source-pilot runtime; not installed application identity.')
        records = load(root/'opt/icstudio/files.json')
        require(sha(root/'opt/icstudio/files.json') == load(root/'opt/icstudio/runtime.json')['files_sha256'],
                'Source runtime inventory changed.')
    require(isinstance(records, dict) and bool(records), 'Missing runtime inventory.')
    require({'opt/icstudio/bin/klayout', 'usr/bin/klayout'} <= set(records), 'KLayout launcher/payload is not locked.')
    # Validate names on the host; hash the full locked payload on its native
    # filesystem to avoid tens of thousands of Windows UNC round trips.
    for name, value in records.items():
        gui.relative(name)
        require(re.fullmatch('[0-9a-f]{64}', value or ''), 'Invalid runtime hash: '+name)
    for name in ('opt/icstudio/bin/klayout','usr/bin/klayout','opt/icstudio/bin/python3'):
        require(name in records and sha(root/name) == records[name], 'Runtime entry point changed: '+name)
    native_root = '/' if selected['kind']=='wsl' else str(root)
    prefix = [shutil.which('wsl.exe') or 'wsl.exe','--distribution',selected['distro'],'--exec'] if selected['kind']=='wsl' else []
    python = str(PurePosixPath(native_root)/'opt/icstudio/bin/python3')
    script = ('import hashlib,json,pathlib,sys; r=pathlib.Path(sys.argv[1]); '
        'p=r/"opt/icstudio/files.json"; h=lambda q: hashlib.file_digest(q.open("rb"),"sha256").hexdigest(); '
        'assert h(p)==sys.argv[2], "Runtime lock changed"; m=json.loads(p.read_text()); '
        'bad=[n for n,v in m.items() if not (r/n).is_file() or h(r/n)!=v]; '
        'assert not bad, "Runtime files changed: "+repr(bad[:10]); '
        'print(json.dumps({"status":"PASS","files":len(m),"files_sha256":h(p)},sort_keys=True))')
    args=prefix+['/usr/bin/env','-i','PATH=/usr/bin:/bin','LANG=C','LC_ALL=C',python,'-B','-c',script,native_root,sha(root/'opt/icstudio/files.json')]
    result=subprocess.run(args,capture_output=True,text=True,timeout=600)
    require(result.returncode==0,'Native runtime inventory check failed: '+(result.stdout+result.stderr)[-2000:])
    proof=json.loads(result.stdout)
    require(proof==dict(status='PASS',files=len(records),files_sha256=sha(root/'opt/icstudio/files.json')),'Unexpected runtime inventory proof.')
    return dict(selected=selected, files=records, files_sha256=sha(root/'opt/icstudio/files.json'),
                runtime_sha256=sha(root/'opt/icstudio/runtime.json'), verification=dict(command=args,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,result=proof), engine='opt/icstudio/bin/klayout',
                engine_sha256=records['opt/icstudio/bin/klayout'], payload_sha256=records['usr/bin/klayout'],
                scope='Complete recorded managed runtime inventory; not a hermetic host OS claim.')


def native_stage(runtime_info, out, nonce):
    selected = runtime_info['selected']
    if selected['kind'] == 'wsl':
        native = '/var/tmp/icstudio-mim-public-drc-'+nonce
        host = Path(selected['root'])/native.lstrip('/')
        prefix = [shutil.which('wsl.exe') or 'wsl.exe', '--distribution', selected['distro'], '--exec']
        engine = '/opt/icstudio/bin/klayout'
    else:
        host = out/'native'; native = str(host)
        prefix = []
        engine = str(Path(selected['root'])/'opt/icstudio/bin/klayout')
    require(not host.exists(), 'Native stage already exists; fresh evidence is required.')
    host.mkdir(parents=True)
    return host, native, prefix, engine


def command(prefix, engine, folder, top):
    variables = dict(input=folder+'/input.gds', top_cell=top, report=folder+'/report.lyrdb', thr='1', **FLAGS)
    args = prefix+['/usr/bin/env', '-i', 'PATH=/usr/bin:/bin', 'HOME='+folder+'/home',
                   'LANG=C', 'LC_ALL=C', 'QT_QPA_PLATFORM=offscreen', engine, '-b', '-r', folder+'/sky130A_mr.drc']
    for key, value in variables.items():
        args += ['-rd', key+'='+str(value)]
    return args, variables


def measured(path, top, categories):
    root = ET.parse(path).getroot()
    require(root.tag == 'report-database' and root.findtext('top-cell') == top, 'Wrong public report format/top.')
    actual = [v.text for v in root.findall('./categories/category/name')]
    require(len(categories) == 255 and sorted(actual) == categories and len(set(actual)) == len(actual),
            'Public rule categories are missing, duplicated or changed.')
    items = root.find('items'); require(items is not None, 'Missing raw violation inventory.')
    counts = Counter()
    for item in items:
        require(item.tag == 'item' and item.findtext('category'), 'Malformed raw violation.')
        name = item.findtext('category').strip("'")
        require(name in actual, 'Unknown raw violation category.')
        counts[name] += 1
    return dict(categories=len(actual), markers=sum(counts.values()), violations=dict(sorted(counts.items())))


def fault(source, target, top):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(source)); cell = layout.cell(top)
    require(cell is not None and abs(layout.dbu-.001) < 1e-12, 'Unexpected control layout/top/grid.')
    metal = layout.layer(68, 20)
    cell.shapes(metal).insert(db.Box(100000, 100000, 100100, 100100))
    layout.write(str(target))
    fault_geometry(source, target, top)


def fault_geometry(source, target, top):
    import klayout.db as db
    a, b = gui.mask_read(source, top), gui.mask_read(target, top)
    def texts(path):
        layout=db.Layout(); layout.read(str(path)); cell=layout.cell(top)
        require(cell is not None and not list(cell.each_inst()), 'Control requires a flat coupon.')
        return sorted((layout.get_info(i).layer,layout.get_info(i).datatype,str(s.text))
            for i in layout.layer_indexes() for s in cell.shapes(i).each() if s.is_text())
    require(texts(source) == texts(target), 'Control altered text or ports.')
    expected = db.Region(db.Box(100000, 100000, 100100, 100100))
    require((a.get((68, 20), db.Region()) & expected).is_empty(), 'Control overlaps source metal.')
    for layer in set(a)|set(b):
        old, new = a.get(layer, db.Region()), b.get(layer, db.Region())
        wanted = (old | expected).merged() if layer == (68, 20) else old
        require((wanted ^ new).is_empty(), 'Control changed unintended masks: '+str(layer))
    return dict(layer=[68,20], box_dbu=[100000,100000,100100,100100], dbu_um=.001,
                width_um=.1, required_minimum_um=.14, required_category='MR_met1.WID.1')


def guard(binding, asset_map):
    root = Path(binding['gui_root'])
    require(sha(root/'report.json') == binding['report_sha256'] and sha(root/'files.json') == binding['files_sha256'] and
            load(root/'files.json') == gui.inventory(root, ('files.json','report.json')), 'Original GUI evidence changed.')
    for row in binding['cases'].values():
        for name, value in row['files'].items():require(sha(value) == row['hashes'][name], 'Original GUI input changed: '+name)
    for row in asset_map.values():require(sha(row['path']) == row['sha256'], 'Bundled public source changed.')
    package = binding['simulation_package']; gui.package(package['path'], package['manifest_sha256'])
    require(sha(Path(package['path']).parent/'collection.json') == package['collection_sha256'], 'Package collection changed.')
    if binding['mode'] == 'installed':
        supplied = Path(binding['supplied_root'])
        require(sha(supplied/'verification.json') == binding['verification_sha256'] and
                sha(supplied/'invocation.json') == binding['invocation_sha256'] and
                sha(binding['application']['path']) == binding['application']['sha256'], 'Installed prerequisite identity changed.')


def execute_case(name, row, source, asset_map, host, native, prefix, engine, out):
    folder = host/name; folder.mkdir(); (folder/'home').mkdir()
    if name == FAULT:fault(source, folder/'input.gds', row['top'])
    else:shutil.copyfile(source, folder/'input.gds')
    for asset, value in asset_map.items():shutil.copyfile(value['path'], folder/asset)
    before = gui.inventory(folder)
    args, variables = command(prefix, engine, native+'/'+name, row['top'])
    invocation = dict(command=args, native_directory=native+'/'+name, host_directory=str(folder),
                      cwd=str(out), environment='Native env -i; exact inline assignments precede locked launcher.', settings=variables)
    write(folder/'invocation.json', invocation)
    started = time.monotonic()
    env = {k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
    with (folder/'console.log').open('wb') as log:
        result = subprocess.run(args, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    elapsed = time.monotonic()-started
    text = (folder/'console.log').read_text(errors='replace')
    require(result.returncode == 0 and text.splitlines().count(RELEASE) == 1 and not re.search(r'(?m)^ERROR:',text),
            'Public native DRC failed or did not finish: '+name)
    require(all(sha(folder/n) == h for n,h in before.items()), 'Public DRC inputs changed.')
    values = measured(folder/'report.lyrdb', row['top'], load(folder/'categories.json'))
    require(values['violations'].get('MR_met1.WID.1',0)>0 if name == FAULT else values['markers']==0,
            'Expected public DRC clean/control result was not observed: '+name)
    if host != out/'native':
        destination = out/'native'/name; destination.parent.mkdir(exist_ok=True)
        shutil.copytree(folder, destination)
        require(gui.inventory(folder) == gui.inventory(destination), 'Public native transfer changed evidence.')
    return dict(case=name, gui_case='p2-r90' if name == FAULT else name, top=row['top'],
                gui_job_id=row['job_id'], gui_design_hash=row['design_hash'], original_gds_sha256=row['hashes']['gds'],
                input_sha256=sha(folder/'input.gds'), invocation=invocation, elapsed_seconds=elapsed,
                returncode=result.returncode, raw_sha256=sha(folder/'report.lyrdb'), console_sha256=sha(folder/'console.log'),
                status='PASS', **values)


def audit(out, binding=None, _verified_runtime=None):
    """Reparse retained native XML, exact commands, input geometry and identities."""
    out = gui.unlinked(out).resolve(); record = load(out/'record.json')
    require(record.get('schema') == 1 and record.get('status') == 'PASS' and
            record.get('gate') == 'mim-installed-public-drc' and
            all(record.get(k) is False for k in ('qualified','release_ready','full_mim_installed')), 'Invalid public DRC scope/status.')
    require(re.fullmatch('[0-9a-f]{32}',record.get('execution_id','')) and record['execution_root'] == str(out),
            'Wrong fresh public DRC execution identity/root.')
    saved = record['binding']
    if binding is None:binding = inputs.bind_gui(saved['supplied_root'], saved['expected_commit'], source_pilot=saved['mode']=='source-pilot')
    require(saved == binding and record['mode'] == binding['mode'] and
            record['installed'] == (binding['mode']=='installed'), 'Public DRC GUI/candidate identity differs.')
    require(record['policy'] == dict(flags=FLAGS, revision=REVISION, scope=SCOPE, assets=ASSETS), 'Public policy differs.')
    require(record['source_files'] == sources(), 'Public checker source changed.')
    if binding['mode'] == 'installed':inputs.candidate_sources(record['source_files'],binding['expected_commit'])
    asset_map = assets(binding); require(record['assets'] == asset_map, 'Public source paths differ.')
    guard(binding,asset_map)
    require(record['runtime_before'] == record['runtime_after'], 'Native runtime changed.')
    rt = record['runtime_before']; selected=rt['selected']
    actual_runtime = _verified_runtime if _verified_runtime is not None else runtime(binding, record.get('source_klayout'))
    require(actual_runtime == rt, 'Retained runtime differs from the actual selected GUI runtime.')
    runtime_root = Path(selected['root'])
    engine = '/opt/icstudio/bin/klayout' if selected['kind']=='wsl' else str(runtime_root/'opt/icstudio/bin/klayout')
    prefix = [shutil.which('wsl.exe') or 'wsl.exe','--distribution',selected['distro'],'--exec'] if selected['kind']=='wsl' else []
    require([r['case'] for r in record['cases']] == [*CASES,FAULT], 'Incomplete/duplicate public DRC selection.')
    for row in record['cases']:
        name=row['case']; case=binding['cases'][row['gui_case']]; folder=out/'native'/name
        require(row['gui_case'] == ('p2-r90' if name==FAULT else name) and row['top']==case['top'] and
                row['gui_job_id']==case['job_id'] and row['gui_design_hash']==case['design_hash'] and
                row['original_gds_sha256']==case['hashes']['gds'] and row['input_sha256']==sha(folder/'input.gds'),
                'Public DRC input identity differs.')
        if name==FAULT:fault_geometry(case['files']['gds'],folder/'input.gds',case['top'])
        else:require(sha(folder/'input.gds')==case['hashes']['gds'],'Fresh DRC did not use exact GUI export.')
        for asset,h in ASSETS.items():require(sha(folder/asset)==h,'Staged public source changed.')
        native = ('/var/tmp/icstudio-mim-public-drc-'+record['execution_id'] if selected['kind']=='wsl' else str(out/'native'))+'/'+name
        args,variables=command(prefix,engine,native,case['top'])
        invocation=load(folder/'invocation.json')
        require(invocation==row['invocation'] and invocation['command']==args and invocation['settings']==variables and
                invocation['native_directory']==native and invocation['cwd']==str(out), 'Native invocation differs.')
        text=(folder/'console.log').read_text(errors='replace')
        require(row['returncode']==0 and row['status']=='PASS' and text.splitlines().count(RELEASE)==1 and
                not re.search(r'(?m)^ERROR:',text) and sha(folder/'console.log')==row['console_sha256'] and
                sha(folder/'report.lyrdb')==row['raw_sha256'], 'Native completion/integrity differs.')
        values=measured(folder/'report.lyrdb',case['top'],load(folder/'categories.json'))
        require(all(row[k]==v for k,v in values.items()),'Saved public result differs from raw XML.')
        require(values['violations'].get('MR_met1.WID.1',0)>0 if name==FAULT else values['markers']==0,
                'Public raw clean/control decision differs.')
    require(sha(out/'files.json')==record['files_sha256'] and load(out/'files.json')==gui.inventory(out,('files.json','record.json','verification.json')),
            'Public DRC evidence inventory changed.')
    return dict(status='PASS',gate='mim-installed-public-drc',mode=binding['mode'],installed=record['installed'],
                expected_commit=binding['expected_commit'],gui_execution_id=binding['execution_id'],execution_id=record['execution_id'],
                positive_layouts=4,detected_geometry_controls=1,raw_categories_per_layout=255,
                record_sha256=sha(out/'record.json'),files_sha256=sha(out/'files.json'),qualified=False,release_ready=False,full_mim_installed=False)


def run(gui_root,out,expected_commit=None,source_pilot=False,source_klayout=None):
    out=gui.unlinked(out).resolve(); require(not out.exists(),'Use a new output directory.')
    require((source_pilot and expected_commit is None and source_klayout is not None) or
            (not source_pilot and source_klayout is None and re.fullmatch('[0-9a-f]{40}',expected_commit or '')),
            'Choose exact installed candidate or explicit source-pilot mode.')
    out.mkdir(parents=True);started=time.monotonic();nonce=uuid.uuid4().hex
    record=dict(schema=1,gate='mim-installed-public-drc',status='RUNNING',execution_id=nonce,execution_root=str(out),
                qualified=False,release_ready=False,full_mim_installed=False,scope=__doc__,cases=[])
    host=None
    try:
        binding=inputs.bind_gui(gui_root,expected_commit,source_pilot=source_pilot)
        require(list(binding['cases'])==list(CASES),'Incomplete GUI binding.')
        locked=sources()
        if not source_pilot:inputs.candidate_sources(locked,expected_commit)
        asset_map=assets(binding);rt=runtime(binding,source_klayout)
        record.update(binding=binding,source_files=locked,assets=asset_map,runtime_before=rt,
            mode=binding['mode'],installed=not source_pilot,source_klayout=str(Path(source_klayout).absolute()) if source_pilot else None,policy=dict(flags=FLAGS,revision=REVISION,scope=SCOPE,assets=ASSETS))
        write(out/'record.json',record)
        host,native,prefix,engine=native_stage(rt,out,nonce)
        for name in (*CASES,FAULT):
            row=binding['cases']['p2-r90' if name==FAULT else name]
            record['cases'].append(execute_case(name,row,Path(row['files']['gds']),asset_map,host,native,prefix,engine,out))
            write(out/'record.json',record)
        guard(binding,asset_map);record['runtime_after']=runtime(binding,source_klayout)
        require(record['runtime_after']==rt and locked==sources(),'Source/runtime changed during public DRC.')
        record.update(status='PASS',elapsed_seconds=time.monotonic()-started)
        write(out/'files.json',gui.inventory(out,('files.json','record.json','verification.json')))
        record['files_sha256']=sha(out/'files.json');write(out/'record.json',record)
        verified=audit(out,binding,record['runtime_after']);write(out/'verification.json',verified)
        # Retain the bounded WSL stage until archive recovery is verified.
        # Cleanup is an explicit external maintenance step, not acceptance.
        print(json.dumps(verified));return 0
    except Exception as exc:
        record.update(status='FAIL',error=str(exc),traceback=traceback.format_exc(),elapsed_seconds=time.monotonic()-started)
        write(out/'record.json',record);print(json.dumps(dict(status='FAIL',error=str(exc))),flush=True);return 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--expected-commit');parser.add_argument('--source-pilot',action='store_true')
    parser.add_argument('--source-klayout',type=Path)
    args=parser.parse_args();return run(args.gui,args.out,args.expected_commit,args.source_pilot,args.source_klayout)


if __name__=='__main__':raise SystemExit(main())
