"""Create portable, checksummed adapter packages from existing local PDKs."""
import argparse
import json
import shutil
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.pdk_import import scan_local
from icstudio.model import file_digest
from icstudio import __version__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True, help='Parent of the selected installed variants')
    ap.add_argument('--variants', nargs='+', default=['sky130A', 'gf180mcuC', 'ihp-sg13g2'])
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists(): raise ValueError('Use a new output directory.')
    args.output.mkdir(parents=True)
    entries = []
    for name in args.variants:
        if Path(name).name != name: raise ValueError('Variants must be directory names.')
        manifest = scan_local(args.input / name)
        source = Path(manifest.pop('source_root')); target = args.output / name
        if not any('LICENSE' in n.upper() or 'COPYING' in n.upper() for n in manifest['files']):
            raise ValueError('Add the upstream license text before packaging ' + name)
        for rel, sha in manifest['files'].items():
            dest = target / rel; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, dest)
            if file_digest(dest) != sha: raise ValueError('Asset changed while packaging: ' + rel)
        (target / 'package.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        catalog = manifest['technology']['simulation']['catalog']
        entries.append({'variant': name, 'revision': manifest['revision'], 'family': manifest['family'],
                        'assets': len(manifest['files']), 'indexed_symbols': len(catalog),
                        'placeable_symbols': sum(not v.get('unavailable') for v in catalog.values()),
                        'manifest_sha256': file_digest(target / 'package.json')})
    (args.output / 'collection.json').write_text(json.dumps({'application': __version__, 'packages': entries}, indent=2))
    (args.output / 'START-HERE.md').write_text('''# Open PDK adapter collection

Extract this entire archive. In IC Design Studio choose **Tools → Set up an open PDK → Add folder** and select this directory. Leave the desired variants checked and choose **Check and register**. On Registered revisions, select one and choose **New project with this PDK**.

These are pinned model, symbol and layer-map subsets for the application's adapters, not complete foundry PDK installations. SKY130 includes the physical support assets present in the supplied source snapshot. GF180MCU and IHP physical verification require the appropriate external rule decks. File-level locks and upstream provenance are retained inside each package. collection.json gives the exact revisions and catalogue counts.

IHP requires matching OSDI libraries. Its Verilog-A sources and notices are included; use the application's PDK installation guide for compilation and runtime selection. The supplied Windows ngspice binary alone is not an IHP runtime qualification.

No simulation or manufacturing qualification follows from successful package installation. Use a small representative circuit to validate the chosen models, simulator and corner. Built-in examples remain available without these packages.
''', encoding='utf-8')
    print(json.dumps(entries, indent=2))


if __name__ == '__main__': main()
