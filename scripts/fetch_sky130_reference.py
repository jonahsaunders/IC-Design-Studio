"""Fetch the exact reference PDK archives, verify SHA256, then extract locally."""
import argparse,hashlib,json,shutil,subprocess,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();out=args.output.resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty PDK destination.')
    # Python 3.12 tarfile needs external zstd to decompress these upstream assets.
    zstd=shutil.which('zstd')
    if not zstd:raise ValueError('Install the zstd command before fetching the reference PDK.')
    lock=json.loads((ROOT/'examples/sky130-reference-assets.json').read_text());out.mkdir(parents=True,exist_ok=True);cache=out/'downloads';cache.mkdir()
    for name,expected in lock['files'].items():
        path=cache/name;url=f'https://github.com/{lock["repository"]}/releases/download/{lock["release"]}/{name}'
        with urllib.request.urlopen(url,timeout=60) as response,path.open('wb') as f:shutil.copyfileobj(response,f)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Checksum mismatch: '+name)
        tar=cache/(name+'.tar');subprocess.run([zstd,'-d','-f',str(path),'-o',str(tar)],check=True)
        with tarfile.open(tar) as archive:archive.extractall(out,filter='data')
        tar.unlink();print('Verified and extracted '+name)
    print('SKY130A directory: '+str(out/'sky130A'))
if __name__=='__main__':main()
