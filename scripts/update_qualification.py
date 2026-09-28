"""Render reviewed reference evidence consistently; --check is used by release CI."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.qualification import catalog, status, documentation, markdown


def update(check=False):
    for key in catalog(ROOT):
        record = status(key, root=ROOT)
        if record['errors']:
            raise ValueError(key+': '+'; '.join(record['errors']))
    path = ROOT/'docs/REFERENCE_QUALIFICATION.md'
    contents = documentation(ROOT)
    targets = {path: contents}
    for path in (ROOT/'README.md', ROOT/'examples/gf180-banba/layout/README.md'):
        text = path.read_text(encoding='utf-8')
        start, end = '<!-- qualification:banba:start -->', '<!-- qualification:banba:end -->'
        if start not in text or end not in text:
            raise ValueError('Missing qualification markers: '+str(path))
        block = markdown(status('gf180-banba-layout', root=ROOT))
        targets[path] = text.split(start)[0]+start+'\n'+block+'\n'+end+text.split(end)[1]
    for path, text in targets.items():
        if check:
            if not path.is_file() or path.read_text(encoding='utf-8') != text:
                raise ValueError('Stale generated qualification: '+str(path))
        else:
            newline = '\r\n' if path.exists() and b'\r\n' in path.read_bytes() else '\n'
            path.write_bytes(text.replace('\n', newline).encode('utf-8'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    update(parser.parse_args().check)
