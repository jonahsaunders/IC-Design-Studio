"""Independent raw readback for the finite IHP tap linked pilot.

Does not trust producer numerical summaries or its extracted R projection.
Numerical agreement cannot distinguish the identical public tap models; model
identity and TIE/body roles are independently required in the native text.
"""
import argparse
import cmath
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

REL=1e-6
ABS=1e-10

def require(ok,msg):
    if not ok:raise ValueError(msg)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def raw(path):
    lines=Path(path).read_text().splitlines();v=lines.index('Variables:');start=lines.index('Values:')
    header='\n'.join(line.rstrip() for line in lines[:v]);n=int(re.search(r'^No\. Variables:\s*(\d+)$',header,re.M)[1]);count=int(re.search(r'^No\. Points:\s*(\d+)$',header,re.M)[1])
    require(1<n<30 and 1<count<100,'Unexpected raw size.')
    flags=[line.split(':',1)[1].strip() for line in lines[:v] if line.startswith('Flags:')]
    require(flags in (['real'],['complex']),'Unknown or duplicate raw flags.')
    complex_data=flags==['complex']
    names=[]
    for i,line in enumerate(lines[v+1:start]):
        fields=line.split();require((len(fields)==3 or (complex_data and i==0 and fields==['0','frequency','frequency','grid=3'])) and fields[0]==str(i),'Raw variable indexing changed.');names.append(fields[1])
    require(len(names)==n and len(set(names))==n,'Raw variable cardinality.')
    fields=[s.split() for s in lines[start+1:] if s.strip()];require(len(fields)==n*count,'Incomplete raw payload.')
    rows=[]
    for i in range(count):
        row=[]
        for j in range(n):
            part=fields[i*n+j];require(len(part)==(2 if j==0 else 1),'Raw value field cardinality.')
            if j==0:require(part[0]==str(i),'Raw point index changed.')
            token=part[-1];pair=token.split(',');require(len(pair)==(2 if complex_data else 1),'Raw numeric encoding changed.')
            number=complex(*map(float,pair)) if complex_data else float(token)
            require(math.isfinite(number.real) and math.isfinite(number.imag),'Nonfinite raw number.');row.append(number)
        rows.append(row)
    return names,rows,complex_data

def compare_raw(path,analysis,resistance,expect_fault=False):
    names,rows,iscomplex=raw(path);require(iscomplex==(analysis=='ac'),'Wrong plot kind.')
    require(all(n in names for n in ('v(input)','v(output)','i(vdrive)')),'Missing driven voltage/current.')
    ii,oo,ci=[names.index(n) for n in ('v(input)','v(output)','i(vdrive)')]
    grid=[-.01+i*.001 for i in range(21)] if analysis=='dc' else [100*10**(i/5) for i in range(26)]
    require(len(rows)==len(grid),'Incomplete raw sweep.');worst=0.;kcl=0.
    for row,x in zip(rows,grid):
        actual_x=row[0].real;require(math.isclose(actual_x,x,rel_tol=1e-9,abs_tol=1e-12),'Wrong raw coordinates.')
        voltage=x if analysis=='dc' else 1.
        require(abs(row[ii]-voltage)<=ABS+REL*abs(voltage),'Wrong applied stimulus.')
        load=1/1000+(2j*math.pi*x*1e-12 if analysis=='ac' else 0)
        expected=voltage/(1+resistance*load)
        error=abs(row[oo]-expected)/(ABS+REL*abs(expected));worst=max(worst,error)
        if not expect_fault:
            kcl=max(kcl,abs(row[ci]+row[oo]*load)/(1e-13+REL*abs(row[ci])))
    require(worst>1 if expect_fault else worst<=1,'Electrical fault not distinguished.' if expect_fault else 'Raw analytical response mismatch.')
    if not expect_fault:require(kcl<=1,'Raw current conservation failed.')
    return {'points':len(rows),'maximum_normalized_response':worst,'maximum_normalized_kcl':None if expect_fault else kcl}

def number(token):
    m=re.fullmatch(r'([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)(p|k|meg)?',token)
    require(m is not None,'Unreviewed numeric deck token.')
    value=float(m[1])*{None:1,'p':1e-12,'k':1000,'meg':1e6}[m[2]]
    require(math.isfinite(value),'Nonfinite deck value.');return value

def deck_controls(text,analysis):
    rows=[l.split() for l in text.splitlines() if l.strip() and not l.lstrip().startswith('*')]
    def one(name):
        found=[r for r in rows if r[0].lower()==name.lower()];require(len(found)==1,'Missing or duplicate deck control: '+name);return found[0]
    require(one('RL')[:3]==['RL','output','0'] and len(one('RL'))==4 and number(one('RL')[3])==1000,'Load resistance changed.')
    require(one('CL')[:3]==['CL','output','0'] and len(one('CL'))==4 and number(one('CL')[3])==1e-12,'Load capacitance changed.')
    v=one('VDRIVE');require(len(v)==7 and v[:3]==['VDRIVE','input','0'] and v[3].upper()=='DC' and float(v[4])==.0005 and v[5].upper()=='AC' and float(v[6])==1,'Source stimulus changed.')
    require(one('.temp')==['.temp','27'],'Temperature changed.')
    if analysis=='dc':
        dc=one('.dc');require(dc[:2]==['.dc','VDRIVE'] and list(map(float,dc[2:]))==[-.01,.01,.001],'DC analysis changed.')
    else:
        ac=one('.ac');require(len(ac)==5 and ac[:2]==['.ac','dec'] and list(map(number,ac[2:]))==[5,100,1e7],'AC analysis changed.')
    active=[r for r in rows if r[0][0].lower() in 'rvclxd' and not r[0].startswith('.')]
    require(len(active)==4,'Unexpected extra electrical instance.')

