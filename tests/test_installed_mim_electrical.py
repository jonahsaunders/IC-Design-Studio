"""Fail-closed input, context, raw and source-law controls for installed MiM."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import installed_mim_inputs as inputs
from scripts import qualify_installed_sky130_mim_electrical as producer
from scripts import audit_installed_sky130_mim_electrical as auditor

CONTRACT = inputs.load(inputs.ROOT/inputs.CONTRACT_PATH)


def raw(path, analysis='op', *, plate=1, section='tt', bias=5, ground=0, change=None, title='fixture'):
    coefficients = CONTRACT['passive_sections'][section]['coefficients']
    names = [f'{kind}({prefix}_{key})' for key in auditor.BRANCHES for kind,prefix in (('v','p'),('v','n'),('i','vp'),('i','vn'))]
    names += ['v(par_'+key+')' for key in auditor.PARAMETERS]
    if analysis=='ac':
        names.insert(0,'frequency')
    count = 8 if analysis=='ac' else 1
    text = f'Title: {title}\nPlotname: '+('AC Analysis' if analysis=='ac' else 'Operating Point')+'\nFlags: '+('complex' if analysis=='ac' else 'real')
    text += f'\nNo. Variables: {len(names)}\nNo. Points: {count}\nVariables:\n'
    text += ''.join(f'{i}\t{name}\tvoltage\n' for i,name in enumerate(names))+'Values:\n'
    for i in range(count):
        f = 1e3*10**i; metal = str(plate+2)
        w = 2+1e6*(coefficients['m'+metal+'_dw']+coefficients['tol_m'+metal])
        l = 10+1e6*(coefficients['m'+metal+'_dw']+coefficients['tol_m'+metal])
        r = coefficients['rm'+metal]*l/w+coefficients['rcvia'+metal]*(.56 if plate==1 else .73)**2/(w*l)
        c = coefficients['camimc']*w*l+2*coefficients['cpmimc']*(w+l); y = 1/complex(r,-1/(2*math.pi*f*c))
        values = {'v(par_'+key+')':complex(coefficients.get(key,0)) for key in auditor.PARAMETERS}
        if analysis=='ac':
            values['frequency'] = complex(f)
        for key in auditor.BRANCHES:
            values.update({f'v(p_{key})':complex(1 if analysis=='ac' else bias), f'v(n_{key})':complex(0 if analysis=='ac' else ground),
                           f'i(vp_{key})':-y if analysis=='ac' else 0j, f'i(vn_{key})':y if analysis=='ac' else 0j})
        values.update(change or {})
        for j,name in enumerate(names):
            value = complex(values[name]); text += (str(i)+'\t' if j==0 else '\t')
            text += (f'{value.real:.17g},{value.imag:.17g}' if analysis=='ac' else f'{value.real:.17g}')+'\n'
    path.write_text(text)


class InstalledMiMElectrical(unittest.TestCase):
    def test_exact_full_and_pilot_contexts_cannot_be_duplicated_or_relabeled(self):
        for pilot,expected in ((True,4),(False,60)):
            contexts = producer.selected([1,2],['tt'] if pilot else list(producer.SECTIONS),[0,90],[0] if pilot else [-5,0,5])
            report = dict(pilot=pilot,selected_cases=[producer.case_name(*v) for v in contexts],
                cases=[dict(plate=p,section=s,rotation=r,bias_V=b,name=producer.case_name(p,s,r,b)) for p,s,r,b in contexts])
            self.assertEqual(len(auditor.case_inventory(report)),expected)
            changed = copy.deepcopy(report); changed['cases'][-1] = changed['cases'][0]
            with self.assertRaises(ValueError): auditor.case_inventory(changed)
            changed = copy.deepcopy(report); changed['cases'][0]['bias_V'] = 4.99
            with self.assertRaises(ValueError): auditor.case_inventory(changed)
            changed = copy.deepcopy(report); changed['cases'][0]['plate'] = True
            with self.assertRaises(ValueError): auditor.case_inventory(changed)

    def test_all_expected_faults_and_domain_rejections_have_exact_coverage(self):
        contexts = producer.selected([1,2],list(producer.SECTIONS),[0,90],[-5,0,5])
        self.assertEqual(sum(len(producer.faults(v[-1])) for v in contexts),180)
        self.assertEqual(len(producer.domain_controls()),5)
        for value in (-5.001,5.001,float('nan'),float('inf'),-float('inf')):
            with self.assertRaises(ValueError): producer.checked_bias(value)

    def test_normalization_changes_only_declared_top_and_preserves_native_body(self):
        top = 'mim_p1_r90_'+'a'*12
        text = f'* native proof\n.subckt {top} P N\nX0 P N sky130_fd_pr__cap_mim_m3_1 w=2 l=10\n.ends {top}\n'
        normalized = producer.normalized(text,top,'device_coupon')
        self.assertEqual(normalized,text.replace(top,'device_coupon'))
        for changed in (text.replace(' P N',' N P'),text+text,text.replace('.ends '+top,'.ends other')):
            with self.assertRaises(ValueError): producer.normalized(changed,top,'device_coupon')

    def test_installed_engine_cannot_be_external_or_custom(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp); folder = bundle/'icstudio/assets/runtime/ngspice'; folder.mkdir(parents=True)
            engine = folder/('ngspice.exe' if os.name=='nt' else 'ngspice'); engine.write_bytes(b'fixture')
            binding = dict(mode='installed',resource_root=str(bundle),engine_discovery=dict(path=str(engine),sha256=inputs.sha(engine),executed=False))
            self.assertEqual(inputs.select_engine(binding),engine.resolve())
            with self.assertRaisesRegex(ValueError,'override'): inputs.select_engine(binding,engine)
            binding['engine_discovery']['path'] = str(bundle/'host-engine')
            with self.assertRaisesRegex(ValueError,'discovery'): inputs.select_engine(binding)

    def test_source_engine_requires_explicit_label_and_no_implicit_path_search(self):
        with self.assertRaisesRegex(ValueError,'explicit'): inputs.select_engine(dict(mode='source-pilot'))

    def test_installed_discovery_changed_bytes_or_execution_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp); folder = bundle/'icstudio/assets/runtime/ngspice'; folder.mkdir(parents=True)
            engine = folder/('ngspice.exe' if os.name=='nt' else 'ngspice'); engine.write_bytes(b'fixture')
            binding = dict(mode='installed',resource_root=str(bundle),engine_discovery=dict(path=str(engine),sha256=inputs.sha(engine),executed=True))
            with self.assertRaises(ValueError): inputs.select_engine(binding)
            binding['engine_discovery']['executed'] = False; engine.write_bytes(b'changed')
            with self.assertRaises(ValueError): inputs.select_engine(binding)

    def test_native_environment_drops_all_inherited_overrides_case_insensitively(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'spinit').write_text('scalar initializer')
            with patch.dict(os.environ,{'Git_Config_Count':'1','ICSTUDIO_NGSPICE':'wrong','LD_PRELOAD':'wrong','PYTHONPATH':'wrong','PATH':'wrong'}):
                env = inputs.native_environment(dict(mode='installed',resource_root=str(root)),root/'ngspice',root)
            self.assertFalse(any(k.upper().startswith('GIT_') or k in ('ICSTUDIO_NGSPICE','LD_PRELOAD','PYTHONPATH') for k in env))
            self.assertNotIn('wrong',env.values()); self.assertEqual(env['SPICE_SCRIPTS'],str(root))

    def test_missing_initializer_is_rejected_for_installed_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'initializer'):
                inputs.native_environment(dict(mode='installed',resource_root=temp),Path(temp)/'ngspice',Path(temp))

    def test_model_closure_uses_slash_paths_without_rewriting_windows_execution_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); models=root/'shared-models'; sources=root/'model-sources'; models.mkdir(); sources.mkdir()
            (models/'pdk-models').mkdir(); (root/'contract-sources').mkdir()
            original=sources/'library.spice'; original.write_text('* independent model-closure fixture\n')
            digest=inputs.sha(original)
            name='pdk-models/'+hashlib.sha256(('library.spice\0'+digest).encode()).hexdigest()[:24]+'.spice'
            (models/name).write_bytes(original.read_bytes())
            inputs.write(models/'pdk-model-files.json',{name:'library.spice'})
            files=inputs.inventory(models); inputs.write(root/'model-files.json',files)
            staged={s:'.lib '+root.as_posix()+'/shared-models/'+name+' '+s for s in auditor.SECTIONS}
            inputs.write(models/'source-identity.json',dict(files=files,staged=staged))
            package=dict(revision='fixture',files={'library.spice':digest},technology=dict(simulation=dict(includes=[
                dict(path='library.spice',sections={s:s for s in auditor.SECTIONS})])))
            inputs.write(root/'contract-sources/package',package)
            report=dict(execution_root=str(root),simulation_package=dict(revision='fixture',manifest_sha256=inputs.sha(root/'contract-sources/package')))
            original_report=copy.deepcopy(report)
            self.assertEqual(auditor.staged_models(root,report,inputs.inventory(root)),staged)
            self.assertEqual(report,original_report)
            (models/name).write_text('* rehashed substituted model\n')
            files=inputs.inventory(models,('source-identity.json',)); inputs.write(root/'model-files.json',files)
            inputs.write(models/'source-identity.json',dict(files=files,staged=staged))
            with self.assertRaisesRegex(ValueError,'statements'):
                auditor.staged_models(root,report,inputs.inventory(root))

    def test_independent_op_requires_actual_bias_and_balanced_zero_current(self):
        coefficients = CONTRACT['passive_sections']['tt']['coefficients']
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'raw'; raw(path)
            self.assertEqual(auditor.op(path,coefficients,5)['extracted']['differential_V'],5)
            for p,n in ((0,0),(-5,0),(4.99,0),(5,.5)):
                raw(path,bias=p,ground=n)
                with self.assertRaisesRegex(ValueError,'bias'): auditor.op(path,coefficients,5)
            raw(path,change={'i(vp_extracted)':1e-6})
            with self.assertRaisesRegex(ValueError,'current'): auditor.op(path,coefficients,5)

    def test_independent_ac_source_law_all_sections_and_both_models(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'raw'
            for plate in (1,2):
                for section in auditor.SECTIONS:
                    raw(path,'ac',plate=plate,section=section)
                    self.assertEqual(len(auditor.ac(path,CONTRACT['passive_sections'][section]['coefficients'],plate)['samples']),8)

    def test_wrong_coefficient_source_kcl_and_nonfinite_fail_even_after_rehash(self):
        coefficients = CONTRACT['passive_sections']['tt']['coefficients']
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'raw'
            for change in ({'v(par_camimc)':3e-15},{'v(p_schematic)':2},{'i(vn_extracted)':0},{'v(n_independent)':float('nan')}):
                raw(path,'ac',change=change); rehashed = inputs.sha(path)
                self.assertEqual(len(rehashed),64)
                with self.assertRaises(ValueError): auditor.ac(path,coefficients,1)

    def test_wrong_model_and_section_numerics_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'raw'; raw(path,'ac',plate=2)
            with self.assertRaisesRegex(ValueError,'RC'): auditor.ac(path,CONTRACT['passive_sections']['tt']['coefficients'],1)
            raw(path,'ac',section='lh')
            with self.assertRaisesRegex(ValueError,'coefficient'): auditor.ac(path,CONTRACT['passive_sections']['tt']['coefficients'],1)

    def test_new_context_binds_gui_nonce_engine_electrical_execution_and_case(self):
        identity = dict(execution_id='a'*32,gui_execution_id='b'*32,engine_sha256='c'*64,inputs_sha256='d'*64,execution_root='/new')
        expected = producer.context_title(identity,'p1-tt-r0-bp5','op')
        self.assertEqual(expected,auditor.execution_title(identity,'p1-tt-r0-bp5','op'))
        for key in identity:
            changed = {**identity,key:'different'}
            self.assertNotEqual(expected,auditor.execution_title(changed,'p1-tt-r0-bp5','op'))
        self.assertNotEqual(expected,auditor.execution_title(identity,'p1-tt-r90-bp5','op'))
        self.assertNotEqual(expected,auditor.execution_title(identity,'p1-tt-r0-bp5','op','sign-reversed'))

    def test_rehashed_stale_raw_or_failure_console_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); deck=folder/'probe.cir'; path=folder/'probe.raw'; log=folder/'console.log'
            deck.write_text('fixture'); log.write_text('No. of Data Rows : 1\n'); raw(path,title='expected')
            runtime=dict(engine='/selected/ngspice',environment={'LANG':'C'})
            record=dict(status='PASS',returncode=0,cwd=str(folder),environment=runtime['environment'],
                command=[runtime['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(path),str(deck)],
                deck_sha256=inputs.sha(deck),raw_sha256=inputs.sha(path),log_sha256=inputs.sha(log))
            auditor.check_execution(folder,record,'op',runtime,'expected')
            path.write_bytes(path.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
            record['raw_sha256']=inputs.sha(path)
            auditor.check_execution(folder,record,'op',runtime,'expected')
            raw(path,title='stale'); record['raw_sha256']=inputs.sha(path)
            with self.assertRaisesRegex(ValueError,'context'): auditor.check_execution(folder,record,'op',runtime,'expected')
            raw(path,title='expected'); record['raw_sha256']=inputs.sha(path); log.write_text('No. of Data Rows : 1\nError: bad model\n'); record['log_sha256']=inputs.sha(log)
            with self.assertRaisesRegex(ValueError,'console'): auditor.check_execution(folder,record,'op',runtime,'expected')

    def test_rehashed_deck_shunt_or_swapped_bias_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'probe.cir'; native=Path(temp)/'native.spice'
            reference='.subckt schematic P N\nX0 P N sky130_fd_pr__cap_mim_m3_1 w=2 l=10 mf=1 m=1\n.ends schematic\n'
            staged='.lib /locked/model.spice tt'; identity={'fixture':'not-native'}
            text=producer.circuit(reference,native,staged,1,5,'op',identity,'p1-tt-r0-bp5')
            title=auditor.execution_title(identity,'p1-tt-r0-bp5','op'); path.write_text(text)
            auditor.check_deck(path,reference,native,staged,1,5,'op',title)
            for changed in (text.replace('.end\n','Rhidden p_extracted 0 1k\n.end\n'),text.replace('DC 5 AC 1','DC 0 AC 1')):
                path.write_text(changed); self.assertEqual(len(inputs.sha(path)),64)
                with self.assertRaisesRegex(ValueError,'deck'): auditor.check_deck(path,reference,native,staged,1,5,'op',title)

    def test_saved_observables_do_not_accept_nan_boolean_or_missing_keys(self):
        for actual in ({'v':True},{'v':float('nan')},{'v':2},{}):
            with self.assertRaises(ValueError): auditor.numeric(actual,{'v':1.0})

    def test_json_duplicate_keys_are_rejected_instead_of_last_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'inputs.json'; path.write_text('{"mode":"source-pilot","mode":"installed"}')
            with self.assertRaisesRegex(ValueError,'Duplicate'): inputs.load(path)

    def test_incomplete_or_lifecycle_only_gui_probe_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for mode,status in (('lifecycle','passed'),('physical','failed')):
                inputs.write(root/'report.json',dict(schema=1,status=status,mode=mode,native_execution=False))
                with self.assertRaisesRegex(ValueError,'completed physical'): inputs.bind_gui(root,source_pilot=True)

    def test_failed_source_bind_creates_failure_receipt_without_installed_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'out'
            with patch.object(inputs,'bind_gui',side_effect=ValueError('prerequisite blocked')):
                result=producer.run(Path(temp)/'gui',out,source_pilot=True,source_engine=Path(temp)/'ngspice')
            self.assertEqual(result['status'],'FAIL'); self.assertFalse(result['installed_electrical_acceptance'])
            self.assertFalse((out/'audit.json').exists()); self.assertIn('prerequisite blocked',result['error'])


if __name__=='__main__':
    unittest.main()
