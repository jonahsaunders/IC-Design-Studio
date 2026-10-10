"""Export the experimental IHP floating-metal model with unchanged signal R/pins."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.digital_fill_spef import parse, require
from icstudio.model import atomic_write
from scripts.ihp_fill_reduction import reduce_floating


def collapse(data, floats):
    require(floats and floats <= data['nets'].keys(), 'Missing extracted floating metal.')
    require({n for n in data['nets'] if n.startswith('ICSTUDIO_FLOAT_')} == floats,
            'Unexpected floating metal declaration.')
    owners = data['owners']
    for f in floats:
        item = data['nets'][f]
        require(all(p[0] == '*N' for p in item['conn']) and len(item['res']) == 1 and
                set(item['ground']) == set(item['res'][0][0]), 'Incomplete or connected floating metal.')
    def node(n): return owners[n] if owners[n] in floats else n
    ground = defaultdict(float); caps = defaultdict(float)
    for n in owners: ground[node(n)] += 0.
    for item in data['nets'].values():
        for n, v in item['ground'].items(): ground[node(n)] += float(v)*1e-12
    for (a, b), v in data['couplings'].items():
        a, b = node(a), node(b)
        if a != b: caps[tuple(sorted((a,b)))] += float(v)*1e-12
    return dict(ground), dict(caps)


def export(path, target, data, reduced):
    """Index each retained capacitance once; retain signal terminals and resistors."""
    floats = set(reduced['floating_nodes']); owners = data['owners']
    kept = {n: v for n,v in data['nets'].items() if n not in floats}
    g = defaultdict(list); c = defaultdict(list)
    for n, v in reduced['ground_f'].items(): g[owners[n]].append((n,v*1e12))
    for row in reduced['coupling_f']:
        a,b,v = row['a'],row['b'],row['value_f']*1e12
        for net in {owners[a],owners[b]}: c[net].append(((a,b),v))
    header = Path(path).read_text().split('*D_NET',1)[0]; mapping = {}; lines = []
    for line in header.splitlines():
        match = re.fullmatch(r'\*(\d+) (\S+)',line)
        if match:
            mapping[match[2]]='*'+match[1]
            if match[2] in floats: continue
        lines.append(line)
    ports = {p[1] for item in kept.values() for p in item['conn'] if p[0]=='*P'}
    def token(n):
        if n in mapping: return mapping[n]
        if ':' not in n:
            require(n in ports,'Unmapped retained port.'); return n
        parent,suffix=n.rsplit(':',1)
        require(parent in mapping,'Unmapped retained node.'); return mapping[parent]+':'+suffix
    for name,item in kept.items():
        total=math.fsum(v for _,v in g[name]+c[name])
        lines += ['',f'*D_NET {mapping[name]} {total:.17g}','*CONN']
        lines += [' '.join([p[0],token(p[1]),*p[2:]]) for p in item['conn']]
        lines.append('*CAP'); i=1
        for n,v in sorted(g[name]): lines.append(f'{i} {token(n)} {v:.17g}');i+=1
        for (a,b),v in sorted(c[name]):lines.append(f'{i} {token(a)} {token(b)} {v:.17g}');i+=1
        lines.append('*RES')
        lines += [f'{i} {token(a)} {token(b)} {v}' for i,((a,b),v) in enumerate(item['res'],1)]
        lines.append('*END')
    atomic_write(target,'\n'.join(lines)+'\n'); reread=parse(target)
    require(reread['nets'].keys()==kept.keys(),'Retained signal net set changed.')
    for name,item in kept.items():
        require(reread['nets'][name]['res']==item['res'] and reread['nets'][name]['conn']==item['conn'],
                'Signal resistance or terminals changed.')
        actual=reread['nets'][name]['ground']; expected=dict(g[name])
        require(actual.keys()==expected.keys() and all(math.isclose(float(actual[n]),v,rel_tol=1e-14,abs_tol=1e-20)
                for n,v in expected.items()),'Ground capacitance export changed.')
    expected={(r['a'],r['b']):r['value_f']*1e12 for r in reduced['coupling_f']}
    require(reread['couplings'].keys()==expected.keys() and all(math.isclose(float(reread['couplings'][p]),v,
            rel_tol=1e-14,abs_tol=1e-20) for p,v in expected.items()),'Mutual capacitance export changed.')


def run(source, represented, output):
    source,represented,output=map(Path,(source,represented,output));output.mkdir(exist_ok=False)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    data=parse(source);shapes=json.loads(represented.read_text())['added'];floats={r['net'] for r in shapes}
    require(len(floats)==len(shapes),'Repeated floating-metal representation.')
    ground,caps=collapse(data,floats);result=reduce_floating(ground,caps,floats)
    export(source,output/'timing.spef',data,result)
    require(hashlib.sha256(source.read_bytes()).hexdigest()==digest,'Extraction input changed.')
    result.update(source_sha256=digest,qualified=False,
                  timing_spef_sha256=hashlib.sha256((output/'timing.spef').read_bytes()).hexdigest())
    atomic_write(output/'reduction.json',json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','represented','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=run(a.source,a.represented,a.output)
    print(json.dumps({k:r[k] for k in ('algorithm','qualified','maximum_iterations','maximum_relative_solve_residual','timing_spef_sha256')}))