def audit(root):
    root=Path(root).resolve();report=json.loads((root/'qualification.json').read_text());require(report['status']=='PASS','Producer did not pass.')
    files=report['files'];actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=root/'qualification.json'};require(actual==set(files),'Evidence inventory cardinality differs.')
    for name,h in files.items():
        p=(root/name).resolve();require(p.is_relative_to(root) and not (root/name).is_symlink() and sha(p)==h,'Evidence identity changed: '+name)
    selection={(model,rot) for model in ('ntap1','ptap1') for rot in (0,90)};require(len(report['cases'])==4 and {(r['model'],r['rotation']) for r in report['cases']}==selection,'Incomplete linked cases.')
    r=1/(Decimal('4e-12')/Decimal('9.8e-10')+Decimal('8e-6')/Decimal('9.8e-4'));resistance=float(r);results=[]
    for model,rot in sorted(selection):
        name=f'{model}-2000-2000-{rot}';folder=root/name;well='well' if model=='ntap1' else 'sub!'
        native=(folder/'native.cir').read_text();records=[l.split() for l in native.splitlines() if l.strip() and not l.lstrip().startswith('*')]
        require(len(records)==3 and records[0][0].lower()=='.subckt' and records[0][1]=='coupon' and set(records[0][2:])=={'TIE',well} and len(records[0])==4,'Native header changed.')
        require(records[1]==['R$1','TIE',well,model,'A=4p','P=8u'],'Exact native A/P/model/body identity changed.')
        require([x.lower() for x in records[2]]==['.ends','coupon'],'Native ending changed.')
        row={'name':name,'analyses':{},'faults':{}}
        for analysis in ('dc','ac'):
            row['analyses'][analysis]={}
            for route in ('application','extracted','independent'):
                d=folder/analysis/route;deck=(d/'input.cir').read_text();deck_controls(deck,analysis);matches=[l.split() for l in deck.splitlines() if l and not l.startswith('*') and re.match(r'(?i)^(?:x|r)_?(?:dut|tap|ref)\s',l)]
                require(len(matches)==1,'Electrical instance missing/ambiguous.');tokens=matches[0];require(tokens[1:3]==['input','output'],'Electrical terminal projection changed.')
                if route!='independent':require(tokens[3]==model,'Electrical model identity changed.')
                else:require(tokens[0]=='RREF' and math.isclose(float(tokens[3]),resistance,rel_tol=1e-14),'Independent literal R changed.')
                row['analyses'][analysis][route]=compare_raw(d/('result.raw' if route=='application' else 'deck.raw'),analysis,resistance)
        for fault in ('area','perimeter','disconnected'):
            d=folder/fault;deck_controls((d/'input.cir').read_text(),'dc');tokens=next((l.split() for l in (d/'input.cir').read_text().splitlines() if l.startswith('XTAP ')),None)
            require(tokens is not None and tokens[2:4]==['output',model],'Fault model/terminal binding changed.')
            expected_r=1/(float(Decimal('4e-12')*(Decimal('1.2') if fault=='area' else 1))/9.8e-10+float(Decimal('8e-6')*(Decimal('1.2') if fault=='perimeter' else 1))/9.8e-4)
            require(len(tokens)==5 and tokens[4].startswith('r=') and math.isclose(float(tokens[4][2:]),expected_r,rel_tol=1e-14),'Fault geometry projection changed.')
            require(tokens[1]==('0' if fault=='disconnected' else 'input'),'Fault stimulus topology changed.')
            row['faults'][fault]=compare_raw(d/'deck.raw','dc',resistance,expect_fault=True)
            if fault!='disconnected':
                row['faults'][fault]['fault_equation']=compare_raw(d/'deck.raw','dc',expected_r)
            else:
                names,values,_=raw(d/'deck.raw');oi=names.index('v(output)');ci=names.index('i(vdrive)')
                require(all(abs(v[oi])<=ABS and abs(v[ci])<=1e-13 for v in values),'Disconnected control is not the declared zero response.')
        results.append(row)
    return {'schema':1,'status':'PASS_FINITE_LINKED_RAW_AUDIT','qualified':False,'installed_acceptance':False,'chunk_complete':False,'physical_scope':'The separately retained native physical report and original faults remain required; this auditor independently checks native tap text and all electrical raw points.','cases':results,'positive_raw_files':24,'fault_raw_files':12,'positive_points':564,'fault_points':252,'resistance_ohm':resistance,'producer_report_sha256':sha(root/'qualification.json')}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('--output',required=True);a=p.parse_args();result=audit(a.root);Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
