"""Proposed source-bound voltage screen; never grants complete-envelope acceptance.

Input is a JSON list of records with model, vds, vgs, vbs, temperature_c.
No simulator is run. Exact model names and signed source-relative volts required.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]/'docs/qualification/sky130-mos-voltage-v1'
CONTRACT_SHA = 'f95def326e8cc74b297958e668b56d0976276c20164b498f360e7ab82c9ef2d3'
LOCK_SHA = '7a57cc833225664e09665a43880b410de9ce70d65e80d1f268b74e3967f0a0f1'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def load_contract(root=ROOT):
    root=Path(root)
    if digest(root/'gap-acceptance-table.json') != CONTRACT_SHA:
        raise ValueError('Changed reviewed model contract')
    if digest(root/'source-lock.json') != LOCK_SHA:
        raise ValueError('Changed source lock')
    lock=json.loads((root/'source-lock.json').read_bytes())
    for name, identity in lock['files'].items():
        if digest(root/'sources'/name) != identity['sha256']:
            raise ValueError('Changed public source: '+name)
    for identity in lock['model_nominal_examples']:
        if digest(root/identity['file']) != identity['sha256']:
            raise ValueError('Changed nominal parameter example')
    contract=json.loads((root/'gap-acceptance-table.json').read_bytes())
    return {row['model']:row for row in contract['models']}

def number(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('Coordinates and temperature must be finite numeric values, excluding booleans')
    return value

class VoltageScreen:
    def __init__(self, root=ROOT):
        self.rows=load_contract(root)

    def check(self, point):
        if set(point) != {'model','vds','vgs','vbs','temperature_c'}:
            raise ValueError('Require exact model, vds, vgs, vbs, temperature_c fields; extra terminal or assurance fields are not accepted')
        model=point['model']
        if not isinstance(model,str) or model not in self.rows:
            raise ValueError('Unknown exact model name; no aliases or name-based inference')
        coords={k:number(point[k]) for k in ('vds','vgs','vbs')}
        temp=number(point['temperature_c'])
        row=self.rows[model]
        result={'model':model,'coordinates_v':coords,'temperature_c':temp,
            'three_axis_status':'BLOCKED','violations':[],
            'temperature_validity_status':'NOT_ESTABLISHED',
            'temperature_is_historical_sample_point':temp in (0,27,85) and bool(row['existing_sampled_acceptance'].get('record')),
            'rated_operating_bounds_status':'NOT_ESTABLISHED','full_operating_envelope_status':'NOT_ESTABLISHED',
            'qualified':False,'source_anchor':row['source_anchor'],
            'remaining_gaps':row['remaining_acceptance_gaps'],'blocked_reasons':row['blocked_reasons']}
        bounds=row['model_voltage_limits_v']
        if bounds is None:
            return result
        bounds={axis:list(pair) for axis,pair in bounds.items()}
        result['drain_predicate']='ordinary_or_conducting_limit'
        if row['off_state_vds_v'] is not None and coords['vgs']==0:
            bounds['vds']=row['off_state_vds_v']
            result['drain_predicate']='exact_zero_gate_extended_drain_limit'
        for axis,value in coords.items():
            lower,upper=bounds[axis]
            if not lower <= value <= upper:
                result['violations'].append({'axis':axis,'value_v':value,'allowed_v':[lower,upper]})
        result['three_axis_status']='OUTSIDE_DOCUMENTED_LIMITS' if result['violations'] else 'WITHIN_DOCUMENTED_LIMITS'
        result['applied_bounds_v']=bounds
        result['soa_status']='SOURCE_REQUIRED_NOT_ESTABLISHED' if row['soa_source_required'] else 'NOT_ASSESSED'
        # Even an in-bounds point is a numerical screen only. The isolated 20 V
        # model additionally has an unbounded fifth terminal in the cited text.
        result['all_terminal_voltage_status']='NOT_ESTABLISHED' if model.endswith('nfet_20v0_iso') else 'THREE_AXIS_SCREEN_ONLY'
        return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    args=parser.parse_args()
    points=json.loads(args.input.read_bytes())
    if not isinstance(points,list) or not points:
        raise ValueError('Expected a non-empty point list')
    screen=VoltageScreen()
    results=[screen.check(p) for p in points]
    print(json.dumps({'schema':1,'scope':'static three-axis source screen only','qualified':False,'results':results},indent=2,allow_nan=False))
    # Exit 0 concerns this screen only; unresolved rating/SOA/temperature remains
    # explicit in every result. An out-of-range or ambiguous point exits 2.
    return 0 if all(r['three_axis_status']=='WITHIN_DOCUMENTED_LIMITS' for r in results) else 2

if __name__=='__main__': raise SystemExit(main())
