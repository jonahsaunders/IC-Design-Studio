"""Same-run desktop handoff; transfers build bytes, never installed acceptance."""
import argparse,ast,hashlib,importlib.util,json,os,platform,re,shutil,stat,subprocess,sys,tarfile,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
MANIFEST='manifest.json';ARCHIVE='payload.tar';READY='build/desktop-handoff-restored.json'
SOURCE='build/desktop-handoff-source/source.zip'
def require(ok,message):
 if not ok:raise ValueError(message)
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pairs(items):
 value={}
 for k,v in items:
  require(k not in value,'Duplicate JSON field');value[k]=v
 return value
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs)
def safe(name):
 require(isinstance(name,str) and name and '\\' not in name and ':' not in name and '\0' not in name,'Invalid relative path')
 p=PurePosixPath(name)
 require(not p.is_absolute() and p.as_posix()==name and all(x not in ('','.','..') for x in name.split('/')),'Unsafe path')
 require(all(not x.endswith((' ','.')) and not re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',x) for x in p.parts),'Unsafe Windows path')
 return p
def unlinked(path,root):
 path=Path(path).absolute();root=Path(root).absolute()
 require(path.is_relative_to(root),'Path escaped workspace')
 current=root
 require(not current.is_symlink(),'Linked workspace')
 for bit in path.relative_to(root).parts:
  current=current/bit
  require(not current.is_symlink() and not (current.exists() and getattr(current.lstat(),'st_file_attributes',0)&0x400),'Linked destination')
 return path
def git(root,*args):
 env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
 return subprocess.check_output(['git',*args],cwd=root,env=env).decode().strip()
def identity(root):
 root=Path(root).resolve();candidate=os.environ.get('GITHUB_SHA','');run=os.environ.get('GITHUB_RUN_ID','');attempt=os.environ.get('GITHUB_RUN_ATTEMPT','');host=os.environ.get('RUNNER_OS','')
 require(re.fullmatch('[0-9a-f]{40}',candidate) and re.fullmatch('[1-9][0-9]*',run) and re.fullmatch('[1-9][0-9]*',attempt),'Full hosted candidate/run/attempt required')
 require(host in ('Windows','Linux') and host==('Windows' if os.name=='nt' else 'Linux'),'Host platform mismatch')
 require(git(root,'rev-parse','HEAD')==candidate,'Checkout does not match candidate')
 return dict(candidate=candidate,run_id=run,attempt=attempt,os=host,machine=platform.machine(),workspace=root.as_posix())
def image():return {k:os.environ.get(k,'') for k in ('ImageOS','ImageVersion')}
def source_zip(path):
 """Read every source member and reject ambiguous/unsafe archive structure."""
 entries={};seen=set()
 with zipfile.ZipFile(path) as z:
  for item in z.infolist():
   name=safe(item.filename);require(name.parts[0]=='IC-Design-Studio' and len(name.parts)>1,'Unexpected source ZIP prefix')
   require(item.filename.casefold() not in seen and not item.is_dir(),'Duplicate/empty source ZIP member');seen.add(item.filename.casefold())
   mode=item.external_attr>>16
   require(stat.S_IFMT(mode) in (0,stat.S_IFREG) and not mode&0o7000,'Linked or special source ZIP member')
   with z.open(item) as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
   entries[item.filename]={'sha256':digest,'bytes':item.file_size}
 require('IC-Design-Studio/main.py' in entries and 'IC-Design-Studio/LICENSE' in entries,'Incomplete source archive')
 return {'sha256':sha(path),'bytes':Path(path).stat().st_size,'files':entries}
def candidate_source(root,path,candidate):
 """Authenticate included tracked source directly to Git, with one build-info exception."""
 source_dirs={'icstudio','tests','native','scripts','docs','examples','packaging','plugins','licenses','.github'}
 excluded_dirs={'build','dist','release','__pycache__','.git','.venv','private-live-data','live-sessions'}
 excluded_suffixes={'.pyc','.spec','.so','.dll','.dylib','.pyd','.o','.obj','.lib','.exp','.exe','.sqlite3','.sqlite3-wal','.sqlite3-shm'}
 env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
 raw=subprocess.check_output(['git','ls-tree','-rz','--full-tree',candidate],cwd=root,env=env)
 checked={}
 with zipfile.ZipFile(path) as z:
  names=set(z.namelist())
  for row in raw.split(b'\0'):
   if not row:continue
   meta,name=row.split(b'\t',1);mode,kind,blob=meta.decode().split();name=name.decode();rel=PurePosixPath(name)
   if kind!='blob' or rel.name=='creation-key.txt' or rel.parts[:4]==('icstudio','assets','runtime','ngspice'):continue
   outside=(len(rel.parts)>1 and rel.parts[0] not in source_dirs) or (len(rel.parts)==1 and (rel.name.startswith(('tmp','pip-')) or rel.name=='core' or rel.suffix.lower() in ('.s','.log')))
   if outside or any(p in excluded_dirs for p in rel.parts) or rel.suffix.lower() in excluded_suffixes:continue
   member='IC-Design-Studio/'+name;require(member in names,'Missing candidate source: '+name)
   data=z.read(member)
   if name=='icstudio/build_info.py':
    tree=ast.parse(data);values={}
    for node in tree.body:
     require(isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name),'Unexpected generated build metadata')
     key=node.targets[0].id;require(key not in values,'Duplicate generated build metadata');values[key]=ast.literal_eval(node.value)
    require(values.get('BUILD_COMMIT')==candidate and values.get('BUILD_DIRTY') is False and set(values)=={'ENGINE_SOURCE_HASH','WORKFLOW_SOURCE_HASH','BUILD_COMMIT','BUILD_BRANCH','BUILD_DIRTY'},'Generated build metadata does not describe candidate')
    engine=z.read('IC-Design-Studio/icstudio/simulation.py')
    modules=sorted(n for n in names if n.startswith('IC-Design-Studio/icstudio/') and len(PurePosixPath(n).parts)==3 and n.endswith('.py') and not n.endswith('/build_info.py'))
    workflow=b''.join(PurePosixPath(n).name.encode()+z.read(n) for n in modules)
    require(values['ENGINE_SOURCE_HASH']==hashlib.sha256(engine).hexdigest() and values['WORKFLOW_SOURCE_HASH']==hashlib.sha256(workflow).hexdigest(),'Generated build source hashes differ')
    require(isinstance(values['BUILD_BRANCH'],str) and values['BUILD_BRANCH'],'Missing generated build branch')
   else:
    require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==blob,'Release source differs from candidate: '+name)
   checked[name]=hashlib.sha256(data).hexdigest()
 require('main.py' in checked and 'LICENSE' in checked,'Candidate source inventory is incomplete')
 return checked
