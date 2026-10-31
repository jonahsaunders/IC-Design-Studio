"""Check the IHP top-metal via recipe with both complete public geometry decks."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import ihp_klayout_drc
from icstudio.layout import kdb, polygon
from icstudio.layout_routing import via_recipes, via_shapes
from icstudio.model import file_digest
from scripts.qualify_standard_mos import load_technology

CASES = {'single': None, 'array': None, 'cut-width': 'TV2.a', 'cut-spacing': 'TV2.b',
         'lower-enclosure': 'TV2.c', 'upper-enclosure': 'TV2.d', 'upper-width': 'TM2.a'}


def accept(name, expected, result):
    # The maximal deck supplements the main deck; it does not duplicate every
    # main-table rule. Require both completed native reports and test their union.
    decks = result['decks']
    if len(decks) != 2 or {d['name'] for d in decks} != {'main', 'maximal'}:
        raise ValueError(name + ': both public decks must finish.')
    if expected is None:
        if result['violations']:
            raise ValueError(name + ': native geometry findings remain: ' + json.dumps(decks))
    elif not any(rule.strip("'\"").split()[0] == expected for d in decks for rule in d['categories']):
        raise ValueError(name + ': expected native rule was not detected.')


def stream(path, name):
    tech, _ = load_technology('ihp-sg13g2')
    recipe = next(v for v in via_recipes(tech) if v['name'] == 'TopMetal1 to TopMetal2')
    db = kdb(); layout = db.Layout(); layout.dbu = .001; top = layout.create_cell('topvia_coupon')
    masks = {r['name']: (r['gds'], r['datatype']) for r in tech['layers']}
    if name == 'cut-width': recipe.update(size=800, enclosure=600, pad=2000)
    if name == 'cut-spacing': recipe['spacing'] = 1000
    points = [(0, 0)]
    if name in ('array', 'cut-spacing'):
        pitch = recipe['size'] + recipe['spacing']
        points = [(x * pitch, y * pitch) for x in range(2) for y in range(2)]
    regions = {}
    for point in points:
        for shape in via_shapes(recipe, point, 'test'):
            poly = polygon(shape)
            if name == 'lower-enclosure' and shape['layer'] == recipe['lower']:
                poly = db.Box(-900, -900, 900, 900)
            if name == 'upper-enclosure' and shape['layer'] == recipe['upper']:
                poly = db.Box(-900, -900, 900, 900)
            if name == 'upper-width' and shape['layer'] == recipe['upper']:
                poly = db.Box(-950, -950, 950, 950)
            regions.setdefault(shape['layer'], db.Region()).insert(poly)
    for layer, region in regions.items():
        top.shapes(layout.layer(*masks[layer])).insert(region.merged())
    layout.write(str(path))
    return recipe


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--klayout', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args(); root = args.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    results = []
    for name, expected in CASES.items():
        source = root / (name + '.gds'); recipe = stream(source, name)
        result = ihp_klayout_drc.drc(args.klayout, source, 'topvia_coupon', root / name)
        accept(name, expected, result)
        results.append(dict(name=name, expected_rule=expected, recipe=recipe, native=result))
        print(name + ' PASS', flush=True)
    report = dict(schema=1, status='PASS', chunk=7, chunk_complete=False, qualified=False,
                  scope='Two ordinary top-metal via fixtures and five specific geometric faults. Full public DRC, no pad/edge-seal, antenna, density, LVS, electrical or complete-chip qualification.',
                  cases=results, runner_sha256=file_digest(__file__))
    (root / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
