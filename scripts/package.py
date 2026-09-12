import os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
import hashlib
sys.path.insert(0,str(root))
from check_simulation_assets import check
from icstudio.runtime_setup import check_ngspice
check(root)
if os.name=='nt':
 from stage_windows_ngspice import ensure
 ensure()
else:
 engine=os.environ.get('ICSTUDIO_BUNDLED_NGSPICE') or shutil.which('ngspice')
 if not engine:raise ValueError('Install ngspice or set ICSTUDIO_BUNDLED_NGSPICE before packaging. Runtime-free releases are not supported.')
 check_ngspice(engine)
 os.environ['ICSTUDIO_BUNDLED_NGSPICE']=engine
from icstudio.build_identity import identity
build=identity()
if build['commit']=='unknown' or build['dirty'] is not False:
 subprocess.run(['git','status','--short','--untracked-files=normal'],cwd=root,check=False)
 raise ValueError('Package a clean, committed source checkout so every binary has an exact source identity: '+repr(build))
metadata=dict(ENGINE_SOURCE_HASH=hashlib.sha256((root/'icstudio'/'simulation.py').read_bytes()).hexdigest(),
 WORKFLOW_SOURCE_HASH=hashlib.sha256(b''.join(f.name.encode()+f.read_bytes() for f in sorted((root/'icstudio').glob('*.py')) if f.name!='build_info.py')).hexdigest(),
 BUILD_COMMIT=build['commit'],BUILD_BRANCH=build['branch'],BUILD_DIRTY=False)
(root/'icstudio'/'build_info.py').write_text(''.join(key+' = '+repr(value)+'\n' for key,value in metadata.items()))
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--name','ICDesignStudio','--windowed','--onedir','--collect-all','klayout','--add-data',f'{root/"icstudio"/"assets"}{os.pathsep}icstudio/assets','--hidden-import','PySide6.QtSvg','--hidden-import','icstudio.cli','--hidden-import','icstudio.sdk','--add-data',f'{root/"docs"}{os.pathsep}docs','--add-data',f'{root/"examples"}{os.pathsep}examples','--add-data',f'{root/"licenses"}{os.pathsep}licenses']
args+=['--recursive-copy-metadata','cryptography']
engine=os.environ.get('ICSTUDIO_BUNDLED_NGSPICE')
if engine:
 if not Path(engine).is_file():raise ValueError('ICSTUDIO_BUNDLED_NGSPICE must name the engine binary for this build platform.')
 args+=['--add-binary',f'{Path(engine).resolve()}{os.pathsep}icstudio/assets/runtime/ngspice']
 args+=['--add-data',f'{root/"icstudio/assets/ngspice/spinit"}{os.pathsep}icstudio/assets/runtime/ngspice']
sys.path.insert(0,str(root))
from icstudio.native_core import native_library_name
for name in filter(None,[native_library_name()]):
 p=root/'icstudio'/name
 if p.exists():args+=['--add-binary',f'{p}{os.pathsep}icstudio']
if os.name=='nt':args+=['--icon',str(root/'icstudio/assets/app.ico')]
args.append(str(root/'main.py'));subprocess.run(args,cwd=root,check=True)

from stage_linux_runtime import stage
stage(root)

check(root/'dist/ICDesignStudio/_internal',runtime=True)
