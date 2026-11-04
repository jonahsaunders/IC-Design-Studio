"""Audit the exact native decap warning, never blanket-suppress device warnings.

The IHP decap CDL ties both source and drain to one rail. Magic represents the
one-sided drawn channel using its explicit missing-terminal connection. Accept
that diagnostic only at every expected decap finger with the correct four nets,
geometry and count. Other extraction warnings remain errors.
"""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex


def audit(ext_path, feedback_path, instances_path, labels_path):
    ext_path,feedback_path,instances_path,labels_path=map(Path,(ext_path,feedback_path,instances_path,labels_path))
    rows=json.loads(instances_path.read_text());labels=json.loads(labels_path.read_text())
    aliases={n['net']:n['alias'] for n in labels['nets']}
    if (not {'VDD','VSS'}<=aliases.keys() or len(aliases)!=len(labels['nets']) or
            len(set(aliases.values()))!=len(aliases)):
        raise ValueError('Missing or ambiguous rail identities.')
    text=ext_path.read_text()
    if not re.search(r'^scale 1000 1 0\.5$',text,re.M):raise ValueError('Unsupported Magic extraction units.')
    cells={r['name']:r for r in rows};buckets=defaultdict(list)
    if len(cells)!=len(rows):raise ValueError('Repeated instance identity.')
    for r in rows:
        x1,y1,x2,y2=r['box_nm']
        if not x1<x2 or not y1<y2:raise ValueError('Invalid instance extent.')
        for x in range(x1//5000,x2//5000+1):
            for y in range(y1//5000,y2//5000+1):buckets[x,y].append(r)
    devices=defaultdict(list)
    for line in text.splitlines():
        if not line.startswith('device '):continue
        t=shlex.split(line)
        if len(t)<19:raise ValueError('Incomplete native device.')
        devices[int(t[3]),int(t[4])].append(t)
    feedback=feedback_path.read_text();pattern=r'box (-?\d+) (-?\d+) (-?\d+) (-?\d+)\nfeedback add "([^"]+)" (\w+)\n?'
    matches=list(re.finditer(pattern,feedback))
    if re.sub(pattern,'',feedback).strip():raise ValueError('Unrecognized extraction feedback.')
    seen=Counter();matched=set();models=Counter()
    for m in matches:
        native=[int(m[i]) for i in range(1,5)];b=[v*5 for v in native];x=(b[0]+b[2])//2;y=(b[1]+b[3])//2
        owners=[r for r in buckets[x//5000,y//5000] if r['box_nm'][0]<=b[0]<b[2]<=r['box_nm'][2] and r['box_nm'][1]<=b[1]<b[3]<=r['box_nm'][3]]
        if len(owners)!=1 or owners[0]['master'] not in ('sg13g2_decap_4','sg13g2_decap_8'):
            raise ValueError('Missing terminal is outside a supported physical decap.')
        candidates=devices[native[0],native[1]]
        if len(candidates)!=1 or tuple(native[:2]) in matched:raise ValueError('Ambiguous or repeated warning device.')
        t=candidates[0];matched.add(tuple(native[:2]))
        if t[1]!='msubckt' or t[2] not in ('sg13_lv_nmos','sg13_lv_pmos'):raise ValueError('Unexpected decap device type.')
        nmos=t[2]=='sg13_lv_nmos';rail=aliases['VSS' if nmos else 'VDD'];gate=aliases['VDD' if nmos else 'VSS']
        if t[7:9]!=['l=200','w=84' if nmos else 'w=200'] or [t[9],t[10],t[13],t[16]]!=[rail,gate,rail,rail]:
            raise ValueError('Decap dimensions or four-terminal rail connections changed.')
        if m[5]!='device missing 1 terminal;\n connecting remainder to node '+rail or m[6]!='pale':
            raise ValueError('Different extraction diagnostic.')
        seen[owners[0]['name']]+=1;models[t[2]]+=1
    expected={r['name']:2 if r['master']=='sg13g2_decap_4' else 4 for r in rows if r['master'] in ('sg13g2_decap_4','sg13g2_decap_8')}
    if dict(seen)!=expected:raise ValueError('A decap finger diagnostic is missing or duplicated.')
    return dict(schema=1,passed=True,qualified=False,warning_count=len(matches),decap_instances=len(expected),devices=dict(models),
                files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ext_path,feedback_path,instances_path,labels_path)},
                scope='Only the documented one-sided decap channel diagnostic; not general device or extraction qualification.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('ext','feedback','instances','labels','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.ext,args.feedback,args.instances,args.labels)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','qualified','warning_count','decap_instances')}))
