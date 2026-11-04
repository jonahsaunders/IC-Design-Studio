"""Produce bounded native runs from the saved pw2dn GUI specimen.

This producer does not judge numerical correctness or device qualification.
An external reader must compare all raw outputs with independent references.
"""
import hashlib,importlib.metadata,json,math,os,platform,re,shutil,sys,time,traceback
from pathlib import Path
from .model import clone,device,file_digest,load_project,save_project
from .catalog import parameter_values
from .acceptance_runtime import native_environment,runtime
from .build_identity import identity
from . import engines

MODEL='sky130_fd_pr__model__parasitic__rf_diode_pw2dn'
KEY='sky130_fd_pr/diode__'+MODEL+'.sym'
POINTS=((2,2,4,8),(4,2,8,12),(10,10,100,40))
CONDITIONS=tuple((c,t) for c in ('nominal','ss','ff') for t in (-40,27,125))
FAULTS=('polarity','area','perimeter')
def require(value,message):
    if not value:raise ValueError(message)
def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def python_identity():
    import PySide6,PySide6.QtCore,shiboken6,shiboken6.Shiboken
    packages={}
    for name in ('PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','numpy','scipy','klayout','cryptography'):
        try:
            dist=importlib.metadata.distribution(name)
            records=[p for p in dist.files or () if str(p).endswith('.dist-info/RECORD')]
            packages[name]={'metadata_available':True,'version':dist.version,'records':{str(p):(file_digest(dist.locate_file(p)) if Path(dist.locate_file(p)).is_file() else None) for p in records}}
        except importlib.metadata.PackageNotFoundError:packages[name]={'metadata_available':False}
    return {'executable':sys.executable,'resolved_executable':str(Path(sys.executable).resolve()),'executable_sha256':file_digest(sys.executable),
            'version':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'platform':platform.platform(),
            'pyside_version':PySide6.__version__,'qt_version':PySide6.QtCore.qVersion(),
            'qtcore_sha256':file_digest(PySide6.QtCore.__file__),'shiboken_sha256':file_digest(shiboken6.Shiboken.__file__),
            'packages':packages,'distribution_scope':'RECORD hashes identify package metadata only; loaded file-backed modules are separately hashed. Virtual PYZ modules are outside the file list.'}

def module_files():
    return {str(Path(m.__file__).resolve()):file_digest(m.__file__) for m in list(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).is_file()}

def calls(text,fault=None):
    rows=[line.split() for line in text.splitlines() if len(line.split())>=4 and line.split()[0].lower().startswith('x') and line.split()[3]==MODEL]
    require(len(rows)==3 and {r[0].lower() for r in rows}=={'x_d0','x_d1','x_d2'},'Unexpected emitted pw2dn calls.')
    for i,(_,_,area,perim) in enumerate(POINTS):
        row=next(r for r in rows if r[0].lower()=='x_d'+str(i))
        pins=['0','d'+str(i)] if fault=='polarity' else ['d'+str(i),'0']
        params={'area':f'{area*.5:g}' if fault=='area' else str(area),
                'perim':f'{perim*1.5:g}' if fault=='perimeter' else str(perim)}
        require(row[1:3]==pins and len(row)==6 and dict(x.split('=',1) for x in row[4:])==params,'Unexpected pw2dn call or fault.')

