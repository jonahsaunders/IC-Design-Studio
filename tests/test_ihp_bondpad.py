"""Real written pad masks, terminal identity and source/domain fault controls."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as db

from icstudio import ihp_bondpad as pad
from icstudio.ihp_bondpad_ui import dialog, nanometres
from icstudio.interchange import export_layout
from icstudio.model import clone, digest, example, load_project, save_project
from scripts.qualify_ihp_bondpad import CASES, check_stream, native_pair, project, qualify, technology, upstream_rectangles


class IHPBondpadTests(unittest.TestCase):
    def test_native_runner_retains_dirty_positive_and_fails_the_selected_gate(self):
        dirty = dict(violations=1, decks=[dict(violations=1, categories=['context-finding'])])
        negative = dict(violations=1, decks=[dict(violations=1, categories=["'Pad.i'"])])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'run'
            with patch('icstudio.ihp_klayout_drc.drc', side_effect=[dirty, negative]), self.assertRaisesRegex(ValueError, 'positive DRC must be clean'):
                qualify(output, klayout='mock-native-engine')
            report = json.loads((output/'record.json').read_bytes())
            self.assertEqual(report['status'], 'failed-selected-native-geometry-gate')
            self.assertEqual(report['public_drc']['positive'], dirty)
            self.assertFalse(report['public_drc']['positive_clean'])
            self.assertTrue(report['public_drc']['control_detected'])
            self.assertTrue(report['drc_executed'])
            self.assertFalse(report['qualified'])

    def test_native_control_requires_the_actual_pad_rule_and_nonzero_findings(self):
        positive = dict(violations=0, decks=[dict(violations=0, categories=[])])
        for category in ('Pad.i', "'Pad.i'"):
            negative = dict(violations=1, decks=[dict(violations=1, categories=[category])])
            self.assertTrue(native_pair(positive, negative)['control_detected'])
        for category, count in (('OTHER', 1), ('Pad.i-extra', 1), ('Pad.i', 0), ('tool failed', 1)):
            negative = dict(violations=count, decks=[dict(violations=count, categories=[category])])
            self.assertFalse(native_pair(positive, negative)['control_detected'])
        self.assertFalse(native_pair(dict(violations=3), negative)['positive_clean'])

    def test_actual_written_geometry_and_project_exchange_for_all_selected_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = qualify(Path(temporary)/'run')
            self.assertEqual(len(result['cases']), 32)
            self.assertEqual({r['format'] for r in result['cases']}, {'gds', 'oas'})
            self.assertTrue(all(r['masks'] == 3 and r['terminal_order'] == ['PAD'] for r in result['cases']))
            self.assertFalse(result['qualified']); self.assertFalse(result['electrical_model'])
            self.assertFalse(result['drc_executed']); self.assertFalse(result['chunk_complete'])

    def test_retained_sources_authenticate_all_bytes_and_the_placeholder_stays_empty(self):
        lock = pad.verify_sources()
        self.assertEqual(lock['commit'], '5e6d592e4002946a4616f798c357f0f3c06cf3b6')
        self.assertEqual(lock['license'], 'Apache-2.0')
        text = (pad.SOURCE/'sg13g2_bondpad.lib').read_text()
        statements = [line.strip().lower() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
        self.assertEqual(statements, ['.subckt bondpad pad', '.params size=80u shape=0 padtype=0', '.ends bondpad'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'source'; shutil.copytree(pad.SOURCE, root)
            for name in ['source-lock.json', *lock['files']]:
                path = root/name; original = path.read_bytes(); path.write_bytes(original+b'\n')
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Changed IHP bondpad source'):
                    pad.verify_sources(root)
                path.write_bytes(original)

    def test_public_selected_branch_has_only_three_rectangles_and_no_invented_substrate(self):
        for q, expected_bounds in ((1, (-40, -40, 40, 40)), (.5, (-40, -20, 40, 20)), (2, (-20, -40, 20, 40))):
            source = upstream_rectangles(dict(diameter_nm=80000, hwquota=q))
            self.assertEqual([name for name, _ in source], ['TopMetal2', 'dfpad.drawing', 'Passiv'])
            self.assertEqual(tuple(round(x, 9) for x in source[0][1]), expected_bounds)
            p, record = project(technology(), dict(diameter_nm=80000, hwquota=q))
            self.assertEqual([t['name'] for t in record['terminals']], ['PAD'])
            self.assertEqual(p['cells'][0]['devices'], [])

    def test_source_domain_fallback_and_silent_rounding_are_rejected_before_mutation(self):
        bad = [{'diameter_nm': 0}, {'diameter_nm': 80005}, {'diameter_nm': True},
               {'diameter_nm': 4200}, {'diameter_nm': 80000, 'hwquota': 9},
               {'hwquota': 1.3}, {'hwquota': 0}, {'hwquota': -1}, {'hwquota': float('nan')},
               {'hwquota': float('inf')}, {'hwquota': True}, {'x_nm': 1},
               {'y_nm': False}, {'rotation': 45}, {'rotation': True},
               {'shape': 'octagon'}, {'stack': True}, {'topMetal': 'TM1'},
               {'fill': True}, {'FlipChip': 'yes'}, {'passEncl': '1u'},
               {'diameter_nm': 2**32}, {'x_nm': 2147483645}]
        for values in bad:
            p = example('empty'); p['pdk'] = technology(); p['cells'][0]['ports'] = ['PAD']; before = clone(p)
            with self.subTest(values=values), self.assertRaises(ValueError):
                pad.install(p, p['top'], 'PAD', values)
            self.assertEqual(p, before)
        # Exact public grid and the 10 um fallback boundary are separate facts
        # from a process/legal pad minimum. Neither is promoted to a rating.
        self.assertEqual(pad.specification({'diameter_nm': 80000, 'hwquota': 8})['radii_nm'], [5000, 40000])
        self.assertEqual(pad.specification({'diameter_nm': 4210})['radii_nm'], [2105, 2105])

    def test_requires_existing_unassigned_explicit_port_and_exact_process_layer_maps(self):
        for modify, name in ((lambda p: p['cells'][0].update(ports=[]), 'missing port'),
                             (lambda p: p['pdk']['package_lock'].update(id='sky130A'), 'wrong process'),
                             (lambda p: p['pdk'].update(grid=10), 'wrong grid'),
                             (lambda p: p['pdk']['layers'].append(clone(p['pdk']['layers'][0])), 'irrelevant duplicate')):
            p = example('empty'); p['pdk'] = technology(); p['cells'][0]['ports'] = ['PAD']; modify(p)
            if name == 'irrelevant duplicate':
                # Only the layer map actually used by this recipe is constrained
                # here; ordinary project validation rejects duplicate names.
                with self.assertRaises(ValueError): pad.install(p, p['top'], 'PAD')
            else:
                before = clone(p)
                with self.subTest(name=name), self.assertRaises(ValueError): pad.install(p, p['top'], 'PAD')
                self.assertEqual(p, before)
        p, _ = project(technology(), {})
        before = clone(p)
        with self.assertRaisesRegex(ValueError, 'already'): pad.install(p, p['top'], 'PAD')
        self.assertEqual(p, before)
        tech = technology(); tech['layers'] = [l for l in tech['layers'] if (l['gds'], l['datatype']) != (134, 0)]
        with self.assertRaisesRegex(ValueError, 'mapping'): pad.geometry(tech)

    def test_pad_attachment_preserves_the_electrical_catalog_and_devices(self):
        p = example('empty'); p['pdk'] = technology(); p['cells'][0]['ports'] = ['PAD']
        simulation = clone(p['pdk']['simulation']); devices = clone(p['cells'][0]['devices'])
        self.assertTrue(simulation['catalog']['sg13g2_pr/bondpad.sym']['unavailable'])
        record = pad.install(p, p['top'], 'PAD')
        self.assertEqual(p['pdk']['simulation'], simulation)
        self.assertEqual(p['cells'][0]['devices'], devices)
        self.assertFalse(record['electrical_model'])
        self.assertEqual(p['cells'][0]['layout_ports'], record['terminals'])

    def test_wrong_masks_openings_dimensions_extra_regions_and_labels_fail_written_readback(self):
        parameters = dict(diameter_nm=80000, hwquota=.5, rotation=90, x_nm=125, y_nm=-325)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); p, _ = project(technology(), parameters); original = folder/'valid.gds'
            export_layout(p, original); check_stream(original, parameters)
            for fault in ('remove_marker', 'wrong_metal', 'widen_opening_5nm', 'shrink_metal_5nm',
                          'extra_metal_island', 'cut_metal', 'wrong_port', 'moved_port',
                          'duplicate_port', 'substrate_port', 'wrong_label_purpose'):
                layout = db.Layout(); layout.read(str(original)); cell = layout.top_cell()
                if fault == 'remove_marker': cell.shapes(layout.layer(41, 0)).clear()
                elif fault == 'wrong_metal':
                    cell.shapes(layout.layer(126, 0)).insert(db.Region(cell.shapes(layout.layer(134, 0))))
                    cell.shapes(layout.layer(134, 0)).clear()
                elif fault in ('widen_opening_5nm', 'shrink_metal_5nm'):
                    index = layout.layer(9, 0) if fault.startswith('widen') else layout.layer(134, 0)
                    region = db.Region(cell.shapes(index)).sized(5 if fault.startswith('widen') else -5)
                    cell.shapes(index).clear(); cell.shapes(index).insert(region)
                elif fault == 'extra_metal_island': cell.shapes(layout.layer(134, 0)).insert(db.Box(100000, 100000, 101000, 101000))
                elif fault == 'cut_metal':
                    index = layout.layer(134, 0); region = db.Region(cell.shapes(index))-db.Region(db.Box(120, -100000, 130, 100000))
                    cell.shapes(index).clear(); cell.shapes(index).insert(region)
                else:
                    index = layout.layer(134, 2); cell.shapes(index).clear()
                    if fault == 'wrong_label_purpose': index = layout.layer(134, 1)
                    name = 'OTHER' if fault == 'wrong_port' else 'PAD'
                    x = 130 if fault == 'moved_port' else 125
                    cell.shapes(index).insert(db.Text(name, db.Trans(x, -325)))
                    if fault in ('duplicate_port', 'substrate_port'):
                        cell.shapes(index).insert(db.Text('SUB' if fault == 'substrate_port' else 'PAD', db.Trans(125, -320)))
                path = folder/(fault+'.gds'); layout.write(str(path))
                with self.subTest(fault=fault), self.assertRaises(ValueError): check_stream(path, parameters)

    def test_ui_builds_reviewed_candidate_and_obeys_layer_locks(self):
        class Studio:
            def __init__(self):
                self.project = example('empty'); self.project['pdk'] = technology(); self.cid = self.project['top']
                self.cell = self.project['cells'][0]; self.cell['ports'] = ['PAD']; self.locked = set()
                self.layout = type('Layout', (), {})(); self.layout.locked_layers = self.locked
            def idle_edit(self): return True
            def workflow_form(self, title, fields, submit, note):
                self.fields = fields; self.submit = submit; return title
            def review_dialog(self, title, build, apply_candidate):
                self.candidate, self.explanation = build(); self.apply = apply_candidate
        studio = Studio(); self.assertEqual(dialog(studio), 'IHP square bondpad')
        values = dict(port='PAD', diameter='80', quota='0.5', x='0.125', y='-0.325', rotation='90')
        before = clone(studio.project); studio.submit(values)
        self.assertEqual(studio.project, before)
        self.assertIn('electrical bondpad model remains unavailable', studio.explanation)
        studio.locked.add('Passiv.drawing')
        with self.assertRaisesRegex(ValueError, 'Unlock'): studio.apply(studio.project, studio.candidate)
        self.assertEqual(studio.project, before)
        studio.locked.clear(); studio.apply(studio.project, studio.candidate)
        self.assertEqual(len(studio.project['cells'][0]['ihp_bondpads']), 1)
        for value in ('nan', 'inf', '0.0001'):
            with self.assertRaises(ValueError): nanometres(value)
        self.assertEqual(nanometres('0.005'), 5)


if __name__ == '__main__':
    unittest.main()
