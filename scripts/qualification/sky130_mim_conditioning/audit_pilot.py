"""Independent readback of a single portable MiM qualification replay."""
from pathlib import Path
import argparse,hashlib,json,re,os,stat,datetime,subprocess,math
from readback import strict,require,sha,scientific,load_contract,validation_errors
TOKEN=b'@FIXTURE_ASSETS@'
MODELS={'dfa418b7569a255978e276cf.spice':('5cb086313d55341351305d30500ca39571d689b692d2be525c4b3b8b4db86e6f',3),'ef0706a98c27cc1375524b13.spice':('a2e9ed5568b23debce5ac002f15df8c675010bac34d05b0c4e8a8dcca916260f',4)}
def unlinked(path):
 p=Path(path).absolute()
 for component in (p,*p.parents):
  try:st=component.lstat()
  except FileNotFoundError:continue
  require(not stat.S_ISLNK(st.st_mode) and not (getattr(st,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)),'linked path component')
 return p

def check_console(text):
 require('Doing analysis at TEMP = 27.000000 and TNOM = 27.000000' in text and re.search(r'No\. of Data Columns\s*:\s*61\b',text) is not None and re.search(r'No\. of Data Rows\s*:\s*8\b',text) is not None and re.search(r'(?im)^\s*(?:error|fatal)\b',text) is None,'console analysis differs')
def check_timing(receipt):
 start=datetime.datetime.fromisoformat(receipt['start_utc']);end=datetime.datetime.fromisoformat(receipt['end_utc']);elapsed=receipt['elapsed_seconds'];require(type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>0 and start.utcoffset()==datetime.timedelta(0) and end.utcoffset()==datetime.timedelta(0) and start<=end and abs((end-start).total_seconds()-elapsed)<1.0,'execution timing differs')
def check_faults(profile,result):
 if profile=='e2':require(all(result['detections'].values()),'native fault not detected')
 return result
def inventory(root,folder):
 unlinked(root);unlinked(folder);out={}
 for p in folder.rglob('*'):
  unlinked(p);st=p.lstat();require(not stat.S_ISLNK(st.st_mode) and not (getattr(st,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)),'linked evidence');
  if p.is_file():out[p.relative_to(root).as_posix()]=sha(p.read_bytes())
 return out
def rewrite(data,name,private):
 if name in MODELS:
  digest,metal=MODELS[name];require(sha(data)==digest,'source model differs');text=data.decode('utf8').replace('\r\n','\n')
  for n,(a,b) in enumerate((('a','b1'),('b1','c1')),1):
   tc='rm' if n==1 else 'rvia';old=f"rs{n} {a}        {b} 'r{n}' tc1 = {{tc1{tc}{metal}}} tc2 = {{tc2{tc}{metal}}}";new=f'hs{n} {a} q{n} vs{n} {{r{n}}}\nvs{n} q{n} {b} 0';require(text.count(old)==1,'resistor source structure differs');text=text.replace(old,new)
  data=text.encode()
 return data.replace(TOKEN,private.as_posix().encode())
def deck_contract(data,plate,rotation,section,profile):
 lines=data.decode('utf8').splitlines();require(bool(lines) and re.fullmatch(r'\* icstudio-mim-hierarchy-electrical-v1 [0-9a-f]{64}',lines[0]) is not None,'deck title differs');base=TOKEN.decode();params=('rm3','rm4','rcvia3','rcvia4','tol_m3','tol_m4','camimc','cpmimc','m3_dw','m4_dw','mc_mm_switch','mc_pr_switch');ports=('p1','n1','p2','n2');profiles={'e1':('1.25','0.25','-0.5','-0.5'),'e2':('0.25','0.25','0.5','-0.5')}
 expected=[lines[0],f'.lib {base}/shared-models/pdk-models/f9bebaecbce128520576fac5.spice {section}',f'.include {base}/shared-models/pdk-models/06afe200ec03af9e2f4f21dd.spice',f'.include {base}/shared-models/pdk-models/04874273a824f6e861ba7f94.spice','.param mc_mm_switch=0 mc_pr_switch=0','.option tnom=27','.temp 27'];saves=[]
 for tag in ('app','reference','native','cross','missing','width'):
  network=f'applications/p{plate}/application.spice' if tag=='app' else f'physical/p{plate}/r{rotation}/schematic.spice' if tag=='reference' else f'physical/p{plate}/r{rotation}/lvs-extraction/extracted.spice' if tag=='native' else f'networks/p{plate}-r{rotation}/{tag}.spice'
  expected.extend((f'.subckt whole_{tag} P1 N1 P2 N2',f'.include "{base}/{network}"','Xwhole P1 N1 P2 N2 mim_pair',f'.ends whole_{tag}'))
  for port,volts in zip(ports,profiles[profile]):expected.append(f'V_{tag}_{port} {tag}_{port} 0 DC 0 AC {volts}');saves.extend((f'v({tag}_{port})',f'i(v_{tag}_{port})'))
  expected.append('X_'+tag+' '+' '.join(tag+'_'+p for p in ports)+' whole_'+tag)
 for name in params:expected.append(f'VPAR_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}');saves.append(f'v(par_{name})')
 expected+=['.ac dec 1 1k 10G','.save '+' '.join(saves),'.end'];require(lines==expected,'deck contract differs')