def roots(root,host):
 needed=['dist/ICDesignStudio','build/physical-adapter/sky130A']
 if host=='Windows':needed.append('dist/installers')
 for rel in needed:
  require((root/rel).is_dir(),'Missing handoff input: '+rel);unlinked(root/rel,root)
 selected=set(needed)
 # Exactly the producer evidence directories that release packaging already includes.
 for p in (root/'build').glob('*evidence'):
  if p.is_dir():selected.add(p.relative_to(root).as_posix())
 # Preserve original diagnostics matches without importing whole caches or state.
 text=(root/'.github/workflows/build-desktop.yml').read_text(encoding='utf-8')
 found=re.search(r'name: desktop-(?:source-)?diagnostics-\$\{\{ runner.os \}\}\s*\n\s*path: \|\n((?:[ ]{12}.*\n)+)',text)
 require(found is not None,'Missing diagnostic path specification')
 for line in found[1].splitlines():
  pattern=line.strip();require(pattern.startswith('build/') and '..' not in pattern and '\\' not in pattern,'Unsafe diagnostic pattern')
  if pattern.startswith('build/digital-state/'):continue
  for p in root.glob(pattern):
   if p.is_file() or p.is_dir():selected.add(p.relative_to(root).as_posix())
 # Never replay ready state; retain only explicitly selected check reports above.
 require('build/digital-state' not in selected,'Ready state cannot be handed off')
 return sorted(selected)
