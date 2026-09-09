"""Provision the pinned public Windows runtime for builds and acceptance tests."""
import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

URL='https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/42/ngspice-42_64.7z/download'
SHA256='aa98b3c74743260a38835bd2698f58221b7237939798d1fdf2297f44ecf1d6ec'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];cache=root/'build/ngspice-windows';cache.mkdir(parents=True,exist_ok=True)
    archive=args.archive or cache/'ngspice-42_64.7z'
    if not archive.exists():
        with urllib.request.urlopen(URL,timeout=120) as response, archive.open('wb') as output:shutil.copyfileobj(response,output)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:raise ValueError('The Windows ngspice archive checksum differs from the pinned release.')
    import py7zr
    with py7zr.SevenZipFile(archive) as package:package.extractall(cache/'unpacked')
    source=cache/'unpacked/Spice64';target=root/'icstudio/assets/runtime/ngspice';target.mkdir(parents=True,exist_ok=True)
    for relative,name in [('bin/ngspice_con.exe','ngspice.exe'),('bin/libomp140.x86_64.dll','libomp140.x86_64.dll'),('docs/COPYING','COPYING.txt')]:shutil.copy2(source/relative,target/name)
    shutil.copy2(root/'icstudio/assets/ngspice/spinit',target/'spinit');print(target/'ngspice.exe')


if __name__=='__main__':main()
