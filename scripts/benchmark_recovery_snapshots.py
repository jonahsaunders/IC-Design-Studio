"""Measure isolated snapshot preparation after one in-place shape edit."""
import argparse,json,platform,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,example
from icstudio.layout import rect
from icstudio.recovery_snapshot import isolate


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    rows=[]
    for count in (1000,10000,100000):
        p=example('empty');p['cells'][0]['shapes']=[rect('metal1',i*1000,0,600,600) for i in range(count)]
        previous=isolate(p);p['cells'][0]['shapes'][count//2]['points'][0][0]+=5
        samples={}
        for name,fn in [('full_copy',lambda:clone(p)),('isolated_reuse',lambda:isolate(p,previous))]:
            times=[]
            for _ in range(5):
                start=time.perf_counter();result=fn();times.append((time.perf_counter()-start)*1000)
                assert result==p
            samples[name]=dict(samples_ms=times,median_ms=statistics.median(times))
        rows.append(dict(shapes=count,measurements=samples))
    report=dict(host=platform.platform(),python=platform.python_version(),workloads=rows,
                scope='Snapshot preparation after an initial isolated snapshot, five samples per method. Includes scanning mutable source data; excludes initial copying, serialization, validation and disk writes. Local timings do not establish native desktop responsiveness.')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
