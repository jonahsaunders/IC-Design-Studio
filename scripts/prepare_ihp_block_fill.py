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


def generation_script(macros, *, exclusions=False, metal_spacing_um=1.5, topmetal_width_um=5.):
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
    return generation_settings('\n'.join(parts) + '\nputs "IHP_FILL_GENERATION_COMPLETE"\n',
                               exclusions, metal_spacing_um, topmetal_width_um)


def generation_settings(script, exclusions=False, metal_spacing_um=1.5, topmetal_width_um=5.):
    """Bound experimental native macro settings; all output rules still run."""
    require(type(exclusions) is bool and metal_spacing_um in (1.35, 1.4, 1.5) and
            topmetal_width_um in (5., 5.2, 8.), 'Unsupported experimental fill settings.')
    if exclusions:
        require(script.count('fill_scope = source.extent') == 1, 'Unsupported exclusion scope.')
        script = script.replace('fill_scope = source.extent', 'fill_scope = source.extent - source.input("10000/0")')
    if metal_spacing_um != 1.5:
        for n in range(1, 6):
            old = f"'distance_m{n}' => 1.5"
            require(script.count(old) == 1, 'Unsupported upstream metal spacing.')
            script = script.replace(old, f"'distance_m{n}' => {metal_spacing_um}")
    if topmetal_width_um != 5.:
        require(script.count('width = 5.0') == 1, 'Unsupported upstream top-metal width.')
        script = script.replace('width = 5.0', f'width = {topmetal_width_um}')
    return script


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
    require(all(before.get(pair, empty).is_empty() for pair in ((39, 0), (189, 0), (235, 0))),
            'Chip seal/boundary geometry needs its own fill scope.')
    poly = before.get((5, 0), empty).area() / bounds.area()
    require(poly > .15, 'Existing poly must exceed GFil.g; dummy-transistor fill is unsupported.')
    return before, bounds, poly


def exclusion_region(layout, view):
    """Accept only original masks plus a bounded auxiliary exclusion layer.

    The caller supplies this generation view. It does not prove cell coverage;
    native electrical re-extraction and the complete-cell audit must do that.
    The exclusion mask never enters the delivered layout.
    """
    import klayout.db as k
    require(view.dbu == layout.dbu and len(list(view.top_cells())) == 1 and
            view.top_cell().name == layout.top_cell().name, 'Invalid exclusion view hierarchy or grid.')
    before, after = masks(layout), masks(view); empty = k.Region(); pair = (10000, 0)
    require(pair not in before and pair in after and not after[pair].is_empty(), 'Missing or preexisting exclusion mask.')
    for layer in before.keys() | after.keys():
        if layer != pair:
            require((before.get(layer, empty) ^ after.get(layer, empty)).is_empty(), 'Exclusion view changed original geometry.')
    require((after[pair] - k.Region(layout.top_cell().bbox())).is_empty(), 'Exclusion region extends beyond the original block.')
    return after[pair]


def substrate_implant(active, before, bounds):
    """Bound a physical P+ alternative to ordinary PWell without circuit edits.

    The pinned manual defines pSD/Activ in PWell as substrate material. This
    changes the delivered process mask; it is not a simulation-only junction
    substitution. Native geometry and electrical checks remain mandatory.
    """
    import klayout.db as k
    require(not active.is_empty() and all(p.is_box() for p in active.each()),
            'P+ fill requires rectangular active filler.')
    # pSD.c requires 180 nm enclosure in NWell. NWell is excluded here, and
    # clipping the optional PWell enclosure preserves the original footprint.
    added = active.sized(180) & k.Region(bounds)
    require((active - added).is_empty(), 'The implant must cover every active filler.')
    forbidden = ((1, 0), (5, 0), (6, 0), (7, 0), (7, 21), (14, 0), (26, 0),
                 (28, 0), (31, 0), (32, 0), (44, 0), (46, 21), (111, 0))
    for pair in forbidden:
        require((added & before.get(pair, k.Region())).is_empty(),
                'P+ fill overlaps circuit material or a process modifier: '+str(pair))
    return added


def merge_fill(layout, fill, target, before, bounds, active_type='n-floating'):
    import klayout.db as k
    require(active_type in ('n-floating', 'p-substrate'), 'Unsupported active-fill type.')
    require(fill.dbu == layout.dbu and len(list(fill.top_cells())) == 1, 'Invalid generated fill hierarchy.')
    generated = masks(fill); empty = k.Region(); counts = {}
    for pair, region in generated.items():
        require(pair[1] == 22 and pair[0] in LAYERS and (region - k.Region(bounds)).is_empty(),
                'Unexpected or out-of-bounds fill mask.')
        require(before.get(pair, empty).is_empty(), 'Fill would overwrite existing material.')
        layout.top_cell().shapes(layout.layer(*pair)).insert(region); counts[str(pair[0])+'/22'] = region.count()
    require(all(not generated.get((n, 22), empty).is_empty() for n in LAYERS), 'Missing required fill layer.')
    require((generated[(1, 22)] & before.get((5, 0), empty)).is_empty(), 'Fill introduced a MOS gate.')
    if active_type == 'p-substrate':
        added = substrate_implant(generated[(1, 22)], before, bounds)
        layout.top_cell().shapes(layout.layer(14, 0)).insert(added)
        generated[14, 0] = added
        counts['14/0'] = added.count()
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False; layout.write(str(target), options)
    check = k.Layout(); check.read(str(target)); after = masks(check)
    require(check.top_cell().bbox() == bounds and check.dbu == layout.dbu, 'Written fill changed its extent or grid.')
    for pair in before.keys() | after.keys():
        expected = before.get(pair, empty) + generated.get(pair, empty)
        require((after.get(pair, empty) ^ expected.merged()).is_empty(), 'Written fill changed an original mask.')
    density = {str(n): 100 * (after.get((n, 0), empty) + after.get((n, 22), empty)).merged().area() / bounds.area()
               for n in (1, 5, 8, 10, 30, 50, 67, 126, 134)}
    return counts, density


