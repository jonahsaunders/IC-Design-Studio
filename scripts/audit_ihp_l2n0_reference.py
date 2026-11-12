"""Authenticate the public two-die L2n0 reference and audit import arithmetic.

No solver is run and no catalog binding, uncertainty bound or device acceptance
is inferred. The original one-port exports remain separate descriptive inputs.
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
from scripts.audit_ihp_measured_reference import compare_geometry, metrics, network

FIXTURE = ROOT/'tests/fixtures/ihp-l2n0-reference-v1'
LOCK_SHA256 = 'ab34bb0a7ab6467f02d5c24b76af765fe44ad410a7b452d1f601859fc7894a09'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_sources(root=FIXTURE):
    root = Path(root)
    if sha(root/'SOURCE.json') != LOCK_SHA256:
        raise ValueError('Changed L2n0 source inventory.')
    record = json.loads((root/'SOURCE.json').read_bytes())
    expected = {'SOURCE.json', *(row['file'] for row in record['files'])}
    if {p.name for p in root.iterdir()} != expected:
        raise ValueError('Changed L2n0 source file set.')
    for row in record['files']:
        data = (root/row['file']).read_bytes()
        blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256'] or blob != row['git_blob']:
            raise ValueError('Changed L2n0 source: '+row['file'])
    return record


def one_port(text):
    """Independent reader for the pinned one-port files' Hz/MA/50-ohm format."""
    options = None
    rows = []
    for raw in text.splitlines():
        line = raw.split('!', 1)[0].strip()
        if not line:
            continue
        if line.startswith('#'):
            if options is not None or rows or line.lower().split() != ['#', 'hz', 's', 'ma', 'r', '50']:
                raise ValueError('Unexpected L2n0 one-port options.')
            options = line
        else:
            row = [float(value) for value in line.split()]
            if options is None or len(row) != 3 or not np.isfinite(row).all() or row[1] < 0:
                raise ValueError('Invalid L2n0 one-port sample.')
            rows.append(row)
    if len(rows) < 3:
        raise ValueError('Missing L2n0 one-port data.')
    rows = np.array(rows)
    if rows[0, 0] <= 0 or not (np.diff(rows[:, 0]) > 0).all():
        raise ValueError('Invalid L2n0 one-port frequencies.')
    scattering = rows[:, 1]*np.exp(1j*np.deg2rad(rows[:, 2]))
    if (abs(1-scattering) == 0).any():
        raise ValueError('Singular L2n0 one-port response.')
    impedance = 50*(1+scattering)/(1-scattering)
    if not np.isfinite(impedance).all():
        raise ValueError('Nonfinite L2n0 impedance.')
    return rows[:, 0], impedance


def audit(root=FIXTURE, exchange_output=None):
    import klayout.db as k
    root = Path(root)
    source = verify_sources(root)
    measurements = {}
    for path in sorted(root.glob('meas_*.S2P')):
        text = path.read_text()
        reference = network(text)
        app = touchstone(text, 2)
        actual = np.array(app['z_real_ohm']) + 1j*np.array(app['z_imag_ohm'])
        np.testing.assert_allclose(app['frequency_hz'], reference['frequency'], rtol=1e-12, atol=0)
        np.testing.assert_allclose(actual, reference['differential'], rtol=1e-8, atol=1e-8)
        one_text = (root/('diff'+path.stem+'.s1p')).read_text()
        f1, z1 = one_port(one_text)
        app1 = touchstone(one_text, 1)
        np.testing.assert_allclose(app1['frequency_hz'], f1, rtol=1e-12, atol=0)
        np.testing.assert_allclose(np.array(app1['z_real_ohm'])+1j*np.array(app1['z_imag_ohm']), z1, rtol=1e-8, atol=1e-8)
        f2, z2 = reference['frequency'], reference['differential']
        selection = (f1 >= f2[0]) & (f1 <= f2[-1])
        interpolated = np.interp(f1[selection], f2, z2.real)+1j*np.interp(f1[selection], f2, z2.imag)
        measurements[path.name] = dict(samples=len(f2), band_hz=[float(f2[0]), float(f2[-1])],
            metrics=metrics(reference), maximum_parser_error_ohm=float(max(abs(actual-z2))),
            maximum_scattering_gain=float(np.linalg.svd(reference['scattering'], compute_uv=False)[:, 0].max()),
            one_port_comparison=dict(samples=int(selection.sum()),
                maximum_relative_z_difference=float(max(abs(z1[selection]-interpolated)/np.maximum(abs(interpolated), 1e-3))),
                method='Complex-Z linear interpolation over the common band, no extrapolation; 1e-3 ohm denominator floor.',
                equivalence_established=False))
    layouts = {}
    output = Path(exchange_output) if exchange_output is not None else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        from icstudio.layout_import import read_layout
        from icstudio.interchange import export_layout
        from icstudio.model import load_project, save_project
    for path in sorted(root.glob('*.gds')):
        layout = k.Layout()
        layout.read(str(path))
        if layout.cells() != 1 or len(layout.top_cells()) != 1:
            raise ValueError('Changed L2n0 reference topology.')
        layers = {str((layout.get_info(i).layer, layout.get_info(i).datatype)):
                  k.Region(layout.top_cell().begin_shapes_rec(i)).count() for i in layout.layer_indexes()}
        entry = dict(top=layout.top_cell().name, dbu_um=layout.dbu, polygons_by_layer=layers)
        if output is not None:
            project, _ = read_layout(path)
            project_path = output/(path.stem+'.icproj')
            save_project(project, project_path)
            project = load_project(project_path)
            entry['exchange'] = {}
            for suffix in ('gds', 'oas'):
                destination = output/(path.stem+'.'+suffix)
                export_layout(project, destination)
                entry['exchange'][suffix] = dict(sha256=sha(destination), comparison=compare_geometry(path, destination))
        layouts[path.name] = entry
    verify_sources(root)
    return dict(schema=1, status='PASS_SOURCE_AND_IMPORT_AUDIT', source_commit=source['commit'],
        source_lock_sha256=LOCK_SHA256, measurements=measurements, layouts=layouts,
        fresh_solver_execution=False, installed_acceptance=False, measurement_uncertainty_known=False,
        catalog_binding_resolved=False, qualified=False, chunk_complete=False,
        scope=__doc__, limitations=source['limitations'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exchange-output', type=Path)
    args = parser.parse_args()
    result = audit(exchange_output=args.exchange_output)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
