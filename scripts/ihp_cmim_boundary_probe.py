"""Inspect imported MIM edges from pinned direct draw; no DRC or LVS claim."""
import argparse
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qualify_ihp_mim_layout import generate,regions
from scripts.qualify_standard_mos import load_technology,write
from icstudio.model import file_digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True)
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',scope=__doc__,qualified=False,cases=[])
    try:
        tech,report['package']=load_technology('ihp-sg13g2')
        for length in (74.98,75.0,75.02):
            label=f'{length:.3f}';p=generate(tech,75,length,out/('generator-'+label),args.magic)
            polys=list(regions(p)[36,0].each());boxes=[]
            for poly in polys:
                b=poly.bbox();boxes.append(dict(left=b.left,bottom=b.bottom,right=b.right,top=b.top,width=b.width(),height=b.height(),area=poly.area(),is_box=poly.is_box()))
            report['cases'].append(dict(requested_width_um=75,requested_length_um=length,units='nm',mim=boxes,
                gds_sha256=file_digest(out/('generator-'+label)/'coupon.gds'),generator_sha256=file_digest(out/('generator-'+label)/'generate.tcl')))
            write(out/'report.json',report)
        report['status']='OBSERVED'
    except Exception as exc:report.update(status='ERROR',error=repr(exc),traceback=traceback.format_exc())
    write(out/'report.json',report);print(json.dumps(report,indent=2));return int(report['status']!='OBSERVED')


if __name__=='__main__':raise SystemExit(main())
