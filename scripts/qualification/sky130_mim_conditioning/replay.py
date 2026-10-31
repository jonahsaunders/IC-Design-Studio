"""Finite SKY130 MiM qualification replay; no general simulator integration."""
from pathlib import Path
import hashlib,json,os,re,stat,subprocess,shutil,time,datetime,argparse,math
TOKEN=b'@FIXTURE_ASSETS@'
MODEL_HASHES={'dfa418b7569a255978e276cf.spice':('5cb086313d55341351305d30500ca39571d689b692d2be525c4b3b8b4db86e6f',3),'ef0706a98c27cc1375524b13.spice':('a2e9ed5568b23debce5ac002f15df8c675010bac34d05b0c4e8a8dcca916260f',4)}
def fail(message):raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def pairs(items):
 out={}
 for k,v in items:
  if k in out:fail('duplicate JSON key')
  out[k]=v
 return out
def finite_float(text):
 value=float(text)
 if not math.isfinite(value):fail('nonfinite JSON number')
 return value
def strict_json(data):
 try:return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda _:fail('non-finite JSON'),parse_float=lambda v:finite_float(v))
 except (ValueError,UnicodeDecodeError) as e:raise ValueError('invalid strict JSON') from e
def unlinked(path):
 p=Path(path).absolute()
 for c in (p,*p.parents):
  try:st=c.lstat()
  except FileNotFoundError:continue
  if stat.S_ISLNK(st.st_mode) or getattr(st,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):fail('linked path component')
 return p
def child(root,name):
 if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/') or any(x in ('','.','..') for x in name.split('/')):fail('unsafe fixture path')
 p=unlinked(root/name)
 if not p.is_relative_to(root):fail('path outside fixture')
 return p
def inventory(root,folder):
 result={}
 for p in folder.rglob('*'):
  unlinked(p)
  if p.is_file():result[p.relative_to(root).as_posix()]=sha(p.read_bytes())
 return result
def load_fixture(fixture,pinned):
 root=unlinked(fixture);p=unlinked(root/'manifest.json');raw=p.read_bytes()
 if sha(raw)!=pinned:fail('fixture manifest identity differs')
 m=strict_json(raw)
 if set(m)!={'schema','kind','sources','decks'} or m['schema']!=1 or m['kind']!='sky130-mim-fixed-v1-ac-40':fail('fixture manifest format differs')
 expected={f'decks/p{p}-r{r}-{s}/{e}.cir' for p in (1,2) for r in (0,90) for s in ('tt','ll','hh','hl','lh') for e in ('e1','e2')}
 if set(m['decks'])!=expected:fail('fixture case inventory differs')
 for group,folder in (('sources','assets'),('decks','decks')):
  if not isinstance(m[group],dict) or inventory(root,root/folder)!=m[group]:fail('fixture '+group+' bytes differ')
  for name in m[group]:child(root,name)
 return root,m
