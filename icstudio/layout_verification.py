"""Fresh process DRC and LVS for imported layouts, without a simulation bench."""
import json
import hashlib
from pathlib import Path
import re
import shutil

from .model import atomic_write, clone, design_digest, file_digest, now, save_project, validate
from .engines import execute, netgen_lvs, require_lvs_match, tcl_word

STAGES=('preflight','layout_export','drc','lvs_extraction','lvs','integrity')


def reference(text, top):
    """Capture a self-contained schematic reference before queueing the job."""
    from .model import NAME, NET
    if not isinstance(text,str) or len(text)>10_000_000 or not NAME.fullmatch(top):
        raise ValueError('Choose a self-contained SPICE netlist under 10 MB and a valid schematic cell name.')
    logical=re.sub(r'\n[ \t]*\+[ \t]*',' ',text)
    if re.search(r'(?im)^\s*\.(include|inc|lib)\b',logical):
        raise ValueError('LVS needs a self-contained schematic netlist. Resolve external includes before selecting this reference.')
    declarations=re.findall(r'(?im)^\s*\.subckt\s+(\S+)([^\n]*)',logical)
    matches=[tail for name,tail in declarations if name.casefold()==top.casefold()]
    if len(matches)!=1:raise ValueError('The schematic reference must declare exactly one .subckt '+top+'.')
    ports=re.split(r'\s+(?:params:|\w+\s*=)',matches[0],maxsplit=1,flags=re.I)[0].split()
    if not ports or len(set(p.casefold() for p in ports))!=len(ports) or any(not NET.fullmatch(p) for p in ports):
        raise ValueError('The schematic reference needs unique named terminals.')
    if not re.search(r'(?im)^\s*[mxrcdqjb]\S*\s+',logical):raise ValueError('The reference has no circuit devices.')
    return dict(text=text,top=top,ports=ports,sha256=hashlib.sha256(text.encode()).hexdigest())


def verification_stream(source, top, ports, target, *, pin_layers):
    """Flatten only the private engine input; retain the editable hierarchy.

    Child-local labels cannot become global connections when flattening.
    Legacy label-only GDS uses the selected schematic as its top-port contract.
    Explicit pin-purpose labels must all belong to that interface.
    """
    import klayout.db as db
    ly=db.Layout();ly.read(str(source));cell=ly.cell(top)
    if cell is None:raise ValueError('Layout top is missing: '+top)
    expected={p.casefold() for p in ports};found=set();explicit=set();removed=0
    def mask(c,i):
        shapes=c.begin_shapes_rec(i)
        shapes.shape_flags=db.Shapes.SBoxes|db.Shapes.SPolygons|db.Shapes.SPaths
        return db.Region(shapes)
    before={i:mask(cell,i) for i in ly.layer_indexes()}
    for c in ly.each_cell():
        for i in ly.layer_indexes():
            info=ly.get_info(i)
            for s in list(c.shapes(i).each()):
                if not s.is_text():continue
                name=s.text.string.casefold()
                if c==cell and (info.layer,info.datatype) in pin_layers:explicit.add(name)
                if c==cell and name in expected:found.add(name)
                else:s.delete();removed+=1
    if explicit-expected:raise ValueError('Layout has extra explicit terminals: '+', '.join(sorted(explicit-expected)))
    if expected-found:raise ValueError('Missing top-level layout labels: '+', '.join(sorted(expected-found)))
    cells=ly.cells();cell.flatten(True)
    for i,region in before.items():
        if not (region ^ mask(cell,i)).is_empty():raise ValueError('Flattening changed physical mask geometry on '+str(ly.get_info(i))+'.')
    ly.write(str(target))
    # Check the bytes delivered to the engine, not only the in-memory layout.
    check=db.Layout();check.read(str(target));other=check.cell(top)
    for i,region in before.items():
        index=check.find_layer(ly.get_info(i))
        actual=mask(other,index) if index is not None else db.Region()
        if not (region ^ actual).is_empty():raise ValueError('Verification stream changed physical mask geometry.')
    return dict(source_sha256=file_digest(source),sha256=file_digest(target),source_cells=cells,
                geometry='Exact flattened region XOR on every layer/datatype',
                removed_noninterface_labels=removed,ports=ports,
                interface='Explicit top pin labels checked; legacy top labels selected by schematic terminals.',
                hierarchy='Flattened only in private verification input; original project and stream retained.')


