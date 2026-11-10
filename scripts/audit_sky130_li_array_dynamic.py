"""Offline historical-input and fresh raw-output audit; no simulator execution.

Finite model linkage only. Historical physical evidence is never relabelled as
fresh extraction, current installed acceptance, calibration or qualification.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

ARCHIVE_SHA='1d0ec0f2afa8739754dc85e34ec5c2fcfe82a640dae043b11960418e225771fa'
CANDIDATE='53c17aa78eb510715eaa28ed34e4f576a7fe7b40'
GUI='frozen-metal-parallel-evidence/'
ELECTRICAL='frozen-metal-parallel-electrical-evidence/'
CASES=tuple(f'l1-m{m}-r{r}' for m in (3,16) for r in (0,90))
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def digest(data):return hashlib.sha256(data).hexdigest()
def require(test,message):
    if not test:raise ValueError(message)


def safe(name):
    p=PurePosixPath(name)
    require(isinstance(name,str) and name and not p.is_absolute() and
            all(s not in ('','.','..') for s in name.split('/')) and '\\' not in name and ':' not in name,'Unsafe member')
    return name


def primitive_rows(text, count, application=False):
    lines=[s.split() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('*')]
    require(lines[0]==['.subckt','coupon','R1','R2'] and lines[-1] in (['.ends'],['.ends','coupon']),'Unexpected interface')
    rows=lines[1:-1];require(len(rows)==(1 if application else count),'Wrong actual unit count')
    require(len({r[0].lower() for r in rows})==len(rows),'Duplicate primitive')
    for row in rows:
        require(len(row)>=6 and row[0].startswith('R') and set(row[1:3])=={'R1','R2'} and row[3]=='sky130_fd_pr__res_generic_l1','Wrong native graph/model')
        pairs=[v.split('=') for v in row[4:]];require(all(len(p)==2 for p in pairs),'Malformed parameters')
        params=dict(pairs);require(len(params)==len(pairs),'Duplicate parameter')
        require(params==({'l':'5','m':str(count),'w':'2'} if application else {'w':'2','l':'5'}),'Wrong unit dimensions/multiplicity')
    return rows


def archive_inputs(archive):
    """Authenticate archive, all two-stage manifest members, then four inputs.

    Does not run archived code, replay GUI checks or claim a new physical pass.
    """
    require(sha(archive)==ARCHIVE_SHA,'Wrong historical artifact')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();require(len(names)==len(set(names)),'Duplicate archive member')
        for i in z.infolist():
            safe(i.filename);require(not stat.S_ISLNK(i.external_attr>>16),'Linked archive member')
        read=z.read;load=lambda n:json.loads(read(n))
        receipt=load(GUI+'verification.json');report=load(GUI+'probe/report.json');inv=load(GUI+'invocation.json')
        require(receipt['status']=='PASS' and receipt['expected_commit']==CANDIDATE==inv['expected_commit'],'Historical candidate receipt differs')
        require(report['build']['commit']==CANDIDATE and report['build']['dirty'] is False and report['native_execution'] is True,'Historical build differs')
        require(report['execution_id']==receipt['execution_id']==inv['execution_id'],'Historical nonce differs')
        require(digest(read(GUI+'probe/report.json'))==receipt['report_sha256'],'Historical report differs')
        require(digest(read(GUI+'probe/files.json'))==receipt['files_sha256']==report['files_sha256'],'Historical GUI manifest differs')
        manifests={GUI+'probe/':load(GUI+'probe/files.json'),ELECTRICAL:load(ELECTRICAL+'manifest.json')}
        verified={}
        for prefix,files in manifests.items():
            for name,value in files.items():
                member=prefix+safe(name);require(digest(read(member))==value,'Historical manifest member changed: '+member);verified[member]=value
        q=load(ELECTRICAL+'qualification.json')
        require(q['status']=='PASS' and q['expected_commit']==CANDIDATE,'Historical electrical receipt differs')
        normal=load(ELECTRICAL+'normalized-inputs.json');selected={};payload={}
        origin=report['execution_root'].rstrip('/')+'/'
        def gui_member(path):
            require(path.startswith(origin),'Historical path outside probe')
            return GUI+'probe/'+safe(path[len(origin):])
        for case in CASES:
            item=next(x for x in report['lifecycle'] if x['case']==case)
            physical=next(x for x in report['physical'] if x['case']==case)
            require(item['model']=='l1' and item['width_um']==2 and item['length_um']==5 and item['multiplicity']==int(case.split('-')[1][1:]),'Wrong selected geometry')
            require(physical['job_id']==item['native_job_id'] and physical['design_hash']==item['native_design_hash'],'Native job binding differs')
            native=physical['report'];require(native['status']=='passed' and native['drc_count']==0 and native['magic_drc_style']=='drc(full)' and native['drc_engine']==native['lvs_extractor']=='magic','Historical physical result differs')
            require([(s['name'],s['status']) for s in native['stages']]==[(n,'passed') for n in ('preflight','layout_export','drc','lvs_extraction','lvs','integrity')],'Historical physical stages differ')
            selected[case]={'multiplicity':item['multiplicity'],'rotation':item['rotation'],'native_job_id':item['native_job_id'],'native_design_hash':item['native_design_hash'],'files':{}}
            for key in ('reference','native','gds','oas','project'):
                member=gui_member(item[key]);require(digest(read(member))==item[key+'_sha256'],'Selected physical file differs')
                selected[case]['files'][key]={'member':member,'sha256':item[key+'_sha256']};payload[member]=read(member)
            for kind,key in [('application','reference'),('native','native')]:
                entry=normal[case][kind];data=read(gui_member(item[key]));require(digest(data)==entry['original_sha256'],'Original electrical input differs')
                retained=ELECTRICAL+f'original-inputs/{case}/{kind}.spice';require(read(retained)==data,'Original retained bytes differ')
                # Independently replay the recorded top-token-only edit proof.
                edits=entry['proof']['edits'];last=len(data);normalized=data
                for edit in reversed(edits):
                    a,b=edit['start'],edit['stop'];require(0<=a<b<=last and data[a:b].decode()==edit['before']==item['top'] and edit['after']=='coupon','Invalid top-only normalization')
                    normalized=normalized[:a]+b'coupon'+normalized[b:];last=a
                member=ELECTRICAL+f'normalized-inputs/{case}/{kind}.spice'
                require(normalized==read(member) and digest(normalized)==entry['normalized_sha256'],'Normalized native input differs')
                primitive_rows(normalized.decode(),item['multiplicity'],application=kind=='application')
                selected[case]['files'][kind+'_normalized']={'member':member,'sha256':digest(normalized)};payload[member]=normalized;payload[retained]=data
        for name in names:
            if name.startswith(ELECTRICAL+('pdk-models/')) or name.startswith(ELECTRICAL+'original-package/') or name in (ELECTRICAL+'selected-model-lines.json',ELECTRICAL+'pdk-model-files.json',ELECTRICAL+'package-files.json',ELECTRICAL+'staged-model-files.json',ELECTRICAL+'normalized-inputs.json',GUI+'verification.json',GUI+'invocation.json',GUI+'probe/report.json',GUI+'probe/files.json',ELECTRICAL+'manifest.json',ELECTRICAL+'qualification.json'):
                payload[name]=read(name)
        return {'archive_sha256':ARCHIVE_SHA,'historical_candidate':CANDIDATE,'historical_nonce':report['execution_id'],'verified_manifest_members':len(verified),'cases':selected,'retained_members':{n:digest(b) for n,b in payload.items()}},payload


def transient_expected(t,resistance):
    gain=10/(10+resistance);tau=1e-9/(.1+1/resistance);rise=1e-9
    if t<=rise:return .001*gain*(t-tau*(-math.expm1(-t/tau)))/rise
    return .001*gain*(1-tau/rise*(-math.expm1(-rise/tau))*math.exp(-(t-rise)/tau))


def resistance(count):return 12.2*5e-6/(2e-6+17e-9)*(1+.0006045*(-3)-3.693e-7*9)/count


def observe(path,analysis,count):
    # Existing independent ASCII reader rejects malformed/truncated/nonfinite
    # plots. Numerical expectations here do not invoke the runner or simulator.
    from scripts.audit_sky130_li_linked import raw
    data,x=raw(path);r=resistance(count)
    require(all(b>a for a,b in zip(x,x[1:])),'Nonmonotonic axis')
    if analysis=='tran':
        require(set(data)=={'time','v(input)','v(output)','i(vdrive)'} and len(x)>=2000 and x[0]==0 and abs(x[-1]-1e-7)<1e-16,'Wrong transient coverage')
        expected=[transient_expected(t,r) for t in x];actual=data['v(output)'];absolute=1e-8;relative=2e-4
        require(max(abs(v-.001*min(t/1e-9,1)) for t,v in zip(x,data['v(input)']))<1e-12,'Wrong transient drive')
        kcl=max(abs(i+(v-o)/r) for i,v,o in zip(data['i(vdrive)'],data['v(input)'],actual))
    elif analysis=='noise':
        require(set(data)=={'frequency','onoise_spectrum','inoise_spectrum'} and len(x)==121 and all(abs(f/(1e3*10**(i/20))-1)<1e-10 for i,f in enumerate(x)),'Wrong noise coverage')
        req=1/(.1+1/r);expected=[math.sqrt(4*1.38064852e-23*300.15*req/(1+(2*math.pi*f*req*1e-9)**2)) for f in x];actual=data['onoise_spectrum'];absolute=1e-18;relative=1e-6;kcl=None
        require(all(v>0 for v in actual+data['inoise_spectrum']),'Nonpositive noise')
    else:raise ValueError('Unknown dynamic analysis')
    maximum=max(abs(a-b)/(absolute+relative*abs(b)) for a,b in zip(actual,expected))
    return {'samples':len(x),'maximum_normalized_error':maximum,'kcl_absolute_error':kcl,'passed':maximum<=1 and (kcl is None or kcl<=1e-11)}


def expected_selection():
    expected={}
    for case in CASES:
        for analysis in ('tran','noise'):
            for kind in ('application','native','analytic'):
                expected[f'{case}-{analysis}-{kind}']=(case,analysis,kind,None)
    for fault in ('remove-one-unit','one-unit-width-3um','load-capacitance-2nF'):
        for analysis in ('tran','noise'):
            expected[f'l1-m3-r0-{analysis}-native-{fault}']=('l1-m3-r0',analysis,'native',fault)
    return expected


def validate_rows(rows):
    expected=expected_selection()
    require(len(rows)==len(expected) and {r['name'] for r in rows}==set(expected),'Incomplete/duplicate dynamic selection')
    for row in rows:
        name=row['name'];case,analysis,kind,fault=expected[name];count=int(case.split('-')[1][1:])
        require((row['case'],row['analysis'],row['kind'],row['fault'],row['count'])==(case,analysis,kind,fault,count),'Wrong dynamic row identity')
        for key,basename in [('raw','result.raw'),('deck','input.cir'),('circuit','circuit.spice'),('log','console.log')]:
            require(row[key]==f'runs/{name}/{basename}','Unbound/reused dynamic output')
    return expected


def verify_inventory(root,files):
    root=Path(root)
    require(not any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in root.rglob('*')),'Linked dynamic evidence')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.relative_to(root).as_posix() not in ('run.json','audit.json')}
    require(actual==set(files),'Dynamic evidence inventory differs')
    for name,value in files.items():require(sha(root/safe(name))==value,'Changed dynamic evidence: '+name)


def audit(root):
    require(sys.platform=='linux','This fresh execution/dependency profile is Linux-only; no Windows acceptance inferred')
    root=Path(root).resolve();record=json.loads((root/'run.json').read_text());require(record['status']=='PASS','Incomplete dynamic run')
    require(record['qualified'] is False and record['installed_acceptance'] is False and record['fresh_physical_acceptance'] is False,'Overstated dynamic scope')
    require(record['output_root']==str(root) and re.fullmatch('[0-9a-f]{32}',record['nonce']),'Wrong execution identity')
    contract_sha='d010749d9278e3dcd99763af17d6f0850b1d5fb82c299c76875c3cf58193c055'
    require(sha(root/'contract.json')==record['contract_sha256']==contract_sha,'Dynamic contract identity differs')
    spec=json.loads((root/'contract.json').read_text())
    verify_inventory(root,record['files'])
    validate_rows(record['runs'])
    for name,value in record['source_files'].items():
        require(sha(ROOT/safe(name))==value==sha(root/'source'/name),'Source snapshot differs')
    require(set(record['source_files'])=={'docs/qualification/sky130-li-array-dynamic-v1.json','scripts/qualify_sky130_li_array_dynamic.py','scripts/audit_sky130_li_array_dynamic.py','scripts/stage_linux_ngspice.py','scripts/audit_sky130_li_linked.py','tests/test_sky130_li_array_dynamic.py'},'Missing checker sources')
    recovered,payload=archive_inputs(record['historical_archive'])
    require(record['historical_archive_sha256']==ARCHIVE_SHA and json.loads((root/'recovery.json').read_text())==recovered,'Historical recovery binding differs')
    for name,data in payload.items():require((root/'historical'/safe(name)).read_bytes()==data,'Historical materialization changed')
    runtime=spec['runtime'];engine=root/'engine/runtime/ngspice'
    require(sha(engine)==runtime['engine_sha256'] and sha(engine.parent/'spinit')==runtime['spinit_sha256'],'Actual engine differs')
    require(sha(root/'engine/manifest.json')==runtime['manifest_sha256'],'Runtime source/license manifest differs')
    rm=json.loads((root/'engine/manifest.json').read_text())
    for name,item in rm['files'].items():require(sha(root/'engine'/safe(name))==item['sha256'],'Runtime closure changed')
    for when in ('before','after'):
        require(json.loads((root/f'dependencies-{when}.json').read_text())==runtime['actual_host_dependencies'],'Runtime dependency receipt differs')
    for name,item in runtime['actual_host_dependencies'].items():require(sha(name)==item['sha256'],'Host dependency changed since execution')
    expected=expected_selection();rows=record['runs']
    require(len(rows)==len(expected) and {r['name'] for r in rows}==set(expected),'Incomplete/duplicate dynamic selection')
    outcomes=[]
    for row in rows:
        name=row['name'];case,analysis,kind,fault=expected[name];count=int(case.split('-')[1][1:])
        require((row['case'],row['analysis'],row['kind'],row['fault'],row['count'])==(case,analysis,kind,fault,count),'Wrong dynamic row identity')
        folder=root/'runs'/name
        for key,basename in [('raw','result.raw'),('deck','input.cir'),('circuit','circuit.spice'),('log','console.log')]:
            require(row[key]==f'runs/{name}/{basename}' and row[key] in record['files'],'Unbound/reused dynamic output')
        require(row['cwd']==str(root/'historical'/ELECTRICAL) and row['returncode']==0,'Wrong native invocation context')
        require(row['command']==[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(folder/'input.cir')],'Wrong engine invocation')
        require(row['environment']=={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC','HOME':str(root/'home'),'TMPDIR':str(root/'tmp'),'SPICE_SCRIPTS':str(engine.parent),'OMP_NUM_THREADS':'1'},'Unexpected native environment')
        log=(folder/'console.log').read_text();require(not re.search(r'error|unknown parameter|aborted',log,re.I),'Failed engine process counted')
        circuit=folder/'circuit.spice'
        if kind!='analytic':
            original=payload[recovered['cases'][case]['files'][kind+'_normalized']['member']].decode()
            lines=original.splitlines();indices=[i for i,v in enumerate(lines) if v.startswith('R')]
            if fault=='remove-one-unit':lines.pop(indices[-1])
            elif fault=='one-unit-width-3um':lines[indices[-1]]=lines[indices[-1]].replace('w=2','w=3')
            expected_circuit='\n'.join(lines)+'\n' if fault in ('remove-one-unit','one-unit-width-3um') else original
            require(circuit.read_text()==expected_circuit,'Actual native input/fault changed')
        else:require(circuit.read_text()=='* analytical lumped reference; no physical extraction claimed\n','Analytic path changed')
        model_lines=json.loads(payload[ELECTRICAL+'selected-model-lines.json'])['tt']
        expected_deck=[f'* LI-array-dynamic-v1 {record["nonce"]} {name}',model_lines,'.option reltol=1e-8 abstol=1e-16 vntol=1e-13 method=gear','.temp 27','VDRIVE input 0 PWL(0 0 1n .001 100n .001) AC 1']
        if kind=='analytic':expected_deck.append(f'RTEST input output {resistance(count):.17g}')
        else:expected_deck.extend([f'.include {circuit.as_posix()}','XTEST input output coupon'])
        expected_deck.extend(['RLOAD output 0 10','CLOAD output 0 '+('2n' if fault=='load-capacitance-2nF' else '1n')])
        expected_deck.extend(['.save v(input) v(output) i(vdrive)','.tran 50p 100n 0 50p'] if analysis=='tran' else ['.noise V(output) VDRIVE dec 20 1k 1g'])
        require((folder/'input.cir').read_text()=='\n'.join(expected_deck+['.end'])+'\n','Executed deck changed')
        raw_text=(root/row['raw']).read_text()
        require(raw_text.splitlines()[0].lower()==('Title: '+expected_deck[0]).lower(),'Raw output belongs to another execution/route')
        require('Command: ngspice-47,' in raw_text,'Wrong raw engine header')
        result=observe(root/row['raw'],analysis,count)
        require(result==row['observation'] and result['passed']==(fault is None),'Unexpected positive/fault result')
        outcomes.append({'name':name,**result})
    return {'status':'PASS','qualified':False,'installed_acceptance':False,'fresh_physical_acceptance':False,'results':outcomes}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);a=p.parse_args();print(json.dumps(audit(a.root),indent=2))
