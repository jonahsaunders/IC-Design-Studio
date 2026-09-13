"""Structured, conservative adapters for digital engine evidence."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path


def diagnostics(text, sources):
    rows=[]; known={f['path'] for f in sources}
    for line in text.splitlines():
        match=re.search(r'(?:%?(Error|Warning)(?:-[A-Z0-9_]+)?:\s*)?(?:\./)?([A-Za-z0-9_./ -]+\.(?:sv|v|vh|svh)):(\d+)(?::\d+)?:?\s*(.*)',line)
        if not match:continue
        path=match[2].strip()
        path=next((p for p in known if path==p or path.endswith('/'+p)),None)
        if path:rows.append({'path':path,'line':int(match[3]),'severity':match[1] or 'Diagnostic','message':match[4][:1000]})
    return rows[:2000]


def source_locations(attributes, files):
    result=[]
    for source in attributes.get('src','').split('|'):
        match=re.match(r'(.*?):(\d+)(?:\.\d+)?-',source)
        if match:
            path=next((f['path'] for f in files if match[1].removeprefix('./')==f['path'] or match[1].endswith('/'+f['path'])),None)
            if path:result.append({'path':path,'line':int(match[2])})
    return result


def netlist_index(data, files):
    out=[]
    for module,m in data.get('modules',{}).items():
        if m.get('attributes',{}).get('blackbox') in ('1','00000000000000000000000000000001',1):continue
        for kind,items in (('cell',m.get('cells',{})),('net',m.get('netnames',{}))):
            for name,item in items.items():
                out.append({'module':module,'name':name,'kind':kind,'type':item.get('type',''),
                            'locations':source_locations(item.get('attributes',{}),files),
                            'connections':item.get('connections',{}),'bits':item.get('bits',[])})
                if len(out)>=100000:raise ValueError('The native netlist index supports at most 100,000 objects.')
    return out


def eqy_report(directory):
    root=Path(directory);partitions={}
    for file in sorted((root/'strategies').glob('*/*/status')):
        text=file.read_text().split();status=text[0] if text else 'ERROR'
        if status=='TIMEOUT':status='UNKNOWN'
        if status not in ('PASS','FAIL','UNKNOWN','ERROR'):status='ERROR'
        partitions.setdefault(file.parent.parent.name,[]).append({'strategy':file.parent.name,'status':status})
    rows=[]
    for name,strategies in partitions.items():
        states={s['status'] for s in strategies}
        status='FAIL' if 'FAIL' in states else 'PASS' if 'PASS' in states else 'UNKNOWN' if 'UNKNOWN' in states else 'ERROR'
        rows.append({'partition':name,'status':status,'strategies':strategies})
    if rows and (root/'PASS').is_file() and all(p['status']=='PASS' for p in rows):status='PASS'
    elif any(p['status']=='FAIL' for p in rows):status='FAIL'
    elif any(p['status']=='UNKNOWN' for p in rows):status='UNKNOWN'
    else:status='ERROR'
    traces=[p.relative_to(root).as_posix() for p in root.rglob('*.vcd') if p.is_file()]
    return {'status':status,'partitions':rows,'counterexamples':traces,
            'scope':'Sequential equivalence under the captured EQY strategy and initialization assumptions.'}


def timing_report(directory):
    root=Path(directory); rows=[]
    for line in (root/'timing_paths.tsv').read_text().splitlines():
        fields=line.split('\t')
        if len(fields)!=5:raise ValueError('OpenSTA returned an invalid timing path record.')
        kind,start,end,slack,pins=fields;value=float(slack)
        if not math.isfinite(value):raise ValueError('Non-finite timing slack.')
        rows.append({'check':kind,'startpoint':start,'endpoint':end,'slack_ns':value,'pins':pins.split('|') if pins else []})
    checks=(root/'timing_checks.txt').read_text();units=(root/'timing_units.txt').read_text()
    # A design with no paths or missing clocks is never a successful timing qualification.
    unconstrained=bool(re.search(r'no clock|unconstrained|no input delay|no output delay|missing.*(?:input_delay|output_delay|clock)',checks,re.I))
    summary={}
    for kind in ('setup','hold'):
        paths=[p for p in rows if p['check']==kind]
        summary[kind+'_worst_slack_ns']=min((p['slack_ns'] for p in paths),default=None)
    status='INCOMPLETE' if unconstrained or not rows else 'FAIL' if any(p['slack_ns']<0 for p in rows) else 'PASS'
    return {'status':status,'paths':rows,'summary':summary,'unconstrained':unconstrained,
            'checks':checks,'units':units,'scope':'Reported paths for the selected library corner; inspect constraints and path coverage.'}


def coverage_report(path):
    """Read Verilator's LCOV export without treating code coverage as a proof."""
    files={};current=None
    for line in Path(path).read_text().splitlines():
        if line.startswith('SF:'):current=line[3:];files.setdefault(current,{})
        elif line.startswith('DA:') and current:
            number,hits,*_=line[3:].split(',');files[current][int(number)]=int(hits)
    points=sum(len(rows) for rows in files.values());hit=sum(v>0 for rows in files.values() for v in rows.values())
    return {'kind':'line','covered':hit,'total':points,'percent':100*hit/points if points else None,
            'files':[{'path':p,'lines':[{'line':n,'hits':v} for n,v in rows.items()]} for p,rows in files.items()],
            'scope':'Verilator instrumented line coverage; it does not establish functional completeness.'}


def compare_results(rows):
    out=[]
    for row in rows:
        data=(row.get('result') or {}).get('digital_result',{})
        values=data.get('statistics',{});timing=data.get('timing',{}).get('summary',{})
        out.append({'run':row['id'],'name':row['name'],'stage':data.get('stage',row['job']['settings']['stage']),
                    'state':row['state'],'verdict':data.get('verdict',''), 'source_hash':data.get('source_hash'),
                    'platform':data.get('platform'), 'area_um2':values.get('area_um2'),
                    'power_w':data.get('power',{}).get('total_w'),
                    'cells':values.get('cells'),**timing,'elapsed_s':row.get('elapsed')})
    baselines={}
    for item in out:
        key=(item['stage'],json.dumps(item['platform'],sort_keys=True))
        if key not in baselines and item['state']=='Complete':baselines[key]=item
        baseline=baselines.get(key)
        if not baseline:continue
        item['baseline']=baseline['name']
        for metric in ('area_um2','cells','setup_worst_slack_ns','hold_worst_slack_ns','power_w'):
            if isinstance(item.get(metric),(int,float)) and isinstance(baseline.get(metric),(int,float)):
                item[metric+'_delta']=item[metric]-baseline[metric]
    return out


def power_report(path):
    # OpenSTA report_power uses watts independently of report_units.
    match=re.search(r'^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)',Path(path).read_text(),re.M)
    data={'scope':'OpenSTA default propagated activity, not workload-annotated power. Values in watts.'}
    if match:
        values=[float(v) for v in match.groups()]
        if all(math.isfinite(v) and v>=0 for v in values):data.update(zip(('internal_w','switching_w','leakage_w','total_w'),values))
    return data