def validate_build_inputs(root,host):
 exe=root/'dist/ICDesignStudio'/('ICDesignStudio.exe' if host=='Windows' else 'ICDesignStudio')
 require(exe.is_file() and exe.stat().st_size>0,'Missing frozen executable')
 lock=load(root/'examples/sky130-qualification-lock.json');pdk=root/'build/physical-adapter/sky130A'
 require(sha(unlinked(pdk/'package.json',root))==lock['manifest_sha256'],'Physical adapter manifest changed')
 package=load(pdk/'package.json')
 require(package['id']==lock['id'] and package['revision']==lock['revision'],'Physical adapter identity changed')
 for name,digest in package['files'].items():
  safe(name);require(sha(unlinked(pdk/name,pdk))==digest,'Physical adapter asset changed: '+name)
 payload=root/'dist/ICDesignStudio/_internal/icstudio/assets/runtime/digital';manifest=load(payload/'manifest.json')
 archive=safe(manifest['archive']);require(len(archive.parts)==1 and sha(payload/str(archive))==manifest['sha256'],'Packaged digital payload changed')
 if host=='Windows':
  installers=root/'dist/installers'
  setups=list(installers.glob('IC-Design-Studio-*-Windows-x64-Setup.exe'))
  require(len(setups)==1 and setups[0].stat().st_size>0,'Expected one exact installer')
  portable=installers/setups[0].name.replace('Windows-x64-Setup.exe','Windows-x64-Portable.zip')
  require(portable.is_file() and portable.stat().st_size>0,'Matching portable archive missing')
def collect(root,selected):
 out={}
 def visit(rel):
  safe(rel);p=root/rel;s=p.lstat();mode=stat.S_IMODE(s.st_mode)
  require(not mode&0o7000,'Special permission bits are not transferable')
  require(not getattr(s,'st_file_attributes',0)&0x400 or p.is_symlink(),'Junction/reparse point not transferable')
  if p.is_symlink():
   target=os.readlink(p);require(not Path(target).is_absolute() and '\\' not in target,'Unsafe link target')
   resolved=p.resolve(strict=True);require(resolved.is_relative_to(root),'Link escapes workspace')
   out[rel]={'type':'symlink','target':target,'resolved':resolved.relative_to(root).as_posix(),'mode':0o777}
  elif stat.S_ISDIR(s.st_mode):
   out[rel]={'type':'directory','mode':mode}
   for child in sorted(p.iterdir()):visit(child.relative_to(root).as_posix())
  else:
   require(stat.S_ISREG(s.st_mode),'Special file is not transferable')
   out[rel]={'type':'file','mode':mode,'bytes':s.st_size,'sha256':sha(p)}
 for rel in selected:visit(rel)
 for rel,row in list(out.items()):
  if row['type']=='symlink':require(row['resolved'] in out and out[row['resolved']]['type'] in ('file','directory'),'Link target absent from handoff')
 require(len({x.casefold() for x in out})==len(out),'Case-colliding payload names')
 return dict(sorted(out.items()))
def write_source(root,destination):
 spec=importlib.util.spec_from_file_location('handoff_source_archive',root/'scripts/release_archives.py')
 module=importlib.util.module_from_spec(spec);sys.path.insert(0,str(root));spec.loader.exec_module(module)
 created=module.source_archive(destination.parent)
 require(created.resolve()!=destination.resolve(),'Unexpected source generator name')
 created.replace(destination)
