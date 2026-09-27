"""Pinned public designs through Studio import, exchange, process DRC and LVS.

Original source defects remain required failures. Corrected design variants
are identified separately and never replace the original reference.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import atomic_write,clone,file_digest,load_project,save_project
from icstudio.interchange import export_layout,export_xschem,import_layout
from icstudio.layout_import import read_layout
from icstudio.native_migration import review_path
from icstudio.native_spice import netlist
from icstudio.layout_verification import reference,run
from icstudio.engines import magic_import,netgen_lvs,require_lvs_match
from icstudio.stream_contract import compare
from scripts.qualification_evidence import Report,magic_verify

LOCK=ROOT/'examples/open-projects/public-layouts-lock.json'


def fetch(destination):
    destination=Path(destination).resolve();lock=json.loads(LOCK.read_text());items=[]
    for name,entry in lock['designs'].items():
        for relative,sha in entry['files'].items():items.append((name,entry,relative,sha))
    def one(item):
        name,entry,relative,sha=item;path=destination/name/relative
        if not path.is_file():
            url=entry['repository'].replace('https://github.com/','https://raw.githubusercontent.com/')+'/'+entry['commit']+'/'+relative
            with urllib.request.urlopen(url,timeout=60) as response:data=response.read(20_000_001)
            if hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Source checksum mismatch: '+relative)
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        if file_digest(path)!=sha:raise ValueError('Pinned source changed: '+str(path))
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(one,items))
    return lock


def inline_netlist(path, *, known=None):
    """Inline only selected local include closures; retain their exact hashes."""
    files={};active=set();size=0;known=known or {}
    def read(file):
        nonlocal size
        file=Path(file).resolve()
        if file in active:raise ValueError('Recursive schematic include.')
        active.add(file);data=file.read_text();size+=len(data)
        if size>20_000_000 or len(files)>1000:raise ValueError('Reference include closure exceeds its budget.')
        files[str(file)]=file_digest(file)
        def include(match):
            name=match[1].strip('"\'');return read(known.get(name,file.parent/name))
        result=re.sub(r'(?im)^\s*\.(?:include|inc)\s+("[^"\n]+"|\'[^\'\n]+\'|\S+)\s*$',include,data)
        active.remove(file);return result
    return read(path),files


def linked_layout(path,technology,top):
    p,notes=read_layout(path);layers=p['pdk']['layers'];p['pdk']=clone(technology);p['pdk']['layers']=layers
    p['top']=next(c['id'] for c in p['cells'] if c['name']==top)
    return p


def qualify(a):
    report=Report(a.out,'public-layouts');out=report.output
    lock=fetch(a.source);report.data['public_sources']=lock
    report.data['lock_hashes']['examples/open-projects/public-layouts-lock.json']=file_digest(LOCK)
    pdk=a.pdk.resolve();m=json.loads((pdk/'package.json').read_text());tech=clone(m['technology'])
    tech['package_root']=str(pdk);tech['package_lock']={k:m[k] for k in ('id','revision','files')}
    tools=dict(magic=report.tool('magic',a.magic,['--version']),netgen=report.tool('netgen',a.netgen,['-batch']))
    technology=pdk/'libs.tech/magic/sky130A.tech';setup=pdk/'libs.tech/netgen/sky130A_setup.tcl'
    std=a.standard_cells.resolve();symbols=a.xschem_libraries.resolve()
    if not std.is_file():raise ValueError('Supply the pinned standard-cell SPICE library.')
    expected=json.loads((ROOT/'examples/sky130-reference-assets.json').read_text())
    upstream=json.loads((std.parents[4]/'upstream-lock.json').read_text())
    if upstream!=expected:raise ValueError('Use the complete checksummed SKY130 reference download.')
    report.data['standard_cell_library']=dict(path=str(std),sha256=file_digest(std),upstream=upstream)
    desktop=[]
    report.data['desktop_cases']=desktop
    for name,top in [('comparator','adc_comp_latch'),('common-mode','adc_vcm_generator'),('amplifier','opamp_v1')]:
        folder=out/name;folder.mkdir();state={}
        def import_schematic():
            source=a.source/('fulgor/xschem/opamp_diego/sch/opamp.sch' if name=='amplifier' else 'sar/xschem/'+top+'.sch')
            locations={'/foss/pdks/sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice':str(std)}
            r=review_path(source,libraries=[symbols],file_locations=locations)
            atomic_write(folder/'migration.json',json.dumps({k:v for k,v in r.items() if k!='candidate'},indent=2))
            if r['candidate'] is None:raise ValueError('Schematic migration blocked; see migration.json.')
            p=r['candidate'];save_project(p,folder/'schematic.icproj')
            atomic_write(folder/'native.spice',netlist(p,folder/'models',mode='lvs'))
            # Emitted model paths are relative to the native netlist directory.
            emitted=folder/'models/reference.spice';atomic_write(emitted,(folder/'native.spice').read_text())
            text,files=inline_netlist(emitted)
            atomic_write(folder/'native-selfcontained.spice',text)
            reftop='opamp' if name=='amplifier' else top
            state.update(schematic=p,reference=reference(text,reftop))
            source_deck=a.source/('fulgor/xschem/opamp_diego/netlist/opamp.spice' if name=='amplifier' else 'sar/spice/'+top+'.sch.spice')
            original,inputs=inline_netlist(source_deck,known=locations)
            if name=='amplifier':original=original.replace('**.subckt','.subckt').replace('**.ends','.ends')
            atomic_write(folder/'author-selfcontained.spice',original)
            require_lvs_match(netgen_lvs(tools['netgen'],folder/'author-selfcontained.spice',reftop,folder/'native-selfcontained.spice',reftop,setup,folder/'schematic-lvs'))
            return dict(cells=len(p['cells']),reference_sha256=state['reference']['sha256'],included_files=inputs,embedded_files=files,
                        note='Amplifier commented top wrapper enabled for comparison; circuit declarations unchanged.' if name=='amplifier' else '')
        report.case(name+'-schematic-import',import_schematic)
        def schematic_roundtrip():
            p=state['schematic'];export_xschem(p,folder/'xschem')
            topname=next(c['name'] for c in p['cells'] if c['id']==p['top'])
            r=review_path(folder/'xschem'/(topname+'.sch'))
            if not r['candidate']:raise ValueError('Reopening the exported Xschem schematic failed.')
            directory=folder/'reopened';atomic_write(directory/'reference.spice',netlist(r['candidate'],directory,mode='lvs'))
            text,_=inline_netlist(directory/'reference.spice');atomic_write(directory/'selfcontained.spice',text)
            require_lvs_match(netgen_lvs(tools['netgen'],folder/'native-selfcontained.spice',topname,directory/'selfcontained.spice',topname,setup,directory/'lvs'))
            return dict(status='passed')
        report.case(name+'-xschem-roundtrip',schematic_roundtrip)
        def import_geometry():
            if name=='amplifier':
                magic_import(tools['magic'],a.source/'fulgor/mag/opamp_v1.mag',technology,folder/'magic-import')
                source=folder/'magic-import/imported.gds'
            else:
                source=folder/'source.gds';source.write_bytes(gzip.decompress((a.source/('sar/gds/'+top+'.gds.gz')).read_bytes()))
            p=linked_layout(source,tech,top);save_project(p,folder/'layout.icproj')
            export_layout(p,folder/'studio.gds');result=compare(source,folder/'studio.gds')
            state.update(layout=p,source=source);return result
        report.case(name+'-layout-import',import_geometry)
        def physical(p,directory,ref=None,expected_match=None):
            ref=ref or state['reference'];r=run(p,p['top'],directory,tools,ref)
            lvs=next(s['status'] for s in r['stages'] if s['name']=='lvs')
            expected_match=(name!='amplifier') if expected_match is None else expected_match
            if r.get('drc_count')!=0 or lvs!=('passed' if expected_match else 'failed') or r['status']!=('passed' if expected_match else 'failed'):
                raise ValueError('Unexpected physical result: '+str(directory)+' '+r.get('error',''))
            if not expected_match:
                text=(directory/'lvs/lvs.log').read_text()
                if 'sky130_fd_pr__cap_mim_m3_1' not in text or 'Netlists do not match' not in text:raise ValueError('Expected capacitor polarity mismatch was not diagnosed.')
            return dict(drc=0,lvs=lvs,expected_lvs='matched' if expected_match else 'source capacitor polarity mismatch',report=str(directory.relative_to(out)/'report.json'))
        for route in ('imported','gds','oasis'):
            def action(route=route):
                p=state['layout']
                if route!='imported':
                    path=folder/('studio.'+('gds' if route=='gds' else 'oas'))
                    export_layout(p,path)
                    # Independent KLayout rewrite, no Studio sidecars involved.
                    import klayout.db as db
                    ly=db.Layout();ly.read(str(path));external=folder/('external'+path.suffix);ly.write(str(external))
                    p=linked_layout(external,tech,top);export_layout(p,folder/(route+'-reopened.gds'))
                    compare(state['source'],folder/(route+'-reopened.gds'))
                return physical(p,folder/('physical-'+route))
            report.case(name+'-'+route+'-drc-lvs',action)
        if 'reference' in state and 'layout' in state:
            atomic_write(folder/'reference.json',json.dumps(state['reference'],indent=2))
            desktop.append(dict(name=name,project=name+'/layout.icproj',reference=name+'/native-selfcontained.spice',top=state['reference']['top'],expected='failed' if name=='amplifier' else 'passed'))
        if name=='comparator' and 'layout' in state:
            def fault(kind):
                p=clone(state['layout']);ref=clone(state['reference']);cell=next(c for c in p['cells'] if c['id']==p['top'])
                if kind=='narrow-metal':
                    from icstudio.layout import rect
                    metal=next(l['name'] for l in p['pdk']['layers'] if (l['gds'],l['datatype'])==(68,20))
                    cell['shapes'].append(rect(metal,1000000,1000000,100,100))
                else:
                    text=ref['text'].replace('W=0.42','W=0.84')
                    if text==ref['text']:raise ValueError('Expected transistor-width control is missing.')
                    ref=reference(text,ref['top'])
                r=run(p,p['top'],folder/('fault-'+kind),tools,ref)
                if r['status']!='failed':raise ValueError('The deliberate physical defect was not rejected.')
                if kind=='narrow-metal' and not r.get('drc_count'):raise ValueError('The deliberate width fault was not found by DRC.')
                if kind=='device-width' and next(s['status'] for s in r['stages'] if s['name']=='lvs')!='failed':raise ValueError('LVS did not reject changed device dimensions.')
                return dict(status=r['status'],drc=r.get('drc_count'),findings=len(r['findings']))
            for kind in ('narrow-metal','device-width'):report.case('comparator-reject-'+kind,lambda kind=kind:fault(kind))
        if name=='amplifier' and 'layout' in state:
            def repair_capacitor():
                p=clone(state['schematic']);cell=next(c for c in p['cells'] if c['id']==p['top'])
                from icstudio.electrical_identity import partition
                cap=next(d for d in cell['devices'] if d['name']=='C1');before=partition(cell);pins=list(cap['nets'])
                if len(pins)!=2:raise ValueError('Expected a two-terminal compensation capacitor.')
                swapped={pins[0]:pins[1],pins[1]:pins[0]}
                expected=sorted(sorted((did,swapped[pin] if did==cap['id'] else pin) for did,pin in group) for group in before)
                cap['rotation']=(cap['rotation']+180)%360
                from icstudio.wiring import rebuild
                rebuild(cell,p)
                if partition(cell)!=expected:raise ValueError('Capacitor rotation did not swap exactly its two terminals.')
                save_project(p,folder/'corrected-schematic.icproj');directory=folder/'corrected'
                atomic_write(directory/'reference.spice',netlist(p,directory,mode='lvs'))
                text,_=inline_netlist(directory/'reference.spice');atomic_write(folder/'corrected-reference.spice',text)
                r=physical(state['layout'],folder/'physical-corrected',reference(text,'opamp'),True)
                r['correction']='Rotated schematic capacitor C1 by 180 degrees to match the existing physical bottom/top plate connections. Original source retained and still required to fail.'
                desktop.append(dict(name='amplifier-corrected',project=name+'/layout.icproj',reference=name+'/corrected-reference.spice',top='opamp',expected='passed'))
                return r
            report.case('amplifier-explicit-capacitor-repair',repair_capacitor)
    def inverter():
        folder=out/'inverter';records={}
        for name in ('inv1','inv1_bad'):
            source=a.source/('hello/'+name+'.gds');r=magic_verify(source,'sky130_fd_sc_hd__inv_1',technology,folder/name,tools['magic'],input_style='sky130()')
            log=netgen_lvs(tools['netgen'],a.source/'hello/inv1.spice','sky130_fd_sc_hd__inv_1',folder/name/'extracted.spice','sky130_fd_sc_hd__inv_1',setup,folder/name/'lvs')
            try:require_lvs_match(log);matched=True
            except ValueError:matched=False
            if matched!=(name=='inv1') or not r['drc']['count']:raise ValueError('Unexpected standalone standard-cell diagnostic.')
            p,_=read_layout(source);export_layout(p,folder/(name+'.gds'));compare(source,folder/(name+'.gds'))
            records[name]=dict(drc=r['drc']['count'],lvs=matched,rules=r['drc']['rules'])
        return dict(layouts=records,scope='Standalone standard-cell leaf lacks tap-cell context. These full-rule violations are source findings, not waived passing designs.')
    report.case('standalone-inverter-source-and-defect',inverter)
    atomic_write(out/'desktop-cases.json',json.dumps(desktop,indent=2)+'\n')
    return report.finish()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','pdk','standard-cells','xschem-libraries','out'):ap.add_argument('--'+name,type=Path,required=True)
    for name in ('magic','netgen'):ap.add_argument('--'+name,required=True)
    a=ap.parse_args();return qualify(a)


if __name__=='__main__':raise SystemExit(main())
