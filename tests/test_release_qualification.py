"""Regressions for portable hierarchy, bus probes and trustworthy release evidence."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from icstudio import __version__
from icstudio.model import clone, load_project, save_project
from icstudio.native_exchange import export_project, review_project
from icstudio.native_migration import review_path
from icstudio.spice_program import prepare_program
from scripts.assemble_prerelease import assemble
from scripts.prepare_release_payload import checksum
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
            archive = directory / (platform + '.zip')
            archive.write_bytes(b'test archive payload')
            data = {'schema': 1, 'status': 'passed', 'version': __version__, 'commit': 'a' * 40,
                    'platform': platform, 'assets': {archive.name: checksum(archive)},
                    'distribution': {'status': 'passed', 'archive': archive.name, 'archive_sha256': checksum(archive)},
                    'installer': {'status': 'passed'} if platform == 'Windows' else None}
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

    def test_release_rejects_changed_asset_before_copying(self):
        inputs = self.payloads()
        (inputs / 'Windows/Windows.zip').write_bytes(b'changed after validation')
        output = self.root / 'release'
        with self.assertRaisesRegex(ValueError, 'changed release asset'):
            assemble(inputs, output, 'a' * 40)
        self.assertFalse(output.exists())

    def test_release_rejects_evidence_from_another_commit(self):
        with self.assertRaisesRegex(ValueError, 'exact selected version and commit'):
            assemble(self.payloads(), self.root / 'release', 'b' * 40)

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
