"""Independent input/deck/raw provenance controls for installed metal evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_installed_sky130_metal_resistors as audit


class MetalElectricalAuditTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.nonce='a'*32
        self.spec=audit.load(audit.ROOT/'docs/qualification/sky130-metal-resistors-linked-v1.json')
        self.row=dict(model='m1',width_um=2,length_um=5,geometry_index=1,rotation=0,multiplicity=1)
        self.top='metal_m1_g1_r0_'+self.nonce[:12]

    def original(self, *, native=False, newline='\n', top=None):
        top=top or self.top
        rows=['* retained original µm',f'.subckt {top} R1 R2',
              'R_R1 R1 R2 sky130_fd_pr__res_generic_m1 l=5 '+('' if native else 'm=1 ')+'w=2',f'.ends {top}','']
        return newline.join(rows).encode()

    def test_normalization_is_two_top_tokens_only_including_crlf_and_utf8_offsets(self):
        for newline in ('\n','\r\n'):
            original=self.original(newline=newline);value,proof=audit.normalized_original(original,self.top)
            self.assertEqual(value,original.replace(self.top.encode(),b'coupon'))
            self.assertEqual(len(proof['edits']),2)
            for edit in proof['edits']:
                self.assertEqual(original[edit['start']:edit['stop']],self.top.encode())
            self.assertEqual(proof['original_sha256'],hashlib.sha256(original).hexdigest())
        data=self.original().replace(b'.ends '+self.top.encode(),b'.ends')
        self.assertEqual(len(audit.normalized_original(data,self.top)[1]['edits']),1)

    def test_old_top_extra_subcircuit_extra_directive_and_wrong_ports_reject(self):
        data=self.original()
        for altered in (data.replace(self.top.encode(),b'old_top'),data+b'.include old.spice\n',
                        data+b'.subckt extra R1 R2\n.ends\n',data.replace(b'.subckt '+self.top.encode()+b' R1 R2',b'.subckt '+self.top.encode()+b' R2 R1')):
            with self.subTest(altered=altered),self.assertRaises(ValueError): audit.normalized_original(altered,self.top)

    def test_fault_copies_change_exactly_one_observable_token(self):
        data=self.original().replace(self.top.encode(),b'coupon')
        expected={'wrong-width':b'w=2.3999999999999999','wrong-length':b'l=6','wrong-model':b'sky130_fd_pr__res_generic_m3',
                  'wrong-multiplicity':b'm=2','disconnected-terminal':b'R_R1 0 R2'}
        for fault in audit.FAULTS:
            altered,proof=audit.fault_original(data,self.row,fault)
            self.assertIn(expected[fault],altered);self.assertEqual(len(proof['edits']),1)
            edit=proof['edits'][0];self.assertEqual(data[edit['start']:edit['stop']],edit['before'].encode())
            self.assertEqual(altered,data[:edit['start']]+edit['after'].encode()+data[edit['stop']:])
        with self.assertRaises(ValueError): audit.fault_original(data.replace(b'w=2',b'w=3'),self.row,'wrong-width')
        with self.assertRaises(ValueError): audit.fault_original(data,self.row,'unknown')

    def retained_fixture(self):
        # The producer's independent byte-span writer creates the fixture; the
        # auditor never calls it, including when its helpers are patched below.
        from scripts import installed_metal_resistor_inputs as producer_inputs
        binding=dict(cases={});normalized={};faults={}
        for model in ('m1','m2','m3','m4'):
            for geometry,(width,length) in enumerate(((.5,.5),(2,5),(5,2))):
                for rotation in (0,90):
                    name=f'{model}-g{geometry}-r{rotation}';top='metal_'+name.replace('-','_')+'_'+self.nonce[:12]
                    row=dict(model=model,geometry_index=geometry,width_um=width,length_um=length,rotation=rotation,top=top,
                             files={},hashes={});binding['cases'][name]=row;normalized[name]={};faults[name]={}
                    for kind,original_kind in (('application','reference'),('native','native')):
                        data=(f'.subckt {top} R1 R2\nR0 R1 R2 sky130_fd_pr__res_generic_{model} '
                              f'w={width:g} l={length:g}'+(' m=1' if kind=='application' else '')+f'\n.ends {top}\n').encode()
                        source=self.root/'gui'/name/(original_kind+'.spice');source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(data)
                        row['files'][original_kind]=str(source);row['hashes'][original_kind]=audit.sha(source)
                        retained=self.root/'original-inputs'/name/(kind+'.spice');retained.parent.mkdir(parents=True,exist_ok=True);retained.write_bytes(data)
                        value,proof=producer_inputs.normalize_top(data,top)
                        target=self.root/'normalized-inputs'/name/(kind+'.spice');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
                        normalized[name][kind]=dict(original_path=str(source),original_sha256=audit.sha(source),retained_path=str(retained),
                            normalized_path=str(target),normalized_sha256=audit.sha(target),proof=proof)
                        if kind=='application':
                            for fault in audit.FAULTS:
                                changed,mutation=producer_inputs.fault_copy(value,row,fault)
                                path=self.root/'fault-inputs'/name/(fault+'.spice');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(changed)
                                faults[name][fault]=dict(path=str(path),sha256=audit.sha(path),source_sha256=audit.sha(target),proof=mutation)
        (self.root/'normalized-inputs.json').write_text(json.dumps(normalized));(self.root/'fault-inputs.json').write_text(json.dumps(faults))
        return binding,normalized,faults

    def test_all_twenty_four_original_pairs_and_faults_independently_reaudit(self):
        binding,_,_=self.retained_fixture()
        with patch.object(audit.inputs,'normalize_top',side_effect=AssertionError('producer normalization called')), \
             patch.object(audit.inputs,'fault_copy',side_effect=AssertionError('producer fault writer called')):
            actual=audit.input_copies(self.root,binding)
        self.assertEqual(len(actual[0]),24);self.assertEqual(sum(map(len,actual[1].values())),120)

    def test_rehashed_normalized_primitive_substitution_rejects(self):
        binding,normalized,_=self.retained_fixture();row=normalized['m3-g1-r0']['native'];target=Path(row['normalized_path'])
        target.write_bytes(target.read_bytes().replace(b'generic_m3',b'generic_m4'))
        row['normalized_sha256']=audit.sha(target);row['proof']['normalized_sha256']=audit.sha(target)
        (self.root/'normalized-inputs.json').write_text(json.dumps(normalized))
        with self.assertRaisesRegex(ValueError,'beyond top-name'):audit.input_copies(self.root,binding)

    def test_rehashed_fault_second_edit_and_missing_input_reject(self):
        binding,_,faults=self.retained_fixture();row=faults['m1-g1-r0']['wrong-width'];path=Path(row['path'])
        path.write_bytes(path.read_bytes().replace(b'l=5',b'l=6'));row['sha256']=audit.sha(path);row['proof']['mutated_sha256']=audit.sha(path)
        (self.root/'fault-inputs.json').write_text(json.dumps(faults))
        with self.assertRaisesRegex(ValueError,'single token'):audit.input_copies(self.root,binding)
        normalized=audit.load(self.root/'normalized-inputs.json');normalized.pop('m2-g1-r0')
        (self.root/'normalized-inputs.json').write_text(json.dumps(normalized))
        with self.assertRaisesRegex(ValueError,'coverage'):audit.input_copies(self.root,binding)

    def test_context_uri_is_derived_from_actual_execution_directory(self):
        portable=self.root.as_posix();portable=('/'+portable) if os.name=='nt' else portable
        report=dict(execution_directory=str(self.root),execution=dict(root=portable,nonce=self.nonce))
        self.assertEqual(audit.execution_identity(self.root,report),report['execution'])
        for value in ('/another-run',portable+'/old',str(self.root) if os.name=='nt' else 'relative/path'):
            changed=copy.deepcopy(report);changed['execution']['root']=value
            with self.subTest(value=value),self.assertRaises(ValueError):audit.execution_identity(self.root,changed)

    def literal_deck(self, analysis='dc'):
        name='tt-t27-'+analysis+'-positive';case=dict(name=name,section='tt',temperature_c=27,analysis=analysis,control='positive')
        logical=[dict(tag='m1_g1_r0_m1',physical_case='m1-w2-l5',**self.row)]
        rows=[{**logical[0],'kind':kind,'fault':None,'branch':prefix+'_m1_g1_r0_m1'}
              for kind,prefix in (('application','a'),('native','n'),('analytic','c'))]
        key='m1-g1-r0';normalized={key:{kind:dict(normalized_path=str(self.root/'normalized-inputs'/key/(kind+'.spice')))
                                      for kind in ('application','native')}}
        selected={'tt':'.lib pdk-models/fixture.spice tt'};execution=dict(root='/source/context',nonce=self.nonce)
        option='.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear'+(' chgtol=1e-24 trtol=1' if analysis=='tran' else '')
        pulse=' '.join(format(self.spec['experiment'][k],'.17g') for k in
                      ('pulse_low_v','pulse_high_v','pulse_delay_s','pulse_edge_s','pulse_edge_s','pulse_width_s','pulse_period_s'))
        text=[audit.raw.context_title(execution,name),selected['tt'],option,'.temp 27',
              'VDRIVE input 0 '+('PULSE('+pulse+')' if analysis=='tran' else 'DC .0005')+' AC 1']
        resistance=audit.raw.resistance(self.spec,rows[2],'tt',27)
        text += ['VS_a_m1_g1_r0_m1 input in_a_m1_g1_r0_m1 DC 0 AC 0','.subckt application_m1_g1_r0 a b',
            '.include '+Path(normalized[key]['application']['normalized_path']).as_posix(),'X_COUPON a b coupon','.ends application_m1_g1_r0',
            'X_a_m1_g1_r0_m1_0 in_a_m1_g1_r0_m1 out_a_m1_g1_r0_m1 application_m1_g1_r0',
            'RL_a_m1_g1_r0_m1 out_a_m1_g1_r0_m1 0 1','CL_a_m1_g1_r0_m1 out_a_m1_g1_r0_m1 0 1n',
            'VS_n_m1_g1_r0_m1 input in_n_m1_g1_r0_m1 DC 0 AC 0','.subckt native_m1_g1_r0 a b',
            '.include '+Path(normalized[key]['native']['normalized_path']).as_posix(),'X_COUPON a b coupon','.ends native_m1_g1_r0',
            'X_n_m1_g1_r0_m1_0 in_n_m1_g1_r0_m1 out_n_m1_g1_r0_m1 native_m1_g1_r0',
            'RL_n_m1_g1_r0_m1 out_n_m1_g1_r0_m1 0 1','CL_n_m1_g1_r0_m1 out_n_m1_g1_r0_m1 0 1n',
            'VS_c_m1_g1_r0_m1 input in_c_m1_g1_r0_m1 DC 0 AC 0',f'RC_c_m1_g1_r0_m1 in_c_m1_g1_r0_m1 out_c_m1_g1_r0_m1 {resistance:.17g}',
            'RL_c_m1_g1_r0_m1 out_c_m1_g1_r0_m1 0 1','CL_c_m1_g1_r0_m1 out_c_m1_g1_r0_m1 0 1n']
        coefficients=self.spec['sections']['tt']['coefficients']
        text += [f'VP_{n} par_{n} 0 DC {{{n}}} AC {{{n}}}' for n in coefficients]
        channels=['v(input)']+[v for r in rows for v in (f'v(in_{r["branch"]})',f'v(out_{r["branch"]})',f'i(vs_{r["branch"]})')]+[f'v(par_{n})' for n in coefficients]
        text+=['.save '+' '.join(channels),dict(dc='.dc VDRIVE -.001 .001 .0001',ac='.ac dec 3 1k 10g',tran='.tran 20p 21n')[analysis],'.end']
        folder=self.root/name;folder.mkdir(exist_ok=True);path=folder/'input.cir';path.write_text('\n'.join(text)+'\n')
        return path,case,rows,selected,normalized,execution

    def test_positive_wrappers_and_transient_accuracy_are_literal(self):
        for analysis in ('dc','ac','tran'):
            path,case,rows,selected,normalized,execution=self.literal_deck(analysis)
            self.assertEqual(audit.check_deck(self.root,self.spec,case,rows,selected,normalized,{},execution),('tt',27))

    def test_shunts_missing_parallel_stale_context_and_manual_parameters_rejected(self):
        path,case,rows,selected,normalized,execution=self.literal_deck();original=path.read_text()
        for value in (original.replace('.end\n','R_SHUNT input 0 1\n.end\n'),
                      original.replace('X_COUPON a b coupon','X_COUPON b a coupon',1),
                      original.replace('X_a_m1_g1_r0_m1_0','X_a_m1_g1_r0_m1_1'),
                      original.replace('.temp 27','.temp 44'),
                      original.replace('.temp 27','.param rm1=1\n.temp 27'),
                      original.replace('native_m1_g1_r0 a b','native_m1_g1_r90 a b')):
            path.write_text(value)
            with self.subTest(value=value),self.assertRaises(ValueError):audit.check_deck(self.root,self.spec,case,rows,selected,normalized,{},execution)

    def test_command_raw_paths_and_console_failures_cannot_be_hidden_by_hashes(self):
        path,case,rows,_,_,_=self.literal_deck();folder=path.parent;(folder/'result.raw').write_bytes(b'raw fixture');(folder/'console.log').write_text('complete\n')
        runtime=dict(engine='/reviewed/ngspice',environment=dict(LANG='C'))
        case.update(status='PASS',returncode=0,branches=rows,command=[runtime['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(path)],
                    cwd=str(self.root),environment=runtime['environment'],deck_sha256=audit.sha(path),raw_sha256=audit.sha(folder/'result.raw'),log_sha256=audit.sha(folder/'console.log'))
        audit.check_execution(self.root,case,runtime)
        for key,value in (('returncode',1),('command',['other-engine']),('cwd',str(folder)),('environment',dict(LANG='C',LD_PRELOAD='other'))):
            altered={**case,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):audit.check_execution(self.root,altered,runtime)
        (folder/'console.log').write_text('singular matrix\n');case['log_sha256']=audit.sha(folder/'console.log')
        with self.assertRaisesRegex(ValueError,'failure'):audit.check_execution(self.root,case,runtime)

    def test_source_contract_exact_selection_counts(self):
        logical,cases=audit.raw.selection(self.spec,False)
        self.assertEqual((len(logical),len(cases)),(48,90))
        faults=sum(sum(bool(r['fault']) for r in audit.raw.branches(logical,c)) if c['control']=='positive' else 2*len(logical) for c in cases)
        self.assertEqual(faults,4680)
        logical,cases=audit.raw.selection(self.spec,True)
        self.assertEqual((len(logical),len(cases)),(4,6))

    def runtime_fixture(self):
        engine=self.root/'ngspice';engine.write_bytes(b'profile fixture engine')
        initializer=self.root/'spinit';initializer.write_bytes(b'profile fixture initialization')
        runtime=dict(platform=audit.sys.platform,engine=str(engine),sha256=audit.sha(engine),environment=dict(LANG='C'),
                     files={str(engine):audit.sha(engine),str(initializer):audit.sha(initializer)},elf_dependencies={})
        assets=self.root/'runtime-assets';assets.mkdir()
        for name,digest in runtime['files'].items():(assets/digest).write_bytes(Path(name).read_bytes())
        (self.root/'runtime-assets.json').write_text(json.dumps(runtime['files']))
        for phase in ('before','after'):(self.root/f'runtime-{phase}.json').write_text(json.dumps(runtime))
        report={f'runtime_{phase}_sha256':audit.sha(self.root/f'runtime-{phase}.json') for phase in ('before','after')}
        installed=dict(runtime_profiles={audit.sys.platform:dict(sha256=audit.sha(engine))})
        return engine,runtime,report,installed

    def test_runtime_live_closure_and_retained_initializers_required(self):
        engine,runtime,report,installed=self.runtime_fixture()
        with patch.object(audit.inputs,'select_engine',return_value=engine), \
             patch.object(audit.inputs,'native_environment',return_value=runtime['environment']), \
             patch.object(audit.inputs,'runtime',return_value=runtime):
            audit.runtime_binding(self.root,report,dict(mode='source-pilot'),installed)
            retained=self.root/'runtime-assets'/audit.sha(self.root/'spinit');retained.write_bytes(b'altered initialization')
            with self.assertRaisesRegex(ValueError,'closure'):audit.runtime_binding(self.root,report,dict(mode='source-pilot'),installed)

    def test_rehashed_runtime_initializer_and_missing_dependency_still_fail_live_identity(self):
        engine,runtime,report,installed=self.runtime_fixture()
        for fault in ('changed-initializer','missing-engine'):
            altered=copy.deepcopy(runtime)
            if fault=='changed-initializer':altered['files'][str(self.root/'spinit')]='b'*64
            else:altered['files'].pop(str(engine))
            for phase in ('before','after'):
                path=self.root/f'runtime-{phase}.json';path.write_text(json.dumps(altered));report[f'runtime_{phase}_sha256']=audit.sha(path)
            with patch.object(audit.inputs,'select_engine',return_value=engine), \
                 patch.object(audit.inputs,'native_environment',return_value=runtime['environment']), \
                 patch.object(audit.inputs,'runtime',return_value=runtime), self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'Live engine'):
                audit.runtime_binding(self.root,report,dict(mode='source-pilot'),installed)


if __name__=='__main__':unittest.main()