def pack(root,output,*,identity_fn=identity,source_writer=write_source):
 root=Path(root).resolve();output=unlinked(Path(output).absolute(),root)
 require(not output.exists(),'Choose a new handoff output');before=identity_fn(root)
 selected=roots(root,before['os']);validate_build_inputs(root,before['os']);source_path=unlinked(root/SOURCE,root)
 require(not source_path.parent.exists(),'Source handoff directory already exists')
 source_path.parent.mkdir(parents=True);source_writer(root,source_path);src=source_zip(source_path)
 src['candidate_files']=candidate_source(root,source_path,before['candidate'])
 selected.append(source_path.parent.relative_to(root).as_posix())
 files=collect(root,selected);require(SOURCE in files,'Missing source archive payload')
 output.mkdir(parents=True)
 with tarfile.open(output/ARCHIVE,'w',format=tarfile.PAX_FORMAT) as tar:
  for rel,row in files.items():
   p=root/rel;info=tarfile.TarInfo(rel);info.mode=row['mode'];info.uid=info.gid=0;info.mtime=0
   if row['type']=='directory':info.type=tarfile.DIRTYPE;tar.addfile(info)
   elif row['type']=='symlink':info.type=tarfile.SYMTYPE;info.linkname=row['target'];tar.addfile(info)
   else:
    info.size=row['bytes']
    with p.open('rb') as f:tar.addfile(info,f)
 require(collect(root,selected)==files and identity_fn(root)==before,'Producer changed during transfer capture')
 record=dict(schema=1,identity=before,producer_image=image(),archive=dict(name=ARCHIVE,sha256=sha(output/ARCHIVE),bytes=(output/ARCHIVE).stat().st_size),files=files,source=src)
 (output/MANIFEST).write_text(json.dumps(record,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 return record
def allowed(name):
 return name.startswith(('dist/ICDesignStudio/','dist/installers/','build/')) or name in ('dist/ICDesignStudio','dist/installers')
def validate_payload(folder,record):
 require(set(record)=={'schema','identity','producer_image','archive','files','source'} and record['schema']==1,'Unknown handoff schema')
 arc=record['archive'];require(set(arc)=={'name','sha256','bytes'} and arc['name']==ARCHIVE,'Unknown archive')
 p=unlinked(folder/ARCHIVE,folder);require(p.is_file() and sha(p)==arc['sha256'] and p.stat().st_size==arc['bytes'],'Payload checksum mismatch')
 files=record['files'];require(isinstance(files,dict) and files,'Empty payload')
 for name,row in files.items():
  safe(name);require(allowed(name),'Unexpected payload root')
  require(name!='build/digital-state' and not name.startswith('build/digital-state/'),'Active runtime state cannot be restored')
  require(row['type'] in ('file','directory','symlink') and type(row['mode']) is int and 0<=row['mode']<=0o777,'Invalid payload type/mode')
  fields={'type','mode'}|({'bytes','sha256'} if row['type']=='file' else {'target','resolved'} if row['type']=='symlink' else set())
  require(set(row)==fields,'Unexpected inventory fields')
 require(len({x.casefold() for x in files})==len(files),'Case-colliding payload names')
 with tarfile.open(p,'r:') as tar:
  members=tar.getmembers();require(len(members)==len(files) and {x.name for x in members}==set(files),'Duplicate/extra/omitted tar members')
  for item in members:
   safe(item.name);row=files[item.name];require(item.mode==row['mode'] and not item.mode&0o7000 and not item.islnk(),'Mode/hardlink mismatch')
   if row['type']=='file':
    require(item.isfile() and item.size==row['bytes'] and type(row['bytes']) is int and row['bytes']>=0,'File size/type mismatch')
    with tar.extractfile(item) as f:require(hashlib.file_digest(f,'sha256').hexdigest()==row['sha256'],'File content mismatch')
   elif row['type']=='directory':require(item.isdir(),'Directory type mismatch')
   else:
    require(item.issym() and item.linkname==row['target'],'Link target mismatch')
    target=PurePosixPath(item.name).parent/PurePosixPath(item.linkname)
    require(not PurePosixPath(item.linkname).is_absolute() and '\\' not in item.linkname,'Unsafe link')
    parts=[]
    for part in target.parts:
     if part=='..':require(bool(parts),'Link escaped root');parts.pop()
     elif part!='.':parts.append(part)
    resolved='/'.join(parts);require(resolved==row['resolved'] and resolved in files and files[resolved]['type'] in ('file','directory'),'Missing/recursive link target')
   for parent in PurePosixPath(item.name).parents:
    if str(parent) in files:require(files[str(parent)]['type']=='directory','Payload path traverses link/file')
 require(SOURCE in files and files[SOURCE]['type']=='file' and files[SOURCE]['sha256']==record['source']['sha256'],'Source archive binding missing')
 return files
def restore(root,folder,*,identity_fn=identity):
 root=Path(root).resolve();folder=unlinked(Path(folder).absolute(),root);record=load(unlinked(folder/MANIFEST,root));before=identity_fn(root)
 require(record.get('identity')==before,'Candidate/run/attempt/host/workspace mismatch')
 files=validate_payload(folder,record)
 ready=unlinked(root/READY,root);require(not ready.exists(),'Readiness receipt already exists')
 require(not (root/'build/digital-state').exists(),'Fresh runtime state is required')
 for rel in files:
  p=unlinked(root/rel,root);require(not p.exists(),'Refusing to overwrite handoff destination: '+rel)
 # All content/path validation completes before extraction. Parents are created
 # as plain directories; links are created last and can never redirect writes.
 with tarfile.open(folder/ARCHIVE,'r:') as tar:
  for item in tar.getmembers():
   row=files[item.name];p=root/item.name
   p.parent.mkdir(parents=True,exist_ok=True)
   if row['type']=='directory':p.mkdir(exist_ok=True)
   elif row['type']=='file':
    with tar.extractfile(item) as src,p.open('xb') as dst:shutil.copyfileobj(src,dst)
    p.chmod(row['mode'])
  for rel,row in files.items():
   if row['type']=='symlink':os.symlink(row['target'],root/rel,target_is_directory=files[row['resolved']]['type']=='directory')
  for rel,row in reversed(list(files.items())):
   if row['type']=='directory':(root/rel).chmod(row['mode'])
 actual=collect(root,[x for x in files if not any(str(q) in files for q in PurePosixPath(x).parents)])
 require(actual==files,'Restored bytes/type/modes differ')
 restored_source=source_zip(root/SOURCE);restored_source['candidate_files']=candidate_source(root,root/SOURCE,before['candidate'])
 require(restored_source==record['source'],'Restored source archive differs')
 validate_build_inputs(root,before['os'])
 require(identity_fn(root)==before,'Candidate changed while restoring')
 result=dict(schema=1,status='PASS',scope='Verified package bytes only; fresh installed acceptance is mandatory.',identity=before,producer_image=record['producer_image'],consumer_image=image(),manifest_sha256=sha(folder/MANIFEST),archive_sha256=sha(folder/ARCHIVE),source=record['source'],source_path=SOURCE)
 ready.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 return result
def verified_source(root,path,*,identity_fn=identity):
 root=Path(root).resolve();path=unlinked(Path(path).absolute(),root);receipt=load(unlinked(root/READY,root))
 require(path==root/SOURCE and receipt.get('schema')==1 and receipt.get('status')=='PASS' and receipt.get('identity')==identity_fn(root),'Source archive has no matching restored candidate')
 manifest=unlinked(root/'build/desktop-handoff'/MANIFEST,root);record=load(manifest)
 require(sha(manifest)==receipt['manifest_sha256'] and record['identity']==receipt['identity'] and record['source']==receipt['source'],'Restored source receipt changed')
 current=source_zip(path);current['candidate_files']=candidate_source(root,path,receipt['identity']['candidate'])
 require(current==receipt['source'],'Source archive changed after restoration')
 return path
def main():
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
 sub.add_parser('pack').add_argument('--output',type=Path,required=True)
 sub.add_parser('restore').add_argument('--input',type=Path,required=True)
 a=parser.parse_args()
 result=pack(ROOT,a.output.resolve()) if a.command=='pack' else restore(ROOT,a.input.resolve())
 print(json.dumps({'status':'PASS','command':a.command,'candidate':result['identity']['candidate']},indent=2))
if __name__=='__main__':main()

