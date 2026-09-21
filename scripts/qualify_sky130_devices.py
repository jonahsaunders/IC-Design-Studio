"""Actual pinned DRC/LVS and numerical acceptance for bounded SKY130 devices.

This is a device-recipe regression, not arbitrary-layout or foundry signoff.
Every deliberate failure must be detected by the intended engine evidence.
"""
import argparse
import json
import math
import re
import shutil
import sys
import traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,example,digest,file_digest,atomic_write,save_project
from icstudio.catalog import create_device
from icstudio.sky130_devices import install,install_dummy,install_guard,layers
from icstudio.physical_cells import assign_port
from icstudio.interchange import export_layout
from icstudio.testbenches import native_subcircuit
from icstudio.silicon_flow import magic_script
from icstudio.engines import execute,netgen_lvs,require_lvs_match,ngspice_command,parse_raw

PASSIVES=[('cap',2,2),('cap',10,10),('cap',30,30),('res',.5,1.65),('res',1,20),('res',10,100)]
CONDITIONS=[('nominal',27),('ss',0),('ff',85)]


def fixture(tech,kind,w=2,l=2):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='device_coupon'
    if kind in ('cap','res'):
        key='sky130_fd_pr/'+('cap_mim_m3_1' if kind=='cap' else 'res_generic_po')+'.sym'
        d=create_device(p['pdk'],key,'C1' if kind=='cap' else 'R1');d['model_params'].update(w=w,l=l)
        d['nets']=dict(zip(d['nets'],('P','N')));c['devices']=[d];c['ports']=['P','N']
        install(p,c['id'],d['id'])
        for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    else:
        wide=kind.endswith('-wide')
        d=install_dummy(p,c['id'],'MDUMMY','PMOS' if kind in ('nwell','pmos-wide') else 'NMOS','VREF',w='30u' if wide else '2u',l='.5u' if wide else '1u',x=5000,y=5000)
        c=p['cells'][0];pin=next(v for v in c['layout_pins'] if v['pin']=='b')
        if not wide:install_guard(p,c['id'],dict(kind=kind,x=0,y=0,width=16100,height=17500),'VREF',tie=dict(layer=pin['layer'],point=pin['point']),members=[d['id']])
        c=p['cells'][0];c['ports']=['VREF'];assign_port(p,c['id'],'VREF',pin['layer'],pin['point'])
    return p,p['cells'][0]


def verify(p,c,directory,tools,expected=None):
    directory.mkdir(parents=True);save_project(p,directory/'input.icproj');export_layout(p,directory/'layout.gds')
    atomic_write(directory/'schematic.spice',native_subcircuit(p,c['id']))
    root=Path(p['pdk']['package_root'])
    commands='drc style drc(full)\ndrc ignore none\ndrc check\ndrc catchup\nselect top cell\nbox select\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\nputs "STUDIO_DRC_WHY [drc listall why]"\n'
    commands+='extract all\next2spice lvs\next2spice subcircuit top on\next2spice scale off\next2spice -o extracted.spice'
    log=magic_script(tools['magic'],root/'libs.tech/magic/sky130A.tech',directory/'layout.gds',c['name'],c['ports'],directory/'magic',commands)
    counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)\s*$',log,re.M)
    if len(counts)!=1 or re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)!=['drc(full)']:raise ValueError('Missing unambiguous full-style DRC evidence.')
    count=int(counts[0]);evidence={'drc_count':count,'expected_failure':expected}
    if expected=='drc':
        if count<=0:raise ValueError('Deliberate illegal guard contact spacing was not detected.')
        return evidence
    if count:raise ValueError('Unexpected DRC violations: '+str(count))
    extracted=directory/'magic/extracted.spice'
    log=netgen_lvs(tools['netgen'],directory/'schematic.spice',c['name'],extracted,c['name'],root/'libs.tech/netgen/sky130A_setup.tcl',directory/'lvs')
    if expected=='lvs':
        if not re.search(r'netlists do not match|circuits do not match|property errors|disconnected node:|\(no matching pin\)',log,re.I):raise ValueError('LVS did not report the deliberate geometry/connectivity fault.')
        try:require_lvs_match(log)
        except ValueError:pass
        else:raise ValueError('A deliberate LVS fault was accepted.')
    else:require_lvs_match(log)
    evidence.update(extracted_sha256=file_digest(extracted),lvs_log_sha256=file_digest(directory/'lvs/lvs.log'))
    return evidence


