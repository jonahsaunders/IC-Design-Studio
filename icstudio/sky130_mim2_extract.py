"""Bounded SKY130 MiM orientation from written electrodes, never schematic values.

The pinned public cap_device draws W along the bottom-contact direction and L
across it. Magic reports global X/Y dimensions. Preserve its connectivity and
correct that axis interpretation only for unambiguous rectangular electrodes.
"""
import json
import math
from pathlib import Path
import re
import shlex

from .model import atomic_write, file_digest

MARKER = '# STUDIO_SKY130_MIM2_ORIENTATION_V1'
MODEL = 'sky130_fd_pr__cap_mim_m3_2'
MODELS = {
    'sky130_fd_pr__cap_mim_m3_1': {'cap':(89,44), 'bottom':(70,20), 'cut':(70,44)},
    MODEL: {'cap':(97,44), 'bottom':(71,20), 'cut':(71,44)},
}
TECH = '5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e'
PCELL = '48d2111c3246cbbed88bca5cf479dd8edc4ce4629d5241cca4102368765da69a'


def masks(path, top, model=MODEL):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(path)); cell = layout.cell(top)
    if cell is None:
        raise ValueError('Missing MiM layout top.')
    def region(pair):
        index = layout.find_layer(*pair)
        return db.Region() if index is None else db.Region(cell.begin_shapes_rec(index)).merged()
    # Keep the layout alive while regions reference recursive shape iterators.
    return layout, {key:region(pair) for key,pair in MODELS[model].items()}


def required(path, top):
    needed = False
    for model in MODELS:
        layout, regions = masks(path, top, model)
        for cap in regions['cap'].each():
            box = cap.bbox()
            # A square bounding box does not establish a square electrode.
            # Inspect every electrode before dispatch, including later models.
            if cap.area() != box.area():
                raise ValueError('MiM orientation requires separate rectangular electrodes.')
            needed |= box.width() != box.height()
    # True squares retain native extraction; the nonsquare correction bounds
    # below are not a qualification claim or a new size limit for that path.
    return needed


def electrodes(path, top, model=MODEL):
    import klayout.db as db
    layout, regions = masks(path, top, model); dbu = layout.dbu; rows = []
    for cap in regions['cap'].each():
        box = cap.bbox()
        if cap.area() != box.area():
            raise ValueError('MiM orientation requires separate rectangular electrodes.')
        row = dict(model=model, box=[box.left,box.bottom,box.right,box.top], axis=None)
        if box.width() != box.height():
            nm = [box.width()*dbu*1000,box.height()*dbu*1000]
            if any(not 2000 <= v <= 30000 or abs(v/5-round(v/5)) > 1e-6 for v in nm):
                raise ValueError('Rectangular MiM extraction requires 2–30 µm on the 5 nm grid.')
            if model.endswith('_1') and max(nm) > 5*min(nm):
                raise ValueError('First-plate MiM extraction supports aspect ratio at most 5:1.')
            bottom = [p for p in regions['bottom'].each() if (db.Region(cap)-db.Region(p)).is_empty()]
            if len(bottom) != 1:
                raise ValueError('MiM orientation requires one continuous bottom electrode.')
            bottom = db.Region(bottom[0])
            if len(list((regions['cap'] & bottom).each())) != 1:
                raise ValueError('Shared MiM bottom electrodes need a separate extraction adapter.')
            axes = set(); contacts = []; contact_region = db.Region()
            for cut in regions['cut'].each():
                region = db.Region(cut)
                if not (region-bottom).is_empty() or (region-db.Region(cap)).is_empty():
                    continue
                if not (region & db.Region(cap)).is_empty():
                    raise ValueError('A MiM contact straddles the electrode boundary.')
                contact_region += region
                via = cut.bbox()
                horizontal = ((via.right < box.left or via.left > box.right)
                              and via.top >= box.bottom and via.bottom <= box.top)
                vertical = ((via.top < box.bottom or via.bottom > box.top)
                            and via.right >= box.left and via.left <= box.right)
                axes.add('x' if horizontal and not vertical else 'y' if vertical and not horizontal else 'corner')
                contacts.append([via.left,via.bottom,via.right,via.top])
            # A complete reflection-symmetric surround has no privileged axis.
            # Retain native global X/Y values, with explicit evidence, instead
            # of inventing a W direction or rejecting existing public layouts.
            # This does not qualify its distributed resistance/parasitic model.
            reflect_x = db.Trans(0, True, 0, box.bottom+box.top)
            reflect_y = db.Trans(2, True, box.left+box.right, 0)
            ring = {'x','y'} <= axes and all(
                (region ^ region.transformed(transform)).is_empty()
                for region in (bottom, contact_region) for transform in (reflect_x,reflect_y))
            if ring:
                row.update(axis='native', bottom_contacts=contacts,
                    convention='Reflection-symmetric four-sided contacts: retain native global X/Y; no unique PCell orientation or RF resistance qualification inferred.')
            elif axes == {'x'} or axes == {'y'}:
                row.update(axis=axes.pop(), bottom_contacts=contacts)
            else:
                raise ValueError('MiM orientation needs bottom contacts on exactly one axis.')
        rows.append(row)
    return dbu, rows


