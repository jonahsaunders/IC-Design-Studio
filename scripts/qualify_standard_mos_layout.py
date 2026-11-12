"""Execute native DRC/LVS on standard four-terminal MOS geometry and faults."""
import argparse,json,re,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,example,file_digest
from icstudio.catalog import create_device
from icstudio.process_adapters import ADAPTERS
from icstudio.physical_cells import assign_port
from icstudio.layout_verification import reference,run
from scripts.qualify_standard_mos import PROFILES,GEOMETRIES,geometry,independent_device,load_technology,write


def technology(target,sky130):
    if target!='sky130A':return load_technology(target)
    root=Path(sky130).resolve();package=json.loads((root/'package.json').read_bytes())
    lock=json.loads((ROOT/'examples/sky130-qualification-lock.json').read_bytes())
    if file_digest(root/'package.json')!=lock['manifest_sha256']:raise ValueError('Use the locked SKY130 physical adapter.')
    for name,expected in package['files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or file_digest(path)!=expected:raise ValueError('Changed SKY130 physical asset: '+name)
    tech=clone(package['technology']);tech.update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
    return tech,dict(target=target,revision=package['revision'],manifest_sha256=file_digest(root/'package.json'),
        scope='Separate locked physical adapter; its model/deck revision is recorded independently from the bundled simulation PDK.')


def fixture(tech,target,polarity,shape):
    size=geometry(target,shape);p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='mos_coupon';c['ports']=['D','G','S','B']
    spec=PROFILES[target];d=create_device(p['pdk'],spec['prefix']+spec['symbols'][polarity=='p']+'.sym','M1')
    d['params'].update(w=f"{size['w']}u",l=f"{size['l']}u");d['nets']=dict(d='D',g='G',s='S',b='B');c['devices']=[d]
    implementation=ADAPTERS[target].implementation();implementation.install_mos(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return p,c,implementation.layers(p['pdk'])


def altered(p,layers,fault):
    p=clone(p);c=p['cells'][0]
    if fault=='wrong-length':
        # Contact pads can be narrower than the channel. Select by physical
        # poly/diffusion intersection, never by the size of a poly rectangle.
        from icstudio.layout import kdb,polygon
        db=kdb();active=db.Region()
        for shape in c['shapes']:
            if shape['layer']==layers['diff']:active.insert(polygon(shape))
        gates=[s for s in c['shapes'] if s['layer']==layers['poly'] and s.get('generated_device')
            and not (db.Region(polygon(s)) & active).is_empty()]
        if len(gates)!=1:raise ValueError('Expected one channel-crossing gate for the length control.')
        gate=gates[0]
        right=max(x for x,y in gate['points']);gate['points']=[[x+50 if x==right else x,y] for x,y in gate['points']]
    elif fault=='gate-drain-short':
        from icstudio.layout import rect
        pins={r['pin']:r['point'] for r in c['layout_pins']};a,b=pins['d'],pins['g']
        width=400
        c['shapes'] += [rect(layers['m1'],min(a[0],b[0])-width//2,a[1]-width//2,abs(a[0]-b[0])+width,width),
            rect(layers['m1'],b[0]-width//2,min(a[1],b[1])-width//2,width,abs(a[1]-b[1])+width)]
    elif fault=='drain-open':
        # Remove only drain-contact cuts, preserving diffusion, metal and labels.
        x,y=next(r['point'] for r in c['layout_pins'] if r['pin']=='d')
        cuts={layers[k] for k in ('contact','licon','mcon') if k in layers}
        removed=[s for s in c['shapes'] if s['layer'] in cuts and
            min(a for a,b in s['points'])<=x<=max(a for a,b in s['points']) and
            min(b for a,b in s['points'])<=y<=max(b for a,b in s['points'])]
        if not removed:raise ValueError('No drain contact was selected for the open control.')
        c['shapes']=[s for s in c['shapes'] if s not in removed]
    else:raise ValueError('Unknown physical fault: '+fault)
    return p


def independent_reference(target,polarity,shape):
    fields=independent_device(target,polarity,geometry(target,shape)).split()
    fields[1:5]=['D','G','S','B']
    return reference('.subckt mos_coupon D G S B\n'+' '.join(fields)+'\n.ends mos_coupon\n','mos_coupon')


def fault_detected(report,folder):
    stages={r['name']:r for r in report['stages']}
    if report['status']!='failed' or stages['preflight']['status']!='passed' or stages['layout_export']['status']!='passed':return False
    extracted=folder/'lvs-extraction/extracted.spice'
    if not extracted.is_file():return False
    log=folder/'lvs/lvs.log'
    if log.is_file() and stages['lvs']['status']=='failed':
        return bool(re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin',log.read_text(),re.I))
    # A physically collapsed/lost port is a native extraction/interface failure.
    return stages['lvs_extraction']['status']=='failed' and bool(re.search(
        r'(terminal|port|interface)',stages['lvs_extraction'].get('error',''),re.I))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sky130',type=Path,required=True);parser.add_argument('--magic',required=True);parser.add_argument('--netgen',required=True)
    parser.add_argument('--targets',nargs='+',choices=PROFILES,default=list(PROFILES))
    parser.add_argument('--geometries',nargs='+',choices=GEOMETRIES[:-1],default=list(GEOMETRIES[:-1]))
    parser.add_argument('--faults',action='store_true');a=parser.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,processes={},cases=[],
        source_sha256=file_digest(__file__),source_files_sha256=file_digest(out/'source-files.json'),
        scope='Selected standard MOS geometry and deliberate physical faults. No complete device-family, electrical, density, complete-chip or foundry qualification.')
    tools=dict(magic=a.magic,netgen=a.netgen)
    for target in a.targets:
        tech,identity=technology(target,a.sky130);report['processes'][target]=identity
        for polarity in ('n','p'):
            for shape in a.geometries:
                name=f'{target}-{polarity}-{shape}';start=time.monotonic()
                row=dict(name=name,target=target,polarity=polarity,geometry=geometry(target,shape),status='RUNNING',faults=[])
                try:
                    p,c,layers=fixture(tech,target,polarity,shape);selected=independent_reference(target,polarity,shape)
                    result=run(p,c['id'],out/name,tools,selected);row['native_status']=result['status'];row['drc_count']=result.get('drc_count')
                    row['report_sha256']=file_digest(out/name/'report.json')
                    if result['status']!='passed':raise ValueError(result.get('error','Native verification did not pass.'))
                    if a.faults:
                        for fault in ('wrong-length','drain-open','gate-drain-short'):
                            changed=altered(p,layers,fault);folder=out/(name+'-'+fault)
                            result=run(changed,c['id'],folder,tools,selected);detected=fault_detected(result,folder)
                            row['faults'].append(dict(fault=fault,detected=detected,report_sha256=file_digest(folder/'report.json'),
                                observed=result['status'],error=result.get('error')))
                            if not detected:raise ValueError('Physical fault was not detected by native connectivity/size evidence: '+fault)
                    row['status']='PASS'
                except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
                row['elapsed_seconds']=time.monotonic()-start;report['cases'].append(row);write(out/'qualification.json',report)
                print(name,row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and report['cases'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
