"""Parallel unit geometry, regeneration, terminal routing and native audit guards."""
import json
from pathlib import Path
import tempfile
import unittest
from icstudio.layout import kdb, polygon
from icstudio.layout_eco import regenerate
from icstudio.model import clone, load_project, save_project
from icstudio.process_adapters import ADAPTERS
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_mos_parallel_layouts import TARGETS, FAULTS, sizes, fixture, altered, audit_native


class ParallelMosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.techs = {t: load_technology(t)[0] for t in TARGETS}

    def region(self, cell, layer):
        r = kdb().Region()
        for shape in cell['shapes']:
            if shape['layer'] == layer: r.insert(polygon(shape))
        return r.merged()

    def test_unit_dimensions_terminals_and_metal_clearance(self):
        for target in TARGETS:
            for polarity in ('n', 'p'):
                for width, length, copies in sizes(target):
                    p = fixture(self.techs[target], target, polarity, (width, length, copies)); c = p['cells'][0]
                    ls = ADAPTERS[target].layers(p['pdk']); db = kdb()
                    channels = (self.region(c, ls['diff']) & self.region(c, ls['poly'])).merged()
                    self.assertEqual(channels.count(), copies)
                    for channel in channels.each():
                        self.assertEqual(channel.bbox().width(), round(length*1000))
                        self.assertEqual(channel.bbox().height(), round(width*1000))
                    rails = self.region(c, ls['m2'])
                    self.assertEqual(rails.count(), 4)
                    self.assertTrue(rails.space_check(280 if target.startswith('gf180') else 210).is_empty())
                    self.assertTrue((self.region(c, ls['via']).sized(60) - rails).is_empty())
                    self.assertTrue((self.region(c, ls['via']).sized(60) - self.region(c, ls['m1'])).is_empty())
                    self.assertEqual(len(c['layout_pins']), 4)
                    offsets = c['pdk_layouts'][0]['parallel_units']['offsets_nm']
                    for pin in c['layout_pins']:
                        px, py = pin['point']; rx = px + {'s': -200, 'd': 200}.get(pin['pin'], 0)
                        rail = [r for r in rails.each() if all(r.inside(db.Point(rx, py+dy)) for _, dy in offsets)]
                        self.assertEqual(len(rail), 1)
                    self.assertEqual(len({s['generator_role'] for s in c['shapes']}), len(c['shapes']))

    def test_regeneration_preserves_first_unit_and_pin_ids(self):
        for target in TARGETS:
            w, l, _ = sizes(target)[0]; p = fixture(self.techs[target], target, 'p', (w, l, 1)); c = p['cells'][0]
            original = {s['generator_role']: clone(s) for s in c['shapes']}
            pins = clone(c['layout_pins']); d = c['devices'][0]
            for copies in (2, 16, 3, 1):
                d['model_params']['m'] = str(copies); regenerate(p, c['id'], d['id'])
                self.assertEqual(c['layout_pins'], pins)
                for shape in c['shapes']:
                    if shape['generator_role'] in original: self.assertEqual(shape, original[shape['generator_role']])
                self.assertEqual(ADAPTERS[target].implementation().audit(p, c['id']), [])
                with tempfile.TemporaryDirectory() as td:
                    path = Path(td)/'saved.icproj'; save_project(p, path); q = load_project(path)
                    self.assertEqual(q['cells'][0]['pdk_layouts'], c['pdk_layouts'])
            self.assertEqual(len(c['shapes']), len(original))

    def test_stale_count_and_invalid_copies_or_fingers_are_rejected(self):
        for target in TARGETS:
            p = fixture(self.techs[target], target, 'n', sizes(target)[0]); c = p['cells'][0]; impl = ADAPTERS[target].implementation()
            c['devices'][0]['model_params']['m'] = '3'
            self.assertTrue(impl.audit(p, c['id']))
            for key, value in [('m', '0'), ('m', '-1'), ('m', '1.5'), ('m', '17'),
                               ('ng' if target == 'ihp-sg13g2' else 'nf', '2')]:
                changed = clone(c['devices'][0]); changed['model_params'][key] = value
                with self.subTest(target=target, key=key, value=value), self.assertRaises(ValueError):
                    impl.specification(p['pdk'], changed)

    def test_inverter_arrays_do_not_overlap(self):
        for target in TARGETS:
            impl = ADAPTERS[target].implementation(); tech = self.techs[target]
            for ncount, pcount in ((1, 3), (3, 1), (16, 16)):
                p = fixture(tech, target, 'n', (1, 1, ncount)); c = p['cells'][0]; cid = c['id']
                q = fixture(tech, target, 'p', (1, 1, pcount)); q['cells'][0]['devices'][0]['name'] = 'M2'
                c['devices'].append(q['cells'][0]['devices'][0])
                c['ports'] = ['A', 'Y', 'VPWR', 'VGND']
                for d in c['devices']:
                    supply = 'VGND' if d['kind'] == 'NMOS' else 'VPWR'
                    d['nets'] = dict(d='Y', g='A', s=supply, b=supply)
                for key in ('shapes', 'layout_pins', 'layout_ports', 'pdk_layouts'): c[key] = []
                impl.generate_inverter(p, cid)
                bounds = []
                for d in c['devices']:
                    regions = kdb().Region()
                    for s in c['shapes']:
                        if s.get('generated_device') == d['id']: regions.insert(polygon(s))
                    bounds.append(regions.bbox())
                self.assertGreaterEqual(bounds[1].bottom - bounds[0].top, 3000)

    def test_custom_emission_cannot_turn_an_unused_m_into_physical_copies(self):
        from icstudio.catalog import binding_for
        from icstudio.gf180_layout import mos
        for target in ('gf180mcuC', 'gf180mcuD'):
            p = fixture(self.techs[target], target, 'n', (1, 1, 1)); d = p['cells'][0]['devices'][0]
            binding = binding_for(p['pdk'], d)
            binding['parameters']['copies'] = dict(default='1', positive=True)
            binding['emit_parameters']['m'] = 'copies'
            for m, copies in (('2', '1'), ('1', '2')):
                d['model_params'].update(m=m, copies=copies)
                with self.assertRaisesRegex(ValueError, 'explicit GF180 m'):
                    mos(p['pdk'], d)
            d['model_params'].update(m='1', copies='1')
            self.assertNotIn('parallel_units', mos(p['pdk'], d)['record'])

    def test_faults_remove_actual_unit_or_selected_contact_geometry(self):
        for target in TARGETS:
            p = fixture(self.techs[target], target, 'p', sizes(target)[1]); before = clone(p); c = p['cells'][0]
            for fault in FAULTS:
                other = altered(p, target, fault)['cells'][0]
                self.assertEqual(other['devices'], c['devices']); self.assertEqual(other['layout_ports'], c['layout_ports'])
                removed = [s for s in c['shapes'] if s not in other['shapes']]
                if fault.startswith('reference-'): self.assertEqual(len(removed), 0)
                elif fault.endswith('-via-open'): self.assertEqual(len(removed), 1)
                elif fault == 'all-body-contacts-open': self.assertEqual(len(removed), 3)
                else: self.assertGreater(len(removed), 10)
            self.assertEqual(p, before)

    def test_native_audit_requires_each_unit_dimensions_and_terminals(self):
        good = '.subckt parallel_coupon D G S B\n'+''.join(f'X{i} D G S B nfet_03v3 w=0.22u l=0.28u\n' for i in range(2))+'.ends\n'
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'native.spice'; path.write_text(good, encoding='utf-8')
            self.assertEqual(audit_native(path, 'gf180mcuC', 'n', (.22, .28, 2))['units'], 2)
            for wrong in (good.replace('X1 D', 'X1 FLOAT'), good.replace('w=0.22u', 'w=0.44u', 1),
                          good.replace('l=0.28u', 'l=0.3u', 1), good.replace('nfet_03v3', 'pfet_03v3', 1),
                          good.replace('X1 D G S B nfet_03v3 w=0.22u l=0.28u\n', '')):
                path.write_text(wrong, encoding='utf-8')
                with self.assertRaises(ValueError): audit_native(path, 'gf180mcuC', 'n', (.22, .28, 2))


if __name__ == '__main__': unittest.main()
