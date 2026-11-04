"""Independent ASCII-raw/deck readback of the seeded public MiM experiment.

No application, qualifier or application raw parser imports are used.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_capacitances(path):
    header, data = path.read_text(encoding='utf-8').split('Values:\n', 1)
    variables = [line.split()[1] for line in header.split('Variables:\n')[1].splitlines()]
    assert 'Flags: complex' in header and 'No. Points: 3' in header
    tokens = [line.split()[-1] for line in data.splitlines() if line.strip()]
    assert len(tokens) == 3*len(variables)
    columns = {}
    for i, name in enumerate(variables):
        samples = []
        for j in range(3):
            re, im = map(float, tokens[j*len(variables)+i].split(','))
            samples.append(complex(re, im))
        columns[name] = samples
    assert [v.real for v in columns['frequency']] == [1000., 10000., 100000.]
    capacitances = {}
    for name, samples in columns.items():
        if not name.startswith('i(v'):
            continue
        cs = []
        for f, current in zip((1000., 10000., 100000.), samples):
            # For a series RC, C = |Y|^2 / (omega * Im(Y)).
            assert math.isfinite(current.real) and math.isfinite(current.imag)
            assert current.imag < 0
            cs.append(abs(current)**2 / (-2*math.pi*f*current.imag))
        assert max(cs)/min(cs)-1 < 1e-8
        capacitances[name[3:-1]] = cs
    return capacitances


def audit(root):
    record = json.loads((root/'record.json').read_bytes())
    assert record['status'] == 'PASS' and record['source_unchanged'] and record['inputs_unchanged']
    assert record['chunk_complete'] is False and record['qualified'] is False
    trials = record['trials_per_shape']; assert trials in (2, 16)
    geometries = ((2,2), (2,10), (10,2), (30,30))
    expected = {f'p{k}g{g}t{t}':(k,w,l) for k in (1,2) for g,(w,l) in enumerate(geometries) for t in range(trials)}
    for name, h in record['staged_inputs'].items():
        assert sha(root/name) == h
    profiles = [('nominal',27)] if trials == 2 else [('nominal',27),('ss',0),('ff',85)]
    values = {}; faults = 0; samples = 0; deck_bindings = 0
    for corner, temp in profiles:
        for m in (.5,1,4,16):
            for variant in ('application','independent','nominal') + (() if m == 1 else ('old-vm','missing-m')):
                key = f'{corner}-{temp}-m{m:g}-{variant}'; result = record['results'][key]
                raw = root/key/'result.raw'; deck = root/(key+'.cir')
                assert sha(raw) == result['raw_sha256'] and sha(deck) == result['deck_sha256']
                lines = deck.read_text(encoding='utf-8').splitlines()
                assert f'.option seed={record["seed"]}' in lines
                assert f'.param mc_mm_switch={int(variant != "nominal")}' in lines
                assert f'.temp {temp}' in lines
                calls = [line.split() for line in lines if line.startswith('X_')]
                assert len(calls) == len(expected)
                assert len({line[0] for line in calls}) == len(calls)
                for line in calls:
                    tag = line[0][2:]; k,w,l = expected[tag]
                    assert line[1:4] == [tag,'0',f'sky130_fd_pr__cap_mim_m3_{k}']
                    params = dict(p.split('=') for p in line[4:])
                    mf = 'vm' if variant == 'old-vm' and k == 2 else 'mf'
                    assert len(params) == len(line)-4
                    assert {p:float(v) for p,v in params.items()} == dict(w=w,l=l,**{mf:m,'m':1 if variant=='missing-m' else m})
                    deck_bindings += 1
                cs = read_capacitances(raw); assert cs.keys() == expected.keys()
                values[corner,m,variant] = {tag:xs[0] for tag,xs in cs.items()}
                samples += 3*len(cs)
                for tag,xs in cs.items():
                    assert math.isclose(xs[0], result['capacitances_F'][tag], rel_tol=1e-12)
        get = lambda m,v: values[corner,m,v]
        base, zero = get(1,'independent'), get(1,'nominal')
        for m in (.5,1,4,16):
            actual, ref, nom = get(m,'application'), get(m,'independent'), get(m,'nominal')
            for tag in expected:
                assert math.isclose(actual[tag],ref[tag],rel_tol=1e-9)
                assert math.isclose(nom[tag],m*zero[tag],rel_tol=1e-9)
                # Rearranged public law; compare absolute capacitance deviations.
                assert abs((actual[tag]-nom[tag])-math.sqrt(m)*(base[tag]-zero[tag])) < zero[tag]*m*1e-9
            if m != 1:
                for variant in ('old-vm','missing-m'):
                    bad = get(m,variant)
                    for tag,(k,_,_) in expected.items():
                        if variant == 'old-vm' and k == 1:
                            assert math.isclose(actual[tag],bad[tag],rel_tol=1e-9)
                        else:
                            assert abs(actual[tag]/bad[tag]-1) > 1e-9
                            faults += 1
        # Confirm actual random variation, separately for both model families.
        for k in (1,2):
            ds = [base[tag]/zero[tag]-1 for tag,(kind,_,_) in expected.items() if kind==k]
            assert len({round(v,10) for v in ds}) >= len(ds)//2 and max(map(abs,ds)) > 1e-5
    assert len(values) == record['native_runs'] == len(record['results'])
    reported = sum(sum(row['detected_faults'].values()) for row in record['comparisons'])
    assert reported == faults
    return dict(status='PASS', native_runs=len(values), raw_capacitance_samples=samples,
                verified_device_calls=deck_bindings, detected_faults=faults,
                record_sha256=sha(root/'record.json'), auditor_sha256=sha(Path(__file__)))


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('root',type=Path);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();result=audit(a.root.resolve())
    a.output.write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
