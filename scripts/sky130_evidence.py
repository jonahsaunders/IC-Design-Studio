"""Package immutable run evidence and a portable native project with its models."""
import argparse,json,shutil,zipfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest,atomic_write

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run=args.run.resolve();report=json.loads((run/'report.json').read_text())
    if report['status']!='passed':raise ValueError('Only a completely passing run can be packaged as verified reference evidence.')
    lock=json.loads((run/'pdk-lock.json').read_text());pdk=Path(lock['root']);project=json.loads((run/'inverter.icproj').read_text());project['pdk']['package_root']='pdk/sky130A'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in sorted(run.rglob('*')):
            if f.is_file():z.write(f,Path('evidence')/f.relative_to(run))
        for rel,sha in lock['files'].items():
            f=(pdk/rel).resolve()
            if not f.is_relative_to(pdk) or file_digest(f)!=sha:raise ValueError('PDK assets changed before packaging: '+rel)
            z.write(f,Path('portable/pdk/sky130A')/rel)
        z.writestr('portable/inverter.icproj',json.dumps(project,indent=2))
        z.write(ROOT/'licenses/Apache-2.0.txt','LICENSE-PDK-Apache-2.0.txt');z.write(ROOT/'docs/SKY130_REFERENCE.md','SKY130_REFERENCE.md')
        z.writestr('README.txt','Open portable/inverter.icproj in IC Design Studio 0.4.0. Keep pdk/ beside it. It includes the editable inverter schematic, hierarchical testbench, imported layout and checksummed PDK models. Select ngspice to simulate; generic built-in models are deliberately blocked. The project supplies SKY130 hsa compatibility explicitly; local ngspice startup files are ignored for reproducibility.\n\nThe evidence/ directory is the original immutable run, including original host paths, scripts, hashes, input decks, logs and before/after waveforms. The separate portable project adjusts only the PDK root for reopening on your computer; it is not the original input hash.\n\nThe fixture is an existing SKY130 standard cell. It verifies this bounded adapter flow; it does not qualify arbitrary layouts, full interconnect resistance, other corners, or foundry signoff.\n\nPDK and reference-cell derivatives: Copyright 2020 The SkyWater PDK Authors and contributors; Apache-2.0. All original file notices are retained.\n')
    print(args.output,args.output.stat().st_size)
if __name__=='__main__':main()
