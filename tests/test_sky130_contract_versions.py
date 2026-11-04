"""Current identity rebinding preserves historical contracts and every criterion."""
import copy,hashlib,json,pathlib,tempfile,unittest
from unittest.mock import patch
from scripts import sky130_contract_versions as versions
from scripts import qualify_sky130_li_linked as li
from scripts import qualify_sky130_metal_resistors_linked as metal
from scripts import qualify_sky130_metal_resistor_parallel as parallel
from scripts import installed_metal_resistor_inputs as installed
from scripts import installed_metal_parallel_inputs as arrays
from scripts import qualification_sky130_mos_voltage as voltage
from scripts.prepare_sky130_esd_nvt import predecessor
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_bytes())

class CurrentContractVersions(unittest.TestCase):
    def test_current_contracts_change_only_identity_and_provenance(self):
        for family,rows in versions.VERSIONS.items():
            if family=='voltage':continue
            old=load(ROOT/rows['v1']['path']);new=load(ROOT/rows['v2']['path'])
            self.assertEqual(sha(ROOT/rows['v1']['path']),rows['v1']['sha256'])
            self.assertEqual(sha(ROOT/rows['v2']['path']),rows['v2']['sha256'])
            restored=copy.deepcopy(new)
            for key in ('id','date','as_of'):
                if key in old:restored[key]=old[key]
            self.assertEqual(restored.pop('package_rebinding')['previous_contract'],dict(path=rows['v1']['path'],sha256=rows['v1']['sha256']))
            if family=='li':
                for key,row in restored['sources'].items():
                    if 'package_revision' in row:row['package_revision']=old['sources'][key]['package_revision']
                for key in ('sha256','bytes'):restored['sources']['package'][key]=old['sources']['package'][key]
                restored['minimal_linked_acceptance']['simulation_package']=old['minimal_linked_acceptance']['simulation_package']
            elif family in ('metal','parallel'):
                restored['package']=old['package'];key='icstudio/assets/pdks/sky130A/package.json'
                restored['sources'][key]=old['sources'][key]
            else:
                restored['source_contract']=old['source_contract']
                if family=='installed_parallel':restored['previous_installed_contract']=old['previous_installed_contract']
            self.assertEqual(restored,old,family)
    def test_only_exact_historical_and_current_pairs_are_reviewed(self):
        for family,rows in versions.VERSIONS.items():
            for name,row in rows.items():
                self.assertEqual(versions.selected(family,row['sha256'],row['package_sha256']),row)
                other=rows['v2' if name=='v1' else 'v1']
                with self.assertRaisesRegex(ValueError,'pair differs'):versions.selected(family,row['sha256'],other['package_sha256'])
            with self.assertRaisesRegex(ValueError,'Unreviewed'):versions.selected(family,'0'*64)
            with self.assertRaisesRegex(ValueError,'Unreviewed'):versions.package_version(family,'0'*64)
    def test_changed_and_rehashed_numerical_contract_cannot_be_accepted(self):
        current=versions.selected('metal');value=load(ROOT/current['path']);value['tolerances']['dc_relative']=.5
        changed=(json.dumps(value,indent=2)+'\n').encode();rehash=hashlib.sha256(changed).hexdigest()
        with self.assertRaisesRegex(ValueError,'Unreviewed'):versions.selected('metal',rehash,current['package_sha256'])
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);target=root/current['path'];target.parent.mkdir(parents=True);target.write_bytes(changed)
            with patch.object(metal,'ROOT',root),self.assertRaisesRegex(ValueError,'changed acceptance contract'):metal.contract()
    def test_current_producers_and_installed_inputs_use_the_same_fixed_versions(self):
        self.assertEqual(li.contract()['id'],versions.selected('li')['id'])
        self.assertEqual(metal.contract()['id'],versions.selected('metal')['id'])
        self.assertEqual(parallel.contract()['id'],versions.selected('parallel')['id'])
        i,s,_=installed.contracts();a,p,_=arrays.contracts()
        self.assertEqual(i['source_contract']['sha256'],metal.CONTRACT_SHA)
        self.assertEqual(a['source_contract']['sha256'],parallel.CONTRACT_SHA)
        self.assertEqual(s['package'],p['package'])
        self.assertEqual(i['gui']['clean_native_layouts'],30);self.assertEqual(a['gui']['fresh_native_jobs'],42)
    def test_changed_actual_package_or_model_still_blocks_every_source_gate(self):
        for module in (li,metal,parallel,installed,arrays):
            method=module.contract if module in (li,metal,parallel) else module.contracts
            name='file_digest' if module is li else 'sha';original=getattr(module,name)
            def changed(path):
                return '0'*64 if pathlib.Path(path)==ROOT/'icstudio/assets/pdks/sky130A/package.json' else original(path)
            with patch.object(module,name,side_effect=changed),self.assertRaises(ValueError):method()
        spec=metal.contract();model_path=next(n for n in spec['sources'] if n.endswith('.spice'))
        original=metal.sha
        with patch.object(metal,'sha',side_effect=lambda p:'0'*64 if pathlib.Path(p)==ROOT/model_path else original(p)),self.assertRaisesRegex(ValueError,'Contract source changed'):metal.contract()
    def test_voltage_v2_has_the_same17_models40_aliases_and_public_criteria(self):
        rows=versions.VERSIONS['voltage'];old=ROOT/rows['v1']['path'];new=ROOT/rows['v2']['path']
        a=load(old/'catalog-source-lock.json');b=load(new/'catalog-source-lock.json')
        self.assertEqual(a['models'],b['models']);self.assertEqual(len(b['models']),17)
        self.assertEqual(sum(len(v['aliases']) for v in b['models'].values()),40)
        for p in old.rglob('*'):
            if p.is_file() and p.name not in ('catalog-source-lock.json','README.md'):self.assertEqual(p.read_bytes(),(new/p.relative_to(old)).read_bytes())
        q=voltage.QualificationVoltageContract();self.assertEqual(len(q.aliases),40)
        for model in ('sky130_fd_pr__esd_nfet_05v0_nvt','sky130_fd_pr__esd_nfet_g5v0d10v5'):
            with self.assertRaises(ValueError):q.screen(dict(model=model,vds=1,vgs=1,vbs=0,temperature_c=27))
    def test_historical_voltage_package_retains_its_original_contract_and_scope(self):
        with predecessor(voltage.DEFAULT_PACKAGE) as old:
            q=voltage.QualificationVoltageContract(old)
            point=q.screen(dict(model='sky130_fd_pr__nfet_01v8',vds=1,vgs=1,vbs=0,temperature_c=27))
            self.assertEqual(point['package_manifest_sha256'],voltage.HISTORICAL_PACKAGE_SHA)
            self.assertEqual(point['catalog_source_lock_sha256'],voltage.HISTORICAL_CATALOG_LOCK_SHA)
            self.assertEqual(point['current_package_native_coverage'],'NOT_ESTABLISHED');self.assertFalse(point['qualified'])

    def test_v2_and_v3_readers_reject_rehashed_source_snapshot_missing_version_helper(self):
        from scripts import audit_sky130_metal_resistors_linked as metal_reader
        from scripts import audit_sky130_metal_resistor_parallel as array_reader
        for family,reader in (('metal',metal_reader),('parallel',array_reader)):
            for version in ('v2', 'v3'):
                review=versions.VERSIONS[family][version]
                spec=load(ROOT/review['path']);root=pathlib.Path('/retained-test').resolve()
                required={review['path'],'scripts/qualify_sky130_metal_resistors_linked.py','scripts/audit_sky130_metal_resistors_linked.py',
                    'tests/test_sky130_metal_resistors_linked.py','tests/test_sky130_metal_resistors_linked_audit.py',
                    'scripts/qualify_sky130_metal_resistor_parallel.py','scripts/audit_sky130_metal_resistor_parallel.py',
                    'tests/test_sky130_metal_resistor_parallel.py','tests/test_sky130_metal_resistor_parallel_audit.py',
                    'tests/gui_sky130_metal_resistor_parallel.py','icstudio/sky130_metal_resistors.py','examples/sky130-qualification-lock.json',*spec['sources']}
                source={n:'a'*64 for n in required};source[review['path']]=review['sha256']
                report=dict(schema=1,gate=review['id'],status='PASS',mode='source-integration',qualified=False,installed_acceptance=False,
                    full_family=False,chunk_complete=False,release_ready=False,signoff=False,pilot=False,
                    guards=dict(source=True,simulation_package=True,staged_models=True,physical_package=True,runtime=True),
                    contract_sha256=review['sha256'],source_files_sha256='b'*64,execution=dict(root='/retained-test',nonce='a'*32))
                data={'qualification.json':report,'contract.json':spec,'source-files.json':source,'manifest.json':{}}
                def fake_load(p):return data[pathlib.Path(p).name]
                def fake_sha(p):
                    p=pathlib.Path(p)
                    return review['package_sha256'] if p.name=='package.json' else review['sha256'] if p.name=='contract.json' else 'b'*64
                def fake_inventory(p,*args):
                    return source if pathlib.Path(p)==root/'source' else {'manifest.json':'b'*64} if family=='metal' else {}
                with patch.object(reader,'load',side_effect=fake_load),patch.object(reader,'sha',side_effect=fake_sha),patch.object(reader,'inventory',side_effect=fake_inventory):
                    with self.assertRaisesRegex(ValueError,'source snapshot member missing|Missing required array source identity'):reader.audit(root)

    def _assert_v3_preserves_scientific_criteria(self,family,rows,old,new):
        self.assertEqual(new['package_rebinding']['previous_contract'],
                         dict(path=rows['v2']['path'],sha256=rows['v2']['sha256']))
        restored=copy.deepcopy(new)
        if family in ('installed_metal','installed_parallel'):
            old_linux=dict(engine='ngspice42',sha256='820658317b0b54035208da41936fd6871ce924036e5ea4113a4168b821b7fc45')
            corrected_linux=dict(engine='ngspice47-corrected',sha256='67399d2db139e9a8e7bfd118cab8acfa290bb6db003c996333e55ed682a65d25')
            windows=dict(engine='ngspice46',sha256='86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453')
            self.assertEqual(old['runtime_profiles'],dict(win32=windows,linux=old_linux))
            self.assertEqual(new['runtime_profiles'],dict(win32=windows,linux=corrected_linux))
            self.assertEqual(restored.pop('runtime_rebinding'),dict(
                previous_proposed_linux_profile=old_linux,current_linux_profile=corrected_linux,
                reference_preservation='Historical ngspice42 source/reference files and original formulas remain exact. No claim all47 primitive code is byte-identical42.',
                reviewed_differences=[
                    '47 changes the explicit zero/tiny resistance floor to1e-12.',
                    '47 changes explicit instance-temperature/noise handling; selected global-temperature semantics require actual native checks.',
                    'const.h and res.c in the retained source comparison are identical; restemp diagnostic wording changes.'],
                source_comparison_receipt_sha256='dc7839bb9d4dd61fbce37d97efdfea16519e90ced7fea00e6c9e562a684537b1',
                acceptance='Unchanged selected source equations, stimuli, geometries, multiplicities, numerical limits, fault requirements and installed completion gates. New exact runtime still requires fresh native and frozen/installed acceptance.'))
            # Normalize only the independently checked Linux profile, preserving
            # exhaustive comparison of Windows, every criterion and every field.
            restored['runtime_profiles']['linux']=old_linux
            source_family='metal' if family=='installed_metal' else 'parallel'
            source=versions.VERSIONS[source_family]['v3']
            expected_source=copy.deepcopy(old['source_contract'])
            expected_source.update(path=source['path'],sha256=source['sha256'])
            self.assertEqual(new['source_contract'],expected_source)
            if family=='installed_parallel':
                prior=versions.VERSIONS['installed_metal']['v3']
                expected_prior=copy.deepcopy(old['previous_installed_contract'])
                expected_prior.update(path=prior['path'],sha256=prior['sha256'])
                self.assertEqual(new['previous_installed_contract'],expected_prior)
        for key in ('id','date','as_of','package_rebinding'):
            if key in old:restored[key]=old[key]
        if family=='li':
            for key,row in restored['sources'].items():
                if 'package_revision' in row:row['package_revision']=old['sources'][key]['package_revision']
            for key in ('sha256','bytes'):restored['sources']['package'][key]=old['sources']['package'][key]
            restored['minimal_linked_acceptance']['simulation_package']=old['minimal_linked_acceptance']['simulation_package']
        elif family in ('metal','parallel'):
            restored['package']=old['package'];key='icstudio/assets/pdks/sky130A/package.json'
            restored['sources'][key]=old['sources'][key]
        else:
            restored['source_contract']=old['source_contract']
            if family=='installed_parallel':restored['previous_installed_contract']=old['previous_installed_contract']
        self.assertEqual(restored,old,family)

    def test_v3_runtime_profile_and_provenance_cannot_be_crossed_or_weakened(self):
        for family in ('installed_metal','installed_parallel'):
            rows=versions.VERSIONS[family];old,new=(load(ROOT/rows[v]['path']) for v in ('v2','v3'))
            mutations=[(('runtime_profiles','linux','sha256'),'0'*64),
                (('runtime_profiles','linux','engine'),'ngspice42'),
                (('runtime_profiles','win32','sha256'),new['runtime_profiles']['linux']['sha256']),
                (('runtime_rebinding','current_linux_profile','sha256'),old['runtime_profiles']['linux']['sha256']),
                (('runtime_rebinding','previous_proposed_linux_profile','sha256'),new['runtime_profiles']['linux']['sha256']),
                (('runtime_rebinding','source_comparison_receipt_sha256'),'0'*64),
                (('runtime_rebinding','reviewed_differences'),[]),
                (('source_contract','sha256'),versions.VERSIONS['parallel' if family=='installed_metal' else 'metal']['v3']['sha256'])]
            if family=='installed_parallel':mutations.append((('previous_installed_contract','sha256'),versions.VERSIONS['installed_metal']['v2']['sha256']))
            for path,value in mutations:
                with self.subTest(family=family,path=path):
                    changed=copy.deepcopy(new);node=changed
                    for key in path[:-1]:node=node[key]
                    node[path[-1]]=value
                    with self.assertRaises(AssertionError):self._assert_v3_preserves_scientific_criteria(family,rows,old,changed)

    def test_v3_all_five_scientific_contracts_reject_changed_criteria(self):
        paths={'li':('minimal_linked_acceptance','geometry','width_um'),
            'metal':('tolerances','dc_relative'),'parallel':('electrical','tolerance','relative'),
            'installed_metal':('electrical','conditions','dc'),
            'installed_parallel':('gui','fresh_native_jobs')}
        for family,path in paths.items():
            with self.subTest(family=family):
                rows=versions.VERSIONS[family];old,new=(load(ROOT/rows[v]['path']) for v in ('v2','v3'))
                changed=copy.deepcopy(new);node=changed
                for key in path[:-1]:node=node[key]
                node[path[-1]]+=1
                with self.assertRaises(AssertionError):self._assert_v3_preserves_scientific_criteria(family,rows,old,changed)

    def test_rehashed_installed_runtime_contracts_remain_unreviewed(self):
        for family,module in (('installed_metal',installed),('installed_parallel',arrays)):
            current=versions.VERSIONS[family]['v3'];changed=load(ROOT/current['path'])
            changed['runtime_profiles']['linux']['sha256']='0'*64
            data=(json.dumps(changed,indent=2)+'\n').encode();rehash=hashlib.sha256(data).hexdigest()
            with self.assertRaisesRegex(ValueError,'Unreviewed'):versions.selected(family,rehash,current['package_sha256'])
            with tempfile.TemporaryDirectory() as tmp:
                root=pathlib.Path(tmp);path=root/current['path'];path.parent.mkdir(parents=True);path.write_bytes(data)
                with patch.object(module,'ROOT',root),self.assertRaisesRegex(ValueError,'contract changed'):module.contracts()

    def test_v3_changes_only_explicit_package_identity_and_preserves_v2(self):
        for family,rows in versions.VERSIONS.items():
            self.assertEqual(set(rows), {'v1','v2','v3'})
            for row in rows.values():
                for other in rows.values():
                    if row['package_sha256'] != other['package_sha256']:
                        with self.assertRaisesRegex(ValueError,'pair differs'):
                            versions.selected(family,row['sha256'],other['package_sha256'])
            self.assertEqual(versions.selected(family),rows['v3'])
            if family=='voltage':
                old,new=(ROOT/rows[v]['path'] for v in ('v2','v3'))
                a,b=load(old/'catalog-source-lock.json'),load(new/'catalog-source-lock.json')
                self.assertEqual(a['models'],b['models'])
                for source in old.rglob('*'):
                    if source.is_file() and source.name not in ('catalog-source-lock.json','README.md'):
                        self.assertEqual(source.read_bytes(),(new/source.relative_to(old)).read_bytes())
                continue
            old,new=(load(ROOT/rows[v]['path']) for v in ('v2','v3'))
            self.assertEqual(sha(ROOT/rows['v2']['path']),rows['v2']['sha256'])
            self.assertEqual(sha(ROOT/rows['v3']['path']),rows['v3']['sha256'])
            self._assert_v3_preserves_scientific_criteria(family,rows,old,new)

if __name__=='__main__':unittest.main()