def load_runtime(path,pinned,engine):
 raw=unlinked(path).read_bytes()
 if sha(raw)!=pinned:fail('runtime lock identity differs')
 m=strict_json(raw)
 if set(m)!={'schema','engine_sha256','spice_scripts','files'} or m['schema']!=1 or not isinstance(m['files'],dict):fail('runtime lock format differs')
 engine=unlinked(engine)
 if sha(engine.read_bytes())!=m['engine_sha256']:fail('engine identity differs')
 for path,digest in m['files'].items():
  if sha(Path(path).read_bytes())!=digest:fail('runtime resource identity differs')
 init=Path(m['spice_scripts'])/'spinit'
 if str(init) not in m['files']:fail('initializer not locked')
 if os.name!='nt':
  preload=Path('/etc/ld.so.preload')
  if preload.exists() and preload.read_text().strip():fail('system preload not permitted')
  env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'};scan=subprocess.run(['/usr/bin/ldd',str(engine)],env=env,capture_output=True,text=True,timeout=30)
  if scan.returncode or 'not found' in scan.stdout+scan.stderr:fail('unresolved engine library')
  libs=set(re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',scan.stdout,re.M))
  if not libs or not libs.issubset(m['files']):fail('unlocked engine library')
 return engine,m
def transform(data,name):
 if name not in MODEL_HASHES:fail('unreviewed model')
 digest,metal=MODEL_HASHES[name]
 if sha(data)!=digest:fail('model source identity differs')
 text=data.decode('utf8').replace('\r\n','\n')
 for n,(a,b) in enumerate((('a','b1'),('b1','c1')),1):
  tc='rm' if n==1 else 'rvia';spacing='        ';old=f"rs{n} {a}{spacing}{b} 'r{n}' tc1 = {{tc1{tc}{metal}}} tc2 = {{tc2{tc}{metal}}}"
  new=f'hs{n} {a} q{n} vs{n} {{r{n}}}\nvs{n} q{n} {b} 0'
  if text.count(old)!=1:fail('model resistor graph differs')
  text=text.replace(old,new)
 return text.encode('utf8')
def validate_deck(data,key):
 mt=re.fullmatch(r'decks/p([12])-r(0|90)-(tt|ll|hh|hl|lh)/(e1|e2)\.cir',key)
 if not mt:fail('case outside selection')
 p,r,s,profile=mt.groups();ports=('p1','n1','p2','n2');tags=('app','reference','native','cross','missing','width');params=('rm3','rm4','rcvia3','rcvia4','tol_m3','tol_m4','camimc','cpmimc','m3_dw','m4_dw','mc_mm_switch','mc_pr_switch');profiles={'e1':('1.25','0.25','-0.5','-0.5'),'e2':('0.25','0.25','0.5','-0.5')};rows=data.decode().splitlines()
 if not rows or not re.fullmatch(r'\* icstudio-mim-hierarchy-electrical-v1 [0-9a-f]{64}',rows[0]):fail('deck title differs')
 base=TOKEN.decode();expect=[rows[0],f'.lib {base}/shared-models/pdk-models/f9bebaecbce128520576fac5.spice {s}',f'.include {base}/shared-models/pdk-models/06afe200ec03af9e2f4f21dd.spice',f'.include {base}/shared-models/pdk-models/04874273a824f6e861ba7f94.spice','.param mc_mm_switch=0 mc_pr_switch=0','.option tnom=27','.temp 27'];saves=[]
 for tag in tags:
  path=f'applications/p{p}/application.spice' if tag=='app' else f'physical/p{p}/r{r}/schematic.spice' if tag=='reference' else f'physical/p{p}/r{r}/lvs-extraction/extracted.spice' if tag=='native' else f'networks/p{p}-r{r}/{tag}.spice'
  expect += [f'.subckt whole_{tag} P1 N1 P2 N2',f'.include "{base}/{path}"','Xwhole P1 N1 P2 N2 mim_pair',f'.ends whole_{tag}']
  for port,amplitude in zip(ports,profiles[profile]):expect.append(f'V_{tag}_{port} {tag}_{port} 0 DC 0 AC {amplitude}');saves.extend((f'v({tag}_{port})',f'i(v_{tag}_{port})'))
  expect.append('X_'+tag+' '+' '.join(tag+'_'+x for x in ports)+' whole_'+tag)
 for name in params:expect.append(f'VPAR_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}');saves.append(f'v(par_{name})')
 expect+=['.ac dec 1 1k 10G','.save '+' '.join(saves),'.end']
 if rows!=expect:fail('deck differs from fixed v1 contract')
 return {'plate':int(p),'rotation':int(r),'section':s,'profile':profile}
def materialize(source,relative,private):
 data=source.read_bytes();name=Path(relative).name
 if name in MODEL_HASHES:data=transform(data,name)
 if relative.endswith(('.spice','.cir')):data=data.replace(TOKEN,private.as_posix().encode())
 return data
def replay(fixture,fixture_sha,runtime,runtime_sha,engine,output,case):
 root,m=load_fixture(fixture,fixture_sha);engine,rt=load_runtime(runtime,runtime_sha,engine)
 if case not in m['decks']:fail('case outside locked fixture')
 deck=(root/case).read_bytes();details=validate_deck(deck,case);out=unlinked(output)
 if out==root or out.is_relative_to(root) or root.is_relative_to(out):fail('output overlaps fixture')
 if out.exists():fail('output must be fresh')
 out.mkdir(parents=True);private=out/'assets';private.mkdir()
 for name in m['sources']:
  rel=Path(name).relative_to('assets').as_posix();dest=child(private,rel);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(materialize(root/name,name,private))
 deck_out=deck.replace(TOKEN,private.as_posix().encode());(out/'input.cir').write_bytes(deck_out);before=inventory(out,private);deck_hash=sha(deck_out)
 home=out/'empty-home';tmp=out/'temporary';home.mkdir();tmp.mkdir();env={'LANG':'C','LC_ALL':'C','TZ':'UTC','HOME':str(home),'USERPROFILE':str(home),'TMP':str(tmp),'TEMP':str(tmp),'SPICE_SCRIPTS':rt['spice_scripts']}
 if os.name=='nt':
  system=os.environ.get('SystemRoot',r'C:\Windows');env.update(SystemRoot=system,WINDIR=system,PATH=str(engine.parent)+os.pathsep+str(Path(system)/'System32'))
 else:env['PATH']=str(engine.parent)+':/usr/bin:/bin'
 command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(out/'result.raw'),str(out/'input.cir')];start=datetime.datetime.now(datetime.timezone.utc).isoformat();clock=time.monotonic();proc=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=120);elapsed=time.monotonic()-clock;end=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'console.log').write_text(proc.stdout+proc.stderr,encoding='utf8',newline='\n')
 if proc.returncode:raise ValueError('native execution failed; evidence retained')
 if before!=inventory(out,private) or sha((out/'input.cir').read_bytes())!=deck_hash:fail('private input changed during run')
 load_fixture(root,fixture_sha);load_runtime(runtime,runtime_sha,engine)
 result={'schema':1,'scope':'finite v1 fixture AC replay; not noise/transient or original-model pass','case':case,'details':details,'fixture_sha256':fixture_sha,'runtime_lock_sha256':runtime_sha,'engine_sha256':rt['engine_sha256'],'replay_source_sha256':sha(Path(__file__).read_bytes()),'input_deck_sha256':deck_hash,'private_source_hashes':before,'command':command,'cwd':str(out),'environment':env,'start_utc':start,'end_utc':end,'elapsed_seconds':elapsed,'console_sha256':sha((out/'console.log').read_bytes()),'raw_sha256':sha((out/'result.raw').read_bytes()),'returncode':proc.returncode}
 (out/'receipt.json').write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n');return result
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('fixture','fixture-sha','runtime','runtime-sha','engine','output','case'):p.add_argument('--'+name,required=True)
 a=p.parse_args(argv);record=replay(a.fixture,a.fixture_sha,a.runtime,a.runtime_sha,a.engine,a.output,a.case);print(json.dumps({'case':record['case'],'raw_sha256':record['raw_sha256']}))
if __name__=='__main__':main()
