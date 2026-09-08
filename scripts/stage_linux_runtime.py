"""Stage desktop loader libraries excluded by PyInstaller, from this build host.
Run only when building for that host's Linux baseline. Never bundle glibc.
"""
import os,shutil,sys
from pathlib import Path

def stage(root):
 if not sys.platform.startswith('linux'):return
 dirs=[Path(os.environ.get('ICSTUDIO_SYSTEM_LIB_DIR','/usr/lib/x86_64-linux-gnu')),Path('/usr/lib/x86_64-linux-gnu'),Path('/lib/x86_64-linux-gnu')]
 names=['libEGL.so.1','libGL.so.1','libGLX.so.0','libGLdispatch.so.0','libX11.so.6','libxcb.so.1','libxcb-image.so.0','libxcb-xkb.so.1','libxcb-cursor.so.0','libxcb-keysyms.so.1','libxcb-render-util.so.0','libxcb-icccm.so.4','libxcb-util.so.1','libxkbcommon-x11.so.0']
 target=root/'dist/ICDesignStudio/_internal';missing=[]
 for name in names:
  src=next((d/name for d in dirs if (d/name).exists()),None)
  if src:shutil.copyfile(src,target/name)
  else:missing.append(name)
 if missing:raise RuntimeError('Install desktop runtime libraries before packaging: '+', '.join(missing))
if __name__=='__main__':stage(Path(__file__).resolve().parents[1])
