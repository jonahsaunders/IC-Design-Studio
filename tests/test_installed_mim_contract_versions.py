"""MiM installed source selectors preserve historical contracts and scope."""
import json,shutil,sys,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from scripts import installed_mim_inputs as inputs
from scripts import qualify_installed_sky130_mim_electrical as producer
from scripts import audit_installed_sky130_mim_electrical as auditor
from scripts.prepare_sky130_esd_nvt import predecessor

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'icstudio/assets/pdks/sky130A'
def binding(path,sha):return {'mode':'source-pilot','resource_root':str(ROOT),'simulation_package':{'path':str(path),'manifest_sha256':sha}}
class MiMContractVersionTests(unittest.TestCase):
    def test_exact_current_and_historical_package_mapping(self):
        current=binding(PACKAGE,inputs.CURRENT_PACKAGE)
        contract,mapped=inputs.contracts(current)
        self.assertEqual(contract['id'],'sky130-mim-contract-v2')
        self.assertEqual(contract['sources']['package']['sha256'],inputs.CURRENT_PACKAGE)
        self.assertEqual(mapped['package']['sha256'],inputs.CURRENT_PACKAGE)
        self.assertIn(inputs.CURRENT_CONTRACT_PATH,inputs.source_files(current))
        self.assertIn(inputs.CURRENT_MAP_PATH,inputs.source_files(current))
        with predecessor(PACKAGE) as old:
            prior=binding(old,inputs.PREVIOUS_PACKAGE);historical,old_mapped=inputs.contracts(prior)
            self.assertEqual(historical['id'],'sky130-mim-contract-v1')
            self.assertEqual(old_mapped['package']['sha256'],inputs.PREVIOUS_PACKAGE)
            self.assertNotIn(inputs.CURRENT_CONTRACT_PATH,inputs.source_files(prior))
        for key in ('catalog_entries','next_acceptance','passive_sections'):
            self.assertEqual(contract[key],historical[key],key)
        for name in ('model_1','model_2','symbol_1','symbol_2','models_license','symbols_license'):
            self.assertEqual(mapped[name]['sha256'],old_mapped[name]['sha256'],name)

    def test_unknown_and_spoofed_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside the reviewed'):
            inputs.contracts(binding(PACKAGE,'0'*64))
        with self.assertRaises(ValueError):
            inputs.contracts(binding(PACKAGE,inputs.PREVIOUS_PACKAGE))

    def test_installed_resource_mapping_checks_current_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            resource=Path(tmp)
            for rel in ('docs/qualification/sky130-mos-bias-sources-v1/device-details.rst','docs/qualification/sky130-mim-sources-v1/LICENSE'):
                dest=resource/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dest)
            adapter=resource/'icstudio/assets/runtime/digital/backend/icstudio/sky130_mim2_extract.py'
            adapter.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'icstudio/sky130_mim2_extract.py',adapter)
            selected=binding(PACKAGE,inputs.CURRENT_PACKAGE);selected.update(mode='installed',resource_root=str(resource))
            contract,mapped=inputs.contracts(selected)
            self.assertEqual(contract['sources']['package']['sha256'],inputs.CURRENT_PACKAGE)
            self.assertEqual(Path(mapped['orientation_adapter']['path']),adapter.resolve())
            self.assertEqual(mapped['orientation_adapter']['sha256'],inputs.sha(adapter))

    def test_crossed_or_rehashed_scientific_contract_rejected(self):
        current=binding(PACKAGE,inputs.CURRENT_PACKAGE)
        with patch.object(inputs,'CURRENT_MAP_PATH',inputs.MAP_PATH),patch.object(inputs,'CURRENT_MAP_SHA',inputs.MAP_SHA):
            with self.assertRaises(ValueError):inputs.contracts(current)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'docs/qualification';folder.mkdir(parents=True)
            for name in (inputs.CONTRACT_PATH,inputs.MAP_PATH,inputs.CURRENT_CONTRACT_PATH,inputs.CURRENT_MAP_PATH):
                shutil.copyfile(ROOT/name,root/name)
            contract_path=root/inputs.CURRENT_CONTRACT_PATH;contract=json.loads(contract_path.read_bytes())
            contract['next_acceptance']['tampered_test_condition']=True
            contract_path.write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
            changed_sha=inputs.sha(contract_path)
            map_path=root/inputs.CURRENT_MAP_PATH;mapping=json.loads(map_path.read_bytes())
            mapping['immutable_contract']['sha256']=changed_sha;map_path.write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8')
            with patch.object(inputs,'ROOT',root),patch.object(inputs,'CURRENT_CONTRACT_SHA',changed_sha),patch.object(inputs,'CURRENT_MAP_SHA',inputs.sha(map_path)):
                with self.assertRaisesRegex(ValueError,'scientific contract'):
                    inputs.contracts(current)

    def test_changed_mapped_asset_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed=Path(tmp)/'package';shutil.copytree(PACKAGE,changed)
            model=changed/'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__cap_mim_m3_1.model.spice'
            model.write_bytes(model.read_bytes()+b'\n')
            with self.assertRaises(ValueError):inputs.contracts(binding(changed,inputs.CURRENT_PACKAGE))

    def test_producer_and_auditor_use_selected_copies(self):
        current=binding(PACKAGE,inputs.CURRENT_PACKAGE)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run'
            with patch.object(inputs,'bind_gui',return_value=current),patch.object(inputs,'source_files',side_effect=RuntimeError('stop after contract copy')):
                report=producer.run('unused',out,source_pilot=True)
            self.assertEqual(report['status'],'FAIL')
            self.assertEqual(inputs.sha(out/'contract.json'),inputs.CURRENT_CONTRACT_SHA)
            self.assertEqual(inputs.sha(out/'bias-contract.json'),inputs.CURRENT_MAP_SHA)
            check={'contract_sha256':inputs.CURRENT_CONTRACT_SHA,'source_map_sha256':inputs.CURRENT_MAP_SHA}
            self.assertEqual(auditor.contract_receipt(out,current,check)['id'],'sky130-mim-contract-v2')
            shutil.copyfile(ROOT/inputs.MAP_PATH,out/'bias-contract.json')
            with self.assertRaisesRegex(ValueError,'Reviewed source contracts differ'):
                auditor.contract_receipt(out,current,check)

    def test_producer_completion_rechecks_same_selected_source_tuple(self):
        current=binding(PACKAGE,inputs.CURRENT_PACKAGE);current.update(cases={},execution_id='f'*32,expected_commit=None)
        def stage(tech,out):
            (out/'shared-models').mkdir();return {},{}
        def case(context,*args):return {'name':producer.case_name(*context),'status':'PASS'}
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            out=Path(tmp)/'run';source_spy=stack.enter_context(patch.object(inputs,'source_files',wraps=inputs.source_files))
            stack.enter_context(patch.object(inputs,'bind_gui',return_value=current))
            stack.enter_context(patch.object(inputs,'technology',return_value={'simulation':{'ngspice_compatibility':'hsa'},'package_root':str(PACKAGE)}))
            stack.enter_context(patch.object(inputs,'select_engine',return_value=Path(sys.executable)))
            stack.enter_context(patch.object(inputs,'native_environment',return_value={}))
            stack.enter_context(patch.object(inputs,'runtime',return_value={'test_runtime':'stable'}))
            stack.enter_context(patch.object(producer,'stage_models',side_effect=stage))
            stack.enter_context(patch.object(producer,'execute_case',side_effect=case))
            stack.enter_context(patch.object(auditor,'audit',return_value={'status':'MOCKED_TEST_ONLY'}))
            report=producer.run('unused',out,source_pilot=True,pilot=True)
            self.assertEqual(report['status'],'PASS')
            self.assertFalse(report['installed_electrical_acceptance'])
            self.assertEqual(source_spy.call_count,2)
            self.assertTrue(all(call.args==(current,) for call in source_spy.call_args_list))
            self.assertEqual(report['contract_sha256'],inputs.CURRENT_CONTRACT_SHA)
            self.assertEqual(report['source_map_sha256'],inputs.CURRENT_MAP_SHA)

if __name__=='__main__':unittest.main()
