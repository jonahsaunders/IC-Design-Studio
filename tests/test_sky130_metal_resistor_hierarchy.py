"""Exact imported hierarchy semantics; no simulator/model envelope claim."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k

from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.layout_verification import verification_stream
from icstudio.model import clone, load_project, save_project
from scripts import qualify_sky130_metal_resistor_hierarchy as suite


def leaf(path, model, landing=500):
    ly = k.Layout(); ly.dbu = .001; cell = ly.create_cell('coupon')
    layer = suite.straight.MODELS[model][0]
    cell.shapes(ly.layer(layer, 20)).insert(k.Box(0, -landing, 2000, 5000+landing))
    cell.shapes(ly.layer(layer, 13)).insert(k.Box(0, 0, 2000, 5000))
    cell.shapes(ly.layer(layer, 5)).insert(k.Text('R1', k.Trans(1000, (-landing)//2)))
    cell.shapes(ly.layer(layer, 5)).insert(k.Text('R2', k.Trans(1000, 5000+landing//2)))
    ly.write(str(path))


def native(model='m1'):
    return ('.subckt res_pair A1 B1 A2 B2\n'
            f'R0 A1 B1 sky130_fd_pr__res_generic_{model} w=2 l=5\n'
            f'R1 B2 A2 sky130_fd_pr__res_generic_{model} w=2 l=5\n'
            '.ends res_pair\n')


class ImportedHierarchyTests(unittest.TestCase):
    def test_reused_child_transforms_and_exchange_preserve_actual_masks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for model in suite.MODELS:
                source = root/f'{model}-leaf.gds'; leaf(source, model)
                for angle in suite.ANGLES:
                    with self.subTest(model=model, angle=angle):
                        stream = root/f'{model}-{angle}.gds'
                        proof = suite.make_stream(source, stream, model, angle)
                        self.assertEqual(proof['instances'], 2)
                        p, _ = read_layout(stream)
                        top = next(c for c in p['cells'] if c['id'] == p['top'])
                        top['ports'] = list(suite.PORTS)
                        project = root/'save.icproj'; save_project(p, project)
                        loaded = load_project(project)
                        self.assertEqual(loaded['cells'], p['cells'])
                        for extension in ('gds', 'oas'):
                            target = root/f'out.{extension}'; export_layout(loaded, target)
                            self.assertEqual(suite.compare(stream, target, text_presentation=False)['status'], 'passed')
                            suite.inspect_stream(target, model, angle, source)

    def test_private_native_stream_keeps_four_top_ports_and_removes_child_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root/'leaf.gds'; leaf(source, 'm1')
            for angle in suite.ANGLES:
                stream, target = root/f'input{angle}.gds', root/f'private{angle}.gds'
                suite.make_stream(source, stream, 'm1', angle)
                proof = verification_stream(stream, suite.TOP, suite.PORTS, target, pin_layers={(68, 5)})
                self.assertEqual(proof['removed_noninterface_labels'], 2)
                ly = k.Layout(); ly.read(str(target))
                self.assertEqual({t.string for _, _, t in suite.texts(ly, ly.top_cell())}, set(suite.PORTS))
                self.assertEqual(list(ly.top_cell().each_inst()), [])
                original = k.Layout(); original.read(str(stream))
                suite.same_regions(suite.masks(original, original.top_cell(), True), suite.masks(ly, ly.top_cell(), True))
                suite.inspect_stream(stream, 'm1', angle, source)

    def test_each_exchange_corruption_rejects_instead_of_flattening_it_away(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root/'leaf.gds'; leaf(source, 'm1')
            stream = root/'input.gds'; suite.make_stream(source, stream, 'm1', 0)
            for fault in suite.EXCHANGE_FAULTS:
                with self.subTest(fault=fault):
                    bad = root/(fault+'.gds'); suite.corrupt_exchange(stream, bad, fault, 'm1')
                    with self.assertRaises(ValueError): suite.inspect_stream(bad, 'm1', 0, source)

    def test_native_graph_requires_two_exact_distinct_devices(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'native.spice'; text = native()
            path.write_text(text); self.assertEqual(suite.native_devices(path, 'm1')['devices'], 2)
            mutations = [text.replace('B2 A2', 'B2 A1'), text.replace('B2 A2', 'B1 A2'),
                text.replace('res_generic_m1', 'res_generic_m2'), text.replace('w=2', 'w=3'),
                text.replace('l=5', 'l=4'), text.replace('w=2 l=5', 'w=2 l=5 m=2'),
                text.replace('w=2 l=5', 'w=2 l=5 w=2'), text.replace('A1 B1 A2 B2', 'B1 A1 A2 B2'),
                '\n'.join(text.splitlines()[:2]+text.splitlines()[3:]), text+'Xextra P N dummy\n',
                text+'.include unexpected.spice\n', text.replace('.ends res_pair\n', ''),
                text.replace('R1 B2', 'R0 B2')]
            for changed in mutations:
                with self.subTest(changed=changed):
                    path.write_text(changed)
                    with self.assertRaises(ValueError): suite.native_devices(path, 'm1')

    def test_physical_short_requires_only_the_declared_shared_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'native.spice'
            path.write_text(native().replace('B2 A2', 'B2 A1'))
            suite.native_devices(path, 'm1', short=True)
            for changed in [native(), native().replace('B2 A2', 'B1 A2'),
                            native().replace('B2 A2', 'B1 A1'),
                            native().replace('B2 A2', 'B2 A1').replace('.subckt res_pair A1 B1 A2 B2', '.subckt res_pair A1 B1 A2 FOO')]:
                path.write_text(changed)
                with self.assertRaises(ValueError): suite.native_devices(path, 'm1', short=True)

    def test_reference_controls_are_local_and_keep_all_four_declared_ports(self):
        for model in suite.MODELS:
            original = suite.selected(model)
            for fault in suite.FAULTS:
                changed = suite.selected(model, fault)
                self.assertEqual(changed['ports'], list(suite.PORTS))
                if fault == 'physical-cross-instance-short': self.assertEqual(changed, original)
                else: self.assertNotEqual(changed['sha256'], original['sha256'])
        with self.assertRaises(ValueError): suite.selected('m1', 'unsupported')

    def test_bridge_preserves_leaf_instances_and_changes_only_parent_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root/'leaf.gds'; leaf(source, 'm1', landing=285)
            stream = root/'input.gds'; suite.make_stream(source, stream, 'm1', 0)
            p, _ = read_layout(stream); original = clone(p); changed = suite.bridge(p, 'm1')
            self.assertEqual(p, original)
            old_top = next(c for c in p['cells'] if c['id'] == p['top'])
            new_top = next(c for c in changed['cells'] if c['id'] == changed['top'])
            self.assertEqual(len(new_top['shapes']), len(old_top['shapes'])+4)
            normalized = clone(changed); next(c for c in normalized['cells'] if c['id'] == normalized['top'])['shapes'] = old_top['shapes']
            self.assertEqual(normalized, original)
            self.assertTrue(all(x['layer'] == new_top['shapes'][0]['layer'] for x in new_top['shapes']))
            exported = root/'short.gds'; export_layout(changed, exported)
            ly = k.Layout(); ly.read(str(exported)); top = ly.top_cell()
            addition = suite.masks(ly, top)[68, 20]
            markers = suite.masks(ly, top, recursive=True)[68, 13]
            self.assertTrue((addition & markers).is_empty())
            anchors = {t.string: (t.x, t.y) for _, _, t in suite.texts(ly, top)}
            self.assertEqual(40000-anchors['A2'][0], 143)
            # The first pilot's symmetric 0.4um cap actually crossed this body.
            a = anchors['A2']; old_cap = k.Region(k.Box(a[0]-200, a[1]-200, a[0]+200, a[1]+200))
            self.assertFalse((old_cap & markers).is_empty())

    def test_fault_does_not_pass_on_setup_failure_or_missing_native_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'lvs-extraction').mkdir(); (root/'lvs').mkdir()
            (root/'lvs-extraction/extracted.spice').write_text(native())
            (root/'report.json').write_text('{}')
            log = root/'lvs/lvs.log'; log.write_text('Netlists do not match.\n')
            result = dict(status='failed', drc_count=0,
                stages=[dict(name=name, status='failed' if name == 'lvs' else 'passed') for name in suite.STAGES])
            suite.check_fault(result, root, 'merged-reference-terminal', 'm1')
            for stage in ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'integrity'):
                with self.subTest(stage=stage):
                    changed = clone(result)
                    next(s for s in changed['stages'] if s['name'] == stage)['status'] = 'failed'
                    with self.assertRaises(ValueError): suite.check_fault(changed, root, 'merged-reference-terminal', 'm1')
            for text in ('', 'exec failed: missing tool', 'Circuits match uniquely.'):
                log.write_text(text)
                with self.assertRaises(ValueError): suite.check_fault(result, root, 'merged-reference-terminal', 'm1')

    def test_physical_short_cannot_use_an_unrelated_extraction_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'lvs-extraction').mkdir(); (root/'report.json').write_text('{}')
            (root/'lvs-extraction/extracted.spice').write_text(native().replace('B2 A2', 'B2 A1').replace('A1 B1 A2 B2', 'A1 B1 B2'))
            result = dict(status='failed', drc_count=0, stages=[dict(name=name, status=
                'passed' if name in suite.STAGES[:3] else 'failed' if name == 'lvs_extraction' else 'not_run')
                for name in suite.STAGES])
            stage = next(s for s in result['stages'] if s['name'] == 'lvs_extraction')
            stage['error'] = 'Extracted port order differs from the schematic: retained three-port test fixture.'
            suite.check_fault(result, root, 'physical-cross-instance-short', 'm1')
            stage['error'] = 'Native process timed out.'
            with self.assertRaises(ValueError): suite.check_fault(result, root, 'physical-cross-instance-short', 'm1')


if __name__ == '__main__': unittest.main()
