"""Reproducible SKY130 inverter reference flow with independent evidence gates.

This validates one PDK standard cell and this application's adapters. It does
not qualify arbitrary user layouts or establish foundry tapeout signoff.
"""
from pathlib import Path
import json,re,shutil,math,os
from .model import example,device,uid,clone,scalar,save_project,atomic_write,file_digest,digest,now
from .engines import execute,tcl_word,parse_raw,run_ngspice,run_deck,netgen_lvs,require_lvs_match
TOP='sky130_fd_sc_hd__inv_1'


def subcircuit(text,name):
    # Join SPICE continuation lines before parsing headers and devices.
    text=re.sub(r'\n\s*\+\s*',' ',text)
    match=re.search(r'^\.subckt\s+'+re.escape(name)+r'\s+([^\n]+)\n(.*?)^\.ends[^\n]*',text,re.I|re.M|re.S)
    if not match:raise ValueError('Missing reference subcircuit '+name)
    return match.group(1).split(),match.group(2),match.group(0)+'\n'


def logic_metrics(result):
    xs=result['x'];traces=result['traces'];vin=traces.get('vin');vout=traces.get('vout')
    if vin is None or vout is None or len(xs)<20:raise ValueError('Missing inverter waveforms.')
    if any(not math.isfinite(float(v)) for values in (xs,vin,vout) for v in values):raise ValueError('Nonfinite simulation output.')
    # Check settled logic windows of a 20 ns input period after startup.
    high=[vo for t,vi,vo in zip(xs,vin,vout) if t>4e-9 and 4e-9<(t-2e-9)%20e-9<8e-9 and vi>1.6]
    low=[vo for t,vi,vo in zip(xs,vin,vout) if t>4e-9 and 14e-9<(t-2e-9)%20e-9<18e-9 and vi<.2]
    if not high or not low:raise ValueError('No settled high/low input windows were sampled.')
    metrics={'samples':len(xs),'output_high_min_V':min(low),'output_low_max_V':max(high),'supply_V':1.8,'load_F':5e-15}
    if min(low)<1.6 or max(high)>.2:raise ValueError('Inverter fails settled logic levels: '+json.dumps(metrics))
    def crossings(values,rising):
        return [a+(b-a)*(.9-va)/(vb-va) for a,b,va,vb in zip(xs,xs[1:],values,values[1:]) if (va<.9<=vb if rising else va>.9>=vb)]
    delays=[]
    for rising in (False,True):
        for edge in crossings(vin,rising):
            matches=[t-edge for t in crossings(vout,not rising) if 0<=t-edge<5e-9]
            if matches:delays.append(min(matches))
    if len(delays)<4:raise ValueError('Too few switching transitions to measure propagation delay.')
    metrics['mean_delay_s']=sum(delays)/len(delays);metrics['measured_transitions']=len(delays);return metrics


def locked_assets(root):
    files={}
    for directory in ('libs.tech/ngspice','libs.ref/sky130_fd_pr/spice','libs.tech/magic','libs.tech/netgen'):
        for f in (root/directory).rglob('*'):
            if f.is_file():files[f.relative_to(root).as_posix()]=file_digest(f)
    for rel in ('SOURCES','libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds','libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'):
        f=root/rel
        if f.is_file():files[rel]=file_digest(f)
    return files


def native_project(root,reference,layout_path,lock):
    from .interchange import import_layout
    ports,body,_=subcircuit(reference,TOP);p=example('empty');p['name']='SKY130 reference inverter';child={'id':uid(),'name':TOP,'ports':ports,'devices':[],'shapes':[]};p['cells'].append(child)
    devices=[];bindings={}
    for line in body.strip().splitlines():
        if not line.strip() or line.lstrip().startswith('*'):continue
        parts=line.split()
        if len(parts)<8 or parts[0][0].upper()!='X':raise ValueError('Reference inverter is not the supported two-MOS subcircuit.')
        model=parts[5];kind='PMOS' if '__pfet_' in model else 'NMOS' if '__nfet_' in model else None
        if not kind:raise ValueError('Unexpected reference device '+model)
        params=dict(t.split('=',1) for t in parts[6:] if '=' in t)
        if set(params)!={'w','l'}:raise ValueError('Reference MOS parameters changed; review the adapter.')
        d=device(kind,'MP1' if kind=='PMOS' else 'MN1',350,180 if kind=='PMOS' else 400,nets=dict(zip(('d','g','s','b'),parts[1:5])))
        # SKY130's library applies scale=1u; native dimensions are in metres.
        d['params'].update(w=f'{scalar(params["w"]):.12g}u',l=f'{scalar(params["l"]):.12g}u');devices.append(d)
        bindings[kind]={'model':model,'prefix':'X','pin_order':['d','g','s','b'],'parameter_scale':{'w':1e6,'l':1e6}}
    if len(devices)!=2 or len(bindings)!=2:raise ValueError('Expected one NMOS and one PMOS.')
    child['devices']=devices
    imported,_=import_layout(layout_path);layout_cell=next(c for c in imported['cells'] if c['name']==TOP);child['shapes']=layout_cell['shapes']
    p['pdk']=imported['pdk'];p['pdk'].update(name='SKY130A · inverter reference',revision=digest(lock)[:16],status='reference flow only; not foundry signoff',package_root=str(root),package_lock={'id':'sky130A-reference','revision':digest(lock)[:16],'files':lock},simulation={'ngspice_compatibility':'hsa','includes':[{'path':'libs.tech/ngspice/sky130.lib.spice','sections':{'nominal':'tt','tt':'tt'}}],'devices':bindings})
    top=p['cells'][0];top['name']='testbench';top['devices']=[device('V','VDD',140,180,nets={'p':'vdd','n':'0'}),device('V','VIN',140,400,nets={'p':'vin','n':'0'},source={'type':'pulse','low':'0','high':'1.8','period':'20n','delay':'2n','duty':'0.5','ac':'1'}),device('X','XINV',400,280,cell=child['id'],nets={'A':'vin','VGND':'0','VNB':'0','VPB':'vdd','VPWR':'vdd','Y':'vout'}),device('C','CL',650,280,value='5f',nets={'p':'vout','n':'0'})]
    p['analysis'].update(type='tran',step='20p',stop='62n',corner='tt')
    from .wiring import migrate
    for cell in p['cells']:migrate(cell,p)
    return p