def prepare(gds, top, die, macros, deck, executable, output, active_type='n-floating', *,
            exclusion_view=None, metal_spacing_um=1.5, topmetal_width_um=5.):
    import klayout.db as k
    paths = [Path(p).resolve() for p in (gds, macros, deck, executable, output)]
    gds, macros, deck, executable, output = paths
    require(not output.exists(), 'Use a new output directory to preserve earlier evidence.')
    layout = k.Layout(); layout.read(str(gds)); before, bounds, poly = validate_input(layout, top, die)
    excluded = None; exclusion_digest = None
    if exclusion_view is not None:
        exclusion_view = Path(exclusion_view).resolve()
        view = k.Layout(); view.read(str(exclusion_view))
        excluded = exclusion_region(layout, view); exclusion_digest = sha(exclusion_view)
    script = generation_script(macros, exclusions=excluded is not None,
                               metal_spacing_um=metal_spacing_um, topmetal_width_um=topmetal_width_um)
    deck_bytes = deck.read_bytes().replace(b'\r\n', b'\n')
    require(hashlib.sha256(deck_bytes).hexdigest() == DECK, 'The native maximal DRC deck changed.')
    version = subprocess.check_output([str(executable), '-v'], text=True).strip()
    require(version == 'KLayout 0.30.5', 'Use the qualified KLayout 0.30.5 engine.')
    source_digest = sha(gds); output.mkdir(parents=True)
    (output/'generate.drc').write_text(script, encoding='utf-8', newline='\n')
    (output/'sg13g2_maximal.lydrc').write_bytes(deck_bytes)
    shutil.copyfile(gds, output/'original.gds')
    generation_input = output/'original.gds'
    if excluded is not None:
        generation_input = output/'generation-input.gds'
        shutil.copyfile(exclusion_view, generation_input)
        require(sha(generation_input) == exclusion_digest, 'Exclusion view changed during capture.')
    commands = []
    def run(script_name, log_name, options, timeout):
        cmd = [str(executable), '-b', '-r', str(output/script_name)]
        for key, value in options.items():
            cmd.extend(['-rd', key+'='+str(value)])
        commands.append(cmd)
        with (output/log_name).open('w', encoding='utf-8') as log:
            proc = subprocess.run(cmd, cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        require(proc.returncode == 0, 'Native engine failed; inspect ' + log_name)
    run('generate.drc', 'generation.log', dict(in_gds=generation_input, out_gds=output/'fill-only.gds'), 600)
    require('IHP_FILL_GENERATION_COMPLETE' in (output/'generation.log').read_text(), 'Incomplete fill generation.')
    fill = k.Layout(); fill.read(str(output/'fill-only.gds'))
    if excluded is not None:
        require(all((region & excluded).is_empty() for region in masks(fill).values()),
                'Generated filler overlaps the requested exclusion region.')
    counts, density = merge_fill(layout, fill, output/'filled.gds', before, bounds, active_type)
    run('sg13g2_maximal.lydrc', 'engine.log', dict(in_gds=output/'filled.gds', report_file=output/'full.lyrdb',
                                                fillerRules='true', densityRules='true'), 1800)
    items = ET.parse(output/'full.lyrdb').findall('./items/item')
    require(sha(gds) == source_digest, 'Input changed during generation.')
    record = dict(schema=1, status='native-geometry-passed' if not items else 'native-geometry-failed', qualified=False,
        top=top, original_gds_sha256=source_digest, filled_gds_sha256=sha(output/'filled.gds'),
        original_die_nm=die, original_masks_unchanged=active_type == 'n-floating',
        original_circuit_geometry_preserved=True, active_fill_type=active_type, original_poly_percent=100*poly,
        exclusion_view_sha256=exclusion_digest, exclusion_area_nm2=None if excluded is None else excluded.area(),
        metal_spacing_um=metal_spacing_um, topmetal_width_um=topmetal_width_um,
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
    parser.add_argument('--active-type', choices=('n-floating', 'p-substrate'), default='n-floating',
                        help='Experimental physical fill type; both require separate electrical qualification.')
    parser.add_argument('--exclusion-view', type=Path, help='Original masks plus auxiliary layer 10000/0; requires electrical coverage verification.')
    parser.add_argument('--metal-spacing-um', type=float, choices=(1.35, 1.4, 1.5), default=1.5)
    parser.add_argument('--topmetal-width-um', type=float, choices=(5., 5.2, 8.), default=5.)
    args = parser.parse_args()
    result = prepare(args.gds, args.top, args.die_nm, args.macros, args.deck, args.executable, args.output, args.active_type,
                     exclusion_view=args.exclusion_view, metal_spacing_um=args.metal_spacing_um, topmetal_width_um=args.topmetal_width_um)
    print(json.dumps({k:result[k] for k in ('status','qualified','markers','filled_gds_sha256')}))
    return 0 if result['markers'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
