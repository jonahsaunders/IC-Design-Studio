"""Run unmodified public candidate decks and a missing-contact control."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import klayout.db as k

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))
from scripts.sky130_interconnect_geometry import check

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reference-root', required=True, type=Path,
                    help='Directory containing <counter|uart|apb>/sky130-pin-export/final.gds')
parser.add_argument('--output', required=True, type=Path, help='New evidence directory')
parser.add_argument('--klayout', required=True, type=Path, help='KLayout executable with Ruby DRC support')
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
source = repo / 'tests/fixtures/sky130-public-decks-v1'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
lock = json.loads((source / 'source-lock.json').read_bytes())
decks = {item['path'].split('/')[0]: (source / item['path'], item['sha256']) for item in lock['files']}
for path, digest in decks.values():
    assert sha(path) == digest
record = dict(schema=1, status='RUNNING', qualified=False, chunk_complete=False,
              new_coverage_decisions=0, driver_sha256=sha(__file__),
              source_lock_sha256=sha(source / 'source-lock.json'),
              engine=subprocess.check_output([str(args.klayout), '-b', '-v'], text=True).strip(),
              engine_sha256=sha(args.klayout), runs=[], controls=[],
              limitations=[
                  'Only native FEOL, BEOL and off-grid reference checks; not the full Tiny Tapeout harness precheck.',
                  'Seal and floating-metal options are explicitly false; prior independent connectivity evidence is separate.',
                  'SRAM_EXCLUDE is false, but upstream contains additional hard-coded cell filters. No full coverage is inferred.',
                  'Positive controls demonstrate the contact-coverage predicate only, not physical validity of an entire SRAM design.',
                  'No density, antenna, missing mask construction, x.20 threshold or catalog acceptance is established here.',
              ])

def save():
    (out / 'record.json').write_bytes((json.dumps(record, indent=2) + '\n').encode())

def run(label, gds, top, deck_name, flags):
    directory = out / label / deck_name
    directory.mkdir(parents=True)
    report = directory / 'report.lyrdb'
    command = [str(args.klayout), '-b', '-r', str(decks[deck_name][0])]
    variables = dict(input=str(gds), top_cell=top, report=str(report), thr='1',
                     feol='false', beol='false', offgrid='false', seal='false',
                     floating_met='false', sram_exclude='false')
    variables.update(flags)
    for name, value in variables.items():
        command += ['-rd', f'{name}={value}']
    start = time.monotonic()
    result = subprocess.run(command, cwd=directory, capture_output=True, timeout=240)
    (directory / 'stdout.log').write_bytes(result.stdout)
    (directory / 'stderr.log').write_bytes(result.stderr)
    item = dict(label=label, deck=deck_name, gds_sha256=sha(gds), command=command,
                returncode=result.returncode, elapsed_seconds=round(time.monotonic()-start, 2),
                stdout_sha256=sha(directory / 'stdout.log'), stderr_sha256=sha(directory / 'stderr.log'))
    record['runs'].append(item)
    save()
    assert result.returncode == 0, result.stderr.decode(errors='replace')[-4000:]
    tree = ET.parse(report)
    assert tree.getroot().tag == 'report-database'
    assert tree.find('items') is not None
    counts = {}
    for marker in tree.findall('.//items/item'):
        category = marker.findtext('category')
        counts[category] = counts.get(category, 0) + 1
    item.update(markers=sum(counts.values()), categories=counts, report_sha256=sha(report))
    save()
    print(json.dumps(dict(label=label, deck=deck_name, markers=item['markers'], categories=counts)), flush=True)
    return counts

try:
    for case, top in [('counter','counter'), ('uart','uart_tx'), ('apb','apb_fifo')]:
        gds = args.reference_root.resolve() / case / 'sky130-pin-export/final.gds'
        for deck in decks:
            run(case, gds, top, deck, dict(feol='true',beol='true',offgrid='true'))
    for core in (False, True):
        for covered in (False, True):
            name = f'mcon-core-{int(core)}-covered-{int(covered)}'
            layout = k.Layout()
            layout.dbu = 0.001
            cell = layout.create_cell('mcon_control')
            masks = {(67,44): k.Region(k.Box(0,0,170,170)),
                     (68,20): k.Region(k.Box(-200,-200,370,370))}
            if core:
                masks[(81,2)] = k.Region(k.Box(-1000,-1000,1000,1000))
            if covered:
                masks[(67,20)] = k.Region(k.Box(-200,-200,370,370))
            for layer, region in masks.items():
                cell.shapes(layout.layer(*layer)).insert(region)
            gds = out / (name + '.gds')
            layout.write(str(gds))
            studio = next(row['violations'] for row in check(masks)['checks'] if row['rule']=='ct.4')
            values = {}
            for deck in decks:
                counts = run(name, gds, cell.name, deck, dict(beol='true'))
                values[deck] = sum(value for key,value in counts.items() if 'MR_mcon.CON.10' in key)
            record['controls'].append(dict(name=name, core=core, covered=covered, studio_ct4=studio, native_mcon_coverage=values))
            assert (studio > 0) == (not covered)
            assert (values['chipfoundry'] > 0) == (not covered)
            assert (values['tinytapeout'] > 0) == (not covered and not core)
    record['status']='PASS'
    record['reference_native_checks_pass']=all(run['markers']==0 for run in record['runs'] if run['label'] in ('counter','uart','apb'))
    record['scope']='Successful execution/comparison only; native reference violations are retained. Not a full Tiny Tapeout precheck, foundry acceptance, or complete catalog coverage.'
finally:
    if record['status']=='RUNNING':
        record['status']='FAIL'
    save()
