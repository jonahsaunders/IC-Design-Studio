"""Compare corrected model calls with untouched unit models, including M=3."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from scripts.qualify_resistor_families import vectors,probes
from scripts.qualify_standard_mos import write


def check(actual,original,target='sky130A'):
    a=vectors(actual,target,True);b=vectors(original,target,True);errors={}
    for row in probes(target):
        key='v'+row['tag'];unit=key[:-1]+'1';m=row['m']
        errors[key]=max(abs(x-m*y)/(1e-15+1e-6*abs(m*y)) for x,y in zip(a[key],b[unit]))
    if any(v>1 for v in errors.values()):raise ValueError('Corrected resistor differs from original parallel unit devices: '+str(errors))
    return dict(vectors=len(errors),maximum_normalized_error=max(errors.values()))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--original-batch',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a new reference audit output.')
    batch=json.loads((a.batch/'qualification.json').read_bytes());old=json.loads((a.original_batch/'qualification.json').read_bytes())
    if batch['status']!='PASS' or not batch['implementation_unchanged'] or not old['implementation_unchanged']:raise ValueError('Completed unchanged-source runs are required.')
    rows={r['name']:r for r in old['cases']};records=[]
    for row in batch['cases']:
        if row['target']!='sky130A':raise ValueError('This audit requires SKY130-only results.')
        previous=rows[row['name']]
        if previous['comparison']['status']!='PASS':raise ValueError('Missing original independent unit-model agreement.')
        for side in ('application','independent'):
            first=a.batch/row['name']/side/'response.json';second=a.original_batch/row['name']/'independent/response.json'
            records.append(dict(case=row['name'],side=side,current_sha256=file_digest(first),original_sha256=file_digest(second),
                **check(json.loads(first.read_bytes()),json.loads(second.read_bytes()))))
    record=dict(status='PASS',checker_sha256=file_digest(__file__),batch_sha256=file_digest(a.batch/'qualification.json'),original_batch_sha256=file_digest(a.original_batch/'qualification.json'),cases=records,
        scope='Corrected M=1 agrees with untouched unit models; corrected M=3 agrees with three parallel untouched unit responses at each tested condition. Statistical mismatch, noise and full envelopes are not established.')
    write(a.output,record);print('PASS',len(records),'responses',sum(r['vectors'] for r in records),'vectors')


if __name__=='__main__':main()