def run(p,cid,output,tools,selected,progress=lambda *_:None,blocked_reason=None):
    from .interchange import export_layout
    from .interoperability import tool_asset
    from .process_adapters import ADAPTERS
    from .silicon_flow import magic_script
    from .external_tools import extraction_commands,check_extracted_interface
    from .hierarchical_flow import verify_integrity,record_stage
    out=Path(output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty verification directory.')
    out.mkdir(parents=True,exist_ok=True);c=next(c for c in p['cells'] if c['id']==cid)
    report=dict(schema=3,created=now(),status='running',mode='drc_lvs',cell_id=cid,cell_name=c['name'],
                design_hash=design_digest(p),stages=[],qualification='Process DRC and strict LVS for the recorded layout, schematic reference and PDK. No simulation, antenna/density signoff or fabrication signoff.')
    assets={};resolved={};files={};ref={};contract={}
    def publish():atomic_write(out/'report.json',json.dumps(report,indent=2,allow_nan=False))
    def stage(name,fn):return record_stage(report,name,fn,publish,progress)
    def preflight():
        if blocked_reason:raise ValueError(blocked_reason)
        validate(p);ref.update(reference(selected['text'],selected['top']))
        if ref!=selected:raise ValueError('The captured schematic reference changed before verification.')
        report['reference']={k:v for k,v in ref.items() if k!='text'}
        adapter=ADAPTERS.get(p['pdk'].get('package_lock',{}).get('id'))
        contract.update(p['pdk'].get('interoperability',{}).get('tools',{}).get('magic',{}))
        style=contract.get('drc_style','drc(full)' if adapter else None)
        if not style:raise ValueError('Link a physical PDK with an explicit full Magic DRC style.')
        report['magic_drc_style']=style
        assets['technology']=tool_asset(p['pdk'],'magic','technology',adapter.technology_file if adapter else None)
        assets['setup']=tool_asset(p['pdk'],'netgen','setup',adapter.setup_file if adapter else None)
        for name in ('magic','netgen'):
            path=Path(shutil.which(tools.get(name,'') or name) or tools.get(name,'') or name)
            if not path.is_file():raise ValueError('Configure the '+name+' physical engine.')
            path=path.resolve();resolved[name]=dict(path=str(path),sha256=file_digest(path))
            atomic_write(out/(name+'-version.log'),execute([str(path),'-batch' if name=='netgen' else '--version'],out,timeout=20))
        save_project(p,out/'input.icproj');atomic_write(out/'schematic.spice',ref['text'])
        from .native_spice import lvs_defaults
        comparison,defaults=lvs_defaults(ref['text']);atomic_write(out/'schematic-lvs.spice',comparison)
        report['reference_defaults']=defaults
        files.update({n:file_digest(out/n) for n in ('input.icproj','schematic.spice','schematic-lvs.spice')})
        return dict(assets={str(v):file_digest(v) for v in assets.values()},tools=resolved,reference=report['reference'],model_defaults=defaults)
    try:
        pre=stage('preflight',preflight)
        def stream():
            q=clone(p);q['top']=cid;export_layout(q,out/'original.gds')
            # SKY130 distinguishes pin-purpose 16 from general label-purpose 5.
            # Other PDKs must declare explicit pin purposes in their layer map.
            purposes=p['pdk'].get('interoperability',{}).get('layer_purposes',{})
            pins={(v['gds'],v['datatype']) for v in p['pdk']['layers'] if purposes.get(v['name'],v.get('purpose'))=='pin'}
            if p['pdk'].get('package_lock',{}).get('id')=='sky130A':pins|={(i,16) for i in range(64,73)}
            r=verification_stream(out/'original.gds',c['name'],ref['ports'],out/'layout.gds',pin_layers=pins)
            files.update({n:file_digest(out/n) for n in ('original.gds','layout.gds')});return r
        stage('layout_export',stream)
        def magic(folder,commands):
            log=magic_script(resolved['magic']['path'],assets['technology'],out/'layout.gds',c['name'],ref['ports'],out/folder,commands)
            # Keep the actual rule/extraction logs in the immutable evidence
            # inventory, including runs that demonstrate a repairable defect.
            for path in (out/folder).glob('*.log'):
                files[path.relative_to(out).as_posix()]=file_digest(path)
            return log
        def drc():
            commands='snap internal\nselect top cell\nbox values {*}[select bbox]\nbox grow c 10um\ndrc style '+tcl_word(report['magic_drc_style'])+'\ndrc ignore none\ndrc check\ndrc catchup\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\nputs "STUDIO_MAGIC_SCALE [cif scale out]"\n'
            commands+='set f [open findings.tsv w]\nforeach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\n'
            log=magic('drc',commands);counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)
            if len(counts)!=1 or re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)!=[report['magic_drc_style']]:raise ValueError('Magic did not finish the selected full DRC check.')
            report['drc_count']=int(counts[0])
            if report['drc_count']:raise ValueError(str(report['drc_count'])+' Magic DRC violations; see findings.tsv.')
            return dict(violations=0,style=report['magic_drc_style'])
        # Keep LVS evidence even when the original design fails a layout rule.
        failures=[]
        try:stage('drc',drc)
        except (ValueError,OSError) as exc:failures.append(str(exc))
        def extract():
            commands,_=extraction_commands('lvs',{'hierarchy':False})
            magic('lvs-extraction',commands+'ext2spice -o extracted.spice')
            path=out/'lvs-extraction/extracted.spice'
            check_extracted_interface(path,c['name'],ref['ports'],p['pdk'])
            files['lvs-extraction/extracted.spice']=file_digest(path)
            return dict(deck='lvs-extraction/extracted.spice',sha256=files['lvs-extraction/extracted.spice'])
        stage('lvs_extraction',extract)
        def lvs():
            log=netgen_lvs(resolved['netgen']['path'],out/'schematic-lvs.spice',ref['top'],out/'lvs-extraction/extracted.spice',c['name'],assets['setup'],out/'lvs')
            files['lvs/lvs.log']=file_digest(out/'lvs/lvs.log')
            require_lvs_match(log);return dict(unique_match=True,log='lvs/lvs.log')
        try:stage('lvs',lvs)
        except (ValueError,OSError) as exc:failures.append(str(exc))
        stage('integrity',lambda:verify_integrity(out,files,pre['assets'],resolved))
        report['status']='failed' if failures else 'passed'
        if failures:report['error']='; '.join(failures)
    except InterruptedError:raise
    except Exception as exc:
        report.update(status='blocked' if not report['stages'] or report['stages'][-1]['name']=='preflight' else 'failed',error=str(exc))
    finally:
        for name in STAGES:
            if name not in {s['name'] for s in report['stages']}:report['stages'].append(dict(name=name,status='not_run'))
        from .verification_navigation import collect
        report['findings']=collect(p,cid,out);publish()
    return report
