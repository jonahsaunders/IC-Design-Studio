"""Pinned SKY130 analog references: PVT, independent decks and real physical faults."""
import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest,atomic_write,save_project
from icstudio.analog import reference
from icstudio.analog_bank import generate
from icstudio.hierarchical_flow import run
from icstudio.testbenches import simulate
from icstudio.sky130_layout import layers
from qualify_layout_process import accept_result


# Independent hand-written circuit topology and dimensions, in the model's µm units.
REFERENCES={
    'current_mirror': ('IREF OUT VSS', [('a','IREF IREF VSS VSS','n',10),('b','OUT IREF VSS VSS','n',10)]),
    'differential_pair': ('INP INN OUTP OUTN TAIL VSS', [('a','OUTP INP TAIL VSS','n',10),('b','OUTN INN TAIL VSS','n',10)]),
    'amplifier': ('INP INN OUT BIAS VDD VSS', [('a','NREF INP TAIL VSS','n',10),('b','OUT INN TAIL VSS','n',10),
        ('c','NREF NREF VDD VDD','p',10),('d','OUT NREF VDD VDD','p',10),('e','TAIL BIAS VSS VSS','n',5)])}


def independent(kind):
    ports,devices=REFERENCES[kind]
    return '.subckt '+kind+' '+ports+'\n'+'\n'.join('X'+name+' '+nets+' sky130_fd_pr__'+pol+'fet_01v8 w='+str(w)+' l=1 nf=1' for name,nets,pol,w in devices)+'\n.ends '+kind+'\n'


def check_equivalent(native,other):
    if native['measurements']['status']!='passed' or other['measurements']['status']!='passed':
        raise ValueError('A reference measurement failed: '+str([native['measurements'],other['measurements']]))
    errors=[]
    for a,b in zip(native['measurements']['measurements'],other['measurements']['measurements']):
        if a['name']!=b['name'] or abs(a['value']-b['value'])>max(1e-10,abs(b['value'])*1e-4):
            errors.append(dict(name=a['name'],native=a['value'],independent=b['value']))
    if errors:raise ValueError('Independent netlist mismatch: '+str(errors))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pdk',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    for name in ('magic','netgen','ngspice'):ap.add_argument('--'+name,default=shutil.which(name))
    a=ap.parse_args();out=a.out.resolve()
    if out.exists() and any(out.iterdir()):ap.error('Use an empty evidence directory.')
    out.mkdir(parents=True,exist_ok=True);report=dict(status='running',cases=[],scope='Listed single-finger references, nominal/ss/ff at 27 °C and nominal at 0/85 °C; extracted capacitance only.')
    def publish():atomic_write(out/'qualification.json',json.dumps(report,indent=2))
    try:
        lock=json.loads((ROOT/'examples/sky130-qualification-lock.json').read_text());manifest=a.pdk/'package.json'
        if file_digest(manifest)!=lock['manifest_sha256']:raise ValueError('Pinned adapter manifest differs.')
        m=json.loads(manifest.read_text());root=a.pdk.resolve()
        for relative,expected in m['files'].items():
            path=(root/relative).resolve()
            if not path.is_relative_to(root) or file_digest(path)!=expected:raise ValueError('Locked asset differs: '+relative)
        tech=m['technology'];tech.update(package_root=str(root),package_lock=dict(id=m['id'],revision=m['revision'],files=m['files']))
        tools={name:getattr(a,name) for name in ('magic','netgen','ngspice')}
        if any(not path or not Path(path).is_file() for path in tools.values()):raise ValueError('Install Magic, Netgen and ngspice before qualification.')
        report['process']=dict(id=m['id'],revision=m['revision'],manifest_sha256=file_digest(manifest))
        for kind in REFERENCES:
            p,cid,key=reference(tech,kind);generate(p,cid);save_project(p,out/(kind+'.icproj'))
            deck=out/(kind+'-independent.spice');atomic_write(deck,independent(kind))
            for corner,temp in [('nominal',27),('ss',27),('ff',27),('nominal',0),('nominal',85)]:
                for original in p['testbenches']:
                    q=clone(p);bench=next(t for t in q['testbenches'] if t['id']==original['id']);bench['analysis'].update(corner=corner,temperature=temp)
                    name=f"{original['name']}-{corner}-{temp}";folder=out/name
                    item=dict(name=name,status='running',type='independent_simulation');report['cases'].append(item);publish()
                    try:
                        result=simulate(q,bench,tools['ngspice'],folder/'native')
                        other=simulate(q,bench,tools['ngspice'],folder/'independent',deck)
                        check_equivalent(result,other);item.update(status='passed',measurements=result['measurements'])
                    except Exception as exc:item.update(status='failed',error=str(exc))
                    publish()
            # Both saved analyses include the same full physical verification sequence.
            for bench in p['testbenches']:
                name=bench['name']+'-physical';result=run(p,bench['id'],out/name,tools)
                report['cases'].append(dict(name=name,type='physical',status=result['status'],engine_report=name+'/report.json'));publish()
            for fault in ('narrow-metal','route-open','wrong-channel-length'):
                q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);ls=layers(tech)
                if fault=='narrow-metal':
                    from icstudio.layout import rect
                    c['shapes'].append(rect(ls['m1'],-12000,0,100,100));stage='drc'
                elif fault=='route-open':
                    from collections import Counter
                    from icstudio.physical import erase
                    net=Counter(n for d in c['devices'] for n in d['nets'].values()).most_common(1)[0][0]
                    y=c['analog_bank']['buses'][net];erase(c,ls['m2'],[10000,y-400,11000,y+400]);stage='lvs'
                else:
                    shape=next(s for s in c['shapes'] if s['layer']==ls['poly'] and s.get('generated_device'));shape['points'][1][0]+=50;stage='lvs'
                name=kind+'-'+fault;result=run(q,key,out/name,tools)
                report['cases'].append(dict(name=name,type='deliberate_fault',expected_failure_stage=stage,status='passed' if accept_result(result,stage,out/name) else 'failed',engine_report=name+'/report.json'));publish()
        report['status']='passed' if all(c['status']=='passed' for c in report['cases']) else 'failed'
    except Exception as exc:report.update(status='failed',error=str(exc),traceback=traceback.format_exc())
    publish();print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
