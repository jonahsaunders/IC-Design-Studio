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
                            'connections':item.get('connections',{}),'bits':item.get('bits',[]),
                            'port_directions':item.get('port_directions',{}),
                            'mapping':'compiler source' if item.get('attributes',{}).get('src') else 'unmapped'})
                if len(out)>=100000:raise ValueError('The native netlist index supports at most 100,000 objects.')
    return out


def eqy_report(directory):
    root=Path(directory);partitions={}
    for file in sorted((root/'strategies').glob('*/*/status')):
        text=file.read_text().strip();match=re.fullmatch(r'(PASS|FAIL|UNKNOWN|ERROR|TIMEOUT)( \(cached\))?',text)
        status=match[1] if match else 'ERROR';cached=bool(match and match[2])
        if status=='TIMEOUT':status='UNKNOWN'
        entry={'strategy':file.parent.name,'status':status}
        if cached:entry['cached']=True
        partitions.setdefault(file.parent.parent.name,[]).append(entry)
    rows=[]
    for name,strategies in partitions.items():
        states={s['status'] for s in strategies}
        actual={s['status'] for s in strategies if not s.get('cached')}
        status='FAIL' if 'FAIL' in states else 'PASS' if 'PASS' in actual else 'UNKNOWN' if 'UNKNOWN' in actual else 'ERROR'
        rows.append({'partition':name,'status':status,'strategies':strategies})
    if rows and (root/'PASS').is_file() and all(p['status']=='PASS' for p in rows):status='PASS'
    elif any(p['status']=='FAIL' for p in rows):status='FAIL'
    elif any(p['status']=='UNKNOWN' for p in rows):status='UNKNOWN'
    else:status='ERROR'
    traces=[p.relative_to(root).as_posix() for p in root.rglob('*.vcd') if p.is_file()]
    return {'status':status,'partitions':rows,'counterexamples':traces,
            'scope':'Sequential equivalence under the captured EQY strategy and initialization assumptions.'}


