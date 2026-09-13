"""Exercise managed dispatch from the actual frozen application."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from icstudio.digital_runtime import state_root

out=ROOT/'build/digital-frozen-evidence'; out.mkdir(parents=True,exist_ok=True)
executable=ROOT/'dist/ICDesignStudio'/('ICDesignStudio.exe' if os.name=='nt' else 'ICDesignStudio')
with (out/'setup.log').open('wb') as log:
    subprocess.run([str(executable),'--digital-setup'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1100)
if 'Ready.' not in (out/'setup.log').read_text(encoding='utf-8',errors='replace'):
    raise ValueError('The frozen setup worker did not deliver its completion/progress stream.')
records=sorted(state_root().glob('ready-*.json'),key=lambda p:p.stat().st_mtime)
if not records: raise ValueError('Frozen setup returned without a Ready record.')
record=json.loads(records[-1].read_text()); report=json.loads((Path(record['evidence'])/'report.json').read_text())
if report['status']!='PASS': raise ValueError('Frozen digital acceptance did not pass.')
(out/'report.json').write_text(json.dumps({'status':'PASS','executable':str(executable),'installation':record,'checks':report['checks']},indent=2))
