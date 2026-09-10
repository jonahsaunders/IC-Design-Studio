"""Non-waveform jobs share the cancellable desktop worker protocol."""
from .model import now,digest,design_digest
from .build_info import WORKFLOW_SOURCE_HASH

def check_job(p,cid,kind,progress=lambda *_:None):
    from .physical import connectivity,capacitance_estimate,matching_checks
    from .layout import drc
    progress(.1,'Checking physical design')
    data=connectivity(p,cid) if kind=='connectivity' else capacitance_estimate(p,cid) if kind=='parasitics' else {'issues':drc(p,cid)+matching_checks(p,cid)}
    return {'schema':1,'created':now(),'project_id':p['id'],'revision':p['revision'],'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'rule_hash':digest(p['pdk']['layers']),'cell_id':cid,'settings':{'type':kind},'engine':'KLayout geometry / IC Studio physical checks','engine_hash':digest({'workflow':WORKFLOW_SOURCE_HASH,'klayout':__import__('klayout.db',fromlist=['__version__']).__version__}),'x':[],'x_label':'','y_label':'','traces':{},'phase':{},'operating_point':{},'warnings':[data.get('qualification','Generic geometry rules only.')],'physical_result':data}

def post_layout_job(p,job,directory,progress):
    from .physical import capacitance_estimate,with_parasitics
    from .simulation import run
    from .engines import run_ngspice
    cid=job['cell'];extraction=capacitance_estimate(p,cid);extracted=with_parasitics(p,cid,extraction);settings=job['settings']['analysis']
    r=run(extracted,cid,settings,progress) if job['engine']=='builtin' else run_ngspice(extracted,cid,settings,job['executable'],directory,progress)
    r['extracted_design_hash']=r['design_hash'];r['design_hash']=design_digest(p);r['settings']={'type':'post_layout','analysis':settings};r['extraction']=extraction;r['warnings'].append(extraction['qualification']);return r
