"""Qualify locked fixed PNP geometry with the opt-in upstream-area SKY130 deck."""
import argparse
import json
import re
import shutil
import sys
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device
from icstudio.engines import execute,netgen_lvs,require_lvs_match
from icstudio.interchange import export_layout
from icstudio.model import clone,example,file_digest,save_project,atomic_write
from icstudio.physical import connectivity
from icstudio.physical_cells import assign_port
from icstudio.silicon_flow import magic_script
from icstudio.sky130_bipolar_rules import TECH_SHA256
from icstudio.sky130_devices import install
from icstudio.testbenches import native_subcircuit


def fixture(tech,count=1):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='pnp_coupon'
    d=create_device(p['pdk'],'sky130_fd_pr/pnp_05v5.sym','Q1');d['model_params']['m']=count
    d['nets']=dict(collector='C',base='B',emitter='E');c['devices']=[d];c['ports']=['C','B','E']
    install(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return p,c


def qualify(p,c,folder,tools,negative=False):
    folder.mkdir(parents=True);save_project(p,folder/'input.icproj');export_layout(p,folder/'layout.gds')
    atomic_write(folder/'schematic.spice',native_subcircuit(p,c['id']))
    root=Path(p['pdk']['package_root'])
    commands='drc style drc(full)\ndrc ignore none\ndrc check\ndrc catchup\nselect top cell\nbox select\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\nputs "STUDIO_DRC_WHY [drc listall why]"\nextract all\next2spice lvs\next2spice subcircuit top on\next2spice scale off\next2spice -o extracted.spice'
    log=magic_script(tools['magic'],root/'libs.tech/magic/sky130A.tech',folder/'layout.gds',c['name'],c['ports'],folder/'magic',commands)
    counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)\s*$',log,re.M)
    if len(counts)!=1 or re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)!=['drc(full)']:raise ValueError('Missing unambiguous full DRC evidence.')
    drc=int(counts[0]);extracted=folder/'magic/extracted.spice'
    log=netgen_lvs(tools['netgen'],folder/'schematic.spice',c['name'],extracted,c['name'],root/'libs.tech/netgen/sky130A_setup.tcl',folder/'lvs')
    try:require_lvs_match(log);matched=True
    except ValueError:matched=False
    if negative:
        if matched or not re.search(r'netlists do not match|circuits do not match|property errors',log,re.I):raise ValueError('Emitter-size corruption was not rejected by strict extracted LVS.')
    elif drc or not matched:raise ValueError(f'PNP qualification failed: DRC={drc}, strict LVS={matched}')
    return dict(drc_count=drc,lvs_matched=matched,expected_failure='lvs' if negative else None,
        extracted_sha256=file_digest(extracted),lvs_log_sha256=file_digest(folder/'lvs/lvs.log'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pdk',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    for tool in ('magic','netgen'):parser.add_argument('--'+tool,default=shutil.which(tool))
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):parser.error('Choose an empty qualification output directory.')
    out.mkdir(parents=True,exist_ok=True);report=dict(status='running',scope='Fixed SKY130 PNP W3.40/L3.40, listed multiplicities and emitter-size fault only; no NPN or arbitrary bipolar qualification.',cases=[])
    try:
        root=args.pdk.resolve();manifest=json.loads((root/'package.json').read_text())
        if manifest['id']!='sky130A' or manifest['files'].get('libs.tech/magic/sky130A.tech')!=TECH_SHA256:raise ValueError('Prepare a separate SKY130 adapter with --bipolar first.')
        for name,expected in manifest['files'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or file_digest(path)!=expected:raise ValueError('Locked PDK asset changed: '+name)
        tech=manifest['technology'];tech.update(package_root=str(root),package_lock={k:manifest[k] for k in ('id','revision','files')})
        report['process']=dict(id=manifest['id'],revision=manifest['revision'],manifest_sha256=file_digest(root/'package.json'),technology_sha256=TECH_SHA256)
        report['extraction_update']=json.loads((root/'PNP-EXTRACTION-UPDATE.json').read_text())
        tools={name:str(Path(getattr(args,name)).resolve()) if getattr(args,name) else '' for name in ('magic','netgen')}
        lock=json.loads((ROOT/'examples/physical-engine-lock.json').read_text());report['tools']={}
        for name,path in tools.items():
            if not path or not Path(path).is_file():raise ValueError('Install '+name+' before qualification.')
            version=execute([path,'-batch' if name=='netgen' else '--version'],out,timeout=20)
            if lock[name]['version'] not in version:raise ValueError('Use pinned '+name+' '+lock[name]['version'])
            atomic_write(out/(name+'-version.log'),version);report['tools'][name]=dict(sha256=file_digest(path),version_sha256=file_digest(out/(name+'-version.log')))
        report['source']={str(path):file_digest(ROOT/path) for path in ('icstudio/sky130_fixed_devices.py','icstudio/sky130_bipolar_rules.py','icstudio/sky130_devices.py','icstudio/sky130_layout.py','scripts/prepare_sky130_qualification.py','scripts/qualify_sky130_bipolar.py')}
        for count in (1,2,16):
            p,c=fixture(tech,count)
            if connectivity(p,c['id'])['issues']:raise ValueError('Native PNP terminal connectivity failed.')
            result=qualify(p,c,out/f'm{count}',tools);report['cases'].append(dict(name=f'm{count}',status='passed',**result))
        p,c=fixture(tech);shape=next(s for s in c['shapes'] if s.get('generator_role')=='fixed:65/20:0');edge=max(x for x,y in shape['points'])
        shape['points']=[[x+100 if x==edge else x,y] for x,y in shape['points']]
        result=qualify(p,c,out/'wrong-emitter',tools,True);report['cases'].append(dict(name='wrong-emitter',status='passed',**result));report['status']='passed'
    except Exception as exc:report.update(status='failed',error=str(exc),traceback=traceback.format_exc())
    atomic_write(out/'qualification.json',json.dumps(report,indent=2));print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
