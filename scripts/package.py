import os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
import hashlib
sys.path.insert(0,str(root))
from check_simulation_assets import check
from icstudio.runtime_setup import check_ngspice
check(root)
from stage_openems import stage as stage_openems, verify as verify_openems
solver_runtime = stage_openems(root/"build/openems-runtime", root/"build/openems-downloads")
from icstudio.digital_runtime import manifest as digital_manifest, payload_root as digital_payload
from icstudio.model import file_digest
digital_data=digital_manifest()
if not digital_data or file_digest(digital_payload()/digital_data['archive'])!=digital_data['sha256']:
 raise ValueError('Stage the qualified digital runtime payload before packaging. See scripts/build_digital_runtime.py.')
qualification=digital_payload()/('qualified-'+('Windows' if os.name=='nt' else 'Linux')+'.json')
if not qualification.is_file():raise ValueError('The digital runtime must pass acceptance on this build platform before packaging.')
import json
if json.loads(qualification.read_text()).get('sha256')!=digital_data['sha256']:raise ValueError('The digital runtime acceptance record belongs to another archive.')
if os.name=='nt':
 from stage_windows_ngspice import ensure
 ensure()
else:
 engine=os.environ.get('ICSTUDIO_BUNDLED_NGSPICE') or shutil.which('ngspice')
 if not engine:raise ValueError('Install ngspice or set ICSTUDIO_BUNDLED_NGSPICE before packaging. Runtime-free releases are not supported.')
 check_ngspice(engine)
 os.environ['ICSTUDIO_BUNDLED_NGSPICE']=engine
from icstudio.build_identity import identity
from icstudio.digital_vga import REVISION as vga_revision
vga_assets=root/'build/vga-playground/dist'
if not (vga_assets/'icstudio-build.json').is_file() or json.loads((vga_assets/'icstudio-build.json').read_text())['revision']!=vga_revision:
 raise ValueError('Build the pinned VGA Playground before packaging: python scripts/build_vga_playground.py')
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
args+=['--hidden-import','PySide6.QtWebEngineWidgets','--add-data',f'{vga_assets}{os.pathsep}icstudio/assets/vga-playground']
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

# Copy the independent interpreter verbatim after freezing. PyInstaller must
# not rewrite its libraries or mix them with the application's Python/Qt.
solver_target = root/'dist/ICDesignStudio/_internal/icstudio/assets/runtime/openems'
shutil.copytree(solver_runtime, solver_target, dirs_exist_ok=True)
verify_openems(solver_target)

digital_target=root/'dist/ICDesignStudio/_internal/icstudio/assets/runtime/digital'
shutil.copytree(digital_payload(),digital_target,dirs_exist_ok=True)
# The independent Linux interpreter runs this exact release's backend sources.
shutil.copytree(root/'icstudio',digital_target/'backend/icstudio',
 ignore=shutil.ignore_patterns('assets','__pycache__','*.pyc','*.so','*.dll','*.pyd'))

from stage_linux_runtime import stage
stage(root)

check(root/'dist/ICDesignStudio/_internal',runtime=True)
