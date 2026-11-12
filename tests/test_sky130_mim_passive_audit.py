"""Independent audit controls for falsified MiM numerical summaries.

The raw fixture remains unchanged: these mutations challenge the evidence
consumer rather than the simulator or producer's acceptance calculation.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import klayout.db as db

from scripts import audit_sky130_mim_passive_corners as audit
from scripts import qualify_sky130_mim_passive_corners as runner
from scripts import audit_sky130_mim_physical_case as physical
from tests.test_sky130_mim_passive_corners import CONTRACT, write_raw


class MiMPassiveSummaryAudit(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'probe.raw'
        write_raw(self.path)
        self.coefficients = CONTRACT['passive_sections']['tt']['coefficients']
        self.record = runner.measure(self.path, 1, self.coefficients)

    def test_valid_saved_summary_matches_retained_raw(self):
        self.assertEqual(audit.check_raw(self.path, 1, self.coefficients, self.record), 8)

    def test_nonfinite_saved_admittance_is_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            for component in (0, 1):
                with self.subTest(value=value, component=component):
                    changed = copy.deepcopy(self.record)
                    changed['samples'][0]['paths']['schematic']['Y_S'][component] = value
                    with self.assertRaises(ValueError):
                        audit.check_raw(self.path, 1, self.coefficients, changed)

    def test_saved_analytical_target_must_match_source_equation(self):
        for name in ('expected_R_ohm', 'expected_C_F'):
            for value in (float('nan'), float('inf'), self.record[name] * 2):
                with self.subTest(name=name, value=value):
                    changed = copy.deepcopy(self.record)
                    changed[name] = value
                    with self.assertRaises(ValueError):
                        audit.check_raw(self.path, 1, self.coefficients, changed)


class MiMPassivePhysicalAudit(unittest.TestCase):
    def test_physical_stage_identity_cannot_be_missing_duplicated_or_reordered(self):
        stages = [dict(name=name, status='passed') for name in physical.STAGES]
        self.assertEqual(tuple(physical.stage_map(dict(stages=stages))), physical.STAGES)
        for changed in (stages[:-1], stages + [stages[0]], list(reversed(stages))):
            with self.assertRaises(ValueError): physical.stage_map(dict(stages=changed))

    def test_mask_faults_change_only_the_declared_layer_and_contacts(self):
        for plate, cap, cut in ((1, (89, 44), (70, 44)), (2, (97, 44), (71, 44))):
            with self.subTest(plate=plate):
                dielectric = db.Region(db.Box(0, 0, 2000, 10000))
                top = db.Region(db.Box(100, 100, 300, 300))
                bottom = db.Region(db.Box(2500, 100, 2700, 300))
                metal = (plate + 69, 20)
                original = {cap: dielectric, cut: top + bottom, metal: db.Region(db.Box(-500, -500, 3000, 10500))}
                for fault in physical.FAULTS:
                    expected = {k: v.dup() for k, v in original.items()}
                    if fault == 'dielectric-missing': expected[cap] = db.Region()
                    elif fault == 'top-open': expected[cut] = bottom.dup()
                    elif fault == 'bottom-open': expected[cut] = top.dup()
                    physical.fault_masks(original, expected, plate, fault)
                    unexpected = {k: v.dup() for k, v in expected.items()}
                    unexpected[metal] = db.Region()
                    with self.assertRaises(ValueError): physical.fault_masks(original, unexpected, plate, fault)
                    if not fault.startswith('reference-'):
                        with self.assertRaises(ValueError): physical.fault_masks(original, original, plate, fault)

    def test_reference_mutation_and_open_terminal_are_read_from_native_circuit(self):
        text = '.subckt device_coupon P N\nX1 P N sky130_fd_pr__cap_mim_m3_1 w=2.4 l=10 m=1\n.ends\n'
        physical.circuit(text, 1, (2.4, 10, 1))
        for bad in (text.replace('w=2.4', 'w=2'), text.replace('w=2.4', 'w=2.4 w=2.4'), text.replace('m=1', 'm=nan')):
            with self.assertRaises(ValueError): physical.circuit(bad, 1, (2.4, 10, 1))
        opened = text.replace('X1 P N', 'X1 internal# N').replace('w=2.4', 'w=2')
        physical.circuit(opened, 1, top_open=True)
        with self.assertRaises(ValueError): physical.circuit(opened, 1)
        with self.assertRaises(ValueError): physical.circuit(opened.replace('internal#', 'P'), 1, top_open=True)

    def test_native_completion_requires_one_exact_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'native.log'
            path.write_text('Magic ran.\nSTUDIO_MAGIC_COMPLETE\n')
            physical.native_completion(path)
            for changed in ('Magic failed.\n', 'STUDIO_MAGIC_COMPLETE\nSTUDIO_MAGIC_COMPLETE\n', 'STUDIO_MAGIC_COMPLETE_UNFINISHED\n'):
                path.write_text(changed)
                with self.assertRaises(ValueError): physical.native_completion(path)


class MiMNativeExecutionAudit(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.folder = self.root / 'physical/1/valid-0-plain'
        self.folder.mkdir(parents=True)
        tech = 'libs.tech/magic/sky130A.tech'; pcell = 'libs.tech/magic/sky130A.tcl'
        setup = 'libs.tech/netgen/sky130A_setup.tcl'
        sources = self.root / 'contract-sources'; sources.mkdir()
        release = dict(release='pinned-release', repository='public/source', files={
            'common.tar.zst': '1' * 64, 'sky130_fd_pr.tar.zst': '2' * 64, 'sky130_fd_sc_hd.tar.zst': '3' * 64})
        (sources / 'physical_release_lock').write_text(json.dumps(release))
        (sources / 'physical_technology').write_text('captured technology')
        (sources / 'physical_pcell').write_text('captured generator')
        selected = dict(release); selected['files'] = {k: release['files'][k] for k in ('common.tar.zst', 'sky130_fd_pr.tar.zst')}
        upstream = physical.hashlib.sha256((json.dumps(selected, indent=2, sort_keys=True) + '\n').encode()).hexdigest()
        self.pdk = dict(package_root='/installed/pdk', package_lock=dict(id='sky130A', revision='revision', files={
            'UPSTREAM-LOCK.json': upstream, tech: physical.sha(sources / 'physical_technology'),
            pcell: physical.sha(sources / 'physical_pcell'), setup: '4' * 64, 'libs.tech/netgen/setup.tcl': '4' * 64}),
            physical=dict(magic_technology=tech, netgen_setup=setup), connectivity={'test': 'fixture'}, routing_conductors=['fixture'])
        self.save(self.root / 'physical/1/input.icproj', dict(pdk=self.pdk))
        self.save(self.root / 'contract.json', dict(sources={name: dict(sha256=physical.sha(sources / name)) for name in
            ('physical_release_lock', 'physical_technology', 'physical_pcell')}))
        self.save(self.root / 'qualification.json', dict(physical_package=dict(target='sky130A', revision='revision'),
            execution_root='/original/evidence', tools={name: dict(path='/tools/' + name, sha256='5' * 64) for name in ('magic', 'netgen')}))
        self.context = physical.execution_context(self.folder.parent, 1)
        self.proof = dict(technology_sha256=self.context['assets'][self.context['technology']],
                          pcell_sha256=self.pdk['package_lock']['files'][pcell])
        self.native = dict(drc_engine='magic', lvs_extractor='magic', mim_orientation=self.proof,
            stages=[dict(name=name, status='passed', evidence=dict(assets=self.context['assets'], tools=self.context['tools']))
                    for name in ('preflight', 'integrity')])
        self.write_fixture()

    @staticmethod
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))

    def write_fixture(self, fault=None):
        for stage in ('drc', 'lvs-extraction'):
            (self.folder / stage).mkdir(exist_ok=True)
            for path in (self.folder / stage).glob('*.tcl'): path.unlink()
        origin = self.context['origin'] + '/' + self.folder.name
        for name, text in physical.execution_scripts(origin, self.context['technology'], fault).items():
            (self.folder / name).write_text(text)
        expected = self.pdk if fault else {k: v for k, v in self.pdk.items() if k not in ('connectivity', 'routing_conductors')}
        self.save(self.folder / 'input.icproj', dict(pdk=expected))
        self.save(self.folder / 'lvs-extraction/mim-orientation.json', self.proof)
        (self.folder / 'lvs').mkdir(exist_ok=True)
        (self.folder / 'lvs/console.log').write_text(
            f'Reading netlist file {origin}/schematic-lvs.spice\nReading netlist file {origin}/lvs-extraction/extracted.spice\n'
            f'Reading setup file {self.context["setup"]}\n')

    def test_executed_scripts_cannot_disable_checks_or_redirect_inputs(self):
        physical.check_execution(self.folder, self.native, self.context)
        changes = [('drc/startup.tcl', self.context['technology'], '/unbound/technology'),
                   ('drc/run.tcl', 'drc ignore none', 'drc ignore all'),
                   ('lvs-extraction/run.tcl', 'ext2spice blackbox off', 'ext2spice blackbox on'),
                   ('lvs-extraction/native-extraction.tcl', '/layout.gds', '/other.gds')]
        for name, before, after in changes:
            with self.subTest(name=name):
                path = self.folder / name; original = path.read_text(); path.write_text(original.replace(before, after))
                with self.assertRaisesRegex(ValueError, 'Executed native Tcl differs'):
                    physical.check_execution(self.folder, self.native, self.context)
                path.write_text(original)

    def test_failed_extraction_paths_require_their_actual_script_coverage(self):
        for fault in ('bottom-open', 'dielectric-missing'):
            with self.subTest(fault=fault):
                self.write_fixture(fault)
                physical.check_execution(self.folder, self.native, self.context, fault)
                (self.folder / 'lvs-extraction/injected.tcl').write_text('quit\n')
                with self.assertRaisesRegex(ValueError, 'script coverage'):
                    physical.check_execution(self.folder, self.native, self.context, fault)

    def test_netgen_actual_inputs_and_setup_are_bound(self):
        path = self.folder / 'lvs/console.log'; original = path.read_text()
        for before in ('schematic-lvs.spice', 'extracted.spice', self.context['setup']):
            with self.subTest(before=before):
                path.write_text(original.replace(before, '/unbound/wrong-input'))
                with self.assertRaisesRegex(ValueError, 'Netgen'):
                    physical.check_execution(self.folder, self.native, self.context)
        path.write_text(original)

    def test_receipts_and_saved_pdk_must_match_captured_identity(self):
        for stage in range(2):
            for key in ('assets', 'tools'):
                changed = copy.deepcopy(self.native); changed['stages'][stage]['evidence'][key] = {}
                with self.assertRaisesRegex(ValueError, 'asset/tool receipt'):
                    physical.check_execution(self.folder, changed, self.context)
        saved = json.loads((self.folder / 'input.icproj').read_text()); saved['pdk']['package_root'] = '/unbound/pdk'
        self.save(self.folder / 'input.icproj', saved)
        with self.assertRaisesRegex(ValueError, 'Saved native PDK'):
            physical.check_execution(self.folder, self.native, self.context)

    def test_public_release_projection_is_replay_safe_and_locked(self):
        self.assertEqual(self.context['origin'], '/original/evidence/physical/1')
        self.assertFalse(Path(self.pdk['package_root']).exists())
        for relative in ('UPSTREAM-LOCK.json', 'libs.tech/magic/sky130A.tech', 'libs.tech/magic/sky130A.tcl'):
            with self.subTest(relative=relative):
                changed = copy.deepcopy(self.pdk); changed['package_lock']['files'][relative] = '0' * 64
                self.save(self.root / 'physical/1/input.icproj', dict(pdk=changed))
                with self.assertRaises(ValueError): physical.execution_context(self.folder.parent, 1)


class MiMPassiveManifestAudit(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        (self.root / 'evidence').mkdir()
        (self.root / 'evidence/probe.raw').write_bytes(b'retained native output')
        # A nested file named manifest.json is ordinary evidence, not the root receipt.
        (self.root / 'evidence/manifest.json').write_text('{"asset":"original"}')
        self.inventory = {p.relative_to(self.root).as_posix(): audit.sha(p) for p in self.root.rglob('*') if p.is_file()}
        self.save(self.inventory)

    def save(self, value):
        (self.root / 'manifest.json').write_text(json.dumps(value))

    def test_complete_manifest_includes_nested_manifests(self):
        self.assertEqual(audit.verify_manifest(self.root), self.inventory)

    def test_empty_omitted_added_and_changed_hash_bindings_are_rejected(self):
        omitted = dict(self.inventory); omitted.pop('evidence/manifest.json')
        added = dict(self.inventory); added['unrecorded.raw'] = '0' * 64
        wrong_hash = dict(self.inventory); wrong_hash['evidence/probe.raw'] = '0' * 64
        for value in ({}, omitted, added, wrong_hash):
            with self.subTest(value=value):
                self.save(value)
                with self.assertRaises(ValueError): audit.verify_manifest(self.root)

    def test_changed_file_without_receipt_update_is_rejected(self):
        (self.root / 'evidence/probe.raw').write_bytes(b'changed native output')
        with self.assertRaises(ValueError): audit.verify_manifest(self.root)


if __name__ == '__main__':
    unittest.main()