def run(pdk_root,output,ngspice='ngspice',magic='magic',netgen='netgen',progress=lambda *_:None):
    root=Path(pdk_root).resolve();out=Path(output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty reference-flow output directory.')
    out.mkdir(parents=True,exist_ok=True)
    report={'schema':1,'created':now(),'cell':TOP,'status':'running','qualification':'One standard-cell adapter regression only; no foundry signoff.','stages':[]}
    names=['preflight','layout_import','schematic_simulation','drc','lvs_extraction','lvs','parasitic_extraction','post_layout_simulation']
    def publish():atomic_write(out/'report.json',json.dumps(report,indent=2,allow_nan=False))
    def stage(name,fn):
        entry={'name':name,'status':'running'};report['stages'].append(entry);publish();progress(len(report['stages'])/9,'SKY130: '+name)
        try:entry['evidence']=fn();entry['status']='passed'
        except Exception as exc:entry['status']='failed';entry['error']=str(exc);publish();raise
        publish();return entry['evidence']
    files={'models':root/'libs.tech/ngspice/sky130.lib.spice','magicrc':root/'libs.tech/magic/sky130A.magicrc','technology':root/'libs.tech/magic/sky130A.tech','setup':root/'libs.tech/netgen/sky130A_setup.tcl','gds':root/'libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds','spice':root/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'}
    tools={'ngspice':ngspice,'magic':magic,'netgen':netgen};resolved={}
    def preflight():
        missing=[str(p) for p in files.values() if not p.is_file()]
        for name,value in tools.items():
            f=Path(value) if Path(value).is_file() else Path(shutil.which(value) or '')
            if not f.is_file():missing.append(name+' executable')
            else:resolved[name]=str(f.resolve())
        if missing:raise ValueError('Missing requirements: '+', '.join(missing))
        versions={}
        for name,path in resolved.items():
            text=execute([path,'-batch'] if name=='netgen' else [path,'--version'],out,timeout=15);atomic_write(out/(name+'-version.log'),text);versions[name]=text[:3000]
        return {'tools':{n:{'path':p,'sha256':file_digest(p),'version':versions[n]} for n,p in resolved.items()},'assets':{n:file_digest(f) for n,f in files.items()}}
    try:
        stage('preflight',preflight)
        lock=locked_assets(root);atomic_write(out/'pdk-lock.json',json.dumps({'root':str(root),'files':lock},indent=2))
        ports,body,reference=subcircuit(files['spice'].read_text(),TOP);atomic_write(out/'reference.spice',reference)
        def layout():
            import klayout.db as db
            source=db.Layout();source.read(str(files['gds']));cell=source.cell(TOP)
            if cell is None:raise ValueError('Inverter missing from reference GDS.')
            dest=db.Layout();dest.dbu=source.dbu;dest.create_cell(TOP).copy_tree(cell);dest.write(str(out/'inverter.gds'))
            return {'sha256':file_digest(out/'inverter.gds'),'dbu_um':dest.dbu,'klayout_version':db.__version__}
        stage('layout_import',layout)
        p=native_project(root,reference,out/'inverter.gds',lock);save_project(p,out/'inverter.icproj')
        from .interchange import spice
        _,_,native=subcircuit(spice(p,hierarchical=True),TOP);atomic_write(out/'native-schematic.spice',native)
        def simulate():
            d=out/'schematic';d.mkdir()
            r=run_ngspice(p,p['top'],p['analysis'],resolved['ngspice'],d);atomic_write(d/'result.json',json.dumps(r));return logic_metrics(r)
        pre=stage('schematic_simulation',simulate)
        def magic_run(directory,commands):
            directory.mkdir();script=f'gds read {tcl_word(out/"inverter.gds")}\nload {TOP}\nselect top cell\n'+commands+'\nquit -noprompt\n'
            atomic_write(directory/'run.tcl',script)
            # Use the real PDK startup after setting a relocatable PDK_ROOT.
            rc=directory/'startup.tcl';atomic_write(rc,f'set ::env(PDK_ROOT) {tcl_word(root.parent)}\nsource {tcl_word(files["magicrc"])}\n')
            try:log=execute([resolved['magic'],'-dnull','-noconsole','-rcfile',str(rc)],directory,timeout=240,input_text=script)
            except Exception as exc:atomic_write(directory/'console.log',str(exc));raise
            atomic_write(directory/'console.log',log)
            if re.search(r'contained errors|Malformed line|Illegal keyword|Error:.*required by this techfile|invalid command name',log,re.I):raise ValueError('Magic reported a technology or command error; inspect '+str(directory/'console.log'))
            return log
        def drc():
            log=magic_run(out/'drc','drc euclidean on\ndrc check\ndrc catchup\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_DETAILS [drc listall why]"')
            matches=re.findall(r'^STUDIO_DRC_COUNT\s+(\d+)\s*$',log,re.M)
            if len(matches)!=1:raise ValueError('Magic did not produce an unambiguous DRC count. Inspect drc/console.log.')
            count=int(matches[0])
            if count:raise ValueError(f'Magic reports {count} DRC violations. Inspect drc/console.log.')
            return {'violations':count,'log':'drc/console.log'}
        stage('drc',drc)
        def extract(name,parasitics=False):
            commands='extract all\next2spice lvs\next2spice subcircuit top on\next2spice scale off\n'
            if parasitics:commands+='ext2spice cthresh 0\n'
            commands+='ext2spice -o extracted.spice';magic_run(out/name,commands);deck=out/name/'extracted.spice'
            if not deck.is_file():raise ValueError('Magic did not create extracted.spice.')
            header,body,_=subcircuit(deck.read_text(),TOP)
            if set(header)!=set(ports):raise ValueError('Extracted pin names differ from reference ports: '+str(header))
            capacitors=len(re.findall(r'^C\S+\s',body,re.I|re.M))
            if parasitics and capacitors==0:raise ValueError('Parasitic extraction contains no capacitors.')
            return {'deck':str(deck.relative_to(out)),'sha256':file_digest(deck),'capacitors':capacitors,'profile':'device and interconnect capacitance' if parasitics else 'LVS devices'}
        stage('lvs_extraction',lambda:extract('lvs-extraction'))
        def lvs():
            log=netgen_lvs(resolved['netgen'],out/'native-schematic.spice',TOP,out/'lvs-extraction/extracted.spice',TOP,files['setup'],out/'lvs')
            require_lvs_match(log)
            return {'unique_match':True,'schematic':'native-schematic.spice','schematic_sha256':file_digest(out/'native-schematic.spice'),'log':'lvs/lvs.log'}
        stage('lvs',lvs);stage('parasitic_extraction',lambda:extract('parasitics',True))
        def postlayout():
            directory=out/'post-layout';directory.mkdir();deck=directory/'testbench.cir'
            extracted=out/'parasitics/extracted.spice';header,_,_=subcircuit(extracted.read_text(),TOP);mapping={'A':'vin','VGND':'0','VNB':'0','VPB':'vdd','VPWR':'vdd','Y':'vout'}
            text='* SKY130 inverter extracted testbench\n.lib "'+files['models'].as_posix()+'" tt\n.include "'+extracted.as_posix()+'"\nVDD vdd 0 1.8\nVIN vin 0 PULSE(0 1.8 2n 200f 200f 10n 20n)\nXDUT '+' '.join(mapping[k] for k in header)+' '+TOP+'\nCL vout 0 5f\n.tran 20p 62n\n.save v(vin) v(vout)\n.end\n';atomic_write(deck,text)
            r=run_deck(p,p['top'],{'type':'deck','deck':str(deck)},resolved['ngspice'],directory);atomic_write(directory/'result.json',json.dumps(r));metrics=logic_metrics(r);metrics['delay_delta_s']=metrics['mean_delay_s']-pre['mean_delay_s'];return metrics
        stage('post_layout_simulation',postlayout)
        # Detect modifications to locked dependencies during the run.
        if locked_assets(root)!=lock:raise ValueError('PDK assets changed during execution.')
        report['status']='passed'
    except Exception as exc:
        report['status']='blocked' if report['stages'][-1]['name']=='preflight' else 'failed';report['error']=str(exc)
        done={s['name'] for s in report['stages']}
        for name in names:
            if name not in done:report['stages'].append({'name':name,'status':'not_run'})
    finally:publish()
    return report
