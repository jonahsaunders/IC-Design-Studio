"""Bounded imported MiM graph/exchange controls; no native jobs in the fast lane."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as db

from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.layout_verification import verification_stream
from icstudio.model import clone, load_project, save_project
from scripts import qualify_sky130_mim_hierarchy as suite


def leaf(path, plate):
    ly = db.Layout(); ly.dbu = .001; cell = ly.create_cell('coupon')
    bottom, cap = (70, 89) if plate == 1 else (71, 97)
    cell.shapes(ly.layer(bottom, 20)).insert(db.Box(-2500, -500, 2500, 10500))
    cell.shapes(ly.layer(cap, 44)).insert(db.Box(0, 0, 2000, 10000))
    cell.shapes(ly.layer(bottom+1, 20)).insert(db.Box(0, 0, 2000, 10000))
    cell.shapes(ly.layer(bottom+1, 5)).insert(db.Text('P', db.Trans(1000, 5000)))
    cell.shapes(ly.layer(bottom, 5)).insert(db.Text('N', db.Trans(-1500, 5000)))
    ly.write(str(path))


def native(plate=1, missing=False, ports=None):
    rows = ['.subckt mim_pair '+' '.join(ports or suite.PORTS),
            f'X0 P1 N1 sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10']
    if not missing: rows.append(f'X1 P2 N2 sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10 m=1')
    return '\n'.join([*rows, '.ends', ''])


class ImportedMiMHierarchyTests(unittest.TestCase):
    def test_two_constructions_transforms_save_and_stream_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for plate in suite.PLATES:
                source = root/f'leaf{plate}.gds'; leaf(source, plate)
                for angle in suite.ANGLES:
                    with self.subTest(plate=plate, angle=angle):
                        stream = root/'input.gds'; suite.make_stream(source, stream, plate, angle)
                        project, _ = read_layout(stream)
                        next(c for c in project['cells'] if c['id'] == project['top'])['ports'] = list(suite.PORTS)
                        save_project(project, root/'saved.icproj'); saved = load_project(root/'saved.icproj')
                        self.assertEqual(saved['cells'], project['cells'])
                        for suffix in ('gds', 'oas'):
                            output = root/('output.'+suffix); export_layout(saved, output)
                            suite.compare(stream, output, text_presentation=suffix == 'gds')
                            suite.inspect_stream(output, plate, angle, source)

    def test_private_flatten_keeps_masks_and_four_ordered_top_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for plate in suite.PLATES:
                source = root/'leaf.gds'; leaf(source, plate)
                for angle in suite.ANGLES:
                    stream, target = root/'input.gds', root/'private.gds'
                    suite.make_stream(source, stream, plate, angle)
                    bottom = 70 if plate == 1 else 71
                    proof = verification_stream(stream, suite.TOP, suite.PORTS, target,
                                                pin_layers={(bottom, 5), (bottom+1, 5)})
                    self.assertEqual(proof['source_cells'], 2)
                    self.assertEqual(proof['removed_noninterface_labels'], 2)
                    ly = db.Layout(); ly.read(str(target))
                    self.assertFalse(list(ly.top_cell().each_inst()))
                    self.assertEqual({t.string for _, _, t in suite.texts(ly, ly.top_cell())}, set(suite.PORTS))
                    suite.inspect_stream(stream, plate, angle, source)

    def test_all_exchange_corruptions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for plate in suite.PLATES:
                source = root/'leaf.gds'; leaf(source, plate)
                stream = root/'input.gds'; suite.make_stream(source, stream, plate, 0)
                for fault in suite.EXCHANGE_FAULTS:
                    with self.subTest(plate=plate, fault=fault):
                        bad = root/'bad.gds'; suite.corrupt_exchange(stream, bad, fault, plate)
                        with self.assertRaises(ValueError): suite.inspect_stream(bad, plate, 0, source)

    def test_native_graph_rejects_polarity_shared_nets_model_count_dimensions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'native.spice'
            for plate in suite.PLATES:
                text = native(plate); path.write_text(text)
                self.assertEqual(suite.native_devices(path, plate)['devices'], 2)
                changes = [text.replace('P2 N2', 'N2 P2'), text.replace('X1 P2 N2', 'X1 P1 N2'),
                    text.replace('X1 P2 N2', 'X1 P2 N1'), text.replace('w=2', 'w=3'),
                    text.replace('l=10', 'l=2'), text.replace('m=1', 'm=2'),
                    text.replace('X1 ', 'X0 '), text.replace('w=2', 'w=2 w=2'),
                    text.replace(f'cap_mim_m3_{plate}', f'cap_mim_m3_{3-plate}'),
                    text.replace('P1 N1 P2 N2', 'N1 P1 P2 N2'), text+'.include arbitrary.spice\n',
                    native(plate, missing=True), text.replace('w=2', 'w=NaN')]
                for changed in changes:
                    with self.subTest(plate=plate, changed=changed):
                        path.write_text(changed)
                        with self.assertRaises(ValueError): suite.native_devices(path, plate)

    def test_missing_instance_changes_only_one_occurrence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = root/'leaf.gds'; leaf(source, 1)
            stream = root/'input.gds'; suite.make_stream(source, stream, 1, 0)
            project, _ = read_layout(stream); original = clone(project)
            changed = suite.deleted_instance(project)
            self.assertEqual(project, original)
            top = next(c for c in project['cells'] if c['id'] == project['top'])
            other = next(c for c in changed['cells'] if c['id'] == changed['top'])
            self.assertEqual(len(other['layout_instances']), 1)
            self.assertFalse(other['layout_instances'][0]['mirror'])
            other['layout_instances'] = top['layout_instances']
            self.assertEqual(changed, original)

    def test_reference_faults_preserve_fixed_interface_and_local_mutations(self):
        for plate in suite.PLATES:
            original = suite.selected(plate)
            for fault in suite.FAULTS:
                changed = suite.selected(plate, fault)
                self.assertEqual(changed['ports'], list(suite.PORTS))
                if fault == 'physical-missing-instance': self.assertEqual(changed, original)
                else: self.assertNotEqual(changed['sha256'], original['sha256'])
            self.assertIn('X2 P1 N2 capacitor_leaf', suite.selected(plate, 'merged-reference-terminal')['text'])
            self.assertNotIn('X2 ', suite.selected(plate, 'missing-reference-instance')['text'])
            self.assertIn('w=3 l=10 m=1', suite.selected(plate, 'second-reference-width')['text'])

    def test_fault_rejects_setup_error_wrong_native_graph_and_missing_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); (root/'lvs-extraction').mkdir(); (root/'lvs').mkdir()
            (root/'report.json').write_text('{}')
            path = root/'lvs-extraction/extracted.spice'; path.write_text(native())
            completed = root/'lvs-extraction/native-extraction.log'; completed.write_text('STUDIO_MAGIC_COMPLETE\n')
            log = root/'lvs/lvs.log'; log.write_text('Netlists do not match.\n')
            result = dict(status='failed', drc_count=0, stages=[dict(name=n,
                status='failed' if n == 'lvs' else 'passed') for n in suite.STAGES])
            suite.check_fault(result, root, 'merged-reference-terminal', 1)
            for stage in ('preflight','layout_export','drc','lvs_extraction','integrity'):
                changed = clone(result); next(x for x in changed['stages'] if x['name'] == stage)['status'] = 'failed'
                with self.assertRaises(ValueError): suite.check_fault(changed, root, 'merged-reference-terminal', 1)
            for bad in ('', 'STUDIO_MAGIC_COMPLETE\nSTUDIO_MAGIC_COMPLETE\n', 'STUDIO_MAGIC_ERROR missing'):
                completed.write_text(bad)
                with self.assertRaises(ValueError): suite.check_fault(result, root, 'merged-reference-terminal', 1)

    def test_physical_missing_accepts_only_exact_one_device_and_defined_interface_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); (root/'lvs-extraction').mkdir(); (root/'report.json').write_text('{}')
            (root/'lvs-extraction/extracted.spice').write_text(native(missing=True, ports=('P1','N1')))
            (root/'lvs-extraction/native-extraction.log').write_text('STUDIO_MAGIC_COMPLETE\n')
            result = dict(status='failed', drc_count=0, stages=[dict(name=n,
                status='passed' if n in suite.STAGES[:3] else 'failed' if n == 'lvs_extraction' else 'not_run') for n in suite.STAGES])
            stage = next(s for s in result['stages'] if s['name'] == 'lvs_extraction')
            stage['error'] = 'Extracted port order differs from the schematic: actual retained two-port interface.'
            suite.check_fault(result, root, 'physical-missing-instance', 1)
            for bad in ('Native process timeout.', 'MiM orientation failed.'):
                stage['error'] = bad
                with self.assertRaises(ValueError): suite.check_fault(result, root, 'physical-missing-instance', 1)


if __name__ == '__main__': unittest.main()
