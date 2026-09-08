import os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
import hashlib
(root/"icstudio"/"build_info.py").write_text("ENGINE_SOURCE_HASH = "+repr(hashlib.sha256((root/"icstudio"/"simulation.py").read_bytes()).hexdigest())+"\nWORKFLOW_SOURCE_HASH = "+repr(hashlib.sha256(b"".join(f.name.encode()+f.read_bytes() for f in sorted((root/"icstudio").glob("*.py")) if f.name!="build_info.py")).hexdigest())+"\n")
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--name','ICDesignStudio','--windowed','--onedir','--collect-all','klayout','--add-data',f'{root/"icstudio"/"assets"}{os.pathsep}icstudio/assets','--hidden-import','PySide6.QtSvg','--hidden-import','icstudio.cli','--hidden-import','icstudio.sdk','--add-data',f'{root/"docs"}{os.pathsep}docs','--add-data',f'{root/"examples"}{os.pathsep}examples','--add-data',f'{root/"licenses"}{os.pathsep}licenses']
sys.path.insert(0,str(root))
from icstudio.native_core import native_library_name
for name in filter(None,[native_library_name()]):
 p=root/'icstudio'/name
 if p.exists():args+=['--add-binary',f'{p}{os.pathsep}icstudio']
if os.name=='nt':args+=['--icon',str(root/'icstudio/assets/app.ico')]
args.append(str(root/'main.py'));subprocess.run(args,cwd=root,check=True)

from stage_linux_runtime import stage
stage(root)
