"""Qualify the bounded optional ESD workflow through an exact frozen desktop.

The ordinary platform installation gate remains responsible for installer
provenance. This launches its selected executable and retains two separately
sealed native evidence sets; no default package is promoted.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if (ROOT/'icstudio').is_dir(): sys.path.insert(0,str(ROOT))
from scripts import installed_mim_inputs as runtime_inputs
from scripts import verify_frozen_esd as reader
from scripts.prepare_sky130_esd_nvt import prepare, predecessor
from scripts.verify_frozen_mim import expected_inputs, git_environment, unlinked


def candidate_files(root, commit):
    files = [p for p in (root/'icstudio').glob('*.py') if p.name != 'build_info.py']
    listing = subprocess.run(['git','ls-tree','-rz','--name-only',commit,'--','icstudio'],
                             cwd=root,env=git_environment(),stdout=subprocess.PIPE,check=True).stdout
    canonical = {name.decode('utf-8') for name in listing.split(b'\0') if name and
                 name.count(b'/') == 1 and name.endswith(b'.py') and name != b'icstudio/build_info.py'}
    reader.require(bool(canonical) and {p.relative_to(root).as_posix() for p in files} == canonical,
                   'Application source inventory differs from the selected candidate.')
    files += [root/'scripts'/name for name in (
        'qualify_installed_sky130_esd.py','verify_frozen_esd.py','audit_sky130_esd_nvt.py',
        'prepare_sky130_esd_nvt.py','installed_mim_inputs.py','verify_frozen_mim.py')]
    # Bind the actual selected manifests and public correction/predecessor assets.
    for raw_name in listing.split(b'\0'):
        name = raw_name.decode('utf-8')
        if name in ('icstudio/assets/pdks/collection.json','icstudio/assets/pdks/sky130A/package.json') or name.startswith(('icstudio/assets/qualification/sky130-esd-nvt-source-v1/','icstudio/assets/qualification/sky130-esd-predecessor-v1/')):
            files.append(root/name)
    return {p.relative_to(root).as_posix():reader.sha(unlinked(p)) for p in sorted(files)}


def run_probe(command, out, env, timeout, invocation):
    """Retain launch completion evidence even when the child fails or times out."""
    invocation = {**invocation,'started_utc':datetime.now(timezone.utc).isoformat(),'status':'RUNNING'}
    started = time.monotonic()
    reader.write(out/'invocation.json',invocation)
    try:
        with (out/'launcher.log').open('wb') as log:
            result = subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,
                                    timeout=timeout,check=True)
        invocation.update(status='PASS',returncode=result.returncode)
    except Exception as exc:
        invocation.update(status='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL',
                          returncode=getattr(exc,'returncode',None),error=repr(exc))
        raise
    finally:
        invocation.update(ended_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-started)
        if (out/'launcher.log').is_file(): invocation['launcher_log_sha256'] = reader.sha(out/'launcher.log')
        reader.write(out/'invocation.json',invocation)


def verify(executable, out, commit, timeout=2400, bundled_default=False):
    executable = unlinked(executable).resolve()
    out = unlinked(out).resolve()
    reader.require(re.fullmatch('[0-9a-f]{40}',commit or '') and math.isfinite(timeout) and timeout > 0,
                   'An exact candidate and positive finite timeout are required.')
    reader.require(not out.exists(),'Use a new evidence directory.')
    reader.require(not out.is_relative_to(executable.parent),'Evidence must be outside the selected deliverable.')
    out.mkdir(parents=True)
    start = time.monotonic()
    execution_id = uuid.uuid4().hex
    try:
        sources = candidate_files(ROOT,commit)
        runtime_inputs.candidate_sources(sources,commit)
        inputs = expected_inputs(commit)
        resource = executable.parent/'_internal'
        base = resource/'icstudio/assets/pdks/sky130A'
        reader.require(inputs['package_sha256'] in (reader.BASE,reader.DEFAULT),'Candidate uses an unreviewed bundled package.')
        reader.package_at(base,inputs['package_sha256'])
        collection = resource/'icstudio/assets/pdks/collection.json'
        reader.require(reader.sha(collection) == inputs['collection_sha256'],'Installed collection differs from candidate.')
        previous = None
        if inputs['package_sha256'] == reader.DEFAULT:
            previous = out/'predecessor-package'
            old_manifest = unlinked(resource/'icstudio/assets/qualification/sky130-esd-predecessor-v1/package.json')
            with predecessor(base, manifest=old_manifest) as original:
                shutil.copytree(original,previous)
            reader.package_at(previous,reader.BASE)
        if bundled_default:
            reader.require(previous is not None,'Default gate requires the corrected shipped package.')
            package = base
        else:
            package = out/'optional-package'
            prepare(previous or base,package,resource/'icstudio/assets/qualification/sky130-esd-nvt-source-v1')
            reader.package_at(package,reader.OPTIONAL)
        engine = unlinked(resource/'icstudio/assets/runtime/ngspice'/('ngspice.exe' if os.name == 'nt' else 'ngspice')).resolve()
        engine_hash = reader.sha(engine)
        reader.require(engine_hash in reader.raw_audit.ENGINES,'Installed engine requires an explicit reviewed raw profile.')
        runtime_manifest = reader.load(engine.parent/'runtime-manifest.json')
        runtime_data = dict(files=runtime_manifest['files'],manifest_sha256=reader.sha(engine.parent/'runtime-manifest.json'))
        reader.require(runtime_data['files'].get(engine.name) == engine_hash,'Engine absent from runtime manifest.')
        for name,value in runtime_data['files'].items():
            reader.require(reader.sha(unlinked(engine.parent/reader.relative(name))) == value,'Changed shipped runtime support file.')
        probe = out/'probe'
        # Construct the exact native environment before launch without precreating
        # the producer's new output root. Runtime discovery uses no design inputs.
        preparatory = out/'environment-preparation'
        preparatory.mkdir()
        binding = dict(mode='installed',resource_root=str(resource))
        env_native = runtime_inputs.native_environment(binding,engine,preparatory)
        env_native = {k:v.replace(str(preparatory),str(probe/'native-environment')) for k,v in env_native.items()}
        native_runtime = runtime_inputs.runtime(binding,engine,env_native)
        helper_paths = [Path(reader.__file__).resolve(),ROOT/'scripts/audit_sky130_esd_nvt.py',
                        ROOT/'scripts/installed_mim_inputs.py',ROOT/'scripts/verify_frozen_mim.py',
                        ROOT/'scripts/prepare_sky130_esd_nvt.py',ROOT/'scripts/qualify_installed_sky130_esd.py',
                        ROOT/'icstudio/runtime_setup.py',ROOT/'icstudio/model.py']
        expected = dict(mode='installed',selection='bundled-default' if bundled_default else 'optional',commit=commit,execution_id=execution_id,
                        executable=str(executable),executable_sha256=reader.sha(executable),
                        resource_root=str(resource),engine=str(engine),engine_sha256=engine_hash,
                        runtime=runtime_data,native_environment=env_native,native_runtime=native_runtime,
                        collection_sha256=inputs['collection_sha256'],candidate_sources=sources,
                        reader_files={str(p):reader.sha(unlinked(p)) for p in helper_paths})
        reader.write(out/'prelaunch-inputs.json',expected)
        env = git_environment()
        for key in list(env):
            if key.upper().startswith(('PYTHON','SPICE_','ICSTUDIO_NGSPICE','ICSTUDIO_BUNDLED_NGSPICE')) or key.upper() in (
                    'LD_LIBRARY_PATH','LD_PRELOAD','ICSTUDIO_DIGITAL_PAYLOAD','ICSTUDIO_DIGITAL_NATIVE'):
                env.pop(key)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        command = [str(executable),'--esd-acceptance','--out',str(probe),'--execution-id',execution_id]
        command += ['--bundled-default'] if bundled_default else ['--package',str(package)]
        if previous is not None: command += ['--predecessor',str(previous)]
        run_probe(command,out,env,timeout,dict(command=command,execution_id=execution_id,commit=commit,
                  timeout_seconds=timeout,prelaunch_inputs_sha256=reader.sha(out/'prelaunch-inputs.json')))
        reader.require(reader.sha(executable) == expected['executable_sha256'],'Installed executable changed during probe.')
        expected = {**expected,'report_sha256':reader.sha(probe/'report.json'),
                    'producer_manifest_sha256':reader.sha(probe/'producer-manifest.json')}
        reader.write(out/'expected-inputs.json',expected)
        refs = out/'references'
        reference = reader.references(probe,package,refs,expected)
        result = reader.audit(probe,package,refs,expected,reference['reference_manifest_sha256'])
        runtime_inputs.candidate_sources(sources,commit)
        result.update(expected_commit=commit,execution_id=execution_id,seconds=time.monotonic()-start,
                      expected_inputs_sha256=reader.sha(out/'expected-inputs.json'),
                      prelaunch_inputs_sha256=reader.sha(out/'prelaunch-inputs.json'),
                      invocation_sha256=reader.sha(out/'invocation.json'),
                      launcher_log_sha256=reader.sha(out/'launcher.log'),
                      scope='Selected frozen '+('bundled default' if bundled_default else 'optional')+' ESD GUI/native integration; installation provenance is supplied by the enclosing platform installation gate.')
        reader.write(out/'acceptance.json',result)
        return result
    except Exception as exc:
        reader.write(out/'failure.json',dict(status='FAIL',expected_commit=commit,execution_id=execution_id,
                     error=repr(exc),seconds=time.monotonic()-start,qualified=False,default_promoted=False,chunk_complete=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--expected-commit',required=True)
    parser.add_argument('--timeout',type=float,default=2400,
                        help='Desktop probe deadline in seconds; each independent reference has a separate 180-second deadline.')
    parser.add_argument('--bundled-default',action='store_true',help='Require actual Project Hub selection of the shipped corrected default.')
    args = parser.parse_args()
    print(json.dumps(verify(args.executable,args.out,args.expected_commit,args.timeout,args.bundled_default),indent=2))


if __name__ == '__main__': main()
