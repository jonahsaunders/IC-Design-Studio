"""Meaningful fail-closed tests of the separate installed resistor checker."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_frozen_metal_resistors as check


class FrozenMetalResistorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.exe = self.root/'Installed App/ICDesignStudio.exe'
        self.exe.parent.mkdir(); self.exe.write_bytes(b'actual fixture executable')
        self.commit = 'c'*40; self.nonce = 'a'*32
        self.item = check.case_identity('m1-g1-r0', self.nonce)
        self.header = dict(schema=1, status='passed', mode='physical', frozen=True, native_execution=True,
            build=dict(commit=self.commit, dirty=False, frozen=True), execution_id=self.nonce,
            executable=str(self.exe), executable_sha256=check.sha(self.exe), qualified=False,
            release_ready=False, full_family=False, installed_acceptance=False)

    def put(self, name, text):
        path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        return path

    def deck(self, parameters='w=2 l=5 m=1', *, model='m1', terminals='R1 R2'):
        return f'* reference\n.subckt {self.item["top"]} R1 R2\nR_R1 {terminals} sky130_fd_pr__res_generic_{model} {parameters}\n.ends\n'

    def test_exact_thirty_case_identity_and_candidate_header(self):
        self.assertEqual(len(check.CASES), 30)
        self.assertEqual(len({check.case_identity(c, self.nonce)['top'] for c in check.CASES}), 30)
        self.assertEqual(sum(not c.startswith('l1-') for c in check.CASES), 24)
        check.header(self.header, self.exe, self.commit, self.nonce)
        for case in ('m5-g0-r0', 'm1-g3-r0', 'm1-g1-r180', 'm1-g1-r0-extra'):
            with self.subTest(case=case), self.assertRaises(ValueError): check.case_identity(case, self.nonce)

    def test_source_partial_dirty_stale_wrong_build_and_overclaims_rejected(self):
        mutations = [dict(frozen=False), dict(mode='lifecycle'), dict(native_execution=False), dict(status='failed'),
            dict(execution_id='b'*32), dict(full_family=True), dict(installed_acceptance=True), dict(qualified=True),
            dict(release_ready=True), dict(errors=['worker error']), dict(build=dict(commit='d'*40, dirty=False, frozen=True)),
            dict(build=dict(commit=self.commit, dirty=True, frozen=True)), dict(build=dict(commit=self.commit, dirty=False, frozen=False))]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(ValueError):
                check.header({**self.header, **change}, self.exe, self.commit, self.nonce)
        self.exe.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'executable'): check.header(self.header, self.exe, self.commit, self.nonce)

    def test_actual_application_and_extracted_primitive_contract(self):
        check.circuit(self.deck(), self.item['top'], 'm1', 2, 5)
        check.circuit(self.deck('w=2 l=5', terminals='R2 R1'), self.item['top'], 'm1', 2, 5, extracted=True)
        check.circuit(self.deck('w=2 l=5 m=3'), self.item['top'], 'm1', 2, 5, count=3)

    def test_rehashed_model_dimensions_multiplicity_terminals_and_directives_rejected(self):
        controls = [self.deck(model='m2'), self.deck('w=5 l=2 m=1'), self.deck('w=2 l=5 m=3'),
            self.deck('w=2 l=5'), self.deck('w=2 l=5 m=1 w=2'), self.deck('w=nan l=5 m=1'),
            self.deck(terminals='R2 R1'), self.deck(terminals='R1 R1'), self.deck().replace('.ends', '.include old.spice\n.ends'),
            self.deck().replace('.ends', 'R2 R1 R2 1\n.ends'), self.deck().replace(self.item['top'], 'old_top')]
        for text in controls:
            with self.subTest(text=text), self.assertRaises(ValueError): check.circuit(text, self.item['top'], 'm1', 2, 5)
        with self.assertRaises(ValueError): check.circuit(self.deck(), self.item['top'], 'm1', 2, 5, extracted=True)

    def test_incomplete_reordered_duplicated_and_cross_case_lifecycle_rejected(self):
        for names in ([], check.CASES[:-1], check.CASES[::-1], (*check.CASES, check.CASES[0])):
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, 'layout cases'):
                check.lifecycle(self.root, {'lifecycle': [dict(case=c) for c in names]}, {}, {})
        rows = [check.case_identity(c, self.nonce) for c in check.CASES]
        rows[0]['top'] = rows[1]['top']
        with self.assertRaisesRegex(ValueError, 'case identity'):
            check.lifecycle(self.root, dict(lifecycle=rows, execution_id=self.nonce), {}, {})

    def fixture(self, fault=None):
        drc = fault == 'drc'; width = fault == 'width'
        files = {'drc/console.log': f'STUDIO_DRC_COUNT {int(drc)}\nSTUDIO_DRC_STYLE drc(full)\nSTUDIO_MAGIC_COMPLETE\n',
            'drc/findings.tsv': 'metal width\t0,0,1,1\n' if drc else '',
            'lvs-extraction/console.log': 'STUDIO_MAGIC_COMPLETE\n',
            'lvs-extraction/extracted.spice': self.deck('w=2.4 l=5' if width else 'w=2 l=5'),
            'lvs/lvs.log': ('Property errors were found.\n w circuit1: 2 circuit2: 2.4\nCell pin lists are equivalent.\n' if width else
                           'Final result: Circuits match uniquely.\nCell pin lists are equivalent.\n'),
            'layout.gds': 'native fixture', 'input.icproj': '{}', 'schematic.spice': self.deck(), 'schematic-lvs.spice': self.deck()}
        for name, text in files.items(): self.put(name, text)
        stages = [dict(name=name, status='failed' if (name == 'drc' and drc) or (name == 'lvs' and width) else 'passed', evidence={})
                  for name in check.STAGES]
        stages[3]['evidence'] = dict(deck='lvs-extraction/extracted.spice', sha256=check.sha(self.root/'lvs-extraction/extracted.spice'),
                                     settings=copy.deepcopy(check.EXTRACTION_SETTINGS))
        if width:
            stages[4] = dict(name='lvs',status='failed',error='Netgen did not establish a unique match with equivalent connected pins and no property errors. See lvs/lvs.log.')
        else: stages[4]['evidence'] = dict(unique_match=True, log='lvs/lvs.log')
        stages[5]['evidence'] = dict(verified=True, files={name: check.sha(self.root/name) for name in files})
        return dict(stages=stages, status='failed' if fault else 'passed', drc_engine='magic', lvs_extractor='magic',
                    magic_drc_style='drc(full)', drc_count=int(drc), magic_drc_count=int(drc))

    def rehash(self, native):
        native['stages'][3]['evidence']['sha256'] = check.sha(self.root/'lvs-extraction/extracted.spice')
        records = native['stages'][5]['evidence']['files']
        for name in records: records[name] = check.sha(self.root/name)

    def test_positive_native_drc_lvs_and_both_actual_fault_outcomes(self):
        for fault in (None, 'width', 'drc'):
            with self.subTest(fault=fault): check.native_output(self.root, self.fixture(fault), self.item, fault)

    def test_rehashed_raw_corruption_rejected_after_integrity_repair(self):
        for fault in ('drc-count', 'drc-style', 'duplicate-completion', 'findings', 'model', 'width', 'lvs-property',
                      'lvs-pins', 'blackbox', 'integrity-omission', 'stage-omission'):
            native = self.fixture()
            if fault == 'drc-count': self.put('drc/console.log', 'STUDIO_DRC_COUNT 1\nSTUDIO_DRC_STYLE drc(full)\nSTUDIO_MAGIC_COMPLETE\n')
            elif fault == 'drc-style': self.put('drc/console.log', 'STUDIO_DRC_COUNT 0\nSTUDIO_DRC_STYLE fast\nSTUDIO_MAGIC_COMPLETE\n')
            elif fault == 'duplicate-completion': self.put('lvs-extraction/console.log', 'STUDIO_MAGIC_COMPLETE\nSTUDIO_MAGIC_COMPLETE\n')
            elif fault == 'findings': self.put('drc/findings.tsv', 'unreported\t0,0,1,1\n')
            elif fault == 'model': self.put('lvs-extraction/extracted.spice', self.deck('w=2 l=5', model='m2'))
            elif fault == 'width': self.put('lvs-extraction/extracted.spice', self.deck('w=2.4 l=5'))
            elif fault == 'lvs-property': self.put('lvs/lvs.log', 'Final result: Circuits match uniquely.\nCell pin lists are equivalent.\nProperty errors were found.\n')
            elif fault == 'lvs-pins': self.put('lvs/lvs.log', 'Final result: Circuits match uniquely.\n')
            elif fault == 'blackbox': native['stages'][3]['evidence']['settings']['blackbox'] = True
            elif fault == 'integrity-omission': native['stages'][5]['evidence']['files'].pop('input.icproj')
            self.rehash(native)
            if fault == 'stage-omission': native['stages'].pop()
            with self.subTest(fault=fault), self.assertRaises(ValueError): check.native_output(self.root, native, self.item)

    def test_failed_engine_does_not_count_as_width_fault(self):
        native = self.fixture('width')
        for text in ('cannot open setup file\nProperty errors were found.\n w circuit1: 2\nCell pin lists are equivalent.\n',
                     'Property errors were found.\n l circuit1: 5\nCell pin lists are equivalent.\n',
                     'Final result: Circuits match uniquely.\nCell pin lists are equivalent.\n'):
            self.put('lvs/lvs.log', text); self.rehash(native)
            with self.subTest(text=text), self.assertRaises(ValueError): check.native_output(self.root, native, self.item, 'width')

    def test_native_script_control_detects_disabled_drc_blackbox_wrong_top_and_tech(self):
        from scripts.audit_sky130_li_case import native_script, tcl_literal
        from pathlib import PurePosixPath
        origin = PurePosixPath('/native/case'); pdk = PurePosixPath('/native/pdk')
        expected = {}
        for stage in ('drc', 'lvs-extraction'):
            expected[stage+'/run.tcl'] = native_script(origin, stage).replace('load "coupon"', 'load "'+self.item['top']+'"')
            expected[stage+'/startup.tcl'] = 'tech load '+tcl_literal(pdk/'libs.tech/magic/sky130A.tech')+'\ndrc euclidean on\n'
        for name, text in expected.items(): self.put(name, text)
        check.native_scripts(self.root, str(origin), str(pdk), self.item['top'])
        for name, old, new in [('drc/run.tcl', 'drc ignore none', 'drc ignore all'),
                              ('lvs-extraction/run.tcl', 'blackbox off', 'blackbox on'),
                              ('drc/run.tcl', self.item['top'], 'old_top'),
                              ('drc/startup.tcl', 'sky130A.tech', 'other.tech')]:
            self.put(name, expected[name].replace(old, new))
            with self.subTest(name=name, new=new), self.assertRaises(ValueError):
                check.native_scripts(self.root, str(origin), str(pdk), self.item['top'])
            self.put(name, expected[name])

    def edit_fixture(self):
        original = dict(revision=1, modified='before', pdk=dict(layers=[dict(name='metal1', gds=68, datatype=20)]),
            cells=[dict(shapes=[dict(id='a', layer='metal1', kind='rect', points=[[0,-500],[2000,5500]]),
                               dict(id='b', layer='res', kind='polygon', points=[[0,0],[2000,0],[2000,5000],[0,5000]])])])
        changed = copy.deepcopy(original); changed.update(revision=3, modified='after'); edits = []
        for before, after in zip(original['cells'][0]['shapes'], changed['cells'][0]['shapes']):
            after['points'] = [[x+400 if x == 2000 else x, y] for x,y in before['points']]
            edits.append(dict(shape=before['id'], layer=before['layer'], before_points=before['points'], after_points=after['points']))
        return original, changed, dict(edits=edits)

    def test_width_control_proves_only_the_intended_edit_and_repair_content(self):
        original, changed, control = self.edit_fixture(); check.control_edit(original, changed, control, True)
        changed['cells'][0]['labels'] = []
        check.control_edit(original, changed, control, True)
        changed['cells'][0]['labels'] = ['unexpected']
        with self.assertRaises(ValueError): check.control_edit(original, changed, control, True)
        changed['cells'][0].pop('labels')
        for mutation in ('unrelated', 'missing', 'wrong-edge', 'false-before'):
            value = copy.deepcopy(changed); receipt = copy.deepcopy(control)
            if mutation == 'unrelated': value['cells'][0]['name'] = 'other'
            elif mutation == 'missing': receipt['edits'].pop()
            elif mutation == 'wrong-edge': receipt['edits'][0]['after_points'][0][0] += 400
            else: receipt['edits'][0]['before_points'][0][1] += 5
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): check.control_edit(original, value, receipt, True)
        repaired = copy.deepcopy(original); repaired.update(revision=5, modified='repaired')
        self.assertEqual(check.content_hash(original), check.content_hash(repaired))
        self.assertNotEqual(check.design_hash(original), check.design_hash(repaired))

    def test_missing_control_coverage_and_source_mode_cannot_pass_installed(self):
        with self.assertRaisesRegex(ValueError, 'controls'):
            check.controls(self.root, dict(controls=[]), {}, {}, {}, [])
        self.put('report.json', json.dumps({**self.header, 'frozen':False}))
        with self.assertRaisesRegex(ValueError, 'source-only'):
            check.audit(self.root, self.exe, self.root, self.commit, self.nonce, {}, {}, '0'*64)

    def test_checker_sources_are_exact_candidate_bytes(self):
        with patch.object(check, 'git_blob', side_effect=lambda commit, name: (check.ROOT/name).read_bytes()):
            self.assertEqual(len(check.checker_sources(self.commit)), 3)
        with patch.object(check, 'git_blob', return_value=b'stale checker'):
            with self.assertRaisesRegex(ValueError, 'checker differs'): check.checker_sources(self.commit)

    def test_saved_project_model_lock_parameters_and_pin_mapping(self):
        lock = check.load(check.ROOT/'icstudio/assets/pdks/sky130A/package.json')
        key = 'sky130_fd_pr/res_generic_m1.sym'
        project = dict(top='cell', pdk=copy.deepcopy(lock['technology']), cells=[dict(id='cell', name=self.item['top'],
            ports=['R1','R2'], devices=[dict(kind='PDK', model_ref=dict(pdk='sky130A', revision=lock['revision'], device=key),
            nets=dict(m='R1',p='R2'), model_params=dict(w=2,l=5,mult=1))])])
        project['pdk']['package_lock'] = {**{k:lock[k] for k in ('id','revision','files')}, 'manifest_hash':check.digest(lock)}
        check.project_binding(project,'m1',2,5,1,lock,self.item['top'])
        for fault in ('lock','terminal','model','width','scale'):
            value=copy.deepcopy(project); device=value['cells'][0]['devices'][0]
            if fault=='lock': value['pdk']['package_lock']['revision']='other'
            elif fault=='terminal': device['nets']=dict(m='R2',p='R1')
            elif fault=='model': device['model_ref']['device']='sky130_fd_pr/res_generic_m2.sym'
            elif fault=='width': device['model_params']['w']=2.4
            else: value['pdk']['simulation']['catalog'][key]['parameter_scale']['w']=1
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                check.project_binding(value,'m1',2,5,1,lock,self.item['top'])

    def launcher_fixture(self):
        payload = self.exe.parent/'_internal/icstudio/assets/runtime/digital'; payload.mkdir(parents=True)
        (payload/'runtime.tar.gz').write_bytes(b'fixture runtime')
        (payload/'manifest.json').write_text(json.dumps(dict(schema=1, archive='runtime.tar.gz', sha256=check.sha(payload/'runtime.tar.gz'))))
        collection = self.exe.parent/'_internal/icstudio/assets/pdks/collection.json'; collection.parent.mkdir(parents=True)
        collection.write_text('{}')
        return dict(package_sha256='a'*64, physical_sha256='b'*64, collection_sha256=check.sha(collection))

    def test_launch_actual_frozen_exe_nonce_managed_and_no_source_injections(self):
        inputs = self.launcher_fixture(); out = self.root/'fresh'
        def run(command, **kwargs):
            self.assertEqual(command[:2], [str(self.exe), '--metal-resistor-acceptance'])
            self.assertIn('--managed', command); self.assertEqual(command[command.index('--mode')+1], 'physical')
            self.assertRegex(command[command.index('--execution-id')+1], '^[0-9a-f]{32}$')
            self.assertFalse(any(k.upper().startswith('GIT_') or k.upper() in ('PYTHONPATH','LD_PRELOAD') for k in kwargs['env']))
            self.assertEqual(kwargs['env']['ICSTUDIO_DIGITAL_STATE'], 'selected-state'); self.assertEqual(kwargs['cwd'], out)
            return subprocess.CompletedProcess(command, 0)
        with patch.object(check, 'expected_inputs', return_value=inputs), patch.object(check, 'package'), \
             patch.object(check, 'backend_binding', return_value={'backend.py':'a'*64}), \
             patch.object(check, 'audit', return_value=dict(status='PASS', full_family=False)), \
             patch.object(check.subprocess, 'run', side_effect=run), \
             patch.dict(os.environ, dict(PYTHONPATH='other', LD_PRELOAD='other', GIT_DIR='other', ICSTUDIO_DIGITAL_STATE='selected-state')):
            self.assertEqual(check.verify(self.exe, self.root/'pdk', out, self.commit)['status'], 'PASS')

    def test_existing_output_invalid_candidate_and_timeout_never_launch(self):
        out = self.root/'used'; out.mkdir()
        with patch.object(check.subprocess, 'run') as run:
            for candidate, timeout, output in ((self.commit, 30, out), ('main', 30, self.root/'new'), (self.commit,float('nan'),self.root/'new')):
                with self.assertRaises(ValueError): check.verify(self.exe, self.root/'pdk', output, candidate, timeout)
            run.assert_not_called()

    def test_successful_process_does_not_hide_executable_drift(self):
        inputs = self.launcher_fixture(); out = self.root/'drift'
        def run(command, **kwargs): self.exe.write_bytes(b'changed'); return subprocess.CompletedProcess(command, 0)
        with patch.object(check, 'expected_inputs', return_value=inputs), patch.object(check, 'package'), \
             patch.object(check, 'backend_binding', return_value={}), patch.object(check.subprocess, 'run', side_effect=run):
            with self.assertRaisesRegex(ValueError, 'changed during'): check.verify(self.exe, self.root/'pdk', out, self.commit)
        self.assertEqual(check.load(out/'verification.json')['status'], 'FAIL')


try:
    HAS_KLAYOUT = importlib.util.find_spec('klayout.db') is not None
except ModuleNotFoundError:
    HAS_KLAYOUT = False


@unittest.skipUnless(HAS_KLAYOUT, 'Geometry readback requires the full lane KLayout dependency.')
class GeometryTests(unittest.TestCase):
    def test_marker_landings_dimensions_ports_and_wrong_model(self):
        import klayout.db as db
        item = check.case_identity('m1-g1-r0', 'a'*32)
        good = ({(68,20):db.Region(db.Box(0,-500,2000,5500)), (68,13):db.Region(db.Box(0,0,2000,5000))},
                [((68,5),'R1',1000,-250), ((68,5),'R2',1000,5250)])
        check.resistor_geometry(good,item)
        for fault in ('width','bypass','port','model','marker-hole'):
            masks={k:v.dup() for k,v in good[0].items()}; labels=list(good[1]); altered=dict(item)
            if fault=='width': masks[68,13]=db.Region(db.Box(0,0,2400,5000))
            elif fault=='bypass': masks[68,20].insert(db.Box(1990,-500,2200,5500)); masks[68,20].merge()
            elif fault=='port': labels[0]=((68,5),'R1',1000,1000)
            elif fault=='model': altered['model']='m2'
            else: masks[68,13]-=db.Region(db.Box(500,1000,1000,2000))
            with self.subTest(fault=fault),self.assertRaises(ValueError): check.resistor_geometry((masks,labels),altered)


if __name__ == '__main__': unittest.main()
