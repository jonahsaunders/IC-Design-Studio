"""Build the pinned VGA Playground locally; no network access is needed at runtime.

Requires git and Node.js 22.12+ (or 24). Generated assets stay under build/ and
are copied into desktop packages by package.py. --source accepts a local clone.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital_vga import REVISION, UPSTREAM
from scripts.build_vga_compiler import sha, verify, VERILATOR_REV, EMSCRIPTEN_REV, SDK_REV, SDK_RELEASE


def verify_dist(dist):
    manifest = json.loads((dist/'icstudio-build.json').read_text(encoding='utf-8'))
    compiler = json.loads((dist/'verilator-build.json').read_text(encoding='utf-8'))
    wasm = list((dist/'assets').glob('verilator_bin-*.wasm'))
    if (manifest.get('revision')!=REVISION or manifest.get('compiler_manifest')!=sha(dist/'verilator-build.json')
            or compiler.get('verilator')!=VERILATOR_REV or compiler.get('emscripten')!=EMSCRIPTEN_REV
            or compiler.get('sdk')!=SDK_REV or compiler.get('sdk_release')!=SDK_RELEASE
            or compiler['files']['verilator-source.zip']!=sha(dist/'verilator-source.zip')
            or len(wasm)!=1 or compiler['files']['verilator_bin.wasm']!=sha(wasm[0])):
        raise ValueError('VGA release assets must match the pinned compiler and corresponding source archive.')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('The pinned upstream integration point changed: ' + old[:80])
    return text.replace(old, new)


def build(source=None, run_tests=False, compiler_directory=None):
    work = ROOT / 'build/vga-playground'
    work.mkdir(parents=True, exist_ok=True)
    checkout = Path(source).resolve() if source else work / 'upstream'
    if not source and not (checkout / '.git').exists():
        subprocess.run(['git', 'clone', '--no-checkout', UPSTREAM + '.git', str(checkout)], check=True)
    # Archive the exact commit, never the clone's possibly modified working tree.
    archive = subprocess.check_output(['git', '-C', str(checkout), 'archive', REVISION])
    src = work / 'source'
    if src.exists(): shutil.rmtree(src)
    src.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(src, filter='data')
    compiler_directory = compiler_directory or work/'compiler'
    verify(compiler_directory)
    # The upstream snapshot contains a binary of uncertain build provenance.
    # Overwrite both components before running tests or producing release assets.
    for name in ('verilator_bin.js', 'verilator_bin.wasm'):
        shutil.copy2(compiler_directory/name, src/'src/verilator'/name)
    # Every preset at this revision has this same Apache license.
    apache = (src / 'src/examples/stripes/LICENSE.txt').read_bytes()
    for license_file in (src / 'src/examples').glob('*/LICENSE.txt'):
        if license_file.parent.name != 'common' and license_file.read_bytes() != apache:
            raise ValueError('A preset now needs a distinct license: ' + str(license_file))
    shutil.copy2(ROOT / 'packaging/vga/studio.ts', src / 'src/index.ts')
    shutil.copy2(ROOT / 'packaging/vga/studio.spec.ts', src / 'src/studio.spec.ts')
    shutil.copy2(ROOT / 'packaging/vga/audio-lifecycle.spec.ts', src / 'src/audio-lifecycle.spec.ts')
    audio_player = src / 'src/AudioPlayer.ts'
    text = audio_player.read_text(encoding='utf-8')
    # Worklet loading is asynchronous. Hiding the preview can cancel playback
    # before it finishes; the upstream unconditional resume then undoes that
    # suspension when the user returns to the preview. Reuse the player's
    # pending playback request, which suspend() already clears.
    text = replace_once(text, "      this.audioCtx.resume().then(() => {\n"
                        "        console.log('Audio playback started');\n"
                        "      });",
                        "      if (this.resumeScheduled) {\n"
                        "        this.audioCtx.resume().then(() => {\n"
                        "          console.log('Audio playback started');\n"
                        "        });\n"
                        "      }")
    audio_player.write_text(text, encoding='utf-8')
    with (src / 'src/index.css').open('a', encoding='utf-8') as stream:
        stream.write('\n' + (ROOT / 'packaging/vga/studio.css').read_text(encoding='utf-8'))
    html = (src / 'index.html').read_text(encoding='utf-8')
    html = replace_once(html, '<link href="https://cdn.jsdelivr.net/npm/reset-css@5.0.2/reset.min.css" rel="stylesheet" />', '')
    (src / 'index.html').write_text(html, encoding='utf-8')
    compiler = src / 'src/verilator/compile.ts'
    text = compiler.read_text(encoding='utf-8')
    # Several shipped presets have width/unused-pin warnings. Keep diagnostics,
    # but do not turn those warnings into failed visual simulations.
    text = replace_once(text, "      '-Wall',", "      '-Wall',\n      '-Wno-fatal',")
    text = replace_once(text, '  topModule: string;', '  topModule: string;\n  includeDirs?: string[];\n  defines?: Record<string, string>;')
    text = replace_once(text, '    FS.writeFile(path, source);',
                        "    FS.mkdirTree(path.slice(0, path.lastIndexOf('/')));\n    FS.writeFile(path, source);")
    text = replace_once(text, "      '-Isrc/',", "      ...(opts.includeDirs ?? ['.']).map(path => '-Isrc/' + path),\n"
                        "      ...Object.entries(opts.defines ?? {}).map(([key, value]) => '-D' + key + (value ? '=' + value : '')),")
    compiler.write_text(text, encoding='utf-8')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm: raise ValueError('Install Node.js 22.12+ or 24 with npm before building VGA Playground.')
    subprocess.run([npm, 'ci', '--ignore-scripts'], cwd=src, check=True)
    subprocess.run([npm, 'run', 'typecheck'], cwd=src, check=True)
    if run_tests: subprocess.run([npm, 'test', '--', '--maxWorkers=2'], cwd=src, check=True)
    subprocess.run([npm, 'run', 'build'], cwd=src, check=True)
    dist = src / 'dist'
    # Ship the adapted source, upstream notices and dependency license texts.
    # Nothing from the user's project or installed Python environment is included.
    with zipfile.ZipFile(dist / 'vga-playground-source.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(src.rglob('*')):
            relative = path.relative_to(src)
            if relative.parts[0] in ('node_modules', 'dist', '.git') or not path.is_file(): continue
            if relative.as_posix() in ('src/verilator/verilator_bin.js','src/verilator/verilator_bin.wasm'): continue
            bundle.write(path, str(relative))
        for name in ('build_vga_compiler.py','build_vga_playground.py'):
            bundle.write(ROOT/'scripts'/name, 'studio-build/'+name)
    for name in ('verilator-source.zip','verilator-build.json'):
        shutil.copy2(compiler_directory/name, dist/name)
    notices = dist / 'licenses'
    notices.mkdir()
    shutil.copy2(src / 'LICENSE', notices / 'VGA-Playground-GPL-3.0.txt')
    shutil.copy2(src / 'src/sim/README.txt', notices / '8bitworkshop.txt')
    for path in (src / 'node_modules').rglob('*'):
        if path.is_file() and path.name.lower().split('.')[0] in ('license', 'licence', 'copying', 'notice'):
            destination = notices / 'npm' / path.relative_to(src / 'node_modules')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (dist / 'icstudio-build.json').write_text(json.dumps({'upstream': UPSTREAM, 'revision': REVISION,
        'adapter': 'IC Design Studio native-editor preview', 'source': 'vga-playground-source.zip',
        'compiler_manifest':sha(dist/'verilator-build.json')}, indent=2), encoding='utf-8')
    verify_dist(dist)
    output = work / 'dist'
    if output.exists(): shutil.rmtree(output)
    shutil.copytree(dist, output)
    print('VGA Playground ready: ' + str(output))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Existing upstream git clone containing the pinned commit')
    parser.add_argument('--test', action='store_true', help='Run upstream simulator tests before building')
    parser.add_argument('--compiler', type=Path, help='Verified output of scripts/build_vga_compiler.py')
    args = parser.parse_args()
    build(args.source, args.test, args.compiler)