@validation_errors
def audit(fixture,fixture_sha,runtime,runtime_sha,engine,output,contract,contract_sha,replay_source,replay_sha):
 fixture=unlinked(fixture);out=unlinked(output);engine=unlinked(engine);unlinked(runtime);unlinked(contract);unlinked(replay_source);unlinked(out/'receipt.json');unlinked(fixture/'manifest.json');manifest=(fixture/'manifest.json').read_bytes();require(sha(manifest)==fixture_sha,'fixture identity differs');m=strict(manifest);runtime_bytes=Path(runtime).read_bytes();require(sha(runtime_bytes)==runtime_sha,'runtime identity differs');rt=strict(runtime_bytes);require(sha(engine.read_bytes())==rt['engine_sha256'],'engine differs')
 for p,d in rt['files'].items():require(sha(Path(p).read_bytes())==d,'runtime file differs')
 if os.name!='nt':
  preload=Path('/etc/ld.so.preload');require(not preload.exists() or not preload.read_text().strip(),'system preload not permitted');scan=subprocess.run(['/usr/bin/ldd',str(engine)],env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},capture_output=True,text=True,timeout=30);libs=set(re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',scan.stdout,re.M));require(scan.returncode==0 and 'not found' not in scan.stdout+scan.stderr and bool(libs) and libs.issubset(rt['files']),'runtime library closure differs')
 require(inventory(fixture,fixture/'assets')==m['sources'] and inventory(fixture,fixture/'decks')==m['decks'],'fixture graph differs')
 receipt=strict((out/'receipt.json').read_bytes());require(receipt['schema']==1 and receipt['scope']=='finite v1 fixture AC replay; not noise/transient or original-model pass','receipt scope differs');require(sha(Path(replay_source).read_bytes())==replay_sha and receipt['replay_source_sha256']==replay_sha,'replay source identity differs');case=receipt['case'];require(case in m['decks'] and receipt['fixture_sha256']==fixture_sha and receipt['runtime_lock_sha256']==runtime_sha and receipt['engine_sha256']==rt['engine_sha256'] and receipt['returncode']==0,'receipt identity differs')
 match=re.fullmatch(r'decks/p([12])-r(0|90)-(tt|ll|hh|hl|lh)/(e1|e2)\.cir',case);require(match is not None,'case differs');plate,rotation,section,profile=match.groups();expected_details={'plate':int(plate),'rotation':int(rotation),'section':section,'profile':profile};require(receipt['details']==expected_details,'case receipt differs')
 private=out/'assets';expected={}
 for name,digest in m['sources'].items():
  source=(fixture/name).read_bytes();require(sha(source)==digest,'source differs');rel=Path(name).relative_to('assets').as_posix();data=rewrite(source,Path(name).name,private) if name.endswith(('.spice','.cir')) else source;expected['assets/'+rel]=sha(data)
 require(inventory(out,private)==expected and receipt['private_source_hashes']==expected,'private source differs');template=(fixture/case).read_bytes();require(sha(template)==m['decks'][case],'deck template differs');deck_contract(template,plate,rotation,section,profile);deck=template.replace(TOKEN,private.as_posix().encode());unlinked(out/'input.cir');require((out/'input.cir').read_bytes()==deck and receipt['input_deck_sha256']==sha(deck),'deck differs');command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(out/'result.raw'),str(out/'input.cir')];require(receipt['command']==command and receipt['cwd']==str(out),'execution command differs')
 env=receipt['environment'];require(env['LANG']==env['LC_ALL']=='C' and env['TZ']=='UTC' and env['HOME']==env['USERPROFILE']==str(out/'empty-home') and env['TMP']==env['TEMP']==str(out/'temporary') and env['SPICE_SCRIPTS']==rt['spice_scripts'],'execution environment differs');require(not any(k.upper().startswith('GIT_') or k.upper() in ('LD_PRELOAD','PYTHONPATH','PYTHONHOME') for k in env),'forbidden environment')
 if os.name=='nt':
  require(set(env)=={'LANG','LC_ALL','TZ','HOME','USERPROFILE','TMP','TEMP','SystemRoot','WINDIR','PATH','SPICE_SCRIPTS'} and env['SystemRoot']==env['WINDIR'] and env['PATH']==str(engine.parent)+os.pathsep+str(Path(env['SystemRoot'])/'System32'),'unexpected execution environment')
 else:
  require(set(env)=={'LANG','LC_ALL','TZ','HOME','USERPROFILE','TMP','TEMP','PATH','SPICE_SCRIPTS'} and env['PATH']==str(engine.parent)+':/usr/bin:/bin','unexpected execution environment')
 check_timing(receipt)
 unlinked(out/'console.log');log=(out/'console.log').read_bytes();require(sha(log)==receipt['console_sha256'],'console identity differs');check_console(log.decode('utf8'));unlinked(out/'result.raw');raw=(out/'result.raw').read_bytes();require(sha(raw)==receipt['raw_sha256'] and ('Title: '+deck.decode().splitlines()[0]+'\n').encode() in raw.replace(b'\r\n',b'\n'),'raw identity differs')
 headers=raw.decode('ascii').splitlines();commands=[x for x in headers if x.startswith('Command: ')];engine_id=rt['engine_sha256'];require((engine_id=='86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453' and len(commands)==1 and commands[0].startswith('Command: ngspice-46,')) or (engine_id=='820658317b0b54035208da41936fd6871ce924036e5ea4113a4168b821b7fc45' and not commands),'raw header differs from reviewed engine');coeff=load_contract(contract,contract_sha)[section]['coefficients'];result=check_faults(profile,scientific(raw,int(plate),section,profile,coeff));return {'status':'PASS','scope':'single pilot; not full matrix acceptance','case':case,**result}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('fixture','fixture-sha','runtime','runtime-sha','engine','output','contract','contract-sha','replay-source','replay-sha'):p.add_argument('--'+name,required=True)
 a=p.parse_args(argv);print(json.dumps(audit(a.fixture,a.fixture_sha,a.runtime,a.runtime_sha,a.engine,a.output,a.contract,a.contract_sha,a.replay_source,a.replay_sha),allow_nan=False))
if __name__=='__main__':main()
