"""Experimental IHP block fill: native geometry evidence, no timing acceptance.

Use the checksum-locked upstream macros and maximal DRC deck. Keep the declared
original die, every original mask and all native rule groups. This deliberately
refuses low-poly-density inputs: the active/poly pattern needs separate device
and extraction handling when it would add dummy transistors.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

MACROS = {
    'sg13g2_filler_ActGatP.lym': 'ea36de0e0485bc876481a35a0ebae5039d8d47272e52f7b3488b7b1984278d11',
    'sg13g2_filler_Metal.lym': 'bf1fb2dcdba695ed87d0c7b8cfa5e9829e40e3239d2a43366d1cb88e7df95131',
    'sg13g2_filler_TopMetal.lym': '85f428cb34955f4c31b172d4a6830d6bc56e640dc229160e6a11959b5b410b5c',
}
DECK = '46f21123f6439da8e46f2eb32035d4870c2125ee1a1684308937597c4d4d608a'
LAYERS = (1, 8, 10, 30, 50, 67, 126, 134)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generation_script(macros):
    parts = ['source($in_gds)\ntarget($out_gds, "ICSTUDIO_IHP_FILL")\nfill_scope = source.extent\n']
    for name, digest in MACROS.items():
        path = Path(macros) / name
        require(sha(path) == digest, 'Pinned IHP fill macro changed: ' + name)
        script = ET.parse(path).getroot().findtext('text')
        scope_count = {'sg13g2_filler_ActGatP.lym': 1, 'sg13g2_filler_Metal.lym': 5,
                       'sg13g2_filler_TopMetal.lym': 2}[name]
        require(script and script.count('EdgeSeal.holes') == scope_count, 'Unsupported upstream fill scope.')
        if name == 'sg13g2_filler_ActGatP.lym':
            step = '  (cellframe1-exclLayGatP-exclLayAct).fill(gp_fill, hstep(gp_spacing_h, gp_offset_v), vstep(gp_offset_h, gp_spacing_v))'
            require(script.count(step) == 1, 'Unsupported upstream poly step.')
            script = script.replace(step, '# Existing circuit poly exceeds GFil.g; add no unnecessary dummy MOS gates.')
        if name == 'sg13g2_filler_Metal.lym':
            for n in (3, 4, 5):
                old = "'distance_m%d' => 2.0" % n
                require(script.count(old) == 1, 'Unsupported upstream metal spacing.')
                script = script.replace(old, "'distance_m%d' => 1.5" % n)
        parts.append(script.replace('EdgeSeal.holes', 'fill_scope'))
    return '\n'.join(parts) + '\nputs "IHP_FILL_GENERATION_COMPLETE"\n'


def masks(layout):
    import klayout.db as k
    return {(layout.get_info(i).layer, layout.get_info(i).datatype):
            k.Region(layout.top_cell().begin_shapes_rec(i)).merged() for i in layout.layer_indices()}


def validate_input(layout, top, die):
    import klayout.db as k
    tops = list(layout.top_cells())
    require(layout.dbu == .001 and len(tops) == 1 and tops[0].name == top,
            'Expected a unique IHP top on the 1 nm database grid.')
    bounds = k.Box(*die)
    require(bounds.width() > 0 and bounds.height() > 0 and bounds.area() <= 1_000_000_000_000 and
            tops[0].bbox() == bounds, 'Keep the exact original reference die, limited to 1 mm².')
    before = masks(layout); empty = k.Region()
    require(all(before.get((n, 22), empty).is_empty() for n in (*LAYERS, 5)), 'Input already contains fill.')
    require(all(before.get(pair, empty).is_empty() for pair in ((39, 0), (235, 0))),
            'Chip seal/boundary geometry needs its own fill scope.')
    poly = before.get((5, 0), empty).area() / bounds.area()
    require(poly > .15, 'Existing poly must exceed GFil.g; dummy-transistor fill is unsupported.')
    return before, bounds, poly


def merge_fill(layout, fill, target, before, bounds):
    import klayout.db as k
    require(fill.dbu == layout.dbu and len(list(fill.top_cells())) == 1, 'Invalid generated fill hierarchy.')
    generated = masks(fill); empty = k.Region(); counts = {}
    for pair, region in generated.items():
        require(pair[1] == 22 and pair[0] in LAYERS and (region - k.Region(bounds)).is_empty(),
                'Unexpected or out-of-bounds fill mask.')
        require(before.get(pair, empty).is_empty(), 'Fill would overwrite existing material.')
        layout.top_cell().shapes(layout.layer(*pair)).insert(region); counts[str(pair[0])+'/22'] = region.count()
    require(all(not generated.get((n, 22), empty).is_empty() for n in LAYERS), 'Missing required fill layer.')
    require((generated[(1, 22)] & before.get((5, 0), empty)).is_empty(), 'Fill introduced a MOS gate.')
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False; layout.write(str(target), options)
    check = k.Layout(); check.read(str(target)); after = masks(check)
    require(check.top_cell().bbox() == bounds and check.dbu == layout.dbu, 'Written fill changed its extent or grid.')
    for pair in before.keys() | after.keys():
        expected = before.get(pair, empty) + generated.get(pair, empty)
        require((after.get(pair, empty) ^ expected.merged()).is_empty(), 'Written fill changed an original mask.')
    density = {str(n): 100 * (after.get((n, 0), empty) + after.get((n, 22), empty)).merged().area() / bounds.area()
               for n in (1, 5, 8, 10, 30, 50, 67, 126, 134)}
    return counts, density


def prepare(gds, top, die, macros, deck, executable, output):
    import klayout.db as k
    paths = [Path(p).resolve() for p in (gds, macros, deck, executable, output)]
    gds, macros, deck, executable, output = paths
    require(not output.exists(), 'Use a new output directory to preserve earlier evidence.')
    layout = k.Layout(); layout.read(str(gds)); before, bounds, poly = validate_input(layout, top, die)
    script = generation_script(macros)
    deck_bytes = deck.read_bytes().replace(b'\r\n', b'\n')
    require(hashlib.sha256(deck_bytes).hexdigest() == DECK, 'The native maximal DRC deck changed.')
    version = subprocess.check_output([str(executable), '-v'], text=True).strip()
    require(version == 'KLayout 0.30.5', 'Use the qualified KLayout 0.30.5 engine.')
    source_digest = sha(gds); output.mkdir(parents=True)
    (output/'generate.drc').write_text(script, encoding='utf-8', newline='\n')
    (output/'sg13g2_maximal.lydrc').write_bytes(deck_bytes)
    shutil.copyfile(gds, output/'original.gds')
    commands = []
    def run(script_name, log_name, options, timeout):
        cmd = [str(executable), '-b', '-r', str(output/script_name)]
        for key, value in options.items():
            cmd.extend(['-rd', key+'='+str(value)])
        commands.append(cmd)
        with (output/log_name).open('w', encoding='utf-8') as log:
            proc = subprocess.run(cmd, cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        require(proc.returncode == 0, 'Native engine failed; inspect ' + log_name)
    run('generate.drc', 'generation.log', dict(in_gds=output/'original.gds', out_gds=output/'fill-only.gds'), 600)
    require('IHP_FILL_GENERATION_COMPLETE' in (output/'generation.log').read_text(), 'Incomplete fill generation.')
    fill = k.Layout(); fill.read(str(output/'fill-only.gds'))
    counts, density = merge_fill(layout, fill, output/'filled.gds', before, bounds)
    run('sg13g2_maximal.lydrc', 'engine.log', dict(in_gds=output/'filled.gds', report_file=output/'full.lyrdb',
                                                fillerRules='true', densityRules='true'), 1800)
    items = ET.parse(output/'full.lyrdb').findall('./items/item')
    require(sha(gds) == source_digest, 'Input changed during generation.')
    record = dict(schema=1, status='native-geometry-passed' if not items else 'native-geometry-failed', qualified=False,
        top=top, original_gds_sha256=source_digest, filled_gds_sha256=sha(output/'filled.gds'),
        original_die_nm=die, original_masks_unchanged=True, original_poly_percent=100*poly,
        macro_sha256=MACROS, native_deck_sha256=DECK, engine_version=version, engine_sha256=sha(executable),
        script_sha256=sha(__file__), added_polygons=counts, density_percent=density,
        markers=len(items), categories=dict(Counter(i.findtext('category') for i in items)), commands=commands,
        limitations=['Experimental block fill; no chip seal/scribe qualification.',
                     'Native geometry results do not qualify unimplemented manual rules.',
                     'Device/port LVS, post-fill extraction, timing and production integration are separate gates.'],
        files={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    (output/'record.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8', newline='\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('gds','macros','deck','executable','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--die-nm', nargs=4, type=int, required=True)
    args = parser.parse_args()
    result = prepare(args.gds, args.top, args.die_nm, args.macros, args.deck, args.executable, args.output)
    print(json.dumps({k:result[k] for k in ('status','qualified','markers','filled_gds_sha256')}))
    return 0 if result['markers'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
