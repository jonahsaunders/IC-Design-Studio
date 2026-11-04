"""Rebuild the exact bundled default revisions from retained source packages."""
import argparse,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from scripts.device_qualification_source import PROMOTED,HISTORICAL_PROMOTED,PREVIOUS,INTERMEDIATE,SKY130_ESD_DEFAULT,previous_devices
from scripts.prepare_alternate_models import BASE as ALTERNATE_BASE,prepare as alternate_package
from scripts.sky130_li_source import BASE as LI_BASE
from scripts.sky130_mim_source import BASE as MIM_BASE
from scripts.sky130_rf_source import BASE as RF_BASE
from scripts.gf180_hv_source import BASE as HV_BASE
from scripts.ihp_npn_source import BASE as NPN_BASE


def prepare(source,output,target):
    if target not in PROMOTED:raise ValueError('Unknown device package target.')
    if file_digest(Path(source)/'package.json') not in (PROMOTED[target],SKY130_ESD_DEFAULT if target=='sky130A' else None,HISTORICAL_PROMOTED.get(target),PREVIOUS[target],INTERMEDIATE.get(target),ALTERNATE_BASE.get(target),HV_BASE.get(target),LI_BASE if target=='sky130A' else None,MIM_BASE if target=='sky130A' else None,RF_BASE if target=='sky130A' else None,NPN_BASE if target=='ihp-sg13g2' else None):
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
                    from scripts.prepare_sky130_mim_binding import prepare as mim_package
                    alternate=Path(tmp)/'alternate';alternate_package(base,alternate)
                    li=Path(tmp)/'li';li_package(alternate,li)
                    mim=Path(tmp)/'mim';mim_package(li,mim)
                    from scripts.prepare_sky130_rf_default import prepare as rf_package
                    rf=Path(tmp)/'rf';rf_package(mim,rf)
                    from scripts.promote_sky130_esd_default import prepare as esd_package
                    esd=Path(tmp)/'esd';esd_package(rf,esd)
                    from scripts.prepare_sky130_pw2dn_default import prepare as pw2dn_package
                    record=pw2dn_package(esd,output)
                else:
                    from scripts.prepare_gf180_hv import prepare as hv_package
                    alternate=Path(tmp)/'alternate';alternate_package(base,alternate)
                    record=hv_package(alternate,output)
        elif target=='ihp-sg13g2':
            from scripts.prepare_ihp_taps import prepare as tap_package
            from scripts.prepare_ihp_npn_default import prepare as npn_package
            with tempfile.TemporaryDirectory(prefix='icstudio-default-taps-') as tmp:
                base=Path(tmp)/'package';build(original,base)
                taps=Path(tmp)/'taps';tap_package(base,taps)
                record=npn_package(taps,output)
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
