"""Recreate the locked physical adapter from the verified public SKY130 archives."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import digest, file_digest
from icstudio.pdk_import import scan_local

LOCK = ROOT / 'examples/sky130-qualification-lock.json'


def manifest_for(source):
    source = Path(source).resolve()
    upstream = json.loads((source.parent / 'upstream-lock.json').read_text())
    expected = json.loads((ROOT / 'examples/sky130-reference-assets.json').read_text())
    expected['files'] = {k: v for k, v in expected['files'].items()
                         if k in ('common.tar.zst', 'sky130_fd_pr.tar.zst')}
    if upstream != expected:
        raise ValueError('Use the pinned --physical-only download; upstream provenance differs.')
    manifest = scan_local(source)
    manifest.pop('source_root')
    additions = {
        'LICENSE-PDK.txt': (source / 'libs.tech/xschem/LICENSE').read_bytes(),
        'UPSTREAM-LOCK.json': (json.dumps(upstream, sort_keys=True, indent=2) + '\n').encode(),
        'NOTICE-QUALIFICATION.txt': (
            'SKY130 adapter subset from chipfoundry/volare, built with open_pdks\n'
            'fa87f8f4bbcc7255b6f0c0fb506960f531ae2392.\n'
            'Copyright 2020 The SkyWater PDK Authors and contributors.\n'
            'Model, symbol and rule files retain their original notices.\n'
            'See LICENSE-PDK.txt and UPSTREAM-LOCK.json.\n'
            'This package is a bounded regression input, not foundry signoff.\n').encode(),
    }
    for name, content in additions.items():
        manifest['files'][name] = hashlib.sha256(content).hexdigest()
    manifest['technology']['revision'] = ''
    revision = digest({'files': manifest['files'], 'technology': manifest['technology']})[:16]
    manifest['revision'] = manifest['technology']['revision'] = revision
    content = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    return manifest, content, additions


def prepare(source, output, bipolar=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new adapter output directory.')
    manifest, content, additions = manifest_for(source)
    lock = json.loads(LOCK.read_text())
    if hashlib.sha256(content).hexdigest() != lock['manifest_sha256']:
        raise ValueError('The generated adapter differs from the committed qualification lock.')
    if bipolar:
        from icstudio.sky130_bipolar_rules import corrected_technology,BASE_TECH_SHA256,TECH_SHA256,SOURCE_COMMIT,SOURCE_URL
        rel='libs.tech/magic/sky130A.tech'
        additions[rel]=corrected_technology((source/rel).read_bytes())
        if hashlib.sha256(additions[rel]).hexdigest()!=TECH_SHA256:raise ValueError('PNP correction output differs from its locked recipe.')
        provenance=dict(version=1,base_adapter_revision=manifest['revision'],base_technology_sha256=BASE_TECH_SHA256,
            technology_sha256=TECH_SHA256,upstream_commit=SOURCE_COMMIT,upstream_url=SOURCE_URL,
            change='PNP device selection uses upstream emitter-area rules; DRC and other extraction rules unchanged.',
            scope='Fixed PNP W3.40/L3.40 coupons only; every edited design needs DRC/LVS.')
        additions['PNP-EXTRACTION-UPDATE.json']=(json.dumps(provenance,sort_keys=True,indent=2)+'\n').encode()
        for name,data in additions.items():manifest['files'][name]=hashlib.sha256(data).hexdigest()
        manifest['technology']['native_fixed_devices']={'sky130_fd_pr__pnp_05v5_W3p40L3p40':provenance}
        manifest['technology']['revision']=''
        manifest['revision']=manifest['technology']['revision']=digest({'files':manifest['files'],'technology':manifest['technology']})[:16]
        content=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    output.mkdir(parents=True)
    for name, expected in manifest['files'].items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in additions:
            target.write_bytes(additions[name])
        else:
            origin = (source / name).resolve()
            if not origin.is_relative_to(source) or file_digest(origin) != expected:
                raise ValueError('Source changed during preparation: ' + name)
            shutil.copyfile(origin, target)
        if file_digest(target) != expected:
            raise ValueError('Prepared asset checksum mismatch: ' + name)
    (output / 'package.json').write_bytes(content)
    return {'id': manifest['id'], 'revision': manifest['revision'],
            'manifest_sha256': file_digest(output / 'package.json'), 'files': len(manifest['files'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Fetched sky130A directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bipolar',action='store_true',help='Create a separately versioned experimental adapter with pinned upstream PNP emitter-area extraction rules')
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output,args.bipolar), indent=2))


if __name__ == '__main__':
    main()
