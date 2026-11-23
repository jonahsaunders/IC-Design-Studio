"""Durable job lifecycle gates publication and replay of saved results."""
import json
from pathlib import Path
from .model import atomic_write,now,design_digest,io_path


def state(directory,status,**extra):
    atomic_write(Path(directory)/'status.json',json.dumps({'status':status,'updated':now(),**extra},indent=2))


def read_result(path,project_id,require_complete=True):
    original_path=Path(path);path=io_path(path);status=path.parent/'status.json'
    if status.exists() and require_complete and json.loads(status.read_text(encoding='utf-8'))['status']!='complete':raise ValueError('Run was not completed; result is not publishable.')
    result=json.loads(path.read_text(encoding='utf-8'));job=json.loads((path.parent/'input.json').read_text(encoding='utf-8'))
    if result.get('project_id')!=project_id or job['project']['id']!=project_id:raise ValueError('Result belongs to a different project.')
    if result.get('cell_id')!=job['cell'] or result.get('design_hash')!=design_digest(job['project']):raise ValueError('Result does not match its saved input.')
    if job.get('settings',{}).get('type')=='digital':
        from .digital_flow import validate_result
        from .digital import source_hash
        from .digital_design import config
        validate_result(result,path.parent)
        if result.get('settings')!=job['settings'] or result['digital_result'].get('source_hash')!=source_hash(config(job['project'],job['cell'])):
            raise ValueError('Digital result does not match its saved settings or sources.')
    elif job.get('settings',{}).get('type')=='mixed_signal':
        from .mixed_signal import validate_result
        validate_result(result,job,path.parent)
    elif job.get('settings',{}).get('type')=='external_simulator':
        from .external_simulation import output_manifest
        if (result.get('settings')!=job['settings'] or
                output_manifest((original_path.parent/'external').resolve(),job['settings']['outputs'])!=result.get('external_outputs')):
            raise ValueError('External simulator artifacts or run settings changed since capture.')
    elif job.get('settings',{}).get('type') in ('rf_network','periodic_steady_state'):
        from .model import file_digest
        key,stem=('rf_network','rf') if job['settings']['type']=='rf_network' else ('pss','pss')
        evidence=result.get(key,{})
        if (result.get('settings')!=job['settings'] or
                any(not (path.parent/name).is_file() or file_digest(original_path.parent/name)!=evidence.get(key)
                    for name,key in ((stem+'-input.cir','deck_sha256'),(stem+'.raw','raw_sha256')))):
            raise ValueError('Analysis artifacts or run settings changed since capture.')
    elif not isinstance(result.get('traces'),dict) or not isinstance(result.get('x'),list):raise ValueError('Invalid result structure.')
    if job.get('settings',{}).get('type')=='student_bench_lab':
        from .student_testbench import validate_result
        validate_result(job,result,original_path.parent)
    if result.get('xschem_cases') or result.get('analysis_cases'):
        # Raw captures travel with their saved job; do not retain a previous
        # computer's absolute run directory when reopening copied results.
        result['case_directory']=str(original_path.parent.resolve())
    return result