def timing_report(directory, *, require_parasitics=False):
    root=Path(directory); rows=[]; incomplete=[]

    def read(name):
        path=root/name
        if not path.is_file():
            incomplete.append('Missing timing evidence: '+name)
            return ''
        text=path.read_text()
        if re.search(r'^\s*(?:Error|Fatal)(?:\s|:)',text,re.I|re.M):
            incomplete.append('Engine error in '+name+'; inspect the retained report.')
        return text

    annotation=None
    if require_parasitics:
        diagnostics=read('timing_load.txt')
        if re.search(r'^\s*(?:Warning|Error|Fatal)(?:\s|:)',diagnostics,re.I|re.M):
            incomplete.append('Unresolved netlist, library, constraint or parasitic load diagnostics; inspect timing_load.txt.')
        text=read('parasitic_annotation.txt')
        disconnected=read('disconnected_outputs.txt').splitlines()
        match=re.fullmatch(r'Found (\d+) unannotated drivers\.\n(.*?)Found (\d+) partially unannotated drivers\.\n(.*)',text,re.S)
        # Open outputs of clock-load cells have no interconnect to annotate.
        # The engine must prove disconnection; a cell name is never an exemption.
        if match:
            unannotated=[s.strip() for s in match[2].splitlines() if s.strip()]
            partial=[s.strip() for s in match[4].splitlines() if s.strip()]
            valid=(len(unannotated)==int(match[1]) and len(partial)==int(match[3])
                   and len(set(unannotated))==len(unannotated) and len(set(partial))==len(partial)
                   and len(set(disconnected))==len(disconnected) and all(disconnected))
            missing=sorted(set(unannotated)-set(disconnected))
            annotation=dict(unannotated_drivers=unannotated,partially_unannotated_drivers=partial,
                            disconnected_outputs=disconnected,connected_unannotated_drivers=missing)
            if not valid:incomplete.append('Invalid parasitic annotation evidence; inspect parasitic_annotation.txt.')
            elif missing or partial:incomplete.append('Missing extracted parasitics on connected drivers; inspect parasitic_annotation.txt.')
        else:incomplete.append('Missing or invalid parasitic annotation evidence; inspect parasitic_annotation.txt.')
    for line in read('timing_paths.tsv').splitlines():
        fields=line.split('\t')
        if len(fields)!=5:raise ValueError('OpenSTA returned an invalid timing path record.')
        kind,start,end,slack,pins=fields;value=float(slack)
        if kind not in ('setup','hold') or not start.strip() or not end.strip():
            raise ValueError('OpenSTA returned an invalid timing path identity.')
        if not math.isfinite(value):raise ValueError('Non-finite timing slack.')
        rows.append({'check':kind,'startpoint':start,'endpoint':end,'slack_ns':value,'pins':pins.split('|') if pins else []})
    checks=read('timing_checks.txt');units=read('timing_units.txt')
    # The generated script requests ns. Do not label values from an edited SDC
    # or incompatible engine as nanoseconds without confirming its final units.
    time_units=re.findall(r'^\s*time\s+(\S+)\s*$',units,re.I|re.M)
    if time_units!=['1ns']:incomplete.append('Timing units must report time 1ns.')
    unconstrained=bool(re.search(r'no clock|unconstrained|no input delay|no output delay|missing.*(?:input_delay|output_delay|clock)',checks,re.I))
    if unconstrained:incomplete.append('Missing clock or I/O constraints; inspect timing_checks.txt.')
    elif checks.strip():
        # check_setup is silent when clean. Loops, multiple/generated clocks and
        # unfamiliar diagnostics also need review before a qualification passes.
        incomplete.append('Unresolved timing setup diagnostics; inspect timing_checks.txt.')
    summary={}
    for kind in ('setup','hold'):
        paths=[p for p in rows if p['check']==kind]
        if not paths:incomplete.append('No '+kind+' paths were reported.')
        summary[kind+'_worst_slack_ns']=min((p['slack_ns'] for p in paths),default=None)
        summary[kind+'_reported_violations']=sum(p['slack_ns'] < 0 for p in paths)
        name='timing_totals.txt' if kind=='setup' else 'timing_hold_totals.txt'
        label='max' if kind=='setup' else 'min'
        totals=read(name)
        match=re.fullmatch(r'\s*tns(?:\s+'+label+r')?\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*',totals,re.I)
        value=float(match[1]) if match else float('nan')
        if math.isfinite(value) and value<=0:summary[kind+'_total_negative_slack_ns']=value
        else:incomplete.append('Missing or invalid '+kind+' total negative slack: '+name)
    electrical=read('electrical_checks.txt')
    electrical_failed=bool(re.search(r'\bVIOLATED\b',electrical,re.I))
    electrical_incomplete=any('electrical_checks.txt' in reason for reason in incomplete)
    if re.search(r'^\s*Warning(?:\s|:)',electrical,re.I|re.M):
        incomplete.append('Unresolved electrical diagnostics; inspect electrical_checks.txt.')
        electrical_incomplete=True
    failed=(any(p['slack_ns']<0 for p in rows) or electrical_failed or
            any(summary.get(kind+'_total_negative_slack_ns',0)<0 for kind in ('setup','hold')))
    status='FAIL' if failed else 'INCOMPLETE' if incomplete else 'PASS'
    return {'status':status,'paths':rows,'summary':summary,'unconstrained':unconstrained,
            **({'parasitic_annotation':annotation} if require_parasitics else {}),
            'incomplete_reasons':incomplete,
            'checks':checks,'units':units,'electrical_checks':electrical,
            'electrical_status':'FAIL' if electrical_failed else 'Unavailable' if electrical_incomplete else 'No reported violations',
            'scope':'Reported paths for the selected library corner; inspect constraints and path coverage.'}


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
    from .digital_identity import comparison_context
    out=[]
    for row in rows:
        data=(row.get('result') or {}).get('digital_result',{})
        values=data.get('statistics',{});timing=data.get('timing',{}).get('summary',{})
        out.append({'run':row['id'],'name':row['name'],'stage':data.get('stage',row['job']['settings']['stage']),
                    'state':row['state'],'verdict':data.get('verdict',''), 'source_hash':data.get('source_hash'),
                    'platform':data.get('platform'), 'area_um2':values.get('area_um2'),
                    'power_w':data.get('power',{}).get('total_w'),
                    'cells':values.get('cells'),**timing,'elapsed_s':row.get('elapsed'),
                    'context':comparison_context(row.get('result') or {}),
                    'parasitics':data.get('timing',{}).get('parasitics','—')})
    baselines={}
    for item in out:
        key=json.dumps(item['context'],sort_keys=True)
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
