"""Audit the public measured IHP coil and compare complete complex responses.

This is a reference-data/reproduction audit, not a foundry accuracy certificate
or an attachment of these results to a different generated inductor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.inductor_em import touchstone
from icstudio.openems_waves import maximum_gain

FIXTURE = ROOT/'tests/fixtures/ihp-measured-coil-v1'
LOCK_SHA256 = '698fea216a6a4dd9c55f1e74321ffe08d0feb2a951c2c7041893edd6329a045f'
COMMIT = '0f87e9d069de3e88bdfdc5bb30d4a0958f045d32'
REFERENCES = ('measured.s2p', 'openems-1um.s2p', 'openems-2um.s2p', 'palace-2um.s2p')
# Rounded independent values published in the retained upstream study.
PUBLISHED = {
    'measured.s2p': [4.55, 4.86, 5.01, 15.96, 11.07],
    'openems-1um.s2p': [4.67, 5.14, 4.81, 14.54, 11.08],
    'openems-2um.s2p': [4.66, 5.16, 4.81, 14.31, 10.80],
    'palace-2um.s2p': [4.69, 5.07, 4.90, 14.83, 11.22],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_sources(root=FIXTURE):
    root = Path(root)
    if sha(root/'SOURCE.json') != LOCK_SHA256:
        raise ValueError('Changed measured-coil source inventory.')
    lock = json.loads((root/'SOURCE.json').read_bytes())
    for row in lock['files']:
        data = (root/row['file']).read_bytes()
        blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if (len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']
                or blob != row['git_blob']):
            raise ValueError('Changed measured-coil public source: '+row['file'])
    return lock


def network(text):
    """Independent matrix oracle for these unwrapped Touchstone 1.x inputs.

    Keep DC when present in a published solver file. It is excluded explicitly
    when comparing the common measured band, never relabeled as positive f.
    """
    options = None; rows = []
    for raw in text.splitlines():
        line = raw.split('!', 1)[0].strip()
        if not line: continue
        if line.startswith('#'):
            fields = line[1:].lower().split()
            if (options or rows or len(fields) != 5 or fields[0] not in ('hz', 'khz', 'mhz', 'ghz')
                    or fields[1] != 's' or fields[2] not in ('ri', 'ma', 'db') or fields[3] != 'r'):
                raise ValueError('Invalid two-port reference options.')
            reference = float(fields[4])
            if not np.isfinite(reference) or reference <= 0:
                raise ValueError('Invalid reference impedance.')
            options = fields; continue
        if not options: raise ValueError('Reference options must precede data.')
        values = np.array([float(v) for v in line.split()])
        if len(values) != 9 or not np.isfinite(values).all():
            raise ValueError('Each reference row needs nine finite numbers.')
        pairs = values[1:].reshape(4, 2)
        if options[2] == 'ri': elements = pairs[:, 0]+1j*pairs[:, 1]
        else:
            magnitude = 10**(pairs[:, 0]/20) if options[2] == 'db' else pairs[:, 0]
            if (magnitude < 0).any() or not np.isfinite(magnitude).all():
                raise ValueError('Invalid reference magnitude.')
            elements = magnitude*np.exp(1j*np.deg2rad(pairs[:, 1]))
        scale = dict(hz=1., khz=1e3, mhz=1e6, ghz=1e9)[options[0]]
        rows.append((values[0]*scale, elements.reshape((2, 2), order='F')))
    if len(rows) < 3: raise ValueError('Too few two-port reference samples.')
    f = np.array([row[0] for row in rows]); s = np.array([row[1] for row in rows])
    if not np.isfinite(f).all() or f[0] < 0 or not (np.diff(f) > 0).all():
        raise ValueError('Reference frequency must be nonnegative and strictly increasing.')
    eye = np.eye(2)
    try: z = reference*(eye+s)@np.linalg.inv(eye-s)
    except np.linalg.LinAlgError as exc: raise ValueError('Singular reference network.') from exc
    if not np.isfinite(z).all(): raise ValueError('Nonfinite reference impedance.')
    vector = np.array([1., -1.])
    return dict(frequency=f, scattering=s, impedance=z, differential=vector@z@vector, reference=reference)


def metrics(data):
    """Fixed published metric definitions; interpolate complex Z, not L/Q."""
    f, z = data['frequency'], data['differential']
    if f[0] > 1e8 or f[-1] < 1e9: raise ValueError('Reference must bracket 100 MHz and 1 GHz.')
    crossing = np.flatnonzero((z.imag[:-1] > 0) & (z.imag[1:] <= 0))
    if not len(crossing): raise ValueError('No bracketed first self-resonance.')
    i = int(crossing[0]); srf = f[i]+(f[i+1]-f[i])*z[i].imag/(z[i].imag-z[i+1].imag)
    mask = (f > 0) & (f < srf) & (z.real > 0) & (z.imag > 0)
    if not mask.any(): raise ValueError('No positive inductive Q samples below first resonance.')
    q = np.where(mask, z.imag/np.where(z.real == 0, np.inf, z.real), -np.inf)
    peak = int(np.argmax(q)); one = np.interp(1e9, f, z.real)+1j*np.interp(1e9, f, z.imag)
    return dict(r_at_100mhz_ohm=float(np.interp(1e8, f, z.real)), r_at_1ghz_ohm=float(one.real),
                l_at_1ghz_nh=float(one.imag/(2*np.pi)), peak_q=float(q[peak]),
                peak_q_frequency_hz=float(f[peak]), first_srf_hz=float(srf))


def compare(observed, reference, start_hz=1e8, stop_hz=14e9):
    """Report complex errors on a declared common band without accepting a model."""
    for data in (observed, reference):
        if data['frequency'][0] > start_hz or data['frequency'][-1] < stop_hz:
            raise ValueError('Both responses must cover the entire declared comparison band.')
    if observed['reference'] != reference['reference']:
        raise ValueError('Reference impedances differ; explicit renormalization is required.')
    f = observed['frequency']; mask = (f >= start_hz) & (f <= stop_hz); selected = f[mask]
    if len(selected) < 3: raise ValueError('Too few observed samples in the comparison band.')
    ref = reference['frequency']
    zs = reference['differential']; z = np.interp(selected, ref, zs.real)+1j*np.interp(selected, ref, zs.imag)
    s = np.empty((len(selected), 2, 2), complex)
    for i in range(2):
        for j in range(2):
            values = reference['scattering'][:, i, j]
            s[:, i, j] = np.interp(selected, ref, values.real)+1j*np.interp(selected, ref, values.imag)
    difference = observed['scattering'][mask]-s
    dz = observed['differential'][mask]-z
    return dict(band_hz=[start_hz, stop_hz], samples=len(selected),
                interpolation='Linear interpolation of real and imaginary reference components onto observed frequencies; no extrapolation.',
                maximum_absolute_s_error=float(np.max(abs(difference))),
                rms_complex_s_error=float(np.sqrt(np.mean(abs(difference)**2))),
                maximum_relative_z_error=float(np.max(abs(dz)/np.maximum(abs(z), 1e-3))),
                maximum_relative_r_error=float(np.max(abs(dz.real)/np.maximum(abs(z.real), 1e-3))),
                absolute_floor_ohm=1e-3, measurement_uncertainty_known=False, qualified=False)


def audit(root=FIXTURE):
    root = Path(root); lock = verify_sources(root); reports = {}; networks = {}
    for name in REFERENCES:
        text = (root/name).read_text(); data = network(text); networks[name] = data
        app = touchstone(text, 2)
        values = np.array(app['z_real_ohm'])+1j*np.array(app['z_imag_ohm'])
        np.testing.assert_allclose(app['frequency_hz'], data['frequency'], rtol=1e-12, atol=0)
        np.testing.assert_allclose(values, data['differential'], rtol=1e-8, atol=1e-8)
        gains = np.linalg.svd(data['scattering'], compute_uv=False)[:, 0]
        np.testing.assert_allclose([maximum_gain(s.tolist()) for s in data['scattering']], gains, rtol=1e-12, atol=1e-12)
        measured = metrics(data)
        rounded = [measured['r_at_100mhz_ohm'], measured['r_at_1ghz_ohm'], measured['l_at_1ghz_nh'], measured['peak_q'], measured['first_srf_hz']/1e9]
        if any(abs(a-b) > .025 for a, b in zip(rounded, PUBLISHED[name])):
            raise ValueError('Published reference metrics disagree: '+name)
        reports[name] = dict(sha256=sha(root/name), samples=len(data['frequency']), metrics=measured,
                             maximum_scattering_gain=float(max(gains)),
                             maximum_parser_error_ohm=float(max(abs(values-data['differential']))))
    for name in REFERENCES[1:]:
        reports[name]['comparison_to_measurement'] = compare(networks[name], networks['measured.s2p'])
    return dict(schema=1, status='PASS', source_commit=lock['commit'], source_lock_sha256=LOCK_SHA256,
                references=reports, qualified=False, chunk_complete=False,
                scope='Public source integrity, independent matrix conversion, published metrics and application parser/passivity arithmetic. Published solver results are not fresh application executions; measurement uncertainty and general device accuracy remain unqualified.')


def compare_geometry(first, second):
    """Independent written-mask and text comparison on a common physical grid.

    This public coupon is flat. Import normalizes its 5 nm database to 1 nm;
    compare physical coordinates rather than raw integer database coordinates.
    """
    import klayout.db as k
    layouts = []
    for path in (first, second):
        layout = k.Layout(); layout.read(str(path)); layouts.append(layout)
        if layout.cells() != 1 or any(layout.top_cell().each_inst()):
            raise ValueError('The measured-coil comparison requires its original flat topology.')
    def layers(layout): return {(layout.get_info(i).layer, layout.get_info(i).datatype): i for i in layout.layer_indexes()}
    a, b = layouts; ai, bi = layers(a), layers(b)
    if set(ai) != set(bi): raise ValueError('Measured-coil layer purposes changed.')
    if a.top_cell().name != b.top_cell().name: raise ValueError('Measured-coil top changed.')
    counts = {}
    def mask(layout, index):
        factor = layout.dbu/.001
        if not np.isclose(factor, round(factor), rtol=0, atol=1e-12):
            raise ValueError('Unexpected measured-coil source grid.')
        return k.Region(layout.top_cell().begin_shapes_rec(index)).transformed(k.ICplxTrans(factor, 0, False, 0, 0)).merged()
    def labels(layout, index):
        result = []
        for shape in layout.top_cell().shapes(index).each():
            if not shape.is_text(): continue
            t = shape.text; factor = layout.dbu/.001
            style = dict(rotation=t.trans.angle*90, mirror=t.trans.is_mirror(), size=t.size,
                         font=t.font, halign=int(t.halign), valign=int(t.valign))
            metadata = shape.property(124)
            if metadata is not None:
                # OASIS has no native font/orientation fields. Independently
                # validate the optional appearance property's stream anchor;
                # it must never replace the written text or its position.
                saved = json.loads(metadata); layer = layout.get_info(index)
                if (saved.get('format') != 'icstudio.text-presentation.v1'
                        or saved.get('anchor') != [t.string, layer.layer, layer.datatype, t.x, t.y, layout.dbu]
                        or set(saved.get('style', {})) != set(style)):
                    raise ValueError('Changed measured-coil text appearance anchor.')
                style = saved['style']
                if (type(style['mirror']) is not bool or style['rotation'] not in (0, 90, 180, 270)
                        or any(type(style[key]) is not int for key in ('size', 'font', 'halign', 'valign'))
                        or style['size'] < 0):
                    raise ValueError('Invalid measured-coil text appearance.')
            result.append((t.string, t.x*factor, t.y*factor, style['rotation'], style['mirror'],
                           style['size']*factor, style['font'], style['halign'], style['valign']))
        return sorted(result)
    for pair in ai:
        left, right = mask(a, ai[pair]), mask(b, bi[pair])
        if not (left^right).is_empty(): raise ValueError('Measured-coil physical mask changed: '+str(pair))
        if labels(a, ai[pair]) != labels(b, bi[pair]):
            raise ValueError('Measured-coil text or presentation changed: '+str(pair))
        counts[str(pair)] = dict(polygons=left.count(), area_nm2=left.area(), labels=len(labels(a, ai[pair])))
    return dict(layers=counts, source_dbu_um=a.dbu, compared_dbu_um=b.dbu, comparison_grid_um=.001,
                text_presentation='Native GDS fields; OASIS optional property 124 independently checked against written text, layer and anchor. Other tools may discard OASIS appearance properties.')


def geometry_exchange(output):
    """Exercise ordinary application import, save/reopen and both stream exports."""
    from icstudio.layout_import import read_layout
    from icstudio.interchange import export_layout
    from icstudio.model import save_project, load_project
    verify_sources(); output = Path(output); output.mkdir(parents=True, exist_ok=False)
    source = FIXTURE/'coil.gds'; project, notes = read_layout(source)
    save_project(project, output/'measured-coil.icproj')
    project = load_project(output/'measured-coil.icproj'); reports = {}
    for suffix in ('gds', 'oas'):
        stream = output/('coil.'+suffix); export_layout(project, stream)
        reports[suffix] = dict(sha256=sha(stream), comparison=compare_geometry(source, stream))
    return dict(status='PASS', source_sha256=sha(source), project_sha256=sha(output/'measured-coil.icproj'),
                imports=notes, exports=reports, qualified=False,
                scope='Exact public coupon masks, port rectangles, reference conductor and text survive ordinary import, saved project and GDS/OASIS export. No PDK/device mapping or EM result is attached.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exchange-output', type=Path)
    args = parser.parse_args(); result = audit()
    if args.exchange_output: result['geometry_exchange'] = geometry_exchange(args.exchange_output)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print('Public measured-coil reference audit passed; device qualification remains separate.')


if __name__ == '__main__': main()
