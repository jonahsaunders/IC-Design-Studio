"""Durable job lifecycle gates publication and replay of saved results."""
import json
from pathlib import Path
from .model import atomic_write,now,design_digest


def state(directory,status,**extra):
    atomic_write(Path(directory)/'status.json',json.dumps({'status':status,'updated':now(),**extra},indent=2))


def read_result(path,project_id,require_complete=True):
    path=Path(path);status=path.parent/'status.json'
    if status.exists() and require_complete and json.loads(status.read_text())['status']!='complete':raise ValueError('Run was not completed; result is not publishable.')
    result=json.loads(path.read_text());job=json.loads((path.parent/'input.json').read_text())
    if result.get('project_id')!=project_id or job['project']['id']!=project_id:raise ValueError('Result belongs to a different project.')
    if result.get('cell_id')!=job['cell'] or result.get('design_hash')!=design_digest(job['project']):raise ValueError('Result does not match its saved input.')
    if job.get('settings',{}).get('type')=='digital':
        from .digital_flow import validate_result
        from .digital import source_hash
        validate_result(result,path.parent)
        if result.get('settings')!=job['settings'] or result['digital_result'].get('source_hash')!=source_hash(job['project']['digital']):
            raise ValueError('Digital result does not match its saved settings or sources.')
    elif not isinstance(result.get('traces'),dict) or not isinstance(result.get('x'),list):raise ValueError('Invalid result structure.')
    if result.get('xschem_cases') or result.get('analysis_cases'):
        # Raw captures travel with their saved job; do not retain a previous
        # computer's absolute run directory when reopening copied results.
        result['case_directory']=str(path.parent.resolve())
    return result
