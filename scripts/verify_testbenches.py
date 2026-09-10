"""Actual ngspice checks for each supported saved-bench analysis."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import example,device,uid,save_project,validate,clone
from icstudio.testbenches import create,simulate

def main():
    a=argparse.ArgumentParser();a.add_argument('--ngspice',required=True);a.add_argument('--output',required=True);args=a.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    p=example('empty');c={'id':uid(),'name':'divider','ports':['A','Y','G'],'shapes':[],'devices':[device('R','R1',value='10k',nets={'p':'A','n':'Y'}),device('R','R2',value='10k',nets={'p':'Y','n':'G'})]};p['cells'].append(c);b=p['cells'][0];b['devices']=[device('V','V1',value='1.8',nets={'p':'input','n':'0'}),device('X','XDUT',cell=c['id'],nets={'A':'input','Y':'out','G':'0'})];b['devices'][0]['source']['ac']='1'
    for key in ('wires','labels','junctions'):b.pop(key,None)
    rows=[]
    for typ,analysis,expected in [('op',{},.9),('tran',{'step':'10n','stop':'1u'},.9),('ac',{'start':'10','end':'1meg','points':10},.5),('dc',{'source':'V1','dc_start':'1','dc_stop':'-1','dc_step':'-.1'},-.5)]:
        q=clone(p);t=create(q,b['id'],typ);t['analysis']={'type':typ,'corner':'nominal','temperature':27,**analysis};t['probes']=['out'];t['measurements']=[{'name':'output','kind':'voltage','node':'out','min':expected-1e-8,'max':expected+1e-8}];q['testbenches']=[t];validate(q);save_project(q,out/(typ+'.icproj'));r=simulate(q,t,args.ngspice,out/typ);rows.append({'analysis':typ,'status':r['measurements']['status'],'expected_voltage':expected,'measured_voltage':r['measurements']['measurements'][0].get('value'),'samples':len(r['x'])});(out/'report.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(rows,indent=2));return 0 if all(r['status']=='passed' for r in rows) else 1

if __name__=='__main__':raise SystemExit(main())
