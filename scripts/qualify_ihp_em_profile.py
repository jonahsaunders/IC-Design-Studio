"""Execute a local IHP public-profile field-solver integration reference.

This generated two-terminal coil and top reference-plane fixture are distinct
from the unavailable IHP compact models. No device/EM-accuracy qualification is
inferred from execution or two-mesh agreement.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import ihp_em_profile, inductor, inductor_em, openems_backend, openems_runtime
from icstudio.model import example, file_digest, save_project
from scripts.qualify_standard_mos import load_technology


def fixture(bulk=280):
    project = example('empty')
    project['pdk'], package = load_technology('ihp-sg13g2')
    project['pdk']['em_stackup'] = ihp_em_profile.profile(project['pdk'], bulk)
    spec = dict(inductor.defaults(project), turns=1, width=8000, spacing=3000,
                inner=16000, lead=10000, via_rows=1, via_columns=1)
    if spec['metal'] != 'TopMetal2.drawing':
        raise ValueError('The fixture requires the declared IHP top-metal via.')
    proposal = inductor.plan(project, project['top'], spec)
    inductor.install(project, proposal)
    return project, proposal['device_id'], package


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--python', required=True, type=Path, help='Actual isolated openEMS Python')
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--bulk-um', choices=(280, 180), default=280, type=int)
    ap.add_argument('--start-ghz', default=1., type=float)
    ap.add_argument('--stop-ghz', default=5., type=float)
    ap.add_argument('--threads', default=2, type=int)
    ap.add_argument('--timeout-s', default=900, type=int)
    ap.add_argument('--max-steps', default=2000000, type=int)
    ap.add_argument('--mesh-um', default=2., type=float, help='Base mesh limit; the second mesh uses the same 0.7 refinement factor')
    ap.add_argument('--max-cells', default=2000000, type=int, help='Explicit memory guard for each mesh; no automatic increase')
    args = ap.parse_args()
    root = args.output.resolve()
    project, did, package = fixture(args.bulk_um)
    options = dict(f_start_hz=args.start_ghz*1e9, f_stop_hz=args.stop_ghz*1e9, samples=11, mesh_um=args.mesh_um, margin_um=20.,
                   reference_clearance_um=20., end_db=-40., max_steps=args.max_steps,
                   max_cells=args.max_cells, timeout_s=args.timeout_s, threads=args.threads, mesh_check=True)
    model = openems_backend.prepare(project, project['top'], did, 'isolated', options, root)
    save_project(project, root / 'input.icproj')
    executable = args.python.resolve()
    environment = openems_runtime.environment(executable)
    # Execute each real excitation outside the application Python/Qt process.
    columns = {}
    commands = []
    for scale, port in openems_backend.stages(model['settings']):
        stage = openems_backend.stage_name(scale, port)
        command = [str(executable), '-u', str(root / 'driver.py'), '--model', str(root / 'model.json'),
                   '--port', str(port), '--scale', str(scale)]
        commands.append(command)
        print('Running ' + stage, flush=True)
        with (root / (stage + '.log')).open('w', encoding='utf-8') as log:
            outcome = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=environment,
                                     timeout=model['settings']['timeout_s'])
        if outcome.returncode:
            raise ValueError('Native solver failed in ' + stage + '; original log retained.')
        columns[stage] = openems_backend.check_completion((root / (stage + '.log')).read_text(), root, model, scale, port)
        if stage == 'base-2':
            openems_backend.check_base_feasibility(root, model, columns)
    output = openems_backend.finish(root, model, columns)
    metrics = inductor_em.install_results(project, project['top'], did, output)
    save_project(project, root / 'characterized.icproj')
    report = dict(schema=1, status='PASS', chunk=7, chunk_complete=False, qualified=False,
                  scope=__doc__, bulk_substrate_um=args.bulk_um, package=package,
                  public_profile_source=project['pdk']['em_stackup']['source'],
                  commands=commands, solver_run=output['solver_run'], rows=metrics['rows'],
                  srf_hz=metrics['srf_hz'], runner_sha256=file_digest(__file__),
                  files={p.relative_to(root).as_posix(): file_digest(p) for p in sorted(root.rglob('*')) if p.is_file()})
    (root / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='PASS',solver_run=report['solver_run']), indent=2), flush=True)


if __name__ == '__main__':
    main()
