"""A self-contained implemented macro contract with verified artifact provenance."""
import json
from pathlib import Path
import zipfile

from .digital_flow import validate_result
from .model import clone


def export(result, directory, destination):
    directory=Path(directory);destination=Path(destination)
    validate_result(result,directory);data=result['digital_result'];artifacts=data['artifacts']
    if data['stage']!='finish' or not {'gds','lef','netlist','layout_preview'}<=artifacts.keys():
        raise ValueError('Finish the physical flow before exporting a macro bundle.')
    preview=json.loads((directory/artifacts['layout_preview']['path']).read_text())
    selected={k:v for k,v in artifacts.items() if k in ('gds','lef','netlist','spef','sdc','layout_preview','database','timing','equivalence','def','extraction') or k.startswith(('spef_','extraction_script_'))}
    job=json.loads((directory/'input.json').read_text())
    from .digital_design import config
    manifest={'version':1,'top':config(job['project'],job['cell'])['top'],'source_hash':data['source_hash'],'input_key':data.get('input_key'),
              'project_id':result['project_id'],'cell_id':result['cell_id'],
              'ports':preview.get('pins',[]),'bounds_um':preview['die'],'platform':data.get('platform'),
              'environment':data.get('environment'),'artifacts':clone(selected),
              'qualification':{'physical_stage':'finish','drc':'Not qualified by this export','lvs':'Not qualified by this export',
                               'abstract_timing_model':None,
                               'scope':'LEF/GDS geometry with the actual gate netlist and captured SPEF. No characterized macro Liberty model is implied.'}}
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
    job=json.loads((directory/'input.json').read_text())
    from .digital_design import config
    constraints=[f for f in config(job['project'],job['cell'])['files'] if f['role']=='constraint']
    temporary=destination.with_name(destination.name+'.partial')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
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
