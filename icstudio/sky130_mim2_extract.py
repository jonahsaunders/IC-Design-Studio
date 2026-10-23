"""Bounded MiM2 orientation from written electrodes, never schematic values.

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
TECH = '5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e'
PCELL = '48d2111c3246cbbed88bca5cf479dd8edc4ce4629d5241cca4102368765da69a'


def masks(path, top):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(path)); cell = layout.cell(top)
    if cell is None:
        raise ValueError('Missing MiM layout top.')
    def region(pair):
        index = layout.find_layer(*pair)
        return db.Region() if index is None else db.Region(cell.begin_shapes_rec(index)).merged()
    # Keep the layout alive while regions reference recursive shape iterators.
    return layout, {key:region(pair) for key,pair in
                        {'cap':(97,44), 'bottom':(71,20), 'cut':(71,44)}.items()}


def required(path, top):
    layout, regions = masks(path, top)
    return any(p.bbox().width() != p.bbox().height() for p in regions['cap'].each())


def electrodes(path, top):
    import klayout.db as db
    layout, regions = masks(path, top); dbu = layout.dbu; rows = []
    for cap in regions['cap'].each():
        box = cap.bbox()
        if cap.area() != box.area():
            raise ValueError('MiM orientation requires separate rectangular cap2m electrodes.')
        row = dict(box=[box.left,box.bottom,box.right,box.top], axis=None)
        if box.width() != box.height():
            nm = [box.width()*dbu*1000,box.height()*dbu*1000]
            if any(not 2000 <= v <= 30000 or abs(v/5-round(v/5)) > 1e-6 for v in nm):
                raise ValueError('Rectangular MiM extraction requires 2–30 µm on the 5 nm grid.')
            bottom = [p for p in regions['bottom'].each() if (db.Region(cap)-db.Region(p)).is_empty()]
            if len(bottom) != 1:
                raise ValueError('MiM orientation requires one continuous bottom electrode.')
            bottom = db.Region(bottom[0])
            if len(list((regions['cap'] & bottom).each())) != 1:
                raise ValueError('Shared MiM bottom electrodes need a separate extraction adapter.')
            axes = set(); contacts = []
            for cut in regions['cut'].each():
                region = db.Region(cut)
                if not (region-bottom).is_empty() or (region-db.Region(cap)).is_empty():
                    continue
                if not (region & db.Region(cap)).is_empty():
                    raise ValueError('A MiM contact straddles the electrode boundary.')
                via = cut.bbox()
                horizontal = ((via.right < box.left or via.left > box.right)
                              and box.bottom <= via.bottom and via.top <= box.top)
                vertical = ((via.top < box.bottom or via.bottom > box.top)
                            and box.left <= via.left and via.right <= box.right)
                if horizontal == vertical:
                    raise ValueError('MiM bottom-contact orientation is ambiguous.')
                axes.add('x' if horizontal else 'y')
                contacts.append([via.left,via.bottom,via.right,via.top])
            if len(axes) != 1:
                raise ValueError('MiM orientation needs bottom contacts on exactly one axis.')
            row.update(axis=axes.pop(), bottom_contacts=contacts)
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
    dbu, rows = electrodes(gds, top); step = scale/(dbu*1000)
    path = directory/(top+'.ext'); original = path.read_bytes()
    text = original.decode('utf-8')
    if re.search(r'^use\s', text, re.M):
        raise ValueError('MiM orientation requires the private flattened extraction input.')
    seen = set(); changes = []; lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith('device csubckt '+MODEL+' '):
            tokens = shlex.split(line)
            if len(tokens) < 9 or not tokens[7].startswith('w=') or not tokens[8].startswith('l='):
                raise ValueError('Unreviewed native MiM parameter record.')
            native = [float(v.split('=',1)[1]) for v in tokens[7:9]]
            coords = [int(v)*step for v in tokens[3:7]]
            if any(not math.isfinite(v) or abs(v-round(v)) > 1e-6 for v in coords+native):
                raise ValueError('Nonintegral native MiM geometry.')
            site = db.Box(*(round(v) for v in coords))
            matches = [(i,row) for i,row in enumerate(rows) if
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
    proof = dict(schema=1, model=MODEL, technology_sha256=TECH, pcell_sha256=PCELL,
                 source_convention='sky130::cap_device: W along the bottom-contact direction; L perpendicular.',
                 gds_sha256=file_digest(gds),native_coordinate_nm=scale,gds_dbu_um=dbu,
                 electrodes=rows,changes=changes,native_sha256=file_digest(path),
                 scope='Rectangular 2–30 µm cap2m on the 5 nm grid, one bottom electrode per capacitor and unambiguous contact axis. Connectivity and all other native values are unchanged.')
    if (directory/'native-original.ext').exists():
        raise ValueError('MiM extraction was already normalized.')
    (directory/'native-original.ext').write_bytes(original)
    path.write_bytes(corrected); proof['corrected_sha256'] = file_digest(path)
    atomic_write(directory/'mim-orientation.json', json.dumps(proof,indent=2,allow_nan=False))
    return proof