def measure(p,subcircuits,kind,corner,temp,tools,directory):
    """Independent 1 V probes measure three isolated terminal admittances.

    Loading the large PDK once keeps qualification practical; every variant
    has its own circuit, source, saved current and hierarchy name.
    """
    directory.mkdir(parents=True)
    from icstudio.pdks import model_lines,stage_model_deck
    text='* Independent terminal admittance probes\n'+ '\n'.join(model_lines(p['pdk'],corner))+'\n'
    for phase,subcircuit in subcircuits.items():
        name='device_coupon_'+phase
        subcircuit=re.sub(r'(?im)^(\.subckt|\.ends)\s+device_coupon\b',lambda m:m[1]+' '+name,subcircuit)
        text+=subcircuit+f'\nVP_{phase} P_{phase} 0 DC 0 AC 1\nXDUT_{phase} P_{phase} 0 {name}\n'
    text+=f'\n.temp {temp}\n.ac lin 1 1k 1k\n.save '+' '.join('i(VP_'+phase+')' for phase in subcircuits)+'\n.end\n'
    text=stage_model_deck(p['pdk'],text,directory);deck=directory/'probe.cir';raw=directory/'probe.raw';atomic_write(deck,text)
    log=execute(ngspice_command(p,tools['ngspice'],raw,deck),directory,timeout=90);atomic_write(directory/'console.log',log)
    names,rows,complex_data=parse_raw(raw)
    if not complex_data or len(rows)!=1:raise ValueError('Expected one complex AC sample.')
    frequency=rows[0][names.index('frequency')].real;values={}
    for phase in subcircuits:
        current=-rows[0][names.index('i(vp_'+phase+')')]
        value=current.imag/(2*math.pi*frequency) if kind=='cap' else 1/current.real
        if not math.isfinite(value) or value<=0:raise ValueError('The passive terminal measurement is nonpositive or nonfinite.')
        values[phase]=value
    return values


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pdk',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    for name in ('magic','netgen','ngspice'):ap.add_argument('--'+name,default=shutil.which(name))
    a=ap.parse_args();out=a.out.resolve()
    if out.exists() and any(out.iterdir()):ap.error('Use an empty evidence directory.')
    out.mkdir(parents=True,exist_ok=True);report=dict(status='running',cases=[],scope='Listed bounded geometry and deterministic PVT probes only; no arbitrary-layout or foundry signoff.')
    def publish():atomic_write(out/'qualification.json',json.dumps(report,indent=2))
    try:
        root=a.pdk.resolve();m=json.loads((root/'package.json').read_text());lock=json.loads((ROOT/'examples/sky130-qualification-lock.json').read_text())
        if file_digest(root/'package.json')!=lock['manifest_sha256'] or (m['id'],m['revision'],digest(m['files']))!=(lock['id'],lock['revision'],lock['files_hash']):raise ValueError('Use the committed physical qualification adapter.')
        for rel,expected in m['files'].items():
            path=(root/rel).resolve()
            if not path.is_relative_to(root) or file_digest(path)!=expected:raise ValueError('Locked process asset changed: '+rel)
        tech=m['technology'];tech.update(package_root=str(root),package_lock={k:m[k] for k in ('id','revision','files')})
        tools={name:str(Path(getattr(a,name)).resolve()) if getattr(a,name) else '' for name in ('magic','netgen','ngspice')}
        pinned=json.loads((ROOT/'examples/physical-engine-lock.json').read_text());report['tools']={}
        for name,path in tools.items():
            if not path or not Path(path).is_file():raise ValueError('Install '+name+' before qualification.')
            log=execute([path,'-batch' if name=='netgen' else '--version'],out,timeout=20);atomic_write(out/(name+'-version.log'),log)
            if name in pinned and pinned[name]['version'] not in log:raise ValueError('Use pinned '+name+' '+pinned[name]['version'])
            report['tools'][name]=dict(sha256=file_digest(path),version_sha256=file_digest(out/(name+'-version.log')))
        report['process']=dict(id=m['id'],revision=m['revision'],manifest_sha256=file_digest(root/'package.json'))
        report['source']={str(path):file_digest(ROOT/path) for path in ('icstudio/sky130_devices.py','icstudio/sky130_layout.py','icstudio/contact_rules.py','icstudio/layout_graph.py','scripts/qualify_sky130_devices.py')}
        fixtures={}
        for kind,w,l in PASSIVES+[(k,2,1) for k in ('psub','nwell')]+[(k,30,.5) for k in ('nmos-wide','pmos-wide')]:
            name=f'{kind}-{w:g}x{l:g}';item=dict(name=name,status='running');report['cases'].append(item);publish()
            try:
                p,c=fixture(tech,kind,w,l);directory=out/name;fixtures.setdefault(kind,(p,c))
                from icstudio.physical import connectivity
                if connectivity(p,c['id'])['issues']:raise ValueError('Native physical terminal connectivity failed.')
                item['physical']=verify(p,c,directory,tools)
                if kind in ('cap','res'):
                    item['measurements']=[]
                    # Deliberately independent primitive/model declaration: no
                    # catalog emitter or geometry-derived W/L in this reference.
                    model='sky130_fd_pr__'+('cap_mim_m3_1' if kind=='cap' else 'res_generic_po')
                    independent=f'.subckt device_coupon P N\n'+('X1' if kind=='cap' else 'R1')+f' P N {model} w={w} l={l}\n.ends device_coupon\n'
                    for corner,temp in CONDITIONS:
                        decks=dict(schematic=(directory/'schematic.spice').read_text(),extracted=(directory/'magic/extracted.spice').read_text(),independent=independent)
                        values=measure(p,decks,kind,corner,temp,tools,directory/f'probes-{corner}-{temp}')
                        if any(abs(value/values['independent']-1)>1e-6 for value in values.values()):raise ValueError('Schematic/extracted/independent passive measurement differs: '+str(values))
                        estimate=(2e-15*w*l) if kind=='cap' else 48.2*l/w
                        if not .5*estimate<values['independent']<2*estimate:raise ValueError('Process value is outside the independent physical order-of-magnitude bound.')
                        item['measurements'].append(dict(corner=corner,temperature=temp,unit='F' if kind=='cap' else 'ohm',**values))
                item['status']='passed'
            except Exception as exc:item.update(status='failed',error=str(exc),traceback=traceback.format_exc())
            publish()
        for name,kind,expected in [('mim-wrong-width','cap','lvs'),('poly-wrong-length','res','lvs'),('dummy-gate-open','psub','lvs'),('guard-contact-spacing','nwell','drc')]:
            item=dict(name=name,status='running');report['cases'].append(item);publish()
            try:
                p,c0=fixtures[kind];p=clone(p);c=p['cells'][0]
                if name=='mim-wrong-width':
                    shape=next(s for s in c['shapes'] if s.get('generator_role')=='passive:dielectric_top');right=max(x for x,y in shape['points']);shape['points']=[[x+500 if x==right else x,y] for x,y in shape['points']]
                elif name=='poly-wrong-length':
                    shape=next(s for s in c['shapes'] if s.get('generator_role')=='passive:resistor_marker');right=max(x for x,y in shape['points']);shape['points']=[[x+500 if x==right else x,y] for x,y in shape['points']]
                elif name=='dummy-gate-open':c['shapes']=[s for s in c['shapes'] if s.get('generator_role')!='dummy_tie_2']
                else:
                    shape=next(s for s in c['shapes'] if s.get('pcell_role')=='mcon1');shape['points']=[[x+220,y] for x,y in shape['points']]
                item['physical']=verify(p,c,out/name,tools,expected);item['status']='passed'
            except Exception as exc:item.update(status='failed',error=str(exc),traceback=traceback.format_exc())
            publish()
        report['status']='passed' if all(i['status']=='passed' for i in report['cases']) else 'failed'
    except Exception as exc:report.update(status='failed',error=str(exc),traceback=traceback.format_exc())
    publish();print(json.dumps({'status':report['status'],'cases':[(i['name'],i['status'],i.get('error','')) for i in report['cases']]},indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
