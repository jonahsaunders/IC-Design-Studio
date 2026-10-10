"""Independent native proof of a factorized area-weighted capacitance model.

For net a, W_a=sum_i(w_ai V_ai), D_a=sum_b(C_ab), U_a=sum_b(C_ab W_b)/D_a.
A buffered U_a and capacitors C_ai=D_a*w_ai give each physical endpoint current
I_ai=s*w_ai*(D_a*V_ai-sum_b(C_ab*W_b)). The production implementation uses
affine sums anchored at the largest input weight to preserve common-mode
invariance in the saved coefficients. Compare with the expanded pairwise
network at every endpoint within the declared numerical tolerances.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--ngspice',required=True)
ap.add_argument('--solver',choices=('sparse','klu'),default='sparse')
args=ap.parse_args()
from icstudio.model import file_digest
from icstudio.compact_rc import build as build_compact
out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
weights={'a':{'a0':.125,'a1':.3,'a2':.575},'b':{'b0':.35,'b1':.65},'f':{'f0':.4,'f1':.6}}
coupling={('a','b'):3.7e-12,('a','f'):2.4e-12,('b','f'):1.3e-12}
nodes=[n for values in weights.values() for n in values]
ground={n:(i+1)*1e-14 for i,n in enumerate(nodes)}
# Match the application's area-weighted intrinsic C model while retaining the
# original fixture's total ground capacitance per logical net.
net_ground={net:math.fsum(ground[n] for n in ws) for net,ws in weights.items()}
ground={n:net_ground[net]*w for net,ws in weights.items() for n,w in ws.items()}
matrix={a:{b:0. for b in nodes} for a in nodes}
for n,c in ground.items():matrix[n][n]+=c
for (a,b),c in coupling.items():
    for i,wi in weights[a].items():
        for j,wj in weights[b].items():
            v=c*wi*wj;matrix[i][i]+=v;matrix[j][j]+=v;matrix[i][j]-=v;matrix[j][i]-=v
ngspice=str(Path(args.ngspice).resolve())
report=dict(status='running',qualified=False,scope='Electrical equivalence of a factorized lumped model; no field accuracy or process/timing acceptance.',
    script_sha256=file_digest(Path(__file__)),ngspice_sha256=file_digest(ngspice),solver=args.solver,
    production_implementation_sha256=file_digest(ROOT/'icstudio/compact_rc.py'),weights=weights,
    coupling=[dict(a=a,b=b,farads=c) for (a,b),c in coupling.items()],ground_farads=ground,
    limits=dict(ac_relative=1e-9,ac_absolute_amperes=1e-18,transient_absolute_volts=2e-6),ac=[],transient={},common_mode={})
(out/'ngspice-version.log').write_text(subprocess.check_output([ngspice,'--version'],text=True))
def retain():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def sum_sources(prefix, output, terms):
    result=[];previous='0'
    for i,(node,gain) in enumerate(terms.items()):
        current=output if i==len(terms)-1 else output+'_'+str(i)
        result.append(f'E{prefix}{i} {current} {previous} {node} 0 {gain:.17g}')
        previous=current
    return result

def circuit(mode):
    if mode.startswith('production'):
        model=build_compact({**{n:c*1e18 for n,c in net_ground.items()},'REF':0.},
            {pair:c*1e18 for pair,c in coupling.items()}, {**weights,'REF':{'REF':1.}},
            'REF',physical_nodes=[*nodes,'REF'],max_capacitors=100)
        report['production_model']={key:value for key,value in model.items() if key!='text'}
        lines=model['text'].splitlines()+['VREF REF 0 0']
        if mode=='production-corrupt':
            index=next(i for i,line in enumerate(lines) if line.startswith('G_STUDIO_SUM_'))
            t=lines[index].split();t[5]=format(float(t[5])*1.01,'.17g');lines[index]=' '.join(t)
        if mode=='production-anchor-corrupt':
            index=next(i for i,line in enumerate(lines) if line.startswith('G_STUDIO_SUM_') and line.split()[4:] == ['0','1'])
            t=lines[index].split();t[5]='1.01';lines[index]=' '.join(t)
        if mode=='production-leak':lines.append('RFAULT f0 0 1000000')
        return lines
    lines=[]
    for i,(n,c) in enumerate(ground.items()):lines.append(f'CG{i} {n} 0 {c:.17g}')
    if mode=='expanded':
        for (a,b),c in coupling.items():
            for i,wi in weights[a].items():
                for j,wj in weights[b].items():lines.append(f'CM{i}{j} {i} {j} {c*wi*wj:.17g}')
    else:
        for a,ws in weights.items():
            lines.extend(sum_sources('W'+a,'w'+a,ws))
        for a,ws in weights.items():
            adj={b if a==x else x:c for (x,b),c in coupling.items() if a in (x,b)}
            total=math.fsum(adj.values())
            gains={n:c/total for n,c in adj.items()}
            if mode=='corrupt' and a=='a':gains['b']*=1.01
            lines.extend(sum_sources('U'+a,'u'+a,{'w'+n:g for n,g in gains.items()}))
            for n,w in ws.items():lines.append(f'CM{n} {n} u{a} {total*w:.17g}')
    return lines
def run(folder,lines,commands):
    folder.mkdir(parents=True)
    deck='Compact coupling equivalence\n.option reltol=1e-10 abstol=1e-20 vntol=1e-12 method=gear\n'
    solver='set klu' if args.solver=='klu' else 'unset klu'
    deck+='\n'.join(lines)+'\n.control\n'+solver+'\nset numdgt=17\nset wr_singlescale\nset wr_vecnames\n'+commands+'\nquit\n.endc\n.end\n'
    (folder/'test.spice').write_text(deck)
    command=[ngspice,'-b','test.spice'];start=time.time()
    with (folder/'engine.log').open('w') as log:
        proc=subprocess.run(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    row=dict(command=command,exit_code=proc.returncode,seconds=time.time()-start,
        deck_sha256=file_digest(folder/'test.spice'),log_sha256=file_digest(folder/'engine.log'))
    assert proc.returncode==0,row
    log=(folder/'engine.log').read_text()
    solver_marker='Using KLU as Direct Linear Solver' if args.solver=='klu' else 'Using SPARSE 1.3 as Direct Linear Solver'
    assert solver_marker in log,log
    row['confirmed_solver']=solver_marker
    assert not any(s in log.lower() for s in ('aborted','timestep too small','error:')),log
    assert (folder/'data.txt').is_file(),(folder/'engine.log').read_text()
    lines=(folder/'data.txt').read_text().splitlines()
    row.update(data_sha256=file_digest(folder/'data.txt'),points=len(lines)-1)
    return row,[[float(v) for v in line.split()] for line in lines[1:]]
positive_modes=('expanded','compact','production')
negative_modes=('corrupt','production-corrupt','production-leak')
for mode in ('production','production-anchor-corrupt'):
    lines=[line for line in circuit(mode) if not line.startswith('VREF ')]+['VREF REF 0 DC 0 AC 1']
    lines += [f'V{i} {n} 0 DC 0 AC 1' for i,n in enumerate(nodes)]
    row,data=run(out/'common-mode'/mode,lines,'ac dec 4 1k 1t\nwrdata data.txt '+' '.join('i(v'+str(i)+')' for i in range(len(nodes))))
    assert len(data)==37 and all(len(values)==1+2*len(nodes) for values in data)
    passed=True;maximum=0.
    for values in data:
        for i,n in enumerate(nodes):
            actual=abs(complex(values[1+2*i],values[2+2*i]));maximum=max(maximum,actual)
            passed &= actual <= 1e-18
    row.update(passed=passed,maximum_error_amperes=maximum)
    report['common_mode'][mode]=row;retain()
assert report['common_mode']['production']['passed'] and not report['common_mode']['production-anchor-corrupt']['passed']
for mode in positive_modes+negative_modes:
    for active in nodes:
        folder=out/'ac'/mode/active
        lines=circuit(mode)+[f'V{i} {n} 0 DC 0 AC {int(n==active)}' for i,n in enumerate(nodes)]
        row,data=run(folder,lines,'ac dec 4 1k 1t\nwrdata data.txt '+' '.join('i(v'+str(i)+')' for i in range(len(nodes))))
        errors=[];accepted=True
        for samples in data:
            omega=2*math.pi*samples[0]
            assert len(samples)==1+2*len(nodes)
            for i,n in enumerate(nodes):
                expected=-1j*omega*matrix[n][active]
                actual=complex(samples[1+2*i],samples[2+2*i])
                err=abs(expected-actual);errors.append(err)
                accepted &= err<=max(1e-18,abs(expected)*1e-9)
        row.update(mode=mode,active=active,matches_full_analytical_matrix=accepted,maximum_error_amperes=max(errors))
        report['ac'].append(row);retain();print(json.dumps(dict(mode=mode,active=active,accepted=accepted)),flush=True)
data_by_mode={}
for mode in ('expanded','compact','production'):
    lines=circuit(mode)+['VDRIVE drive 0 PULSE(0 1 .1n .02n .02n 2n 5n)','RD drive a0 1000',
        'RA a0 a1 1700','RA2 a1 a2 2300','RB b0 b1 1900','RL b1 0 50000','RF f0 f1 3300']
    row,data=run(out/'transient'/mode,lines,'tran 2p 10n 0 2p uic\nlinearize '+' '.join('v('+n+')' for n in nodes)+'\nwrdata data.txt '+' '.join('v('+n+')' for n in nodes))
    report['transient'][mode]=row;data_by_mode[mode]=data;retain()
before=data_by_mode['expanded'];errors=[]
for mode in ('compact','production'):
    after=data_by_mode[mode];assert len(before)==len(after)
    local=[]
    for a,b in zip(before,after):
        assert len(a)==len(b)==1+len(nodes) and math.isclose(a[0],b[0],abs_tol=1e-20)
        local.extend(abs(x-y) for x,y in zip(a[1:],b[1:]))
    report['transient'][mode]['maximum_error_volts']=max(local)
    errors.extend(local)
report['transient'].update(maximum_error_volts=max(errors),passed=max(errors)<=2e-6,floating_pair='f0/f1 has only R/C connections; UIC specifies zero initial charge, no artificial leakage.')
report.update(status='completed',positive_controls_passed=all(r['matches_full_analytical_matrix'] for r in report['ac'] if r['mode'] in positive_modes),
    corrupted_gain_detected=all(any(not r['matches_full_analytical_matrix'] for r in report['ac'] if r['mode']==mode) for mode in negative_modes),
    negative_controls={mode:any(not r['matches_full_analytical_matrix'] for r in report['ac'] if r['mode']==mode) for mode in negative_modes},
    expanded_mutual_capacitors=sum(len(weights[a])*len(weights[b]) for a,b in coupling),compact_mutual_capacitors=len(nodes),
    independent_series_controlled_sources=sum(len(w) for w in weights.values())+2*len(coupling))
retain();assert report['positive_controls_passed'] and report['corrupted_gain_detected'] and report['transient']['passed']
print(json.dumps({k:v for k,v in report.items() if k in ('status','positive_controls_passed','corrupted_gain_detected','transient')}),flush=True)
