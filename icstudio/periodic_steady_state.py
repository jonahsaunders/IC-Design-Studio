"""Experimental ngspice shooting PSS with validated time and harmonic plots."""

import math
import re
from pathlib import Path

from .engines import parse_raw
from .model import NET, atomic_write, design_digest, digest, file_digest, now, scalar
from .native_vectors import devices
from .rf_network import fixture_text, ngspice_job, run_fixture


def validate_settings(project, cell_id, settings):
    fixture = next((cell for cell in project['cells'] if cell['id'] == cell_id), None)
    node = settings['node']
    if fixture is None or node == '0' or not NET.fullmatch(node) or not any(
            node.casefold() == net.casefold() for part in devices(fixture, project) for net in part['nets'].values()):
        raise ValueError('Choose an existing non-ground observation net on the fixture schematic.')
    if scalar(settings['frequency']) <= 0 or scalar(settings['stabilization']) <= 0:
        raise ValueError('Use a positive fundamental estimate and stabilization time.')
    points = settings['points']
    if type(points) is not int or not 64 <= points <= 4096 or points & (points-1):
        raise ValueError('Use a power of two from 64 to 4,096 samples per period.')
    if type(settings['harmonics']) is not int or not 2 <= settings['harmonics'] <= min(128, points//2):
        raise ValueError('Choose 2–128 spectral bins within the sample count, including DC.')
    if type(settings['iterations']) is not int or not 2 <= settings['iterations'] <= 200:
        raise ValueError('Choose 2–200 shooting iterations.')
    if not 0 < scalar(settings['coefficient']) <= .1 or scalar(settings['temperature']) <= -273.15:
        raise ValueError('Use a convergence coefficient above zero and at most 0.1, and a temperature above absolute zero.')


def prepare(project, cell_id, settings, configured=''):
    settings = {**settings, 'type': 'periodic_steady_state'}
    validate_settings(project, cell_id, settings)
    return ngspice_job(project, cell_id, settings, configured)


def time_and_harmonics(raw, node, points, harmonics):
    if raw.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('PSS capture exceeds 64 MiB. Reduce the samples or circuit size.')
    plots = {}
    for block in re.split(rb'(?m)(?=^Title:)', raw.read_bytes()):
        match = re.search(rb'(?m)^Plotname: (Time|Frequency) Domain Periodic Steady State Analysis\s*$', block)
        if not match:
            continue
        kind = match[1].decode().lower()
        path = raw.parent/('pss-'+kind+'.raw')
        atomic_write(path, block)
        variables, rows, is_complex = parse_raw(path)
        axis = 'time' if kind == 'time' else 'frequency'
        if kind in plots or is_complex or variables[0] != axis or len(rows) != (points+1 if kind=='time' else harmonics):
            raise ValueError('ngspice did not produce the requested PSS time and frequency grids.')
        x = [row[0] for row in rows]
        series = {name[2:-1]:[row[i] for row in rows]
                  for i, name in enumerate(variables) if name.startswith('v(') and name.endswith(')')}
        if node.casefold() not in series or any(not math.isfinite(v) for data in (x, *series.values()) for v in data):
            raise ValueError('PSS returned incomplete or non-finite voltage data.')
        if any(a >= b for a, b in zip(x, x[1:])):
            raise ValueError('PSS returned a non-increasing time or frequency axis.')
        plots[kind] = {'x': x, 'traces': series}
    if set(plots) != {'time', 'frequency'}:
        raise ValueError('ngspice did not return both periodic-domain plots.')
    return plots


def run(job, directory, progress):
    project, cell, settings = (job[key] for key in ('project', 'cell', 'settings'))
    validate_settings(project, cell, settings)
    directory = Path(directory).resolve()
    frequency = scalar(settings['frequency'])
    text = fixture_text(project, cell, settings, directory)
    text += (f'.pss {frequency:.16g} {scalar(settings["stabilization"]):.16g} {settings["node"]} '
             f'{settings["points"]} {settings["harmonics"]} {settings["iterations"]} '
             f'{scalar(settings["coefficient"]):.16g}\n.end\n')
    progress(.1, 'Running experimental ngspice periodic steady state')
    source, raw, log = run_fixture(job, directory, text, 'pss')
    match = re.search(r'Convergence reached[^\r\n]*predicted fundamental frequency is\s+([0-9.eE+-]+) Hz', log)
    if not match or not math.isfinite(float(match[1])) or float(match[1]) <= 0:
        raise ValueError('ngspice did not report a converged PSS orbit. See the engine log and check the fixture and estimate.')
    fundamental = float(match[1])
    plots = time_and_harmonics(raw, settings['node'], settings['points'], settings['harmonics'])
    time, spectrum = plots['time'], plots['frequency']
    start = time['x'][0]
    x = [value-start for value in time['x']]
    if not math.isclose(x[-1]*fundamental, 1, rel_tol=.005) or not math.isclose(spectrum['x'][1], fundamental, rel_tol=.005):
        raise ValueError('PSS orbit duration or harmonic spacing disagrees with the solver’s fundamental.')
    progress(1, 'Experimental PSS orbit converged')
    return dict(schema=1, created=now(), engine='ngspice · experimental PSS', engine_hash=file_digest(job['executable']),
                project_id=project['id'], revision=project['revision'], design_hash=design_digest(project),
                pdk_hash=digest(project['pdk']), rule_hash=digest(project['pdk']['layers']), cell_id=cell,
                settings=settings, x=x, x_label='Time within period (s)', plot_unit='V', traces=time['traces'],
                pss={'fundamental': fundamental, 'spectrum': spectrum,
                     'deck_sha256': file_digest(source), 'raw_sha256': file_digest(raw)}, log=log,
                warnings=['Experimental ngspice PSS. Verified on the driven RC reference fixture.'])
