"""Opt-in real field-solver smoke run, with explicitly synthetic materials.

Run from the source root with an application Python. --python selects the
independently installed solver Python. Environment overrides are inherited.
This small high-frequency fixture tests execution and evidence, not PDK accuracy.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from icstudio import inductor, openems_backend as backend, em_technology, openems_runtime
from icstudio.model import save_project
from test_inductor_pdks import fixture


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--python', default=openems_runtime.discover()[0])
    parser.add_argument('--out', type=Path, required=True); parser.add_argument('--mesh-check', action='store_true')
    args = parser.parse_args()
    if not args.python: parser.error('No included solver. Run scripts/stage_openems.py or supply --python.')
    p = fixture(); tech = p['pdk']
    tech['routing_vias'][0].update(size=2000, enclosure=1000)
    stack = tech['em_stackup']; stack.pop('technology')
    stack['source'] = 'Synthetic resistive coil in vacuum slabs: software integration smoke test, not a physical PDK'
    for layer in stack['layers']:
        if layer['kind'] in ('conductor', 'via'): layer['conductivity_s_m'] = 1e5
        else: layer.update(epsilon_r=1., conductivity_s_m=0., loss_tangent=0.)
    stack['layers'][0].update(z_um=1, thickness_um=2)
    stack['layers'][1].update(z_um=3, thickness_um=2)
    stack['layers'][2].update(z_um=5, thickness_um=2)
    stack['layers'][-1].update(z_um=-5, thickness_um=5)
    tech['em_stackup'] = em_technology.bind_stackup(tech, stack)
    spec = {**inductor.defaults(p), 'turns': 1, 'width': 4000, 'spacing': 2000,
            'inner': 12000, 'lead': 8000, 'via_rows': 1, 'via_columns': 1}
    proposal = inductor.plan(p, p['top'], spec); inductor.install(p, proposal)
    opts = dict(f_start_hz=5e11, f_stop_hz=1e12, samples=11, mesh_um=2., margin_um=5.,
                reference_clearance_um=5., end_db=-30., max_steps=1000000,
                mesh_check=args.mesh_check, timeout_s=600, threads=1)
    root = args.out.resolve(); model = backend.prepare(p, p['top'], proposal['device_id'], 'isolated', opts, root)
    columns = {}; commands = []; environment = openems_runtime.environment(args.python)
    for scale, port in backend.stages(model['settings']):
        name = backend.stage_name(scale, port); log = root/(name+'.log')
        command = [str(Path(args.python).absolute()), '-u', str(root/'driver.py'), '--model', str(root/'model.json'), '--port', str(port), '--scale', str(scale)]
        commands.append(command); print('Running '+name, flush=True)
        with log.open('w') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, env=environment, timeout=600)
        if result.returncode: raise RuntimeError('Solver failed; see '+str(log))
        columns[name] = backend.check_completion(log.read_text(), root, model, scale, port)
    output = backend.finish(root, model, columns)
    from icstudio import inductor_em
    metrics = inductor_em.install_results(p, p['top'], proposal['device_id'], output)
    save_project(p, root/'characterized.icproj')
    report = dict(status='passed', qualification='Synthetic native execution smoke test; no PDK, boundary or RF accuracy qualification',
                  commands=commands, solver_run=output['solver_run'], rows=metrics['rows'], srf_hz=metrics['srf_hz'])
    (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8'); print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