def produce(selected_project_path,out,engine,execution_id,pilot=False):
    selected_project_path=Path(selected_project_path).resolve();out=Path(out).resolve();engine=Path(engine).resolve()
    require(not out.exists() and re.fullmatch('[0-9a-f]{32}',execution_id),'New output and execution nonce required.')
    frozen=bool(getattr(sys,'frozen',False));resources=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1])).resolve()
    if frozen:
        require(not pilot and engine.parent==resources/'icstudio/assets/runtime/ngspice','Frozen run requires full conditions and its shipped engine.')
    out.mkdir(parents=True);started=time.monotonic();saved=load_project(selected_project_path)
    selected_sha=file_digest(selected_project_path);engine_sha=file_digest(engine)
    require(len(saved['cells'])==1 and len(saved['cells'][0]['devices'])==1,'Expected exactly one saved GUI specimen.')
    dut=saved['cells'][0]['devices'][0];tech=saved['pdk'];binding=tech['simulation']['catalog'][KEY]
    require(dut['model_ref']=={'pdk':'sky130A','revision':'47dbd4fe43bfa7e4','device':KEY} and dut['nets']=={'d0':'A','d1':'K'},'Saved GUI specimen differs.')
    require(parameter_values(binding,dut)==dict(w=4,l=2,area=8,perim=12),'Saved GUI geometry differs.')
    envroot=out/'native-environment';envroot.mkdir()
    env=native_environment(dict(mode='installed' if frozen else 'source-pilot',resource_root=str(resources)),engine,envroot)
    runtime_before=runtime(dict(mode='installed' if frozen else 'source-pilot',resource_root=str(resources)),engine,env)
    selected=CONDITIONS[:1] if pilot else CONDITIONS
    report={'schema':'pw2dn-native-producer-v1','status':'RUNNING','execution_id':execution_id,'frozen':frozen,'build':identity(),'resource_root':str(resources),
        'selected_project':str(selected_project_path),'selected_project_sha256':selected_sha,'engine':str(engine),'engine_sha256':engine_sha,
        'conditions':selected,'geometries':POINTS,'faults':FAULTS,'native_environment':env,'runtime_before':runtime_before,
        'python_before':python_identity(),'python_modules_before':module_files(),
        'scope':'Actual application production only; independent external raw/reference audit required.',
        'qualified':False,'installed_acceptance':False,'cases':[]}
    write(out/'prelaunch.json',report);oldenv=dict(os.environ);original_execute=engines.execute;invocations=[]
    def captured(command,cwd,*args,**kwargs):
        cwd=Path(cwd).resolve();t=time.monotonic();record={'schema':1,'command':list(map(str,command)),'cwd':str(cwd),'environment':kwargs.get('env') or dict(os.environ),'timeout':kwargs.get('timeout',180),'status':'RUNNING'}
        try:
            log=original_execute(command,cwd,*args,**kwargs)
            (cwd/'engine.log').write_bytes(log.encode('utf-8'))
            require(not re.search(r'(?im)^\s*(?:error\b|fatal\b|doAnalyses\s*:|run\s+simulation(?:\(s\)|s)?\s+aborted\b)',log),'Native console reports failure.')
            if '-r' in record['command']:
                raw=Path(record['command'][record['command'].index('-r')+1]);deck=Path(record['command'][-1])
                require(raw.is_file() and deck.is_file(),'Missing native output.')
                text=deck.read_text(encoding='utf-8');analysis='ac' if re.search(r'(?im)^\.ac\b',text) else 'dc' if re.search(r'(?im)^\.dc\b',text) else 'op'
                if analysis!='op':
                    variables,rows,_=engines.parse_raw(raw)
                    require(re.findall(r'(?im)^Circuit:\s*(.*?)\s*$',log)==[text.splitlines()[0].casefold()],'Native console title differs.')
                    require(re.findall(r'ASCII raw file "([^"]+)"',log)==[str(raw)],'Native console raw path differs.')
                    require(re.findall(r'No\. of Data Columns\s*:\s*(\d+)',log)==[str(len(variables))] and re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log)==[str(len(rows))],'Native console dimensions differ.')
                    for marker in ('Total analysis time','Total elapsed time'):
                        values=re.findall(re.escape(marker)+r'\s*\(seconds\)\s*=\s*([\d.eE+-]+)',log)
                        require(len(values)==1 and math.isfinite(float(values[0])) and float(values[0])>=0,'Native console completion timing differs.')
                record.update(analysis=analysis,raw_sha256=file_digest(raw),deck_sha256=file_digest(deck))
            record.update(status='PASS',returncode=0,console_sha256=file_digest(cwd/'engine.log'))
            return log
        except BaseException as exc:record.update(status='FAIL',error=repr(exc));raise
        finally:
            record['seconds']=time.monotonic()-t;write(cwd/'native-invocation.json',record);invocations.append(record)
    def fixture():
        p=clone(saved);p['name']='Saved GUI pw2dn native verification';cell=p['cells'][0]
        vg=device('V','VG',x=100,y=900,value='0',nets={'p':'drive','n':'0'});vg['source']['ac']='1';vg['net_labels']=dict(vg['nets'])
        cell['devices']=[vg];cell['labels']=[];cell['wires']=[];cell['junctions']=[]
        for i,(w,l,area,perim) in enumerate(POINTS):
            d=clone(dut);d['id']='pw2dn-specimen-'+str(i);d['name']='D'+str(i);d.update(x=400+i*400,y=300)
            d['model_params'].update(w=w,l=l);d['nets']={'d0':'d'+str(i),'d1':'0'};d['net_labels']=dict(d['nets'])
            require(parameter_values(binding,d)==dict(w=w,l=l,area=area,perim=perim),'Fixture geometry differs.')
            v=device('V','VD'+str(i),x=400+i*400,y=600,value='0',nets={'p':'d'+str(i),'n':'drive'});v['source']['ac']='0';v['net_labels']=dict(v['nets'])
            cell['devices'] += [v,d]
        return p
    try:
        os.environ.clear();os.environ.update(env);engines.execute=captured
        for corner,temperature in selected:
            folder=out/(corner+'-'+str(temperature));folder.mkdir();row={'corner':corner,'temperature_c':temperature,'analyses':[],'faults':[]}
            settings=dict(corner=corner,temperature=temperature,source='VG',dc_start='0',dc_stop='.6',dc_step='.025',start='1k',end='1g',points=5)
            for analysis in ('dc','ac'):
                dest=folder/analysis/'application';dest.mkdir(parents=True);project=fixture();save_project(project,dest/'input.icproj');project=load_project(dest/'input.icproj')
                result=engines.run_ngspice(project,project['top'],dict(settings,type=analysis),str(engine),dest)
                write(dest/'result.json',result);calls((dest/'input.cir').read_text());row['analyses'].append(analysis)
            positive=folder/'dc/application'
            for fault in FAULTS:
                dest=folder/fault;dest.mkdir()
                for item in positive.iterdir():
                    if item.is_dir() and not item.name.startswith('rf-runtime-'):shutil.copytree(item,dest/item.name)
                    elif item.is_file() and item.name.startswith('pdk-'):shutil.copyfile(item,dest/item.name)
                changed=[]
                for line in (positive/'input.cir').read_text().splitlines():
                    words=line.split()
                    if len(words)>=4 and words[0].lower().startswith('x') and words[3]==MODEL:
                        i=int(words[0][-1]);area,perim=POINTS[i][2:]
                        if fault=='polarity':words[1],words[2]=words[2],words[1]
                        if fault=='area':words[4]=f'area={area*.5:g}'
                        if fault=='perimeter':words[5]=f'perim={perim*1.5:g}'
                        line=' '.join(words)
                    changed.append(line)
                text='\n'.join(changed)+'\n';calls(text,fault);deck=dest/'fault.cir';deck.write_text(text,encoding='utf-8')
                result=engines.run_deck(project,project['top'],dict(deck=str(deck),analysis=dict(settings,type='dc')),str(engine),dest)
                write(dest/'result.json',result);row['faults'].append(fault)
            report['cases'].append(row);write(out/'report.json',report)
        report['runtime_after']=runtime(dict(mode='installed' if frozen else 'source-pilot',resource_root=str(resources)),engine,env)
        require(report['runtime_after']==runtime_before and file_digest(engine)==engine_sha and file_digest(selected_project_path)==selected_sha,'Runtime or saved specimen changed.')
        report['python_after']=python_identity()
        require(report['python_after']==report['python_before'],'Python environment changed.')
        require(all(Path(path).is_file() and file_digest(path)==sha for path,sha in report['python_modules_before'].items()),'Loaded Python module changed.')
        report['python_modules_after']=module_files()
        guards=[]
        for path in sorted(out.rglob('rf-acceptance.json')):
            proof=json.loads(path.read_bytes())
            require(proof['status']=='PASS' and proof['circuit_rewritten'] is False,'RF guard did not pass unchanged.')
            guards.append({'path':path.relative_to(out).as_posix(),'sha256':file_digest(path)})
        require(len(guards)==5*len(selected),'Unexpected runtime guard count.')
        report.update(status='PASS_NATIVE_PRODUCTION_ONLY',application_runs=5*len(selected),invocations=invocations,automatic_runtime_guards=guards)
    except BaseException as exc:report.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc());raise
    finally:
        engines.execute=original_execute;os.environ.clear();os.environ.update(oldenv)
        report['seconds']=time.monotonic()-started;write(out/'report.json',report)
    return report
