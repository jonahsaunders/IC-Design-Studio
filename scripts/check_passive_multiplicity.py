"""Check physical parallel scaling independently of manual-deck agreement."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from scripts.qualify_standard_passives import currents,points
from scripts.qualify_standard_mos import write


def check(data,target):
    vectors=currents(data,target);errors={}
    for row in points(target):
        if row['copies']!=3:continue
        key='v'+row['tag'];single=key[:-1]+'1'
        errors[key]=max(abs(a-3*b)/(1e-15+1e-6*abs(3*b)) for a,b in zip(vectors[key],vectors[single]))
    if not errors or any(v>1 for v in errors.values()):raise ValueError('Parallel passive admittance does not scale by three: '+str(errors))
    return {'parallel_pairs':len(errors),'maximum_normalized_error':max(errors.values())}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--batch',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    batch=json.loads((a.batch/'qualification.json').read_bytes())
    if batch['status']!='PASS' or not batch['implementation_unchanged']:raise ValueError('A completed unchanged-source passive batch is required.')
    if a.output.exists():raise ValueError('Choose a new audit output.')
    report={'schema':1,'status':'PASS','qualification_sha256':file_digest(a.batch/'qualification.json'),
        'checker_sha256':file_digest(__file__),'scope':'Three isolated parallel copies must carry three times the complex AC current of one copy at the same geometry and voltage. This is a model-integration invariant, not a measured-silicon accuracy claim.','cases':[]}
    for row in batch['cases']:
        for side in ('application','independent'):
            path=a.batch/row['name']/side/'comparison-result.json'
            data=json.loads(path.read_bytes());result=check(data,row['target'])
            report['cases'].append(dict(case=row['name'],side=side,result_sha256=file_digest(path),**result))
    write(a.output,report);print(json.dumps({'status':'PASS','responses':len(report['cases']),
        'parallel_pairs':sum(r['parallel_pairs'] for r in report['cases'])}))


if __name__=='__main__':main()
