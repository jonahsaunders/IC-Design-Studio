"""Run a bounded native IHP cap_cmim process-control comparison on Linux."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_ihp_cmim_process_control import (
    CASES, COMMAND, CONTROLS, MANAGED_WRAPPER_SHA, MODEL, MODEL_NAMES, PDK, SOURCE_MODULES, plate_evidence, source_contract, verify,
)
from scripts.verify_frozen_ihp_cmim import FORBIDDEN, confined, require, safe, sha


def deck(spec, driven='lower'):
    bias, temp, frequency, width, length = spec
    grounded = 'upper' if driven == 'lower' else 'lower'
    return f'''IHP cap_cmim process-control comparison
.lib ../models/cornerCAP.lib cap_typ
.temp {temp}
Vdrive {driven} 0 DC {bias} AC 1
Vground {grounded} 0 DC 0 AC 0
Xdut upper lower cap_cmim w={width}u l={length}u m=1 mm_ok=1
.control
set filetype=ascii
set numdgt=17
op
write op.raw v(upper) v(lower) i(vdrive)
ac lin 1 {frequency} {frequency}
write ac.raw v(upper) v(lower) i(vdrive)
quit
.endc
.end
'''


def run(root, out, archive, engine, binary):
    require(sys.platform == 'linux', 'Producer requires native Linux.')
    root, out, engine, binary = map(safe, (root, out, engine, binary))
    require(not out.exists() and not out.is_relative_to(root), 'Use a fresh output outside source.')
    require(engine.is_file() and binary.is_file(), 'Missing native engine inputs.')
    require(engine == binary or (str(engine), str(binary), sha(engine)) ==
            ('/opt/icstudio/bin/ngspice', '/usr/bin/ngspice', MANAGED_WRAPPER_SHA), 'Unverified engine wrapper/binary pairing.')
    source_before = source_contract(root)
    plate_before = plate_evidence(root, archive)
    scripts_before = {name: sha(confined(root, name)) for name in SOURCE_MODULES}
    out.mkdir()
    (out/'home').mkdir()
    (out/'tmp').mkdir()
    (out/'models').mkdir()
    env = dict(PATH='/usr/bin:/bin', HOME=str(out/'home'), TMPDIR=str(out/'tmp'), LANG='C.UTF-8',
               LC_ALL='C.UTF-8', TZ='UTC')
    runtime_env = env if engine == binary else {**env, 'LD_LIBRARY_PATH': str(engine.parent.parent/'lib')}
    linkage = subprocess.run(['/usr/bin/ldd', str(binary)], env=runtime_env, capture_output=True, check=True, timeout=10).stdout
    require(b'not found' not in linkage, 'Incomplete native dynamic library closure.')
    (out/'runtime-ldd.log').write_bytes(linkage)
    # ldd's display addresses vary. Bind bytes of its resolved regular files.
    dependencies = [Path(value.decode()) for value in re.findall(rb'(/[^\s]+) \(0x', linkage)]
    require(all(FORBIDDEN not in path.parts for path in dependencies), 'Invalid native dependency path.')
    paths = {engine, binary, *(path.resolve() for path in dependencies)}

    def runtime_files():
        return {str(path): sha(safe(path)) for path in sorted(paths)}

    runtime_before = runtime_files()
    version = subprocess.run([str(engine), '-n', '-v'], env=env, capture_output=True, check=True, timeout=10)
    (out/'runtime-version.log').write_bytes(version.stdout+version.stderr)
    for name in MODEL_NAMES:
        (out/'models'/name).write_bytes((root/PDK/MODEL/name).read_bytes())
    controls = {name: deck(spec, driven) for name, (spec, driven, _) in CONTROLS.items()}
    returncodes = {}
    for name, text in {**{key: deck(spec) for key, spec in CASES.items()}, **controls}.items():
        folder = out/name
        folder.mkdir()
        (folder/'input.cir').write_text(text, encoding='ascii')
        with (folder/'engine.log').open('xb') as log:
            result = subprocess.run([str(engine), *COMMAND], cwd=folder, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=30)
        returncodes[name] = result.returncode
        require(result.returncode == 0, 'Native ngspice failed: '+name)
    runtime_after = runtime_files()
    require(runtime_before == runtime_after, 'Native runtime changed during execution.')
    invocation = dict(engine=str(engine), binary=str(binary), argv=[str(engine), *COMMAND], environment=env,
                      returncodes=returncodes, runtime_before=runtime_before, runtime_after=runtime_after,
                      version_sha256=sha(out/'runtime-version.log'), linkage_sha256=sha(out/'runtime-ldd.log'))
    (out/'invocation.json').write_text(json.dumps(invocation, indent=2)+'\n', encoding='utf-8')
    result = verify(root, out, archive)
    require(result['source'] == source_before and result['plate_mapping'] == plate_before and
            result['source_code'] == scripts_before, 'Source changed during execution.')
    (out/'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--physical-archive', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--native-binary', type=Path, required=True)
    args = parser.parse_args()
    result = run(ROOT, args.out, args.physical_archive, args.ngspice, args.native_binary)
    print(json.dumps(dict(status=result['status'], out=str(args.out), cases=len(result['native_rows']),
                          controls=len(result['controls'])), allow_nan=False))


if __name__ == '__main__':
    main()
