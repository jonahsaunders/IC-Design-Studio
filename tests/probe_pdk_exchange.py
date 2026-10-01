"""Run every bundled core device after native/capture handoff and relocation.

Uses real ngspice and, for IHP, either the installed included runtime or an
explicit directory of compiled native OSDI models. No simulation substitutes.
"""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from tests.test_pdk_exchange_audit import VARIANTS,core_projects,technology
    from icstudio.model import load_project,atomic_write
    from icstudio.interchange import export_handoff
    from icstudio import native_spice,xschem_runtime
    from icstudio.osdi import configure,needs_managed_runtime
    from icstudio.physical_backend import prepare_simulation,dispatch
    from icstudio.spice_program import find_ngspice
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--ngspice');parser.add_argument('--osdi-directory',type=Path)
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):parser.error('Use a fresh empty output directory.')
    out.mkdir(parents=True,exist_ok=True);engine=find_ngspice(args.ngspice or '')
    if not engine:raise ValueError('A real ngspice installation is required.')
    records=[]
    for variant in VARIANTS:
        work=out/variant;item,capture,native=core_projects(technology(variant),work)
        shutil.rmtree(work/'source')
        for mode,p,run in [('capture',capture,xschem_runtime.run),('native',native,native_spice.run)]:
            if variant=='ihp-sg13g2' and args.osdi_directory:
                p['simulation_runtime']={'osdi':configure(sorted(args.osdi_directory.glob('*.osdi')))}
            export_handoff(p,work/mode);dest=work/(mode+' moved café');shutil.move(work/mode,dest)
            p=load_project(dest/'project.icproj');settings={'type':'program' if mode=='native' else 'xschem','probes':'v(out) v(gate) v(vdd)'}
            if needs_managed_runtime(p):
                job=dict(project=p,cell=p['top'],settings=settings,engine='ngspice');prepare_simulation(job)
                result=dispatch(job,dest/'simulation',lambda *_:None)
                assert Path(result['case_directory'])==dest/'simulation'
            else:result=run(p,p['top'],settings,engine,dest/'simulation')
            voltage=result['traces']['out'][0];cases=result.get('analysis_cases',result.get('xschem_cases'))
            assert result['program_status']=='Complete' and 0<voltage<item['spec']['supply'],result['warnings']
            assert cases and all((Path(result['case_directory'])/case['file']).is_file() for case in cases)
            record=dict(pdk=variant,mode=mode,status='passed',output_voltage=voltage,supply=item['spec']['supply'],cases=len(cases))
            records.append(record);atomic_write(out/'report.json',json.dumps(records,indent=2));print(json.dumps(record),flush=True)


if __name__=='__main__':main()
