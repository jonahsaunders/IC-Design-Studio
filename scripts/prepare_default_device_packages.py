"""Rebuild the exact tested default revisions from retained source packages."""
import argparse,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from scripts.device_qualification_source import PROMOTED,PREVIOUS,INTERMEDIATE,previous_devices
from scripts.prepare_alternate_models import BASE as ALTERNATE_BASE,prepare as alternate_package
from scripts.sky130_li_source import BASE as LI_BASE


def prepare(source,output,target):
    if target not in PROMOTED:raise ValueError('Unknown device package target.')
    if file_digest(Path(source)/'package.json') not in (PROMOTED[target],PREVIOUS[target],INTERMEDIATE.get(target),ALTERNATE_BASE.get(target),LI_BASE if target=='sky130A' else None):
        raise ValueError('Input is not an exact reviewed package for '+target+'.')
    if target=='sky130A':
        from scripts.prepare_sky130_fixed_geometry import prepare as build
    else:
        from scripts.prepare_mos_variant_bindings import prepare as build
    with previous_devices(source) as original:
        if target in ALTERNATE_BASE:
            with tempfile.TemporaryDirectory(prefix='icstudio-default-base-') as tmp:
                base=Path(tmp)/'package';build(original,base)
                if target=='sky130A':
                    from scripts.prepare_sky130_li_qualification import prepare as li_package
                    alternate=Path(tmp)/'alternate';alternate_package(base,alternate)
                    record=li_package(alternate,output)
                else:record=alternate_package(base,output)
        else:record=build(original,output)
    if file_digest(Path(output)/'package.json')!=PROMOTED[target]:
        raise ValueError('Rebuilt default device package differs from the tested revision.')
    return record


if __name__=='__main__':
    import json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--targets',nargs='+',choices=PROMOTED,default=list(PROMOTED));a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    print(json.dumps({t:prepare(a.input/t,a.output/t,t) for t in a.targets},indent=2))
