"""Create a runtime identity proposal for review; it does not approve the runtime."""
from pathlib import Path
import argparse,json,os,re,subprocess
from replay import sha,unlinked,fail

def windows_companion(engine,engine_hash):
 companion=engine.parent/'libomp140.x86_64.dll'
 if engine_hash=='86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453' and not companion.is_file():fail('reviewed Windows ngspice companion missing')
 return unlinked(companion) if companion.is_file() else None

def build(engine,spice_scripts,output,extra_files=()):
 engine=unlinked(engine);scripts=unlinked(spice_scripts);out=unlinked(output);init=unlinked(scripts/'spinit')
 if out.exists():fail('runtime lock output must be fresh')
 files={str(engine):sha(engine.read_bytes()),str(init):sha(init.read_bytes())}
 if os.name=='nt':
  companion=windows_companion(engine,files[str(engine)])
  if companion is not None:files[str(companion)]=sha(companion.read_bytes())
 for item in extra_files:
  p=unlinked(item);files[str(p)]=sha(p.read_bytes())
 if os.name!='nt':
  preload=Path('/etc/ld.so.preload')
  if preload.exists() and preload.read_text().strip():fail('system preload not permitted')
  result=subprocess.run(['/usr/bin/ldd',str(engine)],env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},capture_output=True,text=True,timeout=30)
  if result.returncode or 'not found' in result.stdout+result.stderr:fail('unresolved engine library')
  libraries=set(re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(',result.stdout,re.M))
  if not libraries:fail('missing engine library closure')
  for library in libraries:files[library]=sha(Path(library).read_bytes())
 document={'schema':1,'engine_sha256':files[str(engine)],'spice_scripts':str(scripts),'files':files}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(document,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n');return {'runtime_lock_sha256':sha(out.read_bytes()),'review_required':True}

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',required=True);p.add_argument('--spice-scripts',required=True);p.add_argument('--output',required=True);p.add_argument('--runtime-file',action='append',default=[]);a=p.parse_args(argv);print(json.dumps(build(a.engine,a.spice_scripts,a.output,a.runtime_file),allow_nan=False))
if __name__=='__main__':main()
