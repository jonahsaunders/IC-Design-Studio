import os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if os.name=='nt':
 if shutil.which('cl'):
  subprocess.run(['cl','/nologo','/std:c++20','/O2','/LD',str(root/'native'/'solver.cpp'),'/link','/OUT:'+str(root/'icstudio'/'iccore.dll')],cwd=root,check=True)
 else: print('MSVC cl not found. The application will use the tested Python solver fallback.')
else:
 out=root/'icstudio'/('libiccore.dylib' if sys.platform=='darwin' else 'libiccore.so')
 subprocess.run(['c++','-std=c++20','-O2','-shared','-fPIC',str(root/'native'/'solver.cpp'),'-o',str(out)],check=True)