def normalize(gds, top, technology, directory, log):
    """Correct only native W/L tokens after independently checking mask sizes."""
    import klayout.db as db
    technology = Path(technology); directory = Path(directory)
    pcell = technology.with_suffix('.tcl')
    if file_digest(technology) != TECH or not pcell.is_file() or file_digest(pcell) != PCELL:
        raise ValueError('Rectangular MiM extraction requires the reviewed SKY130 technology and public PCell source.')
    scales = re.findall(r'^STUDIO_MIM_SCALE (\S+)$', log, re.M)
    if len(scales) != 1:
        raise ValueError('Missing or ambiguous native MiM coordinate scale.')
    scale = float(scales[0])*1000
    if not math.isfinite(scale) or min(abs(scale-5),abs(scale-10)) > 1e-5:
        raise ValueError('Unreviewed native MiM coordinate scale.')
    scale = round(scale)
    rows = []
    for model in MODELS:
        dbu, model_rows = electrodes(gds, top, model)
        rows.extend(model_rows)
    step = scale/(dbu*1000)
    path = directory/(top+'.ext'); original = path.read_bytes()
    text = original.decode('utf-8')
    if re.search(r'^use\s', text, re.M):
        raise ValueError('MiM orientation requires the private flattened extraction input.')
    seen = set(); changes = []; lines = []
    for line in text.splitlines(keepends=True):
        if any(line.startswith('device csubckt '+model+' ') for model in MODELS):
            tokens = shlex.split(line)
            if len(tokens) < 9 or not tokens[7].startswith('w=') or not tokens[8].startswith('l='):
                raise ValueError('Unreviewed native MiM parameter record.')
            native = [float(v.split('=',1)[1]) for v in tokens[7:9]]
            coords = [int(v)*step for v in tokens[3:7]]
            if any(not math.isfinite(v) or abs(v-round(v)) > 1e-6 for v in coords+native):
                raise ValueError('Nonintegral native MiM geometry.')
            site = db.Box(*(round(v) for v in coords))
            matches = [(i,row) for i,row in enumerate(rows) if row['model'] == tokens[2] and
                       db.Box(*row['box']).contains(site.p1) and db.Box(*row['box']).contains(site.p2)]
            if len(matches) != 1 or matches[0][0] in seen:
                raise ValueError('Native MiM location does not identify one unused electrode.')
            index,row = matches[0]; seen.add(index); box = db.Box(*row['box'])
            if any(not math.isclose(v*step,dimension,rel_tol=0,abs_tol=1e-6)
                   for v,dimension in zip(native,(box.width(),box.height()))):
                raise ValueError('Native MiM dimensions disagree with the written masks.')
            if row['axis'] == 'y':
                corrected,count = re.subn(r'\bw=([^\s]+)(\s+)l=([^\s]+)',
                                          lambda m:'w='+m[3]+m[2]+'l='+m[1],line)
                if count != 1:raise ValueError('Ambiguous native MiM W/L tokens.')
                changes.append(dict(electrode=index, before=line.rstrip(),after=corrected.rstrip()))
                line = corrected
        lines.append(line)
    if len(seen) != len(rows):
        raise ValueError('Native MiM extraction did not account for every electrode.')
    corrected = ''.join(lines).encode('utf-8')
    models = sorted({row['model'] for row in rows})
    proof = dict(schema=1, model=models[0] if len(models)==1 else None, models=models,
                 technology_sha256=TECH, pcell_sha256=PCELL,
                 source_convention='sky130::cap_device: W along the bottom-contact direction; L perpendicular.',
                 gds_sha256=file_digest(gds),native_coordinate_nm=scale,gds_dbu_um=dbu,
                 electrodes=rows,changes=changes,native_sha256=file_digest(path),
                 scope='Nonsquare capm/cap2m correction is bounded to 2–30 µm on the 5 nm grid (first plate at most 5:1), one bottom electrode per capacitor. Correct unambiguous contact axes; reflection-symmetric four-sided contacts retain native global X/Y without a unique-orientation or RF-resistance claim. True squares retain native dimensions without inheriting these correction bounds or an electrical-validity qualification. Connectivity and all other native values are unchanged.')
    if (directory/'native-original.ext').exists():
        raise ValueError('MiM extraction was already normalized.')
    (directory/'native-original.ext').write_bytes(original)
    path.write_bytes(corrected); proof['corrected_sha256'] = file_digest(path)
    atomic_write(directory/'mim-orientation.json', json.dumps(proof,indent=2,allow_nan=False))
    return proof
