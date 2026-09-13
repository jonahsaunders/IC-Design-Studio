"""Build the release's Linux / private WSL runtime. Docker is a build dependency."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest


def build(output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        context = Path(td)
        shutil.copytree(ROOT/'packaging/digital', context, dirs_exist_ok=True)
        shutil.copytree(ROOT/'icstudio', context/'icstudio', ignore=shutil.ignore_patterns('assets','__pycache__','*.so','*.dll'))
        subprocess.run(['docker','build','--platform','linux/amd64','-t','icstudio-digital-runtime',str(context)],check=True)
    container = subprocess.check_output(['docker','create','icstudio-digital-runtime'],text=True).strip()
    try:
        subprocess.run(['docker','cp',container+':/opt/icstudio/runtime.json',str(output/'manifest.json')],check=True)
        subprocess.run(['docker','export','--output',str(output/'runtime.tar'),container],check=True)
        subprocess.run(['gzip','-f',str(output/'runtime.tar')],check=True)
    finally: subprocess.run(['docker','rm',container],check=True)
    metadata = json.loads((output/'manifest.json').read_text())
    metadata.update(archive='runtime.tar.gz',sha256=file_digest(output/'runtime.tar.gz'),
                    bytes=(output/'runtime.tar.gz').stat().st_size,
                    image_id=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','icstudio-digital-runtime'],text=True).strip())
    (output/'manifest.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='build/digital-payload')
    build(parser.parse_args().output)
