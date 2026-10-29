"""Capture independent source inputs and read one bounded default ESD probe.

Prepare is run while the producer is still executing; finish binds its terminal
report and manifest to those separately captured inputs. This is source-only.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.esd_desktop_probe import runtime_identity, source_identity
from icstudio.model import file_digest
from scripts import installed_mim_inputs as inputs, verify_frozen_esd as reader
from scripts import audit_sky130_esd_nvt as raw_audit, verify_frozen_mim


def write(path, value):
    path = Path(path)
    if path.exists(): raise ValueError('Choose a new output file.')
    path.write_bytes((json.dumps(value, indent=2, allow_nan=False)+'\n').encode())


def prepare(root, engine, execution_id, output):
    root = Path(root).resolve(); engine = Path(engine).resolve()
    if (root/'report.json').exists(): raise ValueError('Capture inputs before producer completion.')
    binding = dict(mode='source-pilot', resource_root=str(ROOT))
    environment = inputs.native_environment(binding, engine, root/'native-environment')
    runtime = inputs.runtime(binding, engine, environment)
    executable = Path(sys.executable).resolve()
    helpers = [Path(reader.__file__).resolve(), Path(raw_audit.__file__).resolve(),
               Path(inputs.__file__).resolve(), Path(verify_frozen_mim.__file__).resolve()]
    expected = dict(mode='source', selection='bundled-default', execution_id=execution_id,
        executable=str(executable), executable_sha256=file_digest(executable),
        engine=str(engine), engine_sha256=file_digest(engine), resource_root=str(ROOT),
        runtime=runtime_identity(engine,None,False), native_environment=environment,
        native_runtime=runtime, collection_sha256=file_digest(ROOT/'icstudio/assets/pdks/collection.json'),
        sources=source_identity(), reader_files={str(p):file_digest(p) for p in helpers})
    write(output, expected)
    return expected


def finish(root, expected_path, reference_root, output):
    root=Path(root).resolve(); expected=json.loads(Path(expected_path).read_bytes())
    expected.update(report_sha256=file_digest(root/'report.json'),
                    producer_manifest_sha256=file_digest(root/'producer-manifest.json'))
    expected_out=Path(output).with_name(Path(output).stem+'-expected.json')
    write(expected_out, expected)
    package=ROOT/'icstudio/assets/pdks/sky130A'
    ref=reader.references(root,package,Path(reference_root),expected)
    result=reader.audit(root,package,Path(reference_root),expected,ref['reference_manifest_sha256'])
    result['expected_sha256']=file_digest(expected_out)
    write(output,result)
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare'); p.add_argument('--root',required=True); p.add_argument('--engine',required=True); p.add_argument('--execution-id',required=True); p.add_argument('--output',required=True)
    p=sub.add_parser('finish'); p.add_argument('--root',required=True); p.add_argument('--expected',required=True); p.add_argument('--references',required=True); p.add_argument('--output',required=True)
    a=ap.parse_args()
    result=prepare(a.root,a.engine,a.execution_id,a.output) if a.action=='prepare' else finish(a.root,a.expected,a.references,a.output)
    print(json.dumps(result,indent=2))
