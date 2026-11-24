"""Build the VGA Verilator compiler from pinned sources on Linux with Emscripten 2.0.6."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

VERILATOR = 'https://github.com/8bitworkshop/verilator'
VERILATOR_REV = '6c3efcd5d869ba772e4ed1365727e155fd9210da'
EMSCRIPTEN = 'https://github.com/emscripten-core/emscripten'
EMSCRIPTEN_REV = 'b22065b0d6efe302dab860118588678e98d1e267'
SDK_REV = 'aec1e16f518517ab140a25f59af0840ae754c86c'
SDK_RELEASE = '4ba921c8c8fe2e8cae071ca9889d5c27f5debd87'
XML_PATCH = 'signed-basic-dtype-v1'
OUTPUT_FILES = ('verilator_bin.js', 'verilator_bin.wasm', 'verilator-source.zip')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source(repository, revision, directory):
    subprocess.run(['git', 'init', str(directory)], check=True)
    subprocess.run(['git', 'fetch', '--depth=1', repository, revision], cwd=directory, check=True)
    subprocess.run(['git', 'checkout', '--detach', revision], cwd=directory, check=True)


def verify(directory):
    manifest = json.loads((directory/'verilator-build.json').read_text(encoding='utf-8'))
    if (manifest.get('verilator') != VERILATOR_REV or manifest.get('emscripten') != EMSCRIPTEN_REV
            or manifest.get('sdk') != SDK_REV or manifest.get('sdk_release') != SDK_RELEASE
            or manifest.get('xml_patch') != XML_PATCH
            or manifest.get('files') != {name: sha(directory/name) for name in OUTPUT_FILES}):
        raise ValueError('Rebuild the VGA compiler and its source archive with scripts/build_vga_compiler.py.')
    return manifest


def build(output):
    version = subprocess.check_output(['emcc', '--version'], text=True)
    if '2.0.6' not in version.splitlines()[0]:
        raise ValueError('Activate the pinned Emscripten SDK 2.0.6 before building the VGA compiler.')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='studio-vga-compiler-') as temporary:
        root = Path(temporary)
        for repo, revision, name in ((VERILATOR, VERILATOR_REV, 'verilator'),
                                     (EMSCRIPTEN, EMSCRIPTEN_REV, 'emscripten')):
            source(repo, revision, root/name)
            subprocess.run(['git', 'archive', '--format=zip', '--prefix='+name+'/',
                            '-o', str(root/(name+'.zip')), revision], cwd=root/name, check=True)
        compiler = root/'verilator'
        # Emit the signedness attribute consumed by vxmlparser.ts. The old
        # distributed WASM carries this behavior beyond the pinned Git tree.
        xml_source = compiler/'src/V3EmitXml.cpp'
        xml = xml_source.read_text(encoding='utf-8')
        anchor = '        outputTag(nodep, "basicdtype");\n'
        if xml.count(anchor) != 1:
            raise ValueError('The pinned Verilator basicdtype emitter changed.')
        xml_source.write_text(xml.replace(anchor, anchor +
            '        // IC Design Studio: retain signedness in VGA simulation XML.\n'
            '        if (nodep->isSigned()) puts(" signed=\\"true\\"");\n'), encoding='utf-8')
        subprocess.run(['autoconf'], cwd=compiler, check=True)
        subprocess.run(['emconfigure', './configure', '--prefix=/share'], cwd=compiler, check=True)
        shutil.copy2('/usr/include/FlexLexer.h', compiler/'include/FlexLexer.h')
        flags = ('-s MODULARIZE=1 -s EXPORT_ES6=1 -s EXPORT_NAME=verilator_bin '
                 "-s 'EXTRA_EXPORTED_RUNTIME_METHODS=[\"FS\",\"callMain\"]' "
                 '-s FORCE_FILESYSTEM=1 -s INITIAL_MEMORY=67108864 -s ALLOW_MEMORY_GROWTH=1')
        subprocess.run(['emmake', 'make', '-C', 'src', '-j', '4', '../bin/verilator_bin',
                        'EMMAKEN_CFLAGS='+flags], cwd=compiler, check=True)
        shutil.copy2(compiler/'bin/verilator_bin', output/'verilator_bin.js')
        shutil.copy2(compiler/'bin/verilator_bin.wasm', output/'verilator_bin.wasm')
        with ZipFile(output/'verilator-source.zip','w') as bundle:
            for name in ('verilator.zip','emscripten.zip'):
                bundle.write(root/name,name)
            bundle.write(Path(__file__).resolve(),'build_vga_compiler.py')
            bundle.write(xml_source,'studio-patches/src/V3EmitXml.cpp')
            bundle.writestr('BUILD.txt', 'Build on Linux with autoconf, make, flex, libfl-dev, bison, g++, and Python 3.12.\n'
                f'Activate emsdk 2.0.6 from https://github.com/emscripten-core/emsdk/tree/{SDK_REV}.\n'
                f'Emscripten SDK release commit: {SDK_RELEASE}.\n'
                'Run python build_vga_compiler.py --output compiler. The recipe fetches the pinned source revisions.\n'
                'The accompanying source archives preserve the exact Verilator and Emscripten source and licenses.\n'
                'The Studio build recipe applies the signed-basic-dtype XML change preserved under studio-patches.\n')
    record = dict(verilator=VERILATOR_REV, emscripten=EMSCRIPTEN_REV, sdk=SDK_REV, sdk_release=SDK_RELEASE,
                  xml_patch=XML_PATCH, files={name:sha(output/name) for name in OUTPUT_FILES})
    (output/'verilator-build.json').write_text(json.dumps(record,indent=2)+'\n', encoding='utf-8')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.resolve())
