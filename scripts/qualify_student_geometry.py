"""Check all corners of the bounded GF180/IHP single-finger size ranges."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,atomic_write,file_digest
from icstudio.student_inverter import profile,create,build_layout,context
from icstudio.layout_verification import reference,run
from icstudio.testbenches import native_subcircuit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--magic',required=True);parser.add_argument('--netgen',required=True)
    args=parser.parse_args()
    if args.out.exists():raise ValueError('Use a fresh output directory.')
    args.out.mkdir(parents=True);records=[]
    for name,minimum in [('gf180mcuC',.28),('gf180mcuD',.28),('ihp-sg13g2',.13)]:
        folder=ROOT/'icstudio/assets/pdks'/name;m=json.loads((folder/'package.json').read_text())
        t=clone(m['technology']);t.update(package_root=str(folder),package_lock=dict(id=name,revision=m['revision'],files=m['files'],manifest_hash=digest(m)))
        for width,length in ((1,minimum),(1,2),(10,minimum),(10,2)):
            p=create(profile(t));_,c=context(p)
            for d in c['devices']:d['params'].update(w=str(width)+'u',l=str(length)+'u')
            build_layout(p);directory=args.out/(name+'-'+str(width)+'-'+str(length))
            r=run(p,c['id'],directory,dict(magic=args.magic,netgen=args.netgen),reference(native_subcircuit(p,c['id']),c['name']))
            records.append(dict(pdk=name,revision=m['revision'],width_um=width,length_um=length,status=r['status'],drc_count=r.get('drc_count'),report_sha256=file_digest(directory/'report.json')))
            atomic_write(args.out/'checks.json',json.dumps(records,indent=2))
            if r['status']!='passed':raise ValueError(name+' size boundary failed: '+r.get('error',''))
            print(name,width,length,'DRC/LVS passed',flush=True)


if __name__=='__main__':main()
