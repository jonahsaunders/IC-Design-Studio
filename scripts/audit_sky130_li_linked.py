"""Independent file/raw-output audit of the selected LI linked experiment.

Uses no application or qualification-runner imports. This audits integration
with the shared public compact model; it does not establish silicon accuracy.
"""
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import re

PARAMETERS={'tt':(12.2,0),'ll':(10.31,.014e-6),'hh':(14.02,-.014e-6),'hl':(14.8,-.020e-6),'lh':(9.5,.020e-6)}
FAULTS={'wrong-width','wrong-length','wrong-metal-model','wrong-multiplicity','disconnected-terminal','wrong-passive-section'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raw_plot(lines):
    header={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in lines[:lines.index('Variables:')] if ':' in line}
    count=int(header['No. Variables']);points=int(header['No. Points']);complex_data=header['Flags']=='complex'
    if header['Flags'] not in ('real','complex'):raise ValueError('Unknown raw-file encoding.')
    start=lines.index('Variables:')+1;names=[]
    for i,line in enumerate(lines[start:start+count]):
        fields=line.split()
        frequency_grid=(i==0 and len(fields)==4 and fields[1:]==['frequency','frequency','grid=3'])
        if (len(fields)!=3 and not frequency_grid) or fields[0]!=str(i):raise ValueError('Malformed raw variable declaration.')
        names.append(fields[1].lower())
    if len(set(names))!=count or lines[start+count]!='Values:':raise ValueError('Invalid raw channels.')
    values=[line.split() for line in lines[start+count+1:] if line.strip()]
    if len(values)!=points*count:raise ValueError('Truncated or extra raw points.')
    rows=[]
    for i in range(points):
        row=[]
        for j in range(count):
            tokens=values[i*count+j]
            if len(tokens)!=(2 if j==0 else 1) or (j==0 and tokens[0]!=str(i)):raise ValueError('Invalid raw point index.')
            token=tokens[-1]
            value=complex(*map(float,token.split(','))) if complex_data else float(token)
            if not math.isfinite(complex(value).real) or not math.isfinite(complex(value).imag):raise ValueError('Nonfinite raw sample.')
            row.append(value)
        rows.append(row)
    return {name:[r[i] for r in rows] for i,name in enumerate(names)},[float(r[0].real) for r in rows]


def raw(path):
    lines=Path(path).read_text(encoding='utf-8').splitlines()
    starts=[i for i,line in enumerate(lines) if line.startswith('Title:')]
    if not starts or starts[0]!=0 or len(starts)>2:raise ValueError('Unexpected native raw plots.')
    first=raw_plot(lines[:starts[1]] if len(starts)==2 else lines)
    if len(starts)==2:
        trailing=lines[starts[1]:]
        if 'Plotname: Noise Spectral Density Curves' not in lines[:starts[1]] or 'Plotname: Integrated Noise' not in trailing:
            raise ValueError('Unexpected trailing raw plot.')
        data,x=raw_plot(trailing)
        if len(x)!=1 or set(data)!={'v(onoise_total)','v(inoise_total)'} or any(len(v)!=1 or not isinstance(v[0],float) or v[0]<=0 for v in data.values()):
            raise ValueError('Invalid integrated noise trailer.')
    return first


def response(path,analysis,section,positive=True):
    data,x=raw(path)
    if any(a>=b for a,b in zip(x,x[1:])):raise ValueError('Non-increasing raw coordinates.')
    if analysis=='dc' and (len(x)!=41 or abs(x[0])>1e-15 or abs(x[-1]-.001)>1e-13):raise ValueError('Incomplete DC axis.')
    if analysis in ('ac','noise') and (len(x)!=26 or any(abs(a/(100*10**(i/5))-1)>1e-9 for i,a in enumerate(x))):raise ValueError('Incomplete frequency axis.')
    if analysis=='tran' and (x[0]>1e-12 or abs(x[-1]-60e-9)>6e-16):raise ValueError('Incomplete transient axis.')
    output=data['onoise_spectrum' if analysis=='noise' else 'v(output)']
    if positive and analysis in ('dc','tran') and max(output)-min(output)<1e-5:raise ValueError('Unexercised positive response.')
    if analysis=='noise' and any(v<=0 for v in output):raise ValueError('Invalid noise response.')
    if analysis in ('dc','tran'):
        for name,value in zip(('v(parameter_rl1)','v(parameter_tol)'),PARAMETERS[section]):
            if any(abs(v-value)>1e-18+1e-10*abs(value) for v in data[name]):raise ValueError('Native passive parameters differ.')
    if analysis in ('dc','ac'):
        for f,vin,vout,current in zip(x,data['v(input)'],data['v(output)'],data['i(vdrive)']):
            if abs(vin-(f if analysis=='dc' else 1))>1e-10:raise ValueError('Applied source differs.')
            load=vout*(.001+(2j*math.pi*f*1e-12 if analysis=='ac' else 0))
            if abs(current+load)>1e-12+1e-6*abs(load):raise ValueError('Loaded-network current conservation differs.')
    return x,output


def compare(actual,reference,analysis):
    x,a=actual;y,b=reference
    if analysis=='tran':
        interpolated=[]
        for t in x:
            i=max(0,min(len(y)-2,bisect.bisect_right(y,t)-1));f=(t-y[i])/(y[i+1]-y[i]);interpolated.append(b[i]+f*(b[i+1]-b[i]))
        b=interpolated
    elif len(x)!=len(y) or any(abs(l-r)>1e-15+1e-10*abs(r) for l,r in zip(x,y)):raise ValueError('Axes differ.')
    relative=.0002 if analysis=='tran' else .000001
    absolute=1e-18 if analysis=='noise' else 1e-8 if analysis=='tran' else 1e-10
    return max(abs(l-r)/(absolute+relative*abs(r)) for l,r in zip(a,b))


def deck_identity(path,kind,section,rotation,execution_root,shared,expected_sha256):
    path=Path(path)
    if sha(path)!=expected_sha256 or path.read_bytes()!=(path.parent/'deck-snapshot.cir').read_bytes():
        raise ValueError('Executed deck snapshot/binding differs.')
    text=path.read_text(encoding='utf-8');lines=[s.strip() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('*')]
    includes=[s for s in lines if re.match(r'(?i)^\.(include|lib)\s',s)]
    expected=shared['staged'][section].splitlines()
    native=Path(execution_root)/'physical/l1-w2-l5'/f'physical-{rotation}'/'lvs-extraction/extracted.spice'
    if kind=='extracted':expected.append('.include '+native.as_posix())
    if sorted(includes)!=sorted(expected):raise ValueError('Deck selected section or extracted-file path differs.')
    components=[s.split() for s in lines if not s.startswith('.')]
    names=[s[0].upper() for s in components]
    expected_device={'application':'R_LI','manual':'RREF','extracted':'XEXTRACT'}[kind]
    if len(names)!=6 or set(names)!={'VDRIVE','RL','CL','VPROBE_RL1','VPROBE_TOL',expected_device}:
        raise ValueError('Comparison path has extra/substituted circuit elements.')
    device=components[names.index(expected_device)]
    if kind=='extracted':
        if device!=['XEXTRACT','input','output','coupon']:raise ValueError('Actual extracted subcircuit is not connected.')
    elif (device[1:4]!=['input','output','sky130_fd_pr__res_generic_l1'] or
          dict(v.split('=',1) for v in device[4:])!={'w':'2','l':'5','m':'1'}):
        raise ValueError('Positive circuit model, geometry or terminals differ.')
    if '.temp 27' not in lines:raise ValueError('Selected temperature differs.')
    return True


def audit(root):
    root=Path(root).resolve();report=json.loads((root/'qualification.json').read_bytes());manifest=json.loads((root/'manifest.json').read_bytes())
    if report['status']!='PASS' or report['qualified'] or report['chunk_complete'] or report['development_reuse']:
        raise ValueError('This is not a passed fresh bounded integration run.')
    for name,expected in manifest.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or sha(path)!=expected:raise ValueError('Changed or missing run artifact: '+name)
    expected=set(report['selected_cases'])
    if not expected or len(expected)!=len(report['selected_cases']) or expected!={c['name'] for c in report['cases']} or len(expected)!=len(report['cases']):
        raise ValueError('Selected case coverage differs.')
    if not all(report[k] for k in ('implementation_unchanged','model_inputs_unchanged','tools_unchanged')):raise ValueError('Run inputs changed.')
    execution_root=report['execution_root']
    shared=json.loads((root/'shared-models/source-identity.json').read_bytes())
    for name,expected_hash in shared['files'].items():
        if sha(root/'shared-models'/name)!=expected_hash:raise ValueError('Staged model closure differs.')
    layout=report['physical']
    if layout['status']!='PASS' or {r['name'] for r in layout['faults']}!={'terminal-open','terminal-short','reference-width','reference-length','reference-model'} or not all(r['detected'] for r in layout['faults']):
        raise ValueError('Physical/fault acceptance incomplete.')
    native_files=0
    for angle in (0,90):
        folder=root/'physical/l1-w2-l5'/f'physical-{angle}'
        physical_report=json.loads((folder/'report.json').read_bytes())
        if physical_report['status']!='passed' or physical_report['drc_count']!=0:raise ValueError('Native physical check failed.')
        log=(folder/'lvs/lvs.log').read_text(encoding='utf-8')
        if 'Circuits match uniquely.' not in log or 'Cell pin lists are equivalent.' not in log or re.search(r'property errors|netlists do not match|disconnected node|no matching pin',log,re.I):raise ValueError('Strict native LVS differs.')
        path=folder/'lvs-extraction/extracted.spice';text=path.read_text(encoding='utf-8')
        devices=[line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(('*','.'))]
        if len(devices)!=1 or len(devices[0])!=6 or set(devices[0][1:3])!={'R1','R2'} or devices[0][3]!='sky130_fd_pr__res_generic_l1':raise ValueError('Native resistor identity differs.')
        if dict(v.split('=',1) for v in devices[0][4:])!={'w':'2','l':'5'}:raise ValueError('Native resistor dimensions differ.')
        native_files+=1
    raw_files=0;faults=0;comparisons=0;largest=0
    for case in report['cases']:
        if case['status']!='PASS' or case['section'] not in PARAMETERS or case['rotation'] not in (0,90):raise ValueError('Invalid selected case.')
        if case['name']!=f"{case['section']}-r{case['rotation']}":raise ValueError('Selected case identity differs.')
        folder=root/case['name'];section=case['section']
        if set(case['analyses'])!={'dc','ac','tran','noise'} or {f['name'] for f in case['faults']}!=FAULTS or len(case['faults'])!=len(FAULTS):raise ValueError('Incomplete analysis/fault coverage.')
        references={}
        for analysis in ('dc','ac','tran','noise'):
            paths=case['analyses'][analysis]['paths']
            if set(paths)!={'manual','application','extracted'}:raise ValueError('Incomplete independent comparison paths.')
            values={}
            for kind in paths:
                path=folder/analysis/kind/'deck.raw'
                if sha(path)!=paths[kind]['raw_sha256']:raise ValueError('Raw output binding differs.')
                deck_identity(path.parent/'input.cir',kind,section,case['rotation'],execution_root,shared,paths[kind]['deck_sha256'])
                values[kind]=response(path,analysis,section);raw_files+=1
            for kind in ('application','extracted'):
                error=compare(values[kind],values['manual'],analysis);largest=max(largest,error);comparisons+=1
                if error>1:raise ValueError('Linked response mismatch.')
            references[analysis]=values['manual']
        for fault in case['faults']:
            if not fault['detected']:raise ValueError('Undetected deliberate fault.')
            path=folder/fault['name']/'deck.raw'
            if sha(path)!=fault['raw_sha256']:raise ValueError('Fault output binding differs.')
            error=compare(response(path,'dc',fault['section'],False),references['dc'],'dc')
            if error<=1:raise ValueError('Fault is not detected in raw output.')
            raw_files+=1;faults+=1
    return dict(status='PASS',qualified=False,chunk_complete=False,case_count=len(expected),native_files=native_files,raw_files=raw_files,
                electrical_comparisons=comparisons,electrical_faults=faults,integrity_bindings=len(manifest),largest_normalized_error=largest,
                scope='Independent raw numerical and native identity readback; shared compact-model integration only. No calibrated model/noise accuracy, full LI manual-rule coverage or operating-envelope claim.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.resolve().is_relative_to(a.root.resolve()):raise ValueError('Write the audit outside the immutable evidence tree.')
    result=audit(a.root);a.output.write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))


if __name__=='__main__':main()
