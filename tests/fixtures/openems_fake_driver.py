"""External-process lifecycle fixture. Does not perform electromagnetic solving."""
import argparse
import json
import math
import os
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--probe', action='store_true'); parser.add_argument('--model')
parser.add_argument('--scale', type=float); parser.add_argument('--port', type=int)
args = parser.parse_args(); mode = os.environ.get('ICSTUDIO_TEST_EM_MODE', '')
if args.probe:
    if mode == 'missing':
        print('No module named openEMS', flush=True); raise SystemExit(1)
    print('ICSTUDIO_EM:'+json.dumps(dict(state='ready', versions={'openEMS': 'PROCESS FIXTURE'})), flush=True)
    raise SystemExit(0)
data = json.loads(Path(args.model).read_text()); opts = data['settings']
print('ICSTUDIO_EM:'+json.dumps(dict(state='mesh', cells=1000)), flush=True)
if mode == 'truncated':
    # Split the native line across separate reads; the UI must recognize the
    # reconstructed line and stop without waiting for its ordinary timeout.
    print('Operator::CalcGaussianPulsExcitation: Cutting to max number of ', end='', flush=True)
    time.sleep(.1)
    print('timesteps!\r', flush=True)
    while True: time.sleep(.1)
if mode == 'hang':
    while True: time.sleep(.1)
time.sleep(.08)
if mode == 'crash': raise SystemExit(7)
if mode == 'unconverged': print('Max. number of timesteps was reached before the end-criteria was reached', flush=True)
print('Energy: 1e-10 (-60.1dB)', flush=True)
frequency = [opts['f_start_hz']*(opts['f_stop_hz']/opts['f_start_hz'])**(i/(opts['samples']-1)) for i in range(opts['samples'])]
real = []; imag = []
incoming = []
for f in frequency:
    a = complex(-2 if mode == 'negative-base' else 2, 2*math.pi*f*1e-9)
    mutual = -4. if mode == 'active-common-mode' else .2
    det = (a+50)**2-mutual**2
    diagonal = ((a-50)*(a+50)-mutual**2)/det; off = 100*mutual/det
    waves = ([1., -.04+.01j] if args.port == 1 else [.03+.02j, 1.]) if mode == 'coupled-waves' else [int(r == args.port-1) for r in (0,1)]
    values = [diagonal*waves[0]+off*waves[1], off*waves[0]+diagonal*waves[1]]
    incoming.append(waves)
    real.append([v.real for v in values]); imag.append([v.imag for v in values])
out = dict(run_hash=data['run_hash'], port=args.port, scale=args.scale, frequency_hz=frequency,
           wave_basis=data['wave_basis'], a_real=[[v.real for v in row] for row in incoming],
           a_imag=[[v.imag for v in row] for row in incoming], b_real=real, b_imag=imag,
           versions={'openEMS': 'PROCESS FIXTURE'}, cells=1000, mesh_lines=[11, 11, 11])
name = ('base' if args.scale == 1 else 'fine')+'-'+str(args.port)
Path(args.model).with_name(name+'.json').write_text(json.dumps(out))
print('ICSTUDIO_EM:'+json.dumps(dict(state='complete')), flush=True)
