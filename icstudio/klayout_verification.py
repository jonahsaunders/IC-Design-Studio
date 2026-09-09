"""KLayout batch rule execution and native report-database interchange."""
import json
from pathlib import Path
from .model import atomic_write, file_digest, digest, design_digest, now


def read_report(path):
    import klayout.rdb as rdb
    report=rdb.ReportDatabase();report.load(str(path))
    if report.num_items()>100000:raise ValueError('The report exceeds 100,000 findings; filter it in KLayout before importing.')
    findings=[]
    for item in report.each_item():
        values=[];boxes=[]
        for value in item.each_value():
            values.append(value.to_s())
            for kind in ('box','polygon','path','edge','edge_pair'):
                if getattr(value,'is_'+kind)():
                    geom=getattr(value,kind)();box=geom if kind=='box' else geom.bbox()
                    boxes.append([box.left,box.bottom,box.right,box.top]);break
        findings.append({'cell':report.cell_by_id(item.cell_id()).name(),'rule':report.category_by_id(item.category_id()).path(),'details':' · '.join(values),'boxes_um':boxes,'comment':item.comment})
    return {'name':report.name(),'top':report.top_cell_name,'count':len(findings),'findings':findings,'report_sha256':file_digest(path)}


def run(p,cid,settings,directory,progress=lambda *_:None):
    from .interchange import export_layout
    from .engines import execute
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    executable=Path(settings['executable']);text=settings['runset_text']
    if file_digest(executable)!=settings['executable_sha256'] or digest(text)!=settings['runset_hash']:raise ValueError('The planned KLayout executable or rule script changed. Plan a new verification run.')
    script=root/'rules.drc';layout=root/'input.gds';report=root/'findings.lyrdb';cwd=root
    if settings.get('rule_bundle'):
        from .rule_bundle import materialize
        bundle=settings['rule_bundle']
        if bundle['files'].get(bundle['entry'])!=text:raise ValueError('Rule bundle entry differs from the planned script.')
        cwd=root/'rule-bundle';script=materialize(bundle,settings['bundle_hash'],cwd)
        atomic_write(root/'rule-bundle.json',json.dumps({'sha256':settings['bundle_hash'],'entry':bundle['entry'],
            'files':{name:digest(content) for name,content in bundle['files'].items()}},indent=2))
    else:atomic_write(script,text)
    export_layout(p,layout);top=next(c['name'] for c in p['cells'] if c['id']==cid)
    args=[str(executable),'-b','-r',str(script),'-rd','input='+str(layout),'-rd','top='+top,'-rd','report='+str(report)]
    atomic_write(root/'command.json',json.dumps(args,indent=2));progress(.05,'Running KLayout rule script')
    try:log=execute(args,cwd,timeout=int(settings.get('timeout',600)),on_line=lambda line:progress(.5,line))
    except Exception as exc:atomic_write(root/'engine.log',str(exc));raise
    atomic_write(root/'engine.log',log)
    if not report.is_file():raise ValueError('KLayout produced no report. The rule script must write its report to $report.')
    data=read_report(report);progress(1,'KLayout report loaded')
    result={'schema':1,'created':now(),'project_id':p['id'],'revision':p['revision'],'cell_id':cid,'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'rule_hash':settings['runset_hash'],'settings':settings,'engine':'KLayout batch DRC','engine_hash':settings['executable_sha256'],'klayout_report':data,'gds_hash':file_digest(layout),'x':[],'x_label':'','y_label':'','traces':{},'phase':{},'operating_point':{},'log':log,'warnings':['Zero findings means this rule script reported none; coverage and process qualification depend on the selected rules.']}
    atomic_write(root/'verification.json',json.dumps({k:result[k] for k in ('design_hash','pdk_hash','rule_hash','engine_hash','gds_hash','klayout_report')},indent=2));return result
