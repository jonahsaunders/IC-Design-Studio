"""Run the native Windows complete-edit benchmark in the source environment."""
import os,struct,subprocess,sys
from datetime import datetime
from pathlib import Path
from source_bootstrap import prepare,environment_path


def main():
    if os.name!='nt' or struct.calcsize('P')!=8 or sys.version_info<(3,12):
        print('Run benchmark-windows.bat with 64-bit Python 3.12 or newer.');return 1
    project=Path(__file__).resolve().parents[1]
    try:
        python=prepare(project,environment_path(project,os.environ.get('LOCALAPPDATA')))
        out=project/'benchmark-results'/datetime.now().strftime('%Y%m%d-%H%M%S')
        probe=subprocess.run([str(python),str(project/'scripts/check_layout_storage.py'),'--out',str(out/'storage')],cwd=project,check=False)
        if probe.returncode:
            print('Storage validation failed before benchmarking. See '+str(out/'storage/storage.json')+'. Move the source folder to a working local drive and retry. No durability checks were disabled.',file=sys.stderr)
            return probe.returncode
        return subprocess.run([str(python),str(project/'scripts/benchmark_layout_pipeline.py'),'--out',str(out),*sys.argv[1:]],cwd=project,check=False).returncode
    except (OSError,ValueError,RuntimeError) as exc:print(str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
