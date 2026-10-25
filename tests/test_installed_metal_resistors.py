import json
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest.mock import patch
import uuid

from scripts import qualify_installed_sky130_metal_resistors as producer
from scripts import qualify_sky130_metal_resistors_linked as old


class InstalledMetalProducerTest(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((producer.ROOT/old.CONTRACT).read_bytes())
        self.rows=old.logical_rows(self.spec,True)
        self.normalized={producer.case_key(r):{k:{'normalized_path':str(Path('/evidence')/'normalized-inputs'/producer.case_key(r)/(k+'.spice'))}
            for k in ('application','native')} for r in self.rows}
        self.faults={key:{f:{'path':str(Path('/evidence')/'fault-inputs'/key/(f+'.spice'))}
            for f in self.spec['experiment']['faults']} for key in self.normalized}
        self.staged={s:'.lib models '+s for s in self.spec['experiment']['sections']}
        self.execution={'root':'/C:/evidence','nonce':'a'*32}

    def build(self,analysis='dc',control='positive'):
        case=next(c for c in old.selection(self.spec,True) if c['analysis']==analysis and c['control']==control)
        rows=old.branches(self.spec,self.rows,analysis,control)
        return producer.deck(self.spec,case,rows,self.staged,self.normalized,self.faults,self.execution,Path('/evidence')/case['name']),rows,case

    def test_positive_decks_include_actual_app_and_native_files(self):
        (text,section,temp),rows,case=self.build('ac')
        self.assertEqual((section,temp),('tt',27))
        self.assertEqual(text.splitlines()[0],old.title(self.execution,case['name']))
        for key in self.normalized:
            for kind in ('application','native'):
                self.assertIn('.include '+Path(self.normalized[key][kind]['normalized_path']).as_posix(),text)
        self.assertNotIn('sky130_fd_pr__res_generic_',text)
        self.assertNotIn(' m=',text)

    def test_multiplicity_three_uses_three_untouched_subcircuit_copies(self):
        (text,_,_),rows,_=self.build('ac')
        for row in rows:
            if row['kind']=='analytic':continue
            commands=[v for v in text.splitlines() if v.startswith('X_'+row['branch']+'_')]
            self.assertEqual(len(commands),row['multiplicity'])
            self.assertEqual(len({v.split()[-1] for v in commands}),1)

    def test_faults_use_separate_inputs_and_sense_sources_are_zero_ac(self):
        (text,_,_),rows,_=self.build()
        for row in rows:
            self.assertIn(f'VS_{row["branch"]} input in_{row["branch"]} DC 0 AC 0',text)
            if row['fault']:
                self.assertIn('.include '+Path(self.faults[producer.case_key(row)][row['fault']]['path']).as_posix(),text)

    def test_transient_stimulus_and_solver_match_fixed_contract(self):
        (text,_,_),_,_=self.build('tran')
        self.assertIn('chgtol=1e-24 trtol=1',text)
        values=text.split('PULSE(',1)[1].split(')',1)[0].split()
        self.assertEqual([float(v) for v in values],[.0001,.001,1e-9,1e-13,1e-13,5e-9,1e-8])
        self.assertIn('.tran 20p 21n',text)

    def test_context_controls_keep_intended_analytic_and_actual_parameter_probe(self):
        (text,section,temp),_,_=self.build(control='wrong-section')
        self.assertEqual(section,'ll');self.assertEqual(temp,27);self.assertIn('.lib models ll',text)
        self.assertIn('VP_rm1 par_rm1 0 DC {rm1} AC {rm1}',text)
        (text,section,temp),_,_=self.build(control='wrong-temperature')
        self.assertEqual((section,temp),('tt',44));self.assertIn('.temp 44',text)

    def test_noise_writes_are_absolute_and_per_branch(self):
        (text,_,_),rows,case=self.build('noise')
        for row in rows:
            target=(Path('/evidence')/case['name']/('noise_'+row['branch']+'.raw')).as_posix()
            self.assertIn('write '+target+' frequency noise_'+row['branch'],text)

    def test_windows_uri_context_is_posix_identity_only(self):
        class WindowsPath:
            def resolve(self):return self
            def as_uri(self):return PureWindowsPath('C:/evidence').as_uri()
        value=producer.execution_identity(WindowsPath(),'b'*32)
        self.assertEqual(value,dict(root='/C:/evidence',nonce='b'*32))
        from scripts.audit_sky130_metal_resistors_linked import context_title
        self.assertEqual(context_title(value,'case'),old.title(value,'case'))

    def test_whitespace_output_rejected_before_gui_or_native_access(self):
        out=Path(tempfile.gettempdir())/('icstudio-uncreated-'+uuid.uuid4().hex)/'not permitted'
        with patch.object(producer.inputs,'bind_gui') as gui,self.assertRaisesRegex(ValueError,'without whitespace'):
            producer.run(out.parent/'missing',out,source_pilot=True)
        gui.assert_not_called();self.assertFalse(out.parent.exists())

    def test_include_whitespace_rejected(self):
        self.normalized['m1-g1-r0']['application']['normalized_path']='/bad path/application.spice'
        with self.assertRaisesRegex(ValueError,'whitespace'):self.build('ac')

    def test_complete_and_pilot_selection_keep_original_counts(self):
        self.assertEqual(len(old.selection(self.spec)),90);self.assertEqual(len(old.selection(self.spec,True)),6)
        logical=old.logical_rows(self.spec)
        self.assertEqual(len(logical),48)
        self.assertEqual(len({producer.case_key(v) for v in logical}),24)


if __name__=='__main__':unittest.main()
