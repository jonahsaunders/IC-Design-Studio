"""Real native ngspice acceptance of the five templates for all bundled PDKs.

IHP requires explicitly compiled libraries for the native platform running this
probe. These results are nominal template checks, not process signoff.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from tests.test_student_physical import technology
    from icstudio.project_templates import TEMPLATES,create,defaults
    from icstudio.osdi import configure
    from icstudio.testbenches import simulate
    from icstudio.spice_program import find_ngspice
    from icstudio.model import atomic_write
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--ngspice',required=True)
    parser.add_argument('--osdi-directory',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();engine=find_ngspice(args.ngspice)
    if not engine:raise ValueError('Install a native ngspice executable.')
    libraries=configure(sorted(args.osdi_directory.glob('*.osdi')))
    if not libraries:raise ValueError('Compile the matching IHP OSDI libraries first.')
    if out.exists() and any(out.iterdir()):parser.error('Use a fresh output directory.')
    out.mkdir(parents=True,exist_ok=True);rows=[]
    for variant in ('sky130A','gf180mcuC','gf180mcuD','ihp-sg13g2'):
        tech=technology(variant);selected=defaults(tech)
        for kind in TEMPLATES:
            p,_,_=create(tech,kind,selected['supply'],selected['NMOS'],selected['PMOS'])
            if variant=='ihp-sg13g2':p['simulation_runtime']={'osdi':libraries}
            for bench in p['testbenches']:
                result=simulate(p,bench,engine,out/variant/bench['name'])
                row=dict(pdk=variant,template=kind,bench=bench['name'],status='passed',samples=len(result['x']),measurements=result['measurements'])
                assert result['x'] and result['measurements']['status']=='passed',row
                if kind=='ring':
                    values=result['traces']['out'];threshold=selected['supply']/2
                    row['rising_half_supply_crossings']=sum(a<threshold<=b for a,b in zip(values,values[1:]))
                    assert row['rising_half_supply_crossings']>=3,row
                rows.append(row);atomic_write(out/'report.json',json.dumps(rows,indent=2));print(json.dumps(row),flush=True)


if __name__=='__main__':main()
