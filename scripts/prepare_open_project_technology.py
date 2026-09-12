"""Backport the pinned upstream SKY130 resistor extraction fix into a new deck."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import atomic_write, file_digest


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    lock_path = ROOT / 'examples/open-projects/sky130-resistor-extraction.json'
    lock = json.loads(lock_path.read_text())
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != lock['base_technology_sha256']:
        raise ValueError('Unknown technology revision; use the pinned physical download. No correction applied.')
    text = data.decode('utf-8')
    if text.count(lock['before']) != 1:
        raise ValueError('Resistor extraction block is not unique.')
    corrected = text.replace(lock['before'], lock['after']).encode('utf-8')
    if hashlib.sha256(corrected).hexdigest() != lock['result_technology_sha256']:
        raise ValueError('Corrected technology checksum differs from the committed lock.')
    if output.exists():
        raise ValueError('Choose a new technology output directory.')
    output.mkdir(parents=True)
    target = output / 'sky130A.tech'
    atomic_write(target, corrected)
    shutil.copyfile(ROOT / 'examples/open-projects/LICENSE-open_pdks.txt', output / 'LICENSE-open_pdks.txt')
    report = {k: v for k, v in lock.items() if k not in ('before', 'after')}
    report.update(correction_lock_sha256=file_digest(lock_path), technology=str(target))
    atomic_write(output / 'provenance.json', json.dumps(report, indent=2) + '\n')
    return target, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Pinned sky130A.tech')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.out)[1], indent=2))
