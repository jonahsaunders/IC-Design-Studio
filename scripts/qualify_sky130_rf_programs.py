"""Check RF control-program history and incompatible-runtime rejection.

Uses the saved projects and independent comparisons from RF application
qualification. The rejected engine must fail through all three execution paths.
"""
from pathlib import Path
import argparse,cmath,json,math,sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from icstudio.model import load_project,file_digest,clone
from icstudio.interchange import spice
from icstudio.pdks import stage_model_deck
from icstudio.spice_program import run_program,read_plot
from icstudio.engines import run_ngspice,run_deck


def qualify(application,executable,rejected_executable,output):
    app=Path(application).resolve();out=Path(output).resolve();exe=Path(executable).resolve();old=Path(rejected_executable).resolve()
    assert json.loads((app/'report.json').read_bytes())['status']=='PASS';out.mkdir(exist_ok=False)
    p=load_project(app/'nominal-27/ac/application/input.icproj');before=clone(p)
    program='op\nac dec 5 1k 1g\ndc VG 0 .6 .025\nac dec 5 1k 1g\n'
    def netlist(p,directory):
        text=spice(p,p['top'],hierarchical=False)
        return stage_model_deck(p['pdk'],text.rsplit('.end',1)[0]+'.temp 27\n.control\n'+program+'.endc\n.end\n',directory)
    settings=dict(probes='v(drive) '+ ' '.join('i(vd'+str(i)+str(j)+')' for i in range(len(json.loads((app/'report.json').read_bytes()).get('models',['ps2nw','pw2dn']))) for j in range(3)))
    accepted=out/'accepted';accepted.mkdir()
    r=run_program(p,p['top'],settings,str(exe),accepted,lambda *_:None,netlist,'RF runtime acceptance',p['pdk']['package_lock'],'cases')
    assert p==before and r['program_status']=='Complete' and [x['analysis'] for x in r['cases']]==['op','ac','dc','ac']
    def values(r):
        return {k.lower().removeprefix('i(').removesuffix(')'):[cmath.rect(a,math.radians(b)) for a,b in zip(v,r.get('current_phase',{}).get(k,[0]*len(v)))] for k,v in r['currents'].items()}
    errors=[]
    for case in r['cases'][1:]:
        actual=read_plot(accepted/case['file']);expected=json.loads((app/('nominal-27/'+case['analysis']+'/application/result.json')).read_bytes())
        left=values(actual);right=values(expected)
        assert len(actual['x'])==len(expected['x']) and all(math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-12) for a,b in zip(actual['x'],expected['x']))
        worst=max(abs(a-b)/(1e-16+1e-6*abs(b)) for key,vs in right.items() if key.startswith('vd') for a,b in zip(left[key],vs))
        assert worst<=1,worst;errors.append(dict(case=case['number'],analysis=case['analysis'],maximum_normalized_error=worst))
    record=dict(status='PASS',host=sys.platform,program_order=['op','ac','dc','ac'],program_comparisons=errors,project_unchanged=p==before,
        runtime_sha256=file_digest(exe),failed_engine_controls=[])
    for mode in ('graphical','program','external'):
        dest=out/('reject-old-'+mode);dest.mkdir()
        try:
            if mode=='graphical':run_ngspice(p,p['top'],dict(type='ac',corner='nominal',temperature=27,start='1k',end='1g',points=5),str(old),dest)
            elif mode=='program':run_program(p,p['top'],settings,str(old),dest,lambda *_:None,netlist,'RF runtime acceptance',p['pdk']['package_lock'],'cases')
            else:
                deck=dest/'reference.cir';deck.write_bytes(netlist(p,dest).encode());run_deck(p,p['top'],dict(deck=str(deck),analysis=dict(type='ac')),str(old),dest)
        except ValueError as error:
            assert 'geometry check' in str(error),str(error)
            assert not (dest/'result.raw').exists() and not (dest/'deck.raw').exists() and not (dest/'waveforms').exists()
            proofs=list(dest.glob('*/rf-acceptance.json'));assert len(proofs)==1
            assert json.loads(proofs[0].read_bytes())['status']=='FAIL'
            record['failed_engine_controls'].append(dict(route=mode,status='REJECTED',error=str(error),acceptance_sha256=file_digest(proofs[0])))
        else:raise AssertionError('Old runtime was not rejected: '+mode)
    assert p==before
    (out/'report.json').write_bytes((json.dumps(record,indent=2)+'\n').encode());return record


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--application',type=Path,required=True)
    ap.add_argument('--ngspice',required=True)
    ap.add_argument('--reject-ngspice',required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();result=qualify(a.application,a.ngspice,a.reject_ngspice,a.output)
    print(result['status'],len(result['failed_engine_controls']),'incompatible-engine controls')
