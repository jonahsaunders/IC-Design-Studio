"""Reject IHP fill models that cannot extract nearby floating-metal coupling."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.digital_fill_spef import parse, require

LAYERS=('Metal1','Metal2','Metal3','Metal4','Metal5','TopMetal1','TopMetal2')


def controls_pass(rows):
    """Require a real positive control and an unchanged far/absent control per layer."""
    if len(rows)!=len(LAYERS) or {r['layer'] for r in rows}!=set(LAYERS):return False
    for row in rows:
        cases=row['cases']
        if set(cases)!={'absent','near','far'}:return False
        if not all(math.isfinite(c[k]) and c[k]>=0 for c in cases.values()
                   for k in ('signal_to_fill_pf','signal_ground_pf')):return False
        if not (cases['near']['signal_to_fill_pf']>0 and
                cases['absent']['signal_to_fill_pf']==cases['far']['signal_to_fill_pf']==0):return False
        if not math.isclose(cases['absent']['signal_ground_pf'],cases['far']['signal_ground_pf'],
                            rel_tol=1e-12,abs_tol=1e-15):return False
    return True


def audit(directory):
    directory=Path(directory);captured=json.loads((directory/'record.json').read_text())
    entries=captured['cases'];require(len({e['case'] for e in entries})==len(entries),'Repeated control case.')
    entries={e['case']:e for e in entries};rows=[];rule_hashes=set();workers=set();checkpoints=set()
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    for layer in LAYERS:
        row=dict(layer=layer,cases={})
        for state in ('absent','near','far'):
            key=layer+'-'+state;require(key in entries,'Missing coupling control: '+key)
            folder=directory/key
            files=entries[key]['files']
            require({'request.json','represented.json','represented.odb','worker.py','rules','engine.log','parasitics.spef'}<=files.keys(),
                    'Incomplete native coupling control.')
            for name,digest in files.items():
                require(Path(name).name==name and sha(folder/name)==digest,'Changed or external control artifact.')
            request=json.loads((folder/'request.json').read_text());geometry=json.loads((folder/'represented.json').read_text())
            require(request['coupon'] is True and request['rules_sha256']==sha(folder/'rules') and
                    request['checkpoint_sha256']==sha(folder/'original.odb'),'Unbound control extraction.')
            workers.add(sha(folder/'worker.py'));checkpoints.add(sha(folder/'original.odb'));rule_hashes.add(sha(folder/'rules'))
            signal=dict(net='SIGNAL',layer=layer,box_nm=[50000,50000,70000,52000]);expected=[signal]
            if state!='absent':
                gap=500 if state=='near' else 40000
                expected.append(dict(layer=layer,box_nm=[50000,52000+gap,70000,54000+gap]))
            require(request['rectangles']==expected and geometry['original_nets']==0 and geometry['total_nets']==len(expected),
                    'Coupling control geometry or net inventory changed.')
            require(geometry['added']==[dict(r,net=r.get('net','ICSTUDIO_FLOAT_'+str(i).zfill(6))) for i,r in enumerate(expected)],
                    'Native readback does not match the control geometry.')
            data=parse(folder/'parasitics.spef');wanted={'SIGNAL'} if state=='absent' else {'SIGNAL','ICSTUDIO_FLOAT_000001'}
            require(data['nets'].keys()==wanted,'Missing or unexpected extracted control net.')
            require([p[:3] for p in data['nets']['SIGNAL']['conn'] if p[0]=='*P']==[['*P','SIGNAL','I']],
                    'Control signal boundary terminal is missing.')
            for name,net in data['nets'].items():
                if name!='SIGNAL':require(all(p[0]=='*N' for p in net['conn']),'Control fill was connected to a terminal.')
            coupling=math.fsum(float(v) for (a,b),v in data['couplings'].items()
                               if {data['owners'][a],data['owners'][b]}=={'SIGNAL','ICSTUDIO_FLOAT_000001'})
            row['cases'][state]=dict(signal_to_fill_pf=coupling,signal_ground_pf=float(sum(data['nets']['SIGNAL']['ground'].values())),
                                     spef_sha256=sha(folder/'parasitics.spef'))
        rows.append(row)
    require(len(rule_hashes)==len(workers)==len(checkpoints)==1,'Controls used differing models, workers or technology databases.')
    passed=controls_pass(rows)
    return dict(schema=1,status='coupling-controls-passed' if passed else 'coupling-controls-failed',
                passed=passed,qualified=False,rules_sha256=next(iter(rule_hashes)),worker_sha256=next(iter(workers)),
                source_record_sha256=sha(directory/'record.json'),controls=rows,
                scope='Seven-layer native near/far coupling response only. Not field accuracy, fill-width calibration or timing acceptance.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.directory);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('status','passed','qualified','rules_sha256')}));raise SystemExit(0 if r['passed'] else 1)
