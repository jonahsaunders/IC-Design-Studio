"""A self-contained implemented macro contract with verified artifact provenance."""
import json
from pathlib import Path
import zipfile

from .digital_flow import validate_result
from .model import clone


def captured_notices(job, directory):
    """Copy the exact captured source notices, independent of the installed PDK."""
    from .digital_design import config
    from .digital_platform import validate
    from .model import file_digest
    platform=config(job['project'],job['cell']).get('platform')
    if not platform:return []
    validate(platform);root=(Path(directory)/'platform').resolve();result=[]
    for record in platform['files']:
        name=Path(record['path']).name.lower()
        if not (name.startswith(('license','copying')) or 'notice' in name or name=='upstream-lock.json'):continue
        path=(root/record['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=record['sha256']:
            raise ValueError('Captured platform notice is missing or changed: '+record['path'])
        result.append((path,{'path':'notices/'+record['path'],'source_path':record['path'],
                            'sha256':record['sha256'],'bytes':record['bytes']}))
    return result


def verify_inputs(result, job):
    """Bind exported metadata to the inputs that produced the retained geometry."""
    from .digital import source_hash
    from .digital_design import config
    from .digital_identity import stage_key
    from .model import design_digest
    message='The captured job inputs do not match the implemented macro. Restore the original input snapshot or run physical finish again.'
    if (not isinstance(job,dict) or not isinstance(job.get('project'),dict)
            or result.get('project_id')!=job['project'].get('id') or result.get('cell_id')!=job.get('cell')
            or result.get('design_hash')!=design_digest(job['project'])):
        raise ValueError(message)
    data=result['digital_result'];value=config(job['project'],job['cell'])
    if (data.get('source_hash')!=source_hash(value)
            or data.get('input_key') and data['input_key']!=stage_key(value,'finish')):
        raise ValueError(message)
    return value


def export(result, directory, destination):
    directory=Path(directory);destination=Path(destination)
    validate_result(result,directory);data=result['digital_result'];artifacts=data['artifacts']
    if data['stage']!='finish' or not {'gds','lef','netlist','layout_preview'}<=artifacts.keys():
        raise ValueError('Finish the physical flow before exporting a macro bundle.')
    preview=json.loads((directory/artifacts['layout_preview']['path']).read_text())
    selected={k:v for k,v in artifacts.items() if k in ('gds','lef','netlist','spef','sdc','layout_preview','database','timing','equivalence','def','extraction','physical_checks') or k.startswith(('spef_','extraction_script_','physical_check_','lvs_reference'))}
    job=json.loads((directory/'input.json').read_text())
    value=verify_inputs(result,job)
    from .digital_physical_checks import validate_saved
    checks=validate_saved(data,directory)
    if checks is not None and checks.get('top')!=value['top']:
        raise ValueError('Physical-check evidence belongs to another top-level design.')
    from .digital_lvs_reference import validate_saved as validate_reference
    reference=validate_reference(data,directory)
    if reference is not None and reference.get('top')!=value['top']:
        raise ValueError('Generated reference belongs to another top-level design.')
    if reference is not None and value.get('platform',{}).get('lvs_reference')!=data.get('environment',{}).get('lvs_reference'):
        raise ValueError('Generated reference policy differs from the captured macro inputs.')
    notices=captured_notices(job,directory)
    manifest={'version':1,'top':value['top'],'source_hash':data['source_hash'],'input_key':data.get('input_key'),
              'design_hash':result['design_hash'],
              'project_id':result['project_id'],'cell_id':result['cell_id'],
              'ports':preview.get('pins',[]),'bounds_um':preview['die'],'platform':data.get('platform'),
              'environment':data.get('environment'),'artifacts':clone(selected),
              'notices':[record for path,record in notices],
              'notices_scope':'Captured platform license/source notices only; custom platforms may supply none. Review the captured sources and redistribution terms for the intended handoff.',
              'qualification':{'physical_stage':'finish','drc':'Not qualified by this export','lvs':'Not qualified by this export',
                               'physical_checks':{'status':checks['status'],'scope':checks['scope'],'artifact':'physical_checks'} if checks else {'status':'Not qualified by this historical job'},
                               'abstract_timing_model':None,
                               'scope':'LEF/GDS geometry with the actual gate netlist and captured SPEF. No characterized macro Liberty model is implied.'}}
    if reference is not None:
        manifest['qualification']['generated_reference']={
            'status':reference['status'],'scope':reference['scope'],'artifact':'lvs_reference',
            'report_artifact':'lvs_reference_report'}
    if 'extraction' in selected:
        extraction=json.loads((directory/selected['extraction']['path']).read_text())
        if extraction.get('schema')!=1 or extraction.get('status')!='complete' or extraction.get('def')!=selected.get('def') or extraction.get('netlist')!=selected['netlist']:
            raise ValueError('Macro extraction evidence does not match the exported final geometry and netlist.')
        if not extraction.get('corners') or any(item.get('spef')!=selected.get(item.get('spef_key')) or item.get('spef_key') not in selected for item in extraction['corners'].values()):
            raise ValueError('Macro export is missing a captured interconnect corner.')
        manifest['interconnect_corners']={name:{'spef_artifact':item['spef_key'],'inputs':item['inputs'],
            'source_def_sha256':extraction['def']['sha256'],'source_netlist_sha256':extraction['netlist']['sha256']}
            for name,item in extraction['corners'].items()}
        manifest['extraction_evidence_scope']='The retained extraction report uses original job paths; exported files are addressed by the artifact keys in this manifest.'
    constraints=[f for f in value['files'] if f['role']=='constraint']
    temporary=destination.with_name(destination.name+'.partial')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for path,record in notices:archive.write(path,record['path'])
            for key,record in selected.items():
                name='artifacts/'+key+Path(record['path']).suffix;archive.write(directory/record['path'],name)
                manifest['artifacts'][key]['path']=name
            import hashlib
            manifest['constraints']=[]
            for source in constraints:
                name='constraints/'+source['path'];archive.writestr(name,source['text'])
                manifest['constraints'].append({'path':name,'sha256':hashlib.sha256(source['text'].encode()).hexdigest()})
            archive.writestr('macro.json',json.dumps(manifest,indent=2))
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True);raise
    return manifest
