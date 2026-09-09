"""Cancellable worker entry points for layout planning and file comparison."""
from pathlib import Path
import shutil
from .model import clone, design_digest, digest, file_digest, now


def run(p,cid,settings,directory,progress=lambda *_:None):
    result={'schema':1,'created':now(),'project_id':p['id'],'cell_id':cid,'revision':p['revision'],
            'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'engine':'KLayout geometry',
            'x':[],'traces':{},'phase':{},'operating_point':{},'x_label':'','y_label':'','log':''}
    import klayout
    from .build_info import WORKFLOW_SOURCE_HASH
    result.update(engine_version=klayout.__version__,workflow_hash=WORKFLOW_SOURCE_HASH)
    if settings['type']=='layout_route':
        from .layout_routing import plan,matched_pair,shield
        functions={'route':plan,'matched_pair':matched_pair,'shield':shield}
        progress(.05,'Planning route and checking conductor and via clearances')
        result['layout_proposal']=functions[settings['operation']](p,cid,**settings['arguments'])
        result['warnings']=[result['layout_proposal']['qualification']]
    elif settings['type']=='layout_compare':
        from .layout_inspection import compare_files
        from .interchange import export_layout
        path=Path(directory)/'current.gds';reference=Path(settings['reference'])
        if file_digest(reference)!=settings['reference_sha256']:raise ValueError('The reference layout changed. Start a new comparison.')
        snapshot=Path(directory)/('reference'+reference.suffix.lower())
        if snapshot.resolve()!=reference.resolve():shutil.copyfile(reference,snapshot)
        if file_digest(snapshot)!=settings['reference_sha256']:raise ValueError('The reference changed while its snapshot was copied.')
        progress(.05,'Exporting the selected design snapshot');export_layout(p,path)
        result['layout_comparison']=compare_files(path,snapshot,next(c['name'] for c in p['cells'] if c['id']==cid),settings.get('reference_top',''))
        if result['layout_comparison']['sha256'][1]!=settings['reference_sha256']:raise ValueError('The reference changed during comparison.')
        result['reference_snapshot_file']=snapshot.name
        result['warnings']=[result['layout_comparison']['qualification']]
    else:raise ValueError('Unknown layout job.')
    progress(1,'Layout result ready for review');return result


def replay_job(row):
    job=clone(row['job']);settings=job['settings']
    if settings.get('type')=='layout_compare' and row.get('result',{}).get('reference_snapshot_file'):
        name=row['result']['reference_snapshot_file']
        if Path(name).name!=name:raise ValueError('Invalid comparison snapshot filename.')
        snapshot=Path(row['path'])/name
        if not snapshot.is_file() or file_digest(snapshot)!=settings['reference_sha256']:raise ValueError('The saved comparison reference is missing or changed.')
        settings['reference']=str(snapshot.resolve())
    return job
