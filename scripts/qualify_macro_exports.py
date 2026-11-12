"""Check macro input binding on retained installed-runtime jobs without editing them."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio import digital_macro, digital_runtime
from icstudio.digital_platform import BUNDLED_PLATFORMS
from icstudio.model import atomic_write, clone, digest, file_digest


def check(evidence):
    root=Path(evidence).resolve();read_original=Path.read_text;records=[];inputs={}
    with tempfile.TemporaryDirectory(prefix='macro-input-check-') as temporary:
        target_root=Path(temporary)
        for platform in BUNDLED_PLATFORMS:
            directory=root/platform/'gds';input_path=directory/'input.json';result_path=directory/'result.json'
            if not input_path.is_file() or not result_path.is_file():
                raise ValueError('Missing required installed-runtime job: '+str(directory))
            inputs[platform]={'input_sha256':file_digest(input_path),'result_sha256':file_digest(result_path)}
            result=json.loads(result_path.read_text());job=json.loads(input_path.read_text())
            if (job['project']['digital'].get('platform',{}).get('name')!=platform
                    or result.get('digital_result',{}).get('platform',{}).get('name')!=platform):
                raise ValueError('The retained job belongs to another platform: '+platform)
            contract=digital_macro.export(result,directory,target_root/(platform+'-original.zip'))
            if contract['design_hash']!=result['design_hash']:raise ValueError('Export omitted the captured design identity.')
            records.append({'platform':platform,'case':'original','status':'passed','notice_count':len(contract['notices'])})
            for fault in ('constraint','top','notice-lock','project-id','cell-id'):
                changed=clone(job);config=changed['project']['digital']
                if fault=='constraint':
                    next(f for f in config['files'] if f['role']=='constraint')['text']+='\n# changed after implementation\n'
                elif fault=='top':config['top']='changed_after_implementation'
                elif fault=='project-id':changed['project']['id']='changed-project'
                elif fault=='cell-id':changed['cell']='changed-cell'
                else:
                    p=config['platform'];p['files']=[f for f in p['files'] if 'redistribution/' not in f['path'] and
                        not Path(f['path']).name.lower().startswith('license') and Path(f['path']).name!='upstream-lock.json']
                    p['fingerprint']=digest(p['files'])
                # Substitute only this input snapshot read. Engine evidence and
                # captured files remain untouched; filesystem edits have unit coverage.
                def read(path,*args,**kwargs):
                    return json.dumps(changed) if path==input_path else read_original(path,*args,**kwargs)
                destination=target_root/(platform+'-'+fault+'.zip');destination.write_bytes(b'previous export')
                try:
                    with patch.object(Path,'read_text',read):digital_macro.export(result,directory,destination)
                except ValueError as error:
                    if destination.read_bytes()!=b'previous export':raise ValueError('Rejected export replaced the previous bundle.')
                    records.append({'platform':platform,'case':fault,'status':'rejected','error':str(error)})
                else:raise ValueError('Macro export accepted changed inputs: '+platform+'/'+fault)
            if inputs[platform]!={'input_sha256':file_digest(input_path),'result_sha256':file_digest(result_path)}:
                raise ValueError('Original engine evidence changed during the export checks.')
    if len(records)!=6*len(BUNDLED_PLATFORMS):raise ValueError('Incomplete macro input-binding coverage.')
    report={'status':'passed','scope':'Retained installed counter jobs and read-only input substitutions; not new engine or tapeout qualification',
        'exporter_sha256':file_digest(ROOT/'icstudio/digital_macro.py'),'qualifier_sha256':file_digest(Path(__file__)),
        'source_jobs':inputs,'cases':records}
    return report


def qualify(evidence, output):
    try:report=check(evidence)
    except Exception as error:
        atomic_write(output,json.dumps({'status':'failed','error':str(error),
            'qualifier_sha256':file_digest(Path(__file__))},indent=2)+'\n')
        raise
    atomic_write(output,json.dumps(report,indent=2)+'\n');return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'build/macro-integrity-installed/report.json')
    args=parser.parse_args();evidence=args.evidence
    if evidence is None:
        state=digital_runtime.status()
        if state['state']!='ready':raise ValueError('Qualify the included runtime before checking its exports.')
        evidence=Path(state['evidence'])
    report=qualify(evidence,args.output);print(json.dumps({'status':report['status'],'cases':len(report['cases'])}))


if __name__=='__main__':main()
