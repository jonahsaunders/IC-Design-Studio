"""Compile the six IHP Verilog-A libraries with an installed OpenVAF compiler."""
import argparse, json, platform, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import atomic_write,file_digest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pdk-root',type=Path,required=True);parser.add_argument('--openvaf',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--generic-cpu',action='store_true',help='Use only with a compiler supporting --target_cpu generic (OpenVAF 23.5 has a known option parser crash).')
    args=parser.parse_args();source=args.pdk_root.resolve()/'libs.tech/verilog-a';compiler=args.openvaf.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    names=['psp103/psp103.va','psp103/psp103_nqs.va','r3_cmc/r3_cmc.va','mosvar/mosvar.va','cap_cmomi/cap_cmomi.va','cap_cmomf/cap_cmomf.va']
    report={'system':platform.system(),'machine':platform.machine(),'cpu_target':'generic' if args.generic_cpu else 'compiler default (native)','compiler_sha256':file_digest(compiler),'models':[]}
    for rel in names:
        path=source/rel;target=out/(path.stem+'.osdi')
        if target.exists():raise ValueError('Use a fresh output folder; refusing to overwrite '+target.name)
        result=subprocess.run([str(compiler),str(path),'--output',str(target)]+(['--target_cpu','generic'] if args.generic_cpu else []),cwd=path.parent,capture_output=True,text=True,timeout=180)
        atomic_write(out/(path.stem+'.log'),result.stdout+result.stderr)
        if result.returncode or not target.is_file():raise RuntimeError('Compilation failed: '+rel+'. See '+str(out/(path.stem+'.log')))
        report['models'].append({'source':rel,'dependencies':{p.relative_to(source).as_posix():file_digest(p) for p in path.parent.iterdir() if p.is_file()},'output':target.name,'sha256':file_digest(target)})
        print('Compiled '+target.name,flush=True)
    atomic_write(out/'build.json',json.dumps(report,indent=2))
if __name__=='__main__':main()
