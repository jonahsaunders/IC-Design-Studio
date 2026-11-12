"""Match every native antenna marker to an exact rectangular fixture oracle.

Run after sky130_antenna_controls.py and the staged KLayout deck. This validates
the native results on these fixtures, not full PDK coverage. Rational expected
ratios decide the pass/fail side without a tolerance. Numeric marker properties
allow only the report format's twelve-significant-digit serialization error.
"""
import argparse
from collections import Counter
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

STAGES=('poly','licon','li','mcon','met1','via','met2','via2','met3','via3','met4','via4','met5')


def require(value, message):
    if not value:
        raise ValueError('SKY130 antenna controls: '+message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(expectations, report, metrics):
    rows=expectations['rows']
    require(len(rows)==178 and [r['id'] for r in rows]==list(range(178)), 'incomplete control inventory')
    require(metrics['status']=='all-stages-executed' and metrics['qualified'] is False and
            [r['stage'] for r in metrics['stages']]==list(STAGES), 'missing stage execution')
    expected=set()
    for row in rows:
        stage=row['stage']
        require(stage in STAGES and row['limit']>0, 'unknown stage')
        exempt=row['protection']=='short' and stage!='poly' and row['variant']=='ordinary'
        ratio=Fraction(row['etched_area_um2'])/Fraction(row['gate_area_um2'])-Fraction(row['diode_credit'])
        violation=not exempt and ratio>row['limit']
        require(ratio==Fraction(row['expected_egar']) and violation==row['expected_violation'], 'inconsistent rational oracle')
        if violation:expected.add((row['id'],stage))
    seen=set(); counts=Counter()
    for item in ET.parse(report).findall('./items/item'):
        cat=item.findtext('category','').strip("'")
        require(cat.startswith('ar_q.') and cat.endswith('.1'), 'unknown marker category')
        stage=cat[5:-2]; require(stage in STAGES, 'unknown reported stage')
        values=[v.text or '' for v in item.findall('./values/value')]
        polygon=[v for v in values if v.startswith('polygon: ')]
        require(len(polygon)==1, 'missing or ambiguous gate polygon')
        coords=[(Decimal(x)*1000,Decimal(y)*1000) for x,y in re.findall(r'([-\d.]+),([-\d.]+)',polygon[0])]
        require(len(coords)==4, 'unexpected marker shape')
        xmin=min(x for x,y in coords); xmax=max(x for x,y in coords)
        ymin=min(y for x,y in coords); ymax=max(y for x,y in coords)
        idx=int(xmin//100000)
        require(0<=idx<len(rows), 'marker outside fixture inventory')
        row=rows[idx]; key=(idx,stage)
        require([xmin,ymin,xmax,ymax]==row['gate_bbox_nm'], 'marker is not the declared gate')
        require(key in expected and key not in seen, 'unexpected or duplicate marker')
        props={m[1]:float(m[2]) for v in values if (m:=re.fullmatch(r'\[#(\w+)\] float: (.+)',v))}
        require(set(props)=={'gate_area','etch_area','diode_area','EGAR','limit'}, 'incomplete numerical evidence')
        wanted=dict(gate_area=float(Fraction(row['gate_area_um2'])),
                    etch_area=float(Fraction(row['etched_area_um2'])),
                    EGAR=float(Fraction(row['expected_egar'])),limit=row['limit'])
        connected_diode=row['variant']=='ordinary' and row['protection'] in ('diode','nwell-tap','two-diodes')
        wanted['diode_area']=.25 if connected_diode else 0.
        require(all(math.isfinite(props[k]) and math.isclose(props[k],v,rel_tol=5e-12,abs_tol=5e-12)
                    for k,v in wanted.items()), 'measured area, credit or ratio differs from rectangular oracle')
        seen.add(key); counts[stage]+=1
    require(seen==expected, 'a deliberate fault was missed')
    require(all(r['markers']==counts[r['stage']] for r in metrics['stages']), 'stage metrics differ from raw report')
    return dict(status='all-antenna-controls-match',qualified=False,coupons=len(rows),
                expected_faults=len(expected),observed_faults=len(seen),accepted_controls=len(rows)-len(expected),
                stages=len(STAGES),numeric_scope='Twelve-significant-digit report values; exact rational pass/fail oracle')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expectations',type=Path,required=True)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output.exists(), 'output already exists')
    oracle=json.loads(args.expectations.read_text(encoding='utf-8'))
    record=json.loads((args.run/'record.json').read_text(encoding='utf-8'))
    require(record['status']=='native-execution-complete' and oracle['gds_sha256']==record['gds_sha256']==sha(args.run/'input.gds'),
            'native run does not match the exact fixture GDS')
    for rel,digest in record['files'].items():
        path=(args.run/rel).resolve()
        require(path.is_relative_to(args.run.resolve()) and sha(path)==digest, 'raw native evidence changed')
    result=check(oracle,args.run/'report.lyrdb',json.loads((args.run/'metrics.json').read_text()))
    result.update(system=__import__('sys').platform,auditor_sha256=sha(__file__),
                  expectation_sha256=sha(args.expectations),run_record_sha256=sha(args.run/'record.json'))
    args.output.write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__=='__main__':
    main()
