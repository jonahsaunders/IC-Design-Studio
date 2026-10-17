"""Prepare an explicit fixed-layout VPP binding with substrate before M5 shield.

The package also retains the explicit parallel-unit varactor adapters. Upstream
assets and the bundled default are unchanged; existing projects keep their locks.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from icstudio.model import clone, digest, file_digest
from icstudio.catalog import validate_catalog
from scripts.device_qualification_source import historical_input
from scripts.prepare_sky130_parallel_varactors import prepare as parallel_package

KEY='sky130_fd_pr/vpp_cap.sym'
MODEL_SHA256='7710a12e99c750841df77b352eb240e818a995e20474ebad70021e4a739adab2'


def correct(entry, model):
    if hashlib.sha256(model).hexdigest()!=MODEL_SHA256:
        raise ValueError('Unreviewed VPP model source.')
    if entry['pin_order']!=['c0','c1','top','sub'] or set(entry['parameters'])!={'w','l','mult'}:
        raise ValueError('Unexpected VPP symbol interface.')
    entry['pin_order']=['c0','c1','sub','top']
    entry['symbol']['pin_order']=list(entry['pin_order'])
    entry['parameters']={'mult':clone(entry['parameters']['mult'])}
    entry['emit_parameters']={'mult':'mult','m':'mult'}
    entry['parameter_scale']={}
    entry['notes'].append('Fixed 11.5 x 11.7 um VPP model: c0, c1, substrate b, M5 shield. W/L are not model geometry inputs; use the fixed layout and positive mult.')


@historical_input
def prepare(source, output):
    source,output=Path(source).resolve(),Path(output).resolve()
    original=json.loads((source/'package.json').read_bytes())
    entry=clone(original['technology']['simulation']['catalog'][KEY])
    correct(entry,(source/entry['model_source']).read_bytes())
    parent=parallel_package(source,output)
    package=json.loads((output/'package.json').read_bytes())
    package['technology']['simulation']['catalog'][KEY]=entry
    validate_catalog(package['technology'])
    note=dict(schema=1,source_model_sha256=MODEL_SHA256,parent_parallel_package=parent,
        original_binding=original['technology']['simulation']['catalog'][KEY],
        contract='Public subcircuit order c0 c1 b m5 maps to c0 c1 sub top. Fixed layout; no W/L scaling. Positive mult retains upstream statistical parameter and subcircuit multiplier semantics.',
        limits='Default fixed-layout model only. Other available_models, physical extraction, complete operating ranges and mismatch accuracy require separate qualification.')
    path=output/'ICSTUDIO-VPP-BINDING.json';path.write_bytes((json.dumps(note,indent=2)+'\n').encode())
    package['files'][path.name]=file_digest(path)
    package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),
        original_manifest_sha256=file_digest(source/'package.json'),model_sha256=MODEL_SHA256)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/sky130A');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
