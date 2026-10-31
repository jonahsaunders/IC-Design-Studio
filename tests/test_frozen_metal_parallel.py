"""Fail-closed structural tests for the additive installed-array checker."""
from pathlib import Path
import copy
import tempfile
import unittest
from unittest.mock import patch
from scripts import verify_frozen_metal_parallel as check


def native(model='l1',count=3,top='actual_nonce_top'):
    return f'.subckt {top} R1 R2\n'+''.join(
        f'R{i} R1 R2 sky130_fd_pr__res_generic_{model} w=2 l=5\n' for i in range(count))+f'.ends {top}\n'


class FrozenParallelTests(unittest.TestCase):
    def test_actual_current_probe_and_reader_bind_same_exact_contract(self):
        from icstudio import metal_resistor_parallel_desktop_probe as producer
        from scripts import sky130_contract_versions as versions
        package=check.ROOT/'icstudio/assets/pdks/sky130A/package.json'
        actual=check.sha(package)
        selected=versions.selected('installed_parallel',package_sha256=actual)
        self.assertEqual(producer.acceptance_contract(actual),check.sha(check.ROOT/selected['path']))
        self.assertEqual(producer.acceptance_contract(actual),check.inputs.CONTRACT_SHA)
        self.assertNotEqual(producer.HISTORICAL_CONTRACT_SHA,check.inputs.CONTRACT_SHA)
        for wrong in ('840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe','0'*64):
            with self.assertRaisesRegex(ValueError,'Unreviewed parallel acceptance package'):
                producer.acceptance_contract(wrong)

    def test_retained_package_contract_pairs_match_independent_contract_documents(self):
        from icstudio import metal_resistor_parallel_desktop_probe as producer
        from scripts import sky130_contract_versions as versions
        for package,contract in ((producer.CURRENT_PACKAGE_SHA,producer.CONTRACT_SHA),
                                 (producer.PW2DN_PACKAGE_SHA,producer.PW2DN_CONTRACT_SHA)):
            selected=versions.package_version('installed_parallel',package)
            self.assertEqual(selected['sha256'],contract)
            self.assertEqual(check.sha(check.ROOT/selected['path']),contract)
            self.assertEqual(producer.acceptance_contract(package),contract)
            self.assertEqual(producer.acceptance_contract(package,contract),contract)

    def test_crossed_unknown_and_original_historical_pairs_reject(self):
        from icstudio import metal_resistor_parallel_desktop_probe as producer
        for package,wrong in ((producer.CURRENT_PACKAGE_SHA,producer.PW2DN_CONTRACT_SHA),
                              (producer.PW2DN_PACKAGE_SHA,producer.CONTRACT_SHA),
                              (producer.PW2DN_PACKAGE_SHA,producer.HISTORICAL_CONTRACT_SHA),
                              (producer.PW2DN_PACKAGE_SHA,'0'*64)):
            with self.assertRaisesRegex(ValueError,'package/contract pair differs'):
                producer.acceptance_contract(package,wrong)
        for package in ('0'*64,'840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'):
            with self.assertRaisesRegex(ValueError,'Unreviewed parallel acceptance package'):
                producer.acceptance_contract(package)

    def test_reader_rejects_stale_probe_contract_before_lifecycle_audit(self):
        import json
        from icstudio import metal_resistor_parallel_desktop_probe as producer
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'files.json').write_text(json.dumps({}))
            package=check.ROOT/'icstudio/assets/pdks/sky130A/package.json'
            report=dict(acceptance_contract_sha256=producer.acceptance_contract(check.sha(package)),
                input_guards=dict(bundled_package_unchanged=True,registry_assets_unchanged=True,
                    executable_unchanged=True,physical_package_unchanged=True),
                files_sha256=check.sha(root/'files.json'))
            with patch.object(check,'lifecycle') as life,patch.object(check,'eco_lifecycle') as eco:
                check.envelope(root,report,{})
                life.assert_called_once();eco.assert_called_once()
                for wrong in (producer.HISTORICAL_CONTRACT_SHA,'0'*64,None):
                    bad=copy.deepcopy(report);bad['acceptance_contract_sha256']=wrong
                    with self.assertRaisesRegex(ValueError,'Missing exact installed-array contract'):
                        check.envelope(root,bad,{})
                self.assertEqual(life.call_count,1);self.assertEqual(eco.call_count,1)

    def test_raw_gui_numeric_strings_are_validated_before_literal_geometry_adapter(self):
        binding=dict(model='sky130_fd_pr__res_generic_m1',prefix='R',emit_parameters=dict(w='w',l='l',m='mult'),
            parameter_scale=dict(w=1e6,l=1e6),pin_order=['m','p'])
        key='sky130_fd_pr/res_generic_m1.sym';catalog={key:binding}
        package=dict(id='sky130A',revision='fixture',files={},technology=dict(simulation=dict(catalog=catalog)))
        project=dict(top='cell',cells=[dict(id='cell',name='nonce_top',ports=['R1','R2'],devices=[dict(kind='PDK',
            model_ref=dict(pdk='sky130A',revision='fixture',device=key),nets=dict(m='R1',p='R2'),
            model_params=dict(w='2',l='5',mult='3'))],shapes=[dict(id='retained-original-shape')])],
            pdk=dict(package_lock=dict(id='sky130A',revision='fixture',files={},manifest_hash=check.digest(package)),
            simulation=dict(catalog=catalog)))
        item=dict(model='m1',multiplicity=3,rotation=0,top='nonce_top');original=copy.deepcopy(project)
        with patch.object(check.source,'editor_project') as literal:
            check.editor_binding(project,item,package)
            adapted=literal.call_args.args[0]
            self.assertEqual(adapted['cells'][0]['devices'][0]['model_params'],dict(w=2,l=5,mult=3))
            self.assertEqual(adapted['cells'][0]['shapes'],original['cells'][0]['shapes'])
            self.assertEqual(project,original)
            for value in ('nan','2+1','4'):
                wrong=copy.deepcopy(original);wrong['cells'][0]['devices'][0]['model_params']['mult']=value
                with self.assertRaises(ValueError):check.editor_binding(wrong,item,package)
            self.assertEqual(literal.call_count,1)

    def test_exact_thirty_case_nonce_and_top_selection(self):
        self.assertEqual(len(check.CASES),30);self.assertEqual(len(set(check.CASES)),30)
        nonce='ab'*16
        for name in check.CASES:
            row=check.case_identity(name,nonce)
            self.assertEqual(row['top'],f'metal_parallel_{row["model"]}_m{row["multiplicity"]}_r{row["rotation"]}_{nonce[:12]}')
        for case,token in (('l1-m1-r0',nonce),('m1-m2-r180',nonce),('m1-m2-r0','A'*32)):
            with self.assertRaises(ValueError):check.case_identity(case,token)

    def test_actual_arrays_require_all_unmerged_units_and_selected_model(self):
        for model in check.MODELS:
            for count in check.COUNTS:
                rows=check.circuit(native(model,count),'actual_nonce_top',model,count,extracted=True)
                self.assertEqual(len(rows),count)
                application=f'.subckt actual_nonce_top R1 R2\nR_RES R1 R2 sky130_fd_pr__res_generic_{model} l=5 m={count} w=2\n.ends actual_nonce_top\n'
                self.assertEqual(len(check.circuit(application,'actual_nonce_top',model,count)),1)
                with self.assertRaises(ValueError):check.circuit(application,'actual_nonce_top',model,count,extracted=True)

    def test_missing_duplicate_substituted_short_and_nonfinite_native_evidence_rejects(self):
        good=native()
        for changed in (native(count=2),good.replace('R2 R1 R2','r0 R1 R2'),good.replace('res_generic_l1','res_generic_m1',1),
            good.replace('R1 R2 sky130','R1 R1 sky130',1),good.replace('w=2','w=3',1),good.replace('l=5','l=nan',1),
            good.replace('l=5','l=5 m=3',1),good.replace('l=5','l=5 w=2',1),good+'.include substitute.spice\n',
            good.replace('.ends actual_nonce_top','.ends stale_top')):
            with self.subTest(text=changed),self.assertRaises(ValueError):check.circuit(changed,'actual_nonce_top','l1',3,extracted=True)

    def test_width_fault_requires_only_one_changed_physical_unit(self):
        good=native().replace('w=2','w=3',1)
        check.circuit(good,'actual_nonce_top','l1',3,extracted=True,width_fault=True)
        for changed in (native(),good.replace('w=2','w=3',1),good.replace('l=5','l=6',1)):
            with self.assertRaises(ValueError):check.circuit(changed,'actual_nonce_top','l1',3,extracted=True,width_fault=True)

    def test_source_or_stale_binary_cannot_pass_installed_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable=Path(tmp)/'studio';executable.write_bytes(b'fixture')
            base=dict(schema=1,status='passed',mode='physical',frozen=True,native_execution=True,
                build=dict(commit='a'*40,dirty=False,frozen=True),execution_id='b'*32,executable=str(executable),
                executable_sha256=check.sha(executable),qualified=False,release_ready=False,full_family=False,installed_acceptance=False)
            check.header(base,executable,'a'*40,'b'*32)
            for field,value in (('frozen',False),('execution_id','c'*32),('native_execution',False),('executable_sha256','0'*64),('installed_acceptance',True)):
                with self.subTest(field=field),self.assertRaises(ValueError):check.header({**base,field:value},executable,'a'*40,'b'*32)


if __name__=='__main__':unittest.main()
