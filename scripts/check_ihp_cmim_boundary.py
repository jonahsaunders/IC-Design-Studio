"""Independent finite source-geometry boundary readback; no installed or signoff claim."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.ihp_cmim_boundary_audit import circuit
from icstudio.ihp_klayout_drc import assets,read_report
from icstudio.stream_contract import compare


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_bytes())
def require(value,reason):
    if not value: raise ValueError(reason)


def native_fault(path,kind):
    text=Path(path).read_text();rows=[v.split() for v in text.splitlines() if v.strip() and not v.lstrip().startswith(('*','.'))]
    headers=re.findall(r'(?im)^\.subckt\s+coupon\s+([^\n]+)',text)
    require(len(headers)==1 and len(rows)==1 and rows[0][3]=='cap_cmim','Missing actual fault capacitor.')
    if kind=='missing-contacts':
        require(headers[0].split()==['C2'] and rows[0][2]=='C2' and rows[0][1].startswith('\\$'), 'Missing contact did not open top terminal.')
    elif kind=='plate-short':
        require(headers[0].split()==['C1|C2'] and rows[0][1:3]==['C1|C2','C1|C2'], 'Plate bridge did not short both terminals.')
    else:raise ValueError('Unknown topology fault.')
    normalized='.subckt coupon C1 C2\n'+' '.join([rows[0][0],'C1','C2',*rows[0][3:]])+'\n.ends coupon\n'
    circuit(normalized,74.98)
    return dict(header=headers[0],terminals=rows[0][1:3])


def geometry(path,area,width,length,rotation=0):
    import klayout.db as k
    ly=k.Layout();ly.read(str(path));require(ly.dbu==.001 and len(ly.top_cells())==1,'Unexpected written stream units/top.')
    cell=ly.top_cell();masks={}
    for pair in ((36,0),(67,0),(126,0),(129,0)):
        index=ly.find_layer(*pair);require(index is not None,'Missing written conductor layer.')
        masks[pair]=k.Region(cell.begin_shapes_rec(index)).merged()
    cap=masks[36,0];polys=list(cap.each());require(len(polys)==1 and polys[0].is_box() and cap.area()==area,'Written MIM geometry differs.')
    box=polys[0].bbox();x,y=(width,length) if rotation==0 else (length,width)
    require([box.left,box.bottom,box.right,box.top]==[-x//2,-y//2,x//2,y//2],'Written mask bounding box or rotation differs.')
    require((masks[67,0]^cap.sized(600)).is_empty(),'Metal5 enclosure differs.')
    require((masks[126,0]^cap.sized(-200)).is_empty(),'TopMetal1 mask differs.')
    require(not masks[129,0].is_empty() and (masks[129,0]-masks[126,0]).is_empty(),'Missing or displaced Vmim cuts.')
    cuts=list(masks[129,0].each())
    require(all(v.is_box() and v.bbox().width()==420 and v.bbox().height()==420 for v in cuts),'Vmim cut geometry differs.')
    if width==75000:require(len(cuts)==3481 and masks[129,0].area()==614048400,'Vmim contact array differs.')
    labels=[]
    for index in ly.layer_indexes():
        info=ly.get_info(index)
        for shape in cell.shapes(index).each():
            if shape.is_text():
                t=shape.text;labels.append((t.string,info.layer,info.datatype,t.x,t.y))
    # Width-fault devices have the same centered source recipe with a 73 um
    # bottom-plate label offset 100 nm outside the right edge.
    end=width//2+100
    expected={('C1',126,2,0,0),('C2',67,2,end,0) if rotation==0 else ('C2',67,2,0,end)}
    require(len(labels)==2 and set(labels)==expected,'Written pin label roles, layers or positions differ.')
    return dict(area_nm2=area,bounds=str(polys[0].bbox()),cuts=len(list(masks[129,0].each())))


def stages(report):return {s['name']:s['status'] for s in report['stages']}


def member(root,name):
    p=Path(name);require(not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name and 'tmpuxoell2b' not in p.parts,'Unsafe retained member.')
    for parent in (p,*p.parents):
        if str(parent)!='.':
            target=root/parent
            require(not target.is_symlink() and not getattr(target,'is_junction',lambda:False)(),'Linked retained member.')
    target=root/p;require(target.resolve().is_relative_to(root),'Escaping retained member.')
    return target


def decks(folder,origin):
    assets(folder/'drc/rules');result={}
    for name in ('main','maximal'):
        path=folder/'drc'/name/'findings.lyrdb';parsed=read_report(path)
        require(parsed['top']=='coupon','Native DRC report top differs.')
        console=(folder/'drc'/name/'console.log').read_text()
        marker="KLayout DRC run for tables 'main' completed in" if name=='main' else 'KLayout DRC run for maximum ruleSet completed in'
        require(marker in console,'Native DRC tool did not complete.')
        if name=='main':require(all(f'{switch} enabled: true' in console for switch in ('FEOL','BEOL','OFFGRID','ANGLE','PIN','FORBIDDEN','RECOMMENDED')),'Required main deck switch disabled.')
        base=PurePosixPath(origin);bundle=base/'drc/rules';entry='ihp-sg13g2.drc' if name=='main' else 'rule_decks/sg13g2_maximal.drc'
        settings=[('input',base/'original.gds'),('topcell','coupon'),('report',base/'drc'/name/'findings.lyrdb'),('log',base/'drc'/name/'native.log'),
                  ('run_mode','flat'),('threads','1'),('drc_json',bundle/'sg13g2_tech_mod.json'),('drc_json_default',bundle/'rule_decks/sg13g2_tech_default.json')]
        command=['/opt/icstudio/bin/klayout','-b','-r',str(bundle/entry)]
        for key,value in settings:command+=['-rd',key+'='+str(value)]
        require(load(folder/'drc'/name/'command.json')==command,'Native deck, command or input binding differs.')
        result[name]=[f['rule'] for f in parsed['findings']]
    return result


def bound_files(folder,report):
    stage=next((v for v in report['stages'] if v['name']=='integrity'),None)
    if stage and stage['status']=='passed':
        for name,digest in stage['evidence']['files'].items():
            p=Path(name);require(not p.is_absolute() and '..' not in p.parts,'Unsafe retained member path.')
            require(sha(folder/p)==digest,'Retained physical evidence changed: '+name)


def extraction(folder,origin):
    base=PurePosixPath(origin)/'lvs-extraction'
    settings=[('input',base/'labels.gds'),('topcell','coupon'),('report',base/'extraction.lvsdb'),('target_netlist',base/'native.cir'),
        ('log',base/'native.log'),('run_mode','flat'),('net_only','true'),('top_lvl_pins','true'),('no_simplify','true'),
        ('combine_devices','false'),('purge','false'),('purge_nets','false'),('purge_devices','false'),('implicit_nets',''),('disable_tap_extraction','false')]
    command=['/opt/icstudio/bin/klayout','-b','-r',str(base/'deck/sg13g2.lvs')]
    for key,value in settings:command+=['-rd',key+'='+str(value)]
    require(load(folder/'lvs-extraction/command.json')==command,'Extraction command or unfiltered settings differ.')
    log=(folder/'lvs-extraction/console.log').read_text()
    require(all(v in log for v in ('LVS Total Run time','[layout_netlist] simplify: SKIPPED','[layout_netlist] combine_devices: SKIPPED',
        '[layout_netlist] purge: SKIPPED','[layout_netlist] purge_nets: SKIPPED','[layout_netlist] purge_devices: SKIPPED')),'Native extraction did not complete unfiltered.')


def audit(root,source,manifest_path,result_path,before_path,after_path,evidence_manifest):
    root=Path(root).resolve();source=Path(source).resolve();manifest=load(manifest_path);run=load(result_path)
    require(run['returncode']==0 and run['sources_and_runtime_unchanged'] is True,'Frozen source/runtime run failed.')
    require(sha(manifest_path)==run['source_manifest_sha256'],'Source manifest binding differs.')
    require(sha(before_path)==run['runtime_before_sha256']==run['runtime_after_sha256']==sha(after_path), 'Runtime snapshots differ.')
    require(load(before_path)==load(after_path),'Runtime changed.')
    for name,digest in manifest['files'].items():
        require(sha(member(source,name))==digest,'Frozen source changed: '+name)
    evidence=load(evidence_manifest)
    require(evidence['producer_result_sha256']==sha(result_path),'Evidence inventory references a different run receipt.')
    for name,digest in evidence['files'].items():
        require(sha(member(root,name))==digest,'Evidence inventory changed: '+name)
    required={'report.json'}
    for case in ('below','at','above'):
        for angle in (0,90):
            folder=f'{case}-{angle}'
            required.update(f'{folder}/{name}' for name in ('report.json','original.gds','schematic-lvs.spice','lvs-extraction/native.cir','lvs-extraction/extracted.spice','lvs/lvs.log','drc/main/command.json','drc/maximal/command.json','drc/main/findings.lyrdb','drc/maximal/findings.lyrdb'))
            required.add(folder+'.oas')
    for fault in ('wrong-width','missing-contacts','plate-short','swapped-reference'):
        folder='fault-'+fault
        required.update(f'{folder}/{name}' for name in ('report.json','original.gds','schematic-lvs.spice','lvs-extraction/native.cir','drc/main/command.json','drc/maximal/command.json','drc/main/findings.lyrdb','drc/maximal/findings.lyrdb'))
    for folder in [f'{case}-{angle}' for case in ('below','at','above') for angle in (0,90)]+['fault-'+f for f in ('wrong-width','missing-contacts','plate-short','swapped-reference')]:
        required.update(f'{folder}/{name}' for name in ('lvs-extraction/command.json','lvs-extraction/console.log','lvs-extraction/labels.gds','drc/main/console.log','drc/maximal/console.log'))
    for fault in ('wrong-width','swapped-reference'):required.add(f'fault-{fault}/lvs/lvs.log')
    require(required<=set(evidence['files']),'Evidence inventory omits a required raw member.')
    report=load(root/'report.json');require(report['status']=='OBSERVED' and report['pilot'] is False and report['reference_form']=='physical-C' and report['qualified'] is False and report['chunk_complete'] is False,'Wrong producer scope.')
    cases={(v['case'],v['rotation']):v for v in report['cases']};expect={'below':(74.98,5623500000),'at':(75.0,5625000000),'above':(75.02,5626500000)}
    require(len(report['cases'])==6 and set(cases)=={(n,r) for n in expect for r in (0,90)},'Incomplete boundary selection.')
    result=[]
    for (name,rotation),row in cases.items():
        length,area=expect[name];folder=root/f'{name}-{rotation}';native=load(folder/'report.json');ss=stages(native)
        require(row['length_um']==length and row['status']=='OBSERVED' and sha(folder/'report.json')==row['physical']['report_sha256'],'Boundary receipt differs.')
        require(all(ss[n]=='passed' for n in ('preflight','layout_export','lvs_extraction','lvs','integrity')),'Boundary native extraction/LVS incomplete.')
        expected_drc='failed' if name=='above' else 'passed';require(ss['drc']==expected_drc,'Boundary DRC outcome differs.')
        origin=PurePosixPath(manifest['source']).parent/'full'/folder.name
        actual_decks=decks(folder,origin);require(actual_decks=={'main':[],'maximal':["'MIM.g'"] if name=='above' else []},'Unexpected public deck findings.')
        bound_files(folder,native);extraction(folder,origin);mask=geometry(folder/'original.gds',area,75000,int(round(length*1000)),rotation)
        compare(folder/'original.gds',root/f'{name}-{rotation}.oas',text_presentation=False)
        for path in ('lvs-extraction/native.cir','lvs-extraction/extracted.spice','schematic-lvs.spice'):circuit((folder/path).read_text(),length)
        log=(folder/'lvs/lvs.log').read_text();require('Final result: Circuits match uniquely.' in log and 'Cell pin lists are equivalent.' in log and not re.search(r'property errors were found|\*\*mismatch\*\*|disconnected|altered to match',log,re.I),'Native strict LVS did not establish unique clean match.')
        result.append(dict(case=name,rotation=rotation,geometry=mask,decks=actual_decks))
    faults={v['fault']:v for v in report['faults']};require(len(report['faults'])==4 and set(faults)=={'wrong-width','missing-contacts','plate-short','swapped-reference'},'Incomplete fault selection.')
    for kind,row in faults.items():
        folder=root/('fault-'+kind);native=load(folder/'report.json');ss=stages(native);require(row['status']=='OBSERVED' and sha(folder/'report.json')==row['physical']['report_sha256'],'Fault receipt differs.')
        require(ss['preflight']==ss['layout_export']=='passed','Fault did not reach native tools.');origin=PurePosixPath(manifest['source']).parent/'full'/folder.name
        actual=decks(folder,origin);extraction(folder,origin);bound_files(folder,native)
        if kind in ('missing-contacts','plate-short'):
            require(ss['lvs_extraction']=='failed','Physical connectivity fault escaped extraction.')
            native_fault(folder/'lvs-extraction/native.cir',kind)
        elif kind=='wrong-width':
            require(ss['drc']=='passed' and ss['lvs_extraction']=='passed' and ss['lvs']=='failed' and actual=={'main':[],'maximal':[]},'Width control was not clean DRC plus native LVS mismatch.')
            geometry(folder/'original.gds',5473540000,73000,74980)
            circuit((folder/'lvs-extraction/native.cir').read_text(),74.98,73)
            circuit((folder/'schematic-lvs.spice').read_text(),74.98)
            log=(folder/'lvs/lvs.log').read_text();require('Property errors were found.' in log,'Width property mismatch not established.')
        else:
            require(ss['lvs_extraction']=='passed' and ss['lvs']=='failed','Swapped terminal control escaped native LVS.')
            circuit((folder/'lvs-extraction/native.cir').read_text(),74.98)
            circuit((folder/'schematic-lvs.spice').read_text(),74.98,terminals=('C2','C1'))
            try:circuit((folder/'schematic-lvs.spice').read_text(),74.98)
            except ValueError:pass
            else:raise ValueError('Swapped reference escaped independent ordered pin check.')
            require('Final result: Top level cell failed pin matching.' in (folder/'lvs/lvs.log').read_text(),'Native swapped-pin failure absent.')
    return dict(status='PASS_BOUNDARY',scope=__doc__,qualified=False,chunk_complete=False,cases=result,faults=sorted(faults),
                source_manifest_sha256=sha(manifest_path),evidence_manifest_sha256=sha(evidence_manifest),
                producer_report_sha256=sha(root/'report.json'),run_result_sha256=sha(result_path),
                runtime_before_sha256=sha(before_path),runtime_after_sha256=sha(after_path),
                reader_sha256=sha(__file__),netlist_reader_sha256=sha(ROOT/'scripts/ihp_cmim_boundary_audit.py'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('root','source','source-manifest','run-result','runtime-before','runtime-after','evidence-manifest','out'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();require(not a.out.exists(),'Choose a fresh audit output.')
    result=audit(a.root,a.source,a.source_manifest,a.run_result,a.runtime_before,a.runtime_after,a.evidence_manifest)
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
