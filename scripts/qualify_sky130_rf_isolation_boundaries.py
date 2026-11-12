"""Native public n-well opening spacing boundary for the RF isolation coupon."""
import argparse,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from icstudio.layout_verification import run
from scripts.qualify_sky130_rf_isolation import stream,project,selected,write
from scripts.qualify_standard_mos_layout import technology


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--sky130',type=Path,required=True)
    ap.add_argument('--klayout',type=Path,required=True);ap.add_argument('--pilot',action='store_true');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tech,identity=technology('sky130A',a.sky130)
    files=[Path(__file__),ROOT/'scripts/qualify_sky130_rf_isolation.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    sources={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    record=dict(schema=1,status='RUNNING',qualified=False,chunk_complete=False,simulation_models=False,
                pdk=identity,source_sha256=sources,rule='MR_nwell.SP.1',minimum_um=1.27,
                scope='Sampled public n-well-hole spacing boundary, not a complete device operating envelope.',cases=[])
    try:
        for width in (1.26,1.27,1.28):
            for angle in ((0,) if a.pilot else (0,90,180,270)):
                name=f'w{width}-r{angle}';folder=out/name;folder.mkdir();gds=folder/'input.gds';stream(gds,width,4,angle)
                p=project(gds,tech);result=run(p,p['top'],folder/'verification',dict(klayout=str(a.klayout.resolve())),selected(width,4),lvs_extractor='sky130-rf-isolation-klayout')
                stages={s['name']:s['status'] for s in result['stages']}
                assert all(stages[s]=='passed' for s in ('preflight','layout_export','lvs_extraction','lvs','integrity')),result
                rules=result['klayout_drc']['rules']
                if width<1.27:assert result['status']=='failed' and rules=={'MR_nwell.SP.1':1},result
                else:assert result['status']=='passed' and rules=={},result
                record['cases'].append(dict(name=name,width_um=width,length_um=4,angle=angle,
                    expected='reject_spacing' if width<1.27 else 'pass',native_status=result['status'],rules=rules,
                    report_sha256=file_digest(folder/'verification/report.json')))
                write(out/'record.json',record);print(name,'EXPECTED RESULT',flush=True)
        assert all(file_digest(ROOT/p)==s for p,s in sources.items())
        record['status']='PASS'
    except Exception as exc:record.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(out/'record.json',record);print(record['status'],record.get('error',''),flush=True)
    return 0 if record['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
