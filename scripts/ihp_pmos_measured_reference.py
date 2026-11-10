"""Strict, finite manufacturer-measured reference. Never a calibration verdict."""
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/qualification/ihp-pmos-measured-reference-v1/measurement.mdm'
DATA_SHA = 'bb12389d5789b8035d388e00253b7d65e5d95d6fdf95d1ee147859b564dd2e47'
GATES = tuple(Decimal(x) for x in ('-.446', '-.672', '-.898', '-1.124', '-1.35'))
HEADER = {'TYPE':'-1', 'TEMP':'27.0000', 'IS_TNOM':'1.00000', 'MAIN.W':'10.00u', 'MAIN.L':'10.00u', 'MAIN.AD':'3.400p', 'MAIN.AS':'3.400p', 'MAIN.PD':'20.68u', 'MAIN.PS':'20.68u', 'MAIN.NF':'1.000', 'MAIN.M':'1', 'MAIN.NRD':'0.000', 'MAIN.NRS':'0.000', 'MODULE':'S549', 'PIN_D':'12', 'PIN_G':'9', 'PIN_S':'10', 'PIN_B':'11'}
ROUTES = ('nominal', 'multiplicity-2', 'width-5um', 'drain-source-swapped')

def require(ok, message):
    if not ok: raise ValueError(message)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def number(token):
    v = Decimal(token)
    require(v.is_finite(), 'Nonfinite value')
    return v

def parse(data, authenticate=True):
    require(isinstance(data, bytes), 'Raw bytes required')
    if authenticate: require(hashlib.sha256(data).hexdigest() == DATA_SHA, 'Measurement identity changed')
    s = data.decode('ascii')
    require(s.count('BEGIN_HEADER') == s.count('END_HEADER') == 1, 'Header cardinality')
    header = s.split('BEGIN_HEADER\n', 1)[1].split('END_HEADER', 1)[0]
    vals = re.findall(r'^\s+(\S+)\s+"([^"\n]*)"\s*$', header, re.M)
    require(len(vals) == len(dict(vals)), 'Duplicate metadata')
    values = {k:v.strip() for k,v in vals}
    for k,v in HEADER.items(): require(values.get(k) == v, 'Metadata mismatch: '+k)
    require(s.count('BEGIN_DB') == s.count('END_DB') == 5, 'Database cardinality')
    blocks = re.findall(r'BEGIN_DB\n(.*?)END_DB', s, re.S)
    rows = []
    for gi, block in enumerate(blocks):
        variables = re.findall(r'^\s*ICCAP_VAR\s+(\w+)\s+(\S+)\s*$', block, re.M)
        require(len(variables)==3 and len(dict(variables))==3, 'Variable cardinality')
        v = {k:number(x) for k,x in variables}
        require(v == {'vg':GATES[gi], 'vb':Decimal(0), 'vs':Decimal(0)}, 'Bias metadata mismatch')
        require(len(re.findall(r'^\s*#vd\s+id\s+ig\s+ib\s+is\s*$', block, re.M))==1, 'Output columns')
        lines = [l.split() for l in block.splitlines() if l.strip() and not l.lstrip().startswith(('ICCAP_VAR','#'))]
        require(len(lines)==28, 'Drain cardinality')
        for di, fields in enumerate(lines):
            require(len(fields)==5, 'Current column count')
            a = [number(x) for x in fields]
            require(a[0] == -Decimal(di)/20, 'Missing/duplicate/reordered drain point')
            rows.append({'vg':str(GATES[gi]), 'vd':str(a[0]), 'currents':dict(zip(('d','g','b','s'),map(str,a[1:])))})
    require(len(rows)==140, 'Point count')
    return rows

def residuals(measured, simulated):
    require(len(measured)==len(simulated)==140, 'Result count')
    result=[]
    for m,s in zip(measured,simulated):
        require(set(s)=={'d','g','s','b'}, 'Terminal set')
        r={}
        for terminal in ('d','g','s','b'):
            ref=float(m['currents'][terminal]); actual=float(s[terminal])
            require(math.isfinite(actual), 'Nonfinite simulated current')
            delta=actual-ref
            require(math.isfinite(delta), 'Nonfinite residual')
            require(not ref or math.isfinite(delta/abs(ref)), 'Nonfinite relative residual')
            r[terminal]={'measured_a':ref,'simulated_a':actual,'signed_residual_a':delta,'absolute_residual_a':abs(delta),'signed_relative_residual':delta/abs(ref) if ref else None}
        result.append({'vg':m['vg'],'vd':m['vd'],'terminals':r})
    return {'qualified':False,'independent_calibration':False,'measurement_residual_acceptance':None,'points':result}

def deck(nonce, route, gate):
    require(route in ROUTES, 'Unknown route')
    require(number(str(gate)) in GATES, 'Unknown gate')
    ports='s g d b' if route=='drain-source-swapped' else 'd g s b'
    width='5u' if route=='width-5um' else '10u'
    mult='2' if route=='multiplicity-2' else '1'
    return '\n'.join([f'* IHP-PMOS-measured-reference-v1 {nonce} {route} {gate}',
        '.lib "pdk/libs.tech/ngspice/models/cornerMOSlv.lib" mos_tt',
        '.option reltol=1e-8 abstol=1e-16 vntol=1e-13', '.option gminsteps=0 srcsteps=0', '.temp 27',
        'VD d 0 0',f'VG g 0 {gate}','VS s 0 0','VB b 0 0',
        f'XDUT {ports} sg13_lv_pmos w={width} l=10u ng=1 m={mult} as=3.4p ad=3.4p ps=20.68u pd=20.68u rfmode=0 mm_ok=0',
        '.save i(vd) i(vg) i(vs) i(vb)', '.dc VD 0 -1.35 -0.05','.end',''])
