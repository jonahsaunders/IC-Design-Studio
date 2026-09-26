"""Require real physical checks from the installed Windows application."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from icstudio.build_identity import identity

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('executable','pdk','out'):ap.add_argument('--'+key,type=Path,required=True)
    a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'QT_QPA_PLATFORM':'offscreen'}
    with (out/'launcher.log').open('wb') as log:
        subprocess.run([str(a.executable.resolve()),'--physical-acceptance','--managed','--pdk',str(a.pdk.resolve()),'--out',str(out/'probe')],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200,check=True)
    report=json.loads((out/'probe/report.json').read_text())
    if report.get('status')!='passed' or report.get('frozen') is not True:
        raise ValueError('Installed physical acceptance did not pass: '+str(report))
    expected=identity()
    if report['build']['commit']!=expected['commit'] or report['build']['dirty'] is not False:
        raise ValueError('Installed physical evidence belongs to a different or dirty build.')
    if report['executable_sha256']!=file_digest(a.executable):raise ValueError('Installed executable changed.')
    print('Installed Windows DRC/LVS, fault navigation and repair passed.')
