"""Exercise included RF wrappers and real incompatible-runtime rejection.

Uses prior explicit-call reference waveforms, retaining circuit/library bytes.
This is a runtime integration check, not physical or full-envelope acceptance.
"""
import argparse
import cmath
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest,load_project
from icstudio.interchange import spice
from icstudio.pdks import stage_model_deck
from icstudio.engines import run_deck
from icstudio.rf_runtime import calls,inspect_inputs


def qualify(application,executable,rejected,output):
    app=Path(application).resolve();exe=Path(executable).resolve();old=Path(rejected).resolve()
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    assert json.loads((app/'report.json').read_bytes())['status']=='PASS'
    project=load_project(app/'nominal-27/ac/application/input.icproj')
    expected=json.loads((app/'nominal-27/ac/application/result.json').read_bytes())
    record=dict(status='RUNNING',qualified=False,chunk_complete=False,host=sys.platform,
                engine_sha256=file_digest(exe),rejected_engine_sha256=file_digest(old),
                reference_sha256=file_digest(app/'nominal-27/ac/application/result.json'),cases=[])
    for mode in ('include','library'):
        folder=out/mode;folder.mkdir();inputs=folder/'inputs';inputs.mkdir()
        libs=inputs/'nested';libs.mkdir()
        text=stage_model_deck(project['pdk'],spice(project,project['top'],
            dict(type='ac',corner='nominal',temperature=27,start='1k',end='1g',points=5),hierarchical=False),inputs)
        models=sorted({call['model'] for call in calls(text)});assert len(models)==2
        wrappers=[]
        for i,model in enumerate(models):
            name='outer'+str(i)
            text=text.replace(model,name)
            wrappers += [f'.subckt {name} a k params: area=4 perim=8',
                         f'Xinner a k {model} area={{area}} perim={{perim}}','.ends '+name]
        # Calls are hidden behind two files; the top-level scanner alone must
        # find nothing. An unrelated inactive section must not be inspected.
        if mode=='library':
            wrapper='\n'.join(['.lib tt',*wrappers,'.endl tt','.lib unused','Runused isolated 0 1k','.endl unused',''])
            include='.lib nested/wrapper.lib TT'
        else:
            wrapper='\n'.join(wrappers)+'\n';include='.include nested/wrapper.lib'
        (libs/'wrapper.lib').write_bytes(wrapper.encode())
        (libs/'entry.inc').write_bytes((include+'\n').encode())
        text=text.replace('.end\n','.include nested/entry.inc\n.end\n')
        assert not calls(text)
        deck=inputs/'input.cir';deck.write_bytes(text.encode())
        inspected=inspect_inputs(text,inputs)
        assert len(inspected['calls'])==2 and not inspected['uncertainty'],inspected
        originals={str(p.relative_to(inputs)):file_digest(p) for p in inputs.rglob('*') if p.is_file()}
        dest=folder/'accepted';dest.mkdir()
        result=run_deck(project,project['top'],dict(deck=str(deck),analysis=dict(type='ac')),str(exe),dest)
        (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        assert len(result['x'])==len(expected['x'])
        assert all(math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-12) for a,b in zip(result['x'],expected['x']))
        def complex_currents(r):
            return {name.casefold():[cmath.rect(a,math.radians(b)) for a,b in zip(values,r['current_phase'][name])]
                    for name,values in r['currents'].items() if name.casefold().startswith('vd')}
        left=complex_currents(result);right=complex_currents(expected);assert set(left)==set(right) and len(right)==6
        errors={key:max(abs(a-b)/(1e-16+1e-6*abs(b)) for a,b in zip(left[key],values)) for key,values in right.items()}
        assert max(errors.values())<=1,errors
        reject=folder/'rejected';reject.mkdir()
        try:
            run_deck(project,project['top'],dict(deck=str(deck),analysis=dict(type='ac')),str(old),reject)
        except ValueError as exc:
            assert 'geometry check' in str(exc),str(exc)
        else:
            raise AssertionError('Incompatible engine was not rejected through included wrappers.')
        assert not (reject/'deck.raw').exists() and not (reject/'deck-snapshot.cir').exists()
        accepted=list(dest.glob('*/rf-acceptance.json'));rejected=list(reject.glob('*/rf-acceptance.json'))
        assert len(accepted)==len(rejected)==1
        assert json.loads(accepted[0].read_bytes())['status']=='PASS'
        assert json.loads(rejected[0].read_bytes())['status']=='FAIL'
        assert originals=={str(p.relative_to(inputs)):file_digest(p) for p in inputs.rglob('*') if p.is_file()}
        record['cases'].append(dict(mode=mode,status='PASS',errors=errors,inputs_unchanged=True,
            input_hashes=originals,inspection=inspected,accepted_sha256=file_digest(accepted[0]),
            rejected_sha256=file_digest(rejected[0]),rejected_before_circuit_run=True))
    record['status']='PASS';(out/'report.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--application',type=Path,required=True)
    ap.add_argument('--ngspice',required=True)
    ap.add_argument('--reject-ngspice',required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();r=qualify(a.application,a.ngspice,a.reject_ngspice,a.output)
    print(r['status'],len(r['cases']),'included RF wrapper cases')
