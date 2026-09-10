"""Compare a flat native circuit against an independently generated SPICE deck.

Net names may differ; terminal membership, terminal order and device values must
agree. This deliberately rejects hierarchy rather than pretending to compare it.
"""
import argparse
import json
import re
import shlex
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.model import load_project, file_digest
from icstudio.native_spice import netlist, render


def compare(project, reference, unit_multiplicity=False):
    top=next(c for c in project['cells'] if c['id']==project['top'])
    if any(d['kind']=='X' for d in top['devices']):raise ValueError('This reference comparison supports flat circuits only.')
    devices={render(d).split()[0].lower():len(d['nets']) for d in top['devices'] if d.get('native_spice',{}).get('type')=='device'}
    def circuit(text):
        text=re.sub(r'\n\s*\+\s*',' ',text);inside=False;found={};nets=defaultdict(list)
        for line in text.splitlines():
            stripped=line.strip()
            if stripped.lower()=='.control':inside=True;continue
            if stripped.lower()=='.endc':inside=False;continue
            if inside or not stripped or stripped[0] in '*.':continue
            parts=shlex.split(stripped,comments=False);name=parts[0].lower()
            if name not in devices and name[0] not in 'rclvi':raise ValueError('Unexpected reference device or unsupported statement: '+name)
            count=devices.get(name,2)
            if name in found:raise ValueError('Duplicate reference designator: '+name)
            values=[''.join(v.lower().split()) for v in parts[count+1:]]
            if unit_multiplicity:values=[v for v in values if v!='m=1']
            found[name]=values
            for pin,net in enumerate(parts[1:count+1]):nets[net.lower()].append((name,pin))
        return found,sorted(sorted(members) for members in nets.values()),sorted(nets.get('0',[]))
    with tempfile.TemporaryDirectory() as tmp:actual=netlist(project,tmp)
    a,an,ag=circuit(actual);b,bn,bg=circuit(Path(reference).read_text())
    differences=[]
    for name in sorted(set(a)|set(b)):
        if a.get(name)!=b.get(name):differences.append({'device':name,'native':a.get(name),'reference':b.get(name)})
    if an!=bn:differences.append({'connectivity':'Terminal membership differs.'})
    if ag!=bg:differences.append({'ground':'Ground terminal membership differs.'})
    return {'status':'passed' if not differences else 'failed','devices_compared':len(a),'schematic_devices':len(devices),'inline_testbench_devices':len(set(a)-set(devices)),'nets_compared':len(an),'differences':differences,'reference_sha256':file_digest(reference),'normalization':['SPICE case folding','line continuations','expression whitespace']+(['Explicit m=1 equals the verified model default'] if unit_multiplicity else [])}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--reference',required=True);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--unit-multiplicity-default',action='store_true');args=parser.parse_args()
    report=compare(load_project(args.project),args.reference,args.unit_multiplicity_default);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
