"""Actual-input, context and raw negative tests for installed parallel arrays."""
from pathlib import Path
import tempfile
import unittest
from scripts import installed_metal_parallel_inputs as inputs
from scripts import qualify_installed_metal_parallel as producer
from scripts import audit_installed_metal_parallel as audit
from tests.test_sky130_metal_resistor_parallel_audit import raw_fixture


class InstalledParallelAuditTests(unittest.TestCase):
    def test_all_sixty_decks_bind_original_paths_and_both_execution_nonces(self):
        _,spec,_=inputs.contracts();selected={'tt':'.lib pdk-models/exact.spice tt'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);execution={'root':'/portable/test','nonce':'a'*32};gui_nonce='b'*32
            for key in inputs.CASES:
                model,count,rotation=key.split('-');row=dict(model=model,multiplicity=int(count[1:]),rotation=int(rotation[1:]),width_um=2,length_um=5)
                normalized={kind:dict(normalized_path=str(root/'normalized-inputs'/key/(kind+'.spice'))) for kind in ('application','native')}
                for analysis in ('dc','ac'):
                    folder=root/'electrical'/(key+'-'+analysis);folder.mkdir(parents=True)
                    text=producer.deck(spec,row,key,analysis,selected,normalized,execution,gui_nonce);(folder/'input.cir').write_text(text)
                    expected=audit.check_deck(root,row,key,analysis,selected,normalized,execution,gui_nonce)
                    self.assertEqual(expected,producer.title(execution,gui_nonce,key,analysis))
            path=folder/'input.cir'
            for changed in (text.replace('native.spice','application.spice'),text.replace('XN in_n out_n native_wrapper','XN in_n out_n native_wrapper m=16'),
                text.replace('.temp 27','.temp 30'),text.replace('exact.spice tt','exact.spice ff'),text.replace('CL_n out_n 0 1n','CL_n out_n 0 2n')):
                path.write_text(changed)
                with self.assertRaises(ValueError):audit.check_deck(root,row,key,analysis,selected,normalized,execution,gui_nonce)
            self.assertNotEqual(audit.context_title(execution,gui_nonce,key,analysis),audit.context_title({**execution,'nonce':'c'*32},gui_nonce,key,analysis))
            self.assertNotEqual(audit.context_title(execution,gui_nonce,key,analysis),audit.context_title(execution,'c'*32,key,analysis))

    def test_actual_retained_array_inputs_allow_only_top_token_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/'gui';original.mkdir();out=root/'electrical';out.mkdir();binding={'cases':{}}
            for key in inputs.CASES:
                model,n,r=key.split('-');count=int(n[1:]);top='array_'+key.replace('-','_');folder=original/key;folder.mkdir()
                app=f'.subckt {top} R1 R2\nR_RES R1 R2 sky130_fd_pr__res_generic_{model} w=2 l=5 m={count}\n.ends {top}\n'
                native=f'.subckt {top} R1 R2\n'+''.join(f'R{i} R1 R2 sky130_fd_pr__res_generic_{model} w=2 l=5\n' for i in range(count))+f'.ends {top}\n'
                files={}
                for kind,text in (('reference',app),('native',native)):
                    path=folder/(kind+'.spice');path.write_text(text);files[kind]=str(path)
                binding['cases'][key]=dict(model=model,multiplicity=count,rotation=int(r[1:]),width_um=2,length_um=5,top=top,
                    files=files,hashes={kind:inputs.sha(path) for kind,path in files.items()})
            normalized=producer.retain_inputs(binding,out);self.assertEqual(audit.input_copies(out,binding),normalized)
            path=out/'normalized-inputs/l1-m2-r0/native.spice';data=path.read_bytes()
            for changed in (data.replace(b'w=2',b'w=3',1),data.replace(b'R1 R2 sky130',b'R1 R1 sky130',1),data+b'.include replacement.spice\n'):
                path.write_bytes(changed)
                with self.assertRaises(ValueError):audit.input_copies(out,binding)
            path.write_bytes(data)
            self.assertEqual(audit.input_copies(out,binding),normalized)

    def test_new_raw_title_and_signed_current_remain_independent(self):
        execution={'root':'/evidence/run','nonce':'a'*32};title=audit.context_title(execution,'b'*32,'l1-m3-r0','dc')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.raw'
            path.write_text(raw_fixture('dc').replace('* array-independent-fixture',title))
            measured=audit.raw.electrical_observation(path,title,'dc','l1',2,5,3);self.assertEqual(measured['samples'],21)
            for change in ('current','response','coefficient','nan','title'):
                path.write_text(raw_fixture('dc',change).replace('* array-independent-fixture',title))
                with self.assertRaises(ValueError):audit.raw.electrical_observation(path,title,'dc','l1',2,5,3)

    def test_live_scope_counts_do_not_infer_transient_noise_or_full_family(self):
        self.assertEqual(audit.COUNTS,dict(fresh_gui_native_inputs=30,electrical_contexts=30,electrical_analyses=60,electrical_path_samples=3870))
        self.assertNotIn('noise_conditions',audit.COUNTS);self.assertNotIn('transient_conditions',audit.COUNTS)


if __name__=='__main__':unittest.main()
