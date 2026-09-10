"""Offline discovery and verification of the simulation packages shipped with Studio."""
import json
from pathlib import Path
import sys
from .model import file_digest


def bundle_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'icstudio/assets/pdks'


def packages(root=None, verify=False):
    root = Path(root or bundle_root()).resolve()
    collection = json.loads((root / 'collection.json').read_text(encoding='utf-8'))
    result = []
    for entry in collection['packages']:
        path = (root / entry['variant']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Invalid bundled PDK path.')
        manifest_path = path / 'package.json'
        if file_digest(manifest_path) != entry['manifest_sha256']:
            raise ValueError('Bundled PDK manifest changed: ' + entry['variant'])
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if verify:
            for relative, sha in manifest['files'].items():
                asset = (path / relative).resolve()
                if not asset.is_relative_to(path) or not asset.is_file() or file_digest(asset) != sha:
                    raise ValueError('Missing or changed bundled PDK asset: ' + relative)
        result.append({'path': str(path), 'kind': 'package', 'name': manifest['id'],
                       'family': manifest['family'], 'revision': manifest['revision']})
    return result
