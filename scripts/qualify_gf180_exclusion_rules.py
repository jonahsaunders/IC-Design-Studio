"""Compare bounded supplemental exclusion checks with the unchanged GF180 deck.

Known native/manual disagreements are retained as disagreements, not waivers.
This runs only the DE rule group on diagnostic coupons, not full-layout DRC.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from icstudio.model import file_digest
import check_gf180_fill as fill
from qualify_gf180_rules import LOCK, verify_deck


def coupons(k):
    """Expected outcomes are fixed from the locked manual and deck source."""
    rows = []
    def add(name, shapes, rule, layer, supplemental_failed, native_failed):
        rows.append(dict(name=name, shapes=shapes, rule=rule, layer=layer,
            supplemental_failed=supplemental_failed, native_failed=native_failed))
    for name, layer, other in (('NDMY', 111, 152), ('PMNDMY', 152, 111)):
        for width in (795, 800, 805):
            add(f'{name}-width-{width}', [(layer, 5, k.Box(10000, 10000, 10000+width, 15000))],
                'DE.2', name, width < 800, width < 800)
        add(f'{name}-masked-width-795', [(layer, 5, k.Box(10000, 10000, 10795, 15000)),
            (other, 5, k.Box(9000, 9000, 16000, 16000))], 'DE.2', name, True, False)
    for width, height in ((99995, 150000), (100000, 150000), (100005, 150000),
                          (80000, 200000), (80005, 200000), (200000, 80000)):
        area = width * height
        add(f'NDMY-area-{width}-{height}', [(111, 5, k.Box(10000, 10000, 10000+width, 10000+height))],
            'DE.3', 'NDMY', area > 15000*1000000 and min(width, height) > 80000,
            area >= 15000*1000000)
    for size, expected in ((180000, False), (20000, True)):
        hole = k.Box(20000, 20000, 20000+size, 20000+size)
        shape = k.Region(k.Box(10000, 10000, 210000, 210000)) - k.Region(hole)
        add(f'NDMY-hole-{size}', [(111, 5, shape)], 'DE.3-geometry-coverage', 'NDMY', expected, expected)
    for gap in (19995, 20000, 20005, -1000):
        add(f'NDMY-space-{gap}', [(111, 5, k.Box(10000, 10000, 15000, 15000)),
            (111, 5, k.Box(15000+gap, 10000, 20000+gap, 15000))],
            'DE.4', 'NDMY', 0 < gap < 20000, 0 < gap < 20000)
    for name, number in (('MCELL_FEOL_MK', 11), ('YMTP_MK', 86)):
        add(name, [(number, 17, k.Box(10000, 10000, 15000, 15000))],
            'unsupported-memory-layer', name, True, False)
    add('MTPMARK-is-distinct', [(122, 5, k.Box(10000, 10000, 15000, 15000))],
        'unsupported-memory-layer', 'YMTP_MK', False, False)
    return rows


def qualify(deck, output, klayout):
    import klayout.db as k
    deck = Path(deck).resolve(); output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    lock = json.loads(LOCK.read_text()); files = verify_deck(deck, lock)
    source = deck / 'klayout/drc/rule_decks/dummy_exclude.drc'
    executable = Path(shutil.which(klayout) or klayout).absolute()
    version = subprocess.run([str(executable), '-v'], check=True, capture_output=True, text=True).stdout.strip()
    if version != 'KLayout 0.30.5' or k.__version__ != '0.30.5':
        raise ValueError('Use KLayout 0.30.5 for both the native engine and Python geometry.')
    record = dict(schema=1, status='running', qualified=False,
        scope='Isolated DE rules and supplemental diagnostic coupons; neither complete native DRC nor process acceptance.',
        qualifier_sha256=file_digest(Path(__file__)), checker_sha256=file_digest(Path(fill.__file__)),
        deck_lock_sha256=file_digest(LOCK), deck_revision=lock['revision'], deck_files=files,
        manual_lock_sha256=file_digest(fill.COVERAGE_MANUAL),
        klayout=dict(path=str(executable), sha256=file_digest(executable), version=version), cases=[])
    def write(path, data): path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', newline='\n')
    def retain(): write(output / 'report.json', record)
    retain()
    try:
        for case in coupons(k):
            folder = output / case['name']; folder.mkdir()
            layout = k.Layout(); layout.dbu = .001; top = layout.create_cell('coupon')
            top.shapes(layout.layer(63, 0)).insert(k.Box(0, 0, 400000, 400000))
            for layer, datatype, shape in case['shapes']:
                top.shapes(layout.layer(layer, datatype)).insert(shape)
            gds = folder / 'coupon.gds'; layout.write(str(gds)); before = file_digest(gds)
            row = {key: value for key, value in case.items() if key != 'shapes'}
            row.update(gds_sha256=before, supplemental={})
            record['cases'].append(row); retain()
            for variant in ('C', 'D'):
                result = fill.inspect(gds, (0, 0, 400, 400), top_name='coupon', variant=variant)
                selected = [c for c in result['checks'] if c['rule'] == case['rule'] and c['layer'] == case['layer']]
                assert len(selected) == 1 and (selected[0]['status'] == 'failed') == case['supplemental_failed'], selected
                assert result['qualified'] is False
                path = folder / (variant+'.json'); write(path, result)
                row['supplemental'][variant] = dict(report_sha256=file_digest(path), check=selected[0])
            # Pass paths as -rd variables, avoiding Ruby source interpolation.
            wrapper = folder / 'wrapper.drc'
            wrapper.write_text("require 'logger'\nsource($input)\nreport('GF180 exclusion coupons', $output)\n"
                "ndmy = input(111, 5)\npmndmy = input(152, 5)\n"
                "logger = Logger.new($stdout)\neval(File.read($deck), binding, $deck)\n"
                "puts 'ICSTUDIO_DE_COMPLETED'\n", newline='\n')
            target = folder / 'native.lyrdb'
            command = [str(executable), '-b', '-r', str(wrapper), '-rd', 'input='+str(gds),
                       '-rd', 'output='+str(target), '-rd', 'deck='+str(source)]
            proc = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=120)
            (folder / 'engine.log').write_text(proc.stdout+proc.stderr, newline='\n')
            row.update(command=command, exit_code=proc.returncode, wrapper_sha256=file_digest(wrapper),
                       log_sha256=file_digest(folder / 'engine.log'))
            assert proc.returncode == 0 and 'ICSTUDIO_DE_COMPLETED' in proc.stdout, proc.stdout+proc.stderr
            for rule in ('DE.2', 'DE.3', 'DE.4'):
                assert proc.stdout.count('Executing rule '+rule) == 1
            tree = ET.parse(target)
            assert tree.getroot().tag == 'report-database' and tree.findtext('top-cell') == 'coupon'
            assert tree.find('categories') is not None and tree.find('items') is not None
            counts = Counter(item.findtext('category').strip("'") for item in tree.findall('./items/item'))
            native_rule = 'DE.3' if case['rule'] == 'DE.3-geometry-coverage' else case['rule']
            actual = counts[native_rule] > 0
            row.update(native_report_sha256=file_digest(target), native_markers=dict(counts),
                native_observed_failed=actual, disagreement=actual != case['supplemental_failed'])
            assert actual == case['native_failed'], row
            assert file_digest(gds) == before
            row['status'] = 'expected-outcomes-reproduced'; retain()
        assert files == verify_deck(deck, lock)
        record.update(status='diagnostic-controls-passed',
            disagreements=sum(row['disagreement'] for row in record['cases']),
            limitations=['Native DE.2 unions the two marker types and can hide a narrow marker.',
                'Native DE.3 reports all edges at or above 15000 um2, including permitted rectangle controls.',
                'Large nonrectangular DE.3 exceptions remain unqualified.',
                'Memory coupons establish supplemental coverage rejection, not a complete native memory-rule audit.',
                'Native rules remain unchanged; disagreements are not acceptance waivers.'])
        retain(); return record
    except Exception as exc:
        record.update(status='failed', error=repr(exc)); retain(); raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deck', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--klayout', default='klayout')
    args = parser.parse_args()
    result = qualify(args.deck, args.output, args.klayout)
    print(json.dumps({key: result[key] for key in ('status', 'qualified', 'disagreements')}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
