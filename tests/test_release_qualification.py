"""Regressions for portable hierarchy, bus probes and trustworthy release evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from icstudio import __version__
from icstudio.digital_vga import PRESET_IDS
from icstudio.model import clone, load_project, save_project
from icstudio.native_exchange import export_project, review_project
from icstudio.native_migration import review_path
from icstudio.spice_program import prepare_program
from scripts.assemble_prerelease import assemble, validate_statistical_qualification
from scripts.prepare_release_payload import checksum, verify_distribution
from scripts.qualify_layout_process import accept_result, magic_versions
from scripts.verify_native_hierarchy import SOURCE, check_analytic, edit, snapshot


class ReleaseQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_three_level_reused_hierarchy_survives_edits_and_source_removal(self):
        source = self.root / 'Original source with spaces'
        shutil.copytree(SOURCE, source)
        record = review_path(source / 'dual-divider.sch')
        self.assertEqual(record['status'], 'Complete', record['items'])
        project = edit(record['candidate'])
        self.assertEqual(len(project['cells']), 3)
        top = next(c for c in project['cells'] if c['id'] == project['top'])
        instances = [d for d in top['devices'] if d['kind'] == 'X']
        self.assertEqual(len({d['cell'] for d in instances}), 1)
        self.assertEqual([d['native_spice']['parameters']['rtop'] for d in instances], ['2k', '3k'])
        project['native_migration'].pop('archive', None)
        shutil.rmtree(source)
        expected = snapshot(project)
        for i in range(2):
            exported = export_project(project, self.root / f'export-{i}')
            # Xschem interprets schematic overrides from the project search
            # path. Each child must resolve there after relocating the export.
            moved = self.root / f'relocated-{i}' / 'Project with spaces'
            moved.parent.mkdir()
            shutil.move(exported['directory'], moved)
            from icstudio.xschem_project import records, properties
            for symbol in moved.rglob('*.sym'):
                attrs = properties(next(r[1] for r in records(symbol.read_text()) if r[0] == 'K'))
                if attrs.get('type') == 'subcircuit':
                    target = (moved / attrs['schematic']).resolve()
                    self.assertTrue(target.is_relative_to(moved.resolve()) and target.is_file())
            exported['directory'] = str(moved)
            record = review_project(Path(exported['directory']) / exported['top'])
            self.assertEqual(record['errors'], [])
            save_project(record['candidate'], self.root / 'reopened.icproj')
            project = load_project(self.root / 'reopened.icproj')
            self.assertEqual(snapshot(project), expected)

    def test_selected_scalar_bus_and_operator_nodes_are_quoted_for_ngspice(self):
        text, count, _ = prepare_program('title\n.control\nop\n.endc\n.end', self.root,
                                        {'probes': 'v(data[0]) v(net+1) v(out) i(V1)'})
        self.assertIn('v("data[0]") v("net+1") v(out) i(V1)', text)
        self.assertEqual(count, 1)

    def test_vector_bus_expansion_still_requires_review(self):
        source = self.root / 'vector-source'
        shutil.copytree(SOURCE, source)
        path = source / 'dual-divider.sch'
        path.write_text(path.read_text().replace('lab=data[0]', 'lab=data[7:0]'))
        record = review_path(path)
        self.assertIsNone(record['candidate'])
        self.assertEqual(record['status'], 'Needs attention')

    def test_numerical_qualification_rejects_nonfinite_waveforms(self):
        plot = {'plot_kind': 'op', 'x': [0], 'traces': {'data[0]': [float('nan')], 'data[1]': [.25]}}
        with self.assertRaisesRegex(AssertionError, 'Nonfinite'):
            check_analytic({'op': plot}, (1000, 3000))

    def payloads(self):
        inputs = self.root / 'inputs'
        for platform in ('Windows', 'Linux'):
            directory = inputs / platform
            directory.mkdir(parents=True)
            prefix = f'IC-Design-Studio-{__version__}-'
            archive = directory / (prefix + ('Windows-x64-Portable.zip' if platform == 'Windows' else 'Linux-x86_64.tar.gz'))
            names = [archive.name, prefix + f'Source-{platform}.zip', prefix + f'Evidence-{platform}.zip']
            if platform == 'Windows': names.append(prefix + 'Windows-x64-Setup.exe')
            for name in names: (directory / name).write_bytes(('Synthetic assembly fixture: ' + name).encode())
            vga = {'status': 'passed', 'version': __version__, 'frozen': True,
                   'build': {'commit': 'a' * 40, 'dirty': False},
                   'presets': [{'id': name, 'status': 'passed'} for name in PRESET_IDS]}
            probe = {'status': 'passed', 'version': __version__, 'frozen': True,
                     'build': {'commit': 'a' * 40, 'dirty': False}}
            installer = {'status': 'passed', 'version': __version__, 'commit': 'a' * 40,
                         'installer': names[-1], 'installer_sha256': checksum(directory / names[-1]),
                         'probes': [dict(probe, scale=scale) for scale in ('1', '1.5', '2')], 'vga': vga}
            data = {'schema': 1, 'status': 'passed', 'version': __version__, 'commit': 'a' * 40,
                    'platform': platform, 'assets': {name: checksum(directory / name) for name in names},
                    'distribution': {'status': 'passed', 'archive': archive.name, 'archive_sha256': checksum(archive), 'vga': vga, 'report': probe},
                    'installer': installer if platform == 'Windows' else None}
            (directory / f'IC-Design-Studio-{__version__}-Validation-{platform}.json').write_text(json.dumps(data))
        return inputs

    def test_release_checksums_cover_the_exact_qualified_payloads(self):
        output = self.root / 'release'
        files = assemble(self.payloads(), output, 'a' * 40)
        lines = (output / f'SHA256SUMS-{__version__}.txt').read_text().splitlines()
        self.assertEqual(len(lines), len(files))
        for line in lines:
            digest, name = line.split('  ')
            self.assertEqual(checksum(output / name), digest)

    def test_statistical_release_gate_requires_same_run_complete_workload_and_recovery(self):
        directory = self.root / 'statistics'
        proof_path = directory / 'statistical-campaign-qualification' / 'qualification.json'
        proof_path.parent.mkdir(parents=True)
        gate_path = directory / 'campaign-gate.json'
        gate_path.write_text(json.dumps({'commit': 'a' * 40, 'run_id': '123'}))
        # This fixture validates release aggregation, not actual simulator execution.
        proof = {'qualification_status': 'passed', 'trials': 128, 'cases': 1152,
                 'completed_cases': 1152, 'retried_cases': 4,
                 'fault': {'exit_code': -9, 'immutable_input_preserved': True,
                           'stale_publication_rejected': True},
                 'statistics': {'joint': {'trials': 128, 'passed': 99, 'failed': 29, 'unresolved': 0}}}
        proof_path.write_text(json.dumps(proof))
        result = validate_statistical_qualification(directory, 'a' * 40, 123)
        self.assertEqual(result['qualification_sha256'], checksum(proof_path))
        self.assertEqual(result['joint']['failed'], 29)
        for commit, run in [('b' * 40, 123), ('a' * 40, 124)]:
            with self.assertRaisesRegex(ValueError, 'commit and workflow run'):
                validate_statistical_qualification(directory, commit, run)
        for mutation in ({'completed_cases': 1151}, {'retried_cases': 0},
                         {'fault': dict(proof['fault'], stale_publication_rejected=False)},
                         {'statistics': {'joint': {'trials': 128, 'passed': 99, 'failed': 28, 'unresolved': 1}}}):
            proof_path.write_text(json.dumps(dict(proof, **mutation)))
            with self.assertRaises(ValueError):
                validate_statistical_qualification(directory, 'a' * 40, 123)

    def test_release_rejects_changed_asset_before_copying(self):
        inputs = self.payloads()
        (inputs / 'Windows' / f'IC-Design-Studio-{__version__}-Windows-x64-Portable.zip').write_bytes(b'changed after validation')
        output = self.root / 'release'
        with self.assertRaisesRegex(ValueError, 'changed release asset'):
            assemble(inputs, output, 'a' * 40)
        self.assertFalse(output.exists())

    def test_release_rejects_evidence_from_another_commit(self):
        with self.assertRaisesRegex(ValueError, 'exact selected version and commit'):
            assemble(self.payloads(), self.root / 'release', 'b' * 40)

    def test_release_rejects_replaced_installer_even_with_refreshed_manifest_hash(self):
        inputs = self.payloads(); directory = inputs / 'Windows'
        name = f'IC-Design-Studio-{__version__}-Windows-x64-Setup.exe'
        (directory / name).write_bytes(b'Replacement installer which was never executed')
        record = directory / f'IC-Design-Studio-{__version__}-Validation-Windows.json'
        data = json.loads(record.read_text()); data['assets'][name] = checksum(directory / name)
        record.write_text(json.dumps(data)); output = self.root / 'release'
        with self.assertRaisesRegex(ValueError, 'installer execution and payload hashes differ'):
            assemble(inputs, output, 'a' * 40)
        self.assertFalse(output.exists())

    def test_distribution_rejects_archive_replaced_during_execution(self):
        archive = self.root / 'desktop.zip'
        executable = 'ICDesignStudio.exe' if os.name == 'nt' else 'ICDesignStudio'
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('ICDesignStudio/' + executable, b'Synthetic probe-orchestration fixture')
        report = {'status': 'passed', 'version': __version__, 'frozen': True,
                  'build': {'commit': 'a' * 40, 'dirty': False}}
        def probe(command, **kwargs):
            output = Path(command[2]); output.mkdir(parents=True)
            (output / 'release-test.json').write_text(json.dumps(report))
            archive.write_bytes(b'Replacement archive that was never extracted or executed')
            return subprocess.CompletedProcess(command, 0, b'', b'')
        with patch('scripts.prepare_release_payload.subprocess.run', side_effect=probe), \
             patch('scripts.prepare_release_payload.subprocess.check_output', return_value='a' * 40), \
             patch('scripts.prepare_release_payload.verify_vga', return_value={}):
            with self.assertRaisesRegex(ValueError, 'archive changed during execution'):
                verify_distribution(archive, self.root / 'distribution')

    def test_release_requires_corresponding_source_and_evidence_for_both_platforms(self):
        inputs = self.payloads()
        for platform in ('Windows', 'Linux'):
            record = inputs / platform / f'IC-Design-Studio-{__version__}-Validation-{platform}.json'
            original = json.loads(record.read_text())
            for kind in ('Source', 'Evidence'):
                with self.subTest(platform=platform, kind=kind):
                    data = clone(original); data['assets'].pop(f'IC-Design-Studio-{__version__}-{kind}-{platform}.zip')
                    record.write_text(json.dumps(data)); output = self.root / 'release'
                    with self.assertRaisesRegex(ValueError, 'Missing required'):
                        assemble(inputs, output, 'a' * 40)
                    self.assertFalse(output.exists())
            record.write_text(json.dumps(original))

    def test_release_requires_clean_desktop_execution_and_all_installed_dpi_probes(self):
        inputs = self.payloads(); record = inputs / 'Windows' / f'IC-Design-Studio-{__version__}-Validation-Windows.json'
        original = json.loads(record.read_text())
        for location in ('distribution', 'installer'):
            for defect in ('missing', 'stale', 'dirty', 'source'):
                with self.subTest(location=location, defect=defect):
                    data = clone(original)
                    probe = data['distribution']['report'] if location == 'distribution' else data['installer']['probes'][0]
                    if defect == 'missing':
                        if location == 'distribution': data['distribution'].pop('report')
                        else: data['installer']['probes'].pop()
                    elif defect == 'stale': probe['build']['commit'] = 'b' * 40
                    elif defect == 'dirty': probe['build']['dirty'] = True
                    elif defect == 'source': probe['frozen'] = False
                    record.write_text(json.dumps(data)); output = self.root / 'release'
                    with self.assertRaises(ValueError): assemble(inputs, output, 'a' * 40)
                    self.assertFalse(output.exists())

    def test_release_rejects_missing_stale_source_only_or_incomplete_vga_evidence(self):
        inputs = self.payloads()
        record = inputs / 'Windows' / f'IC-Design-Studio-{__version__}-Validation-Windows.json'
        original = json.loads(record.read_text())
        for location in ('distribution', 'installer'):
            for defect in ('missing', 'stale', 'source', 'incomplete', 'duplicate', 'failed'):
                with self.subTest(location=location, defect=defect):
                    data = clone(original)
                    vga = data[location]['vga']
                    if defect == 'missing': data[location].pop('vga')
                    elif defect == 'stale': vga['build']['commit'] = 'b' * 40
                    elif defect == 'source': vga['frozen'] = False
                    elif defect == 'incomplete': vga['presets'].pop()
                    elif defect == 'duplicate': vga['presets'][1]['id'] = vga['presets'][0]['id']
                    elif defect == 'failed': vga['presets'][0]['status'] = 'failed'
                    record.write_text(json.dumps(data))
                    output = self.root / 'release'
                    with self.assertRaises(ValueError): assemble(inputs, output, 'a' * 40)
                    self.assertFalse(output.exists())

    def test_lvs_tool_failure_is_not_an_expected_fault_pass(self):
        directory = self.root / 'case'
        (directory / 'lvs').mkdir(parents=True)
        result = {'status': 'failed', 'stages': [{'name': 'drc', 'status': 'passed'},
                                               {'name': 'lvs', 'status': 'failed'},
                                               {'name': 'post_layout_simulation', 'status': 'not_run'}]}
        log = directory / 'lvs/lvs.log'
        log.write_text('Error: cannot read setup file')
        self.assertFalse(accept_result(result, 'lvs', directory))
        log.write_text('Netlists do not match.')
        self.assertTrue(accept_result(result, 'lvs', directory))
        result['stages'][0]['status'] = 'failed'
        self.assertFalse(accept_result(result, 'lvs', directory))

    def test_old_magic_is_rejected_before_physical_cases(self):
        technology='version\n requires magic-8.3.306\nend\n'
        with self.assertRaisesRegex(ValueError,'requires Magic 8.3.306'):
            magic_versions(technology,'8.3.105\n')
        self.assertEqual(magic_versions(technology,'8.3.600\n'),('8.3.306','8.3.600'))


if __name__ == '__main__':
    unittest.main()
