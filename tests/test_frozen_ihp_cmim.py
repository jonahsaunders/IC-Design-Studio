"""Falsification controls for the independent checker; no installed claim."""
import copy
from decimal import Decimal
import json
from pathlib import Path
import shutil
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_frozen_ihp_cmim as gate


class CircuitTests(unittest.TestCase):
    def text(self,line):return '.subckt coupon C1 C2\n'+line+'\n.ends coupon\n'
    def test_original_magic_and_public_exact_interfaces(self):
        for mode,line in [('original','X_C1 C1 C2 cap_cmim w=7u l=7u m=1 mm_ok=1'),('magic','X0 C1 C2 cap_cmim w=7u l=7u'),('public','C0 C1 C2 cap_cmim w=7u l=7u a=49p p=28u m=1')]:
            self.assertEqual(gate.circuit(self.text(line),mode)['ordered_nodes'],['C1','C2'])
    def test_wrong_dimensions_area_perimeter_multiplier_and_order(self):
        line='C0 C1 C2 cap_cmim w=7u l=7u a=49p p=28u m=1'
        for old,new in [('w=7u','w=8u'),('l=7u','l=8u'),('a=49p','a=48p'),('p=28u','p=27u'),('m=1','m=2'),('C1 C2 cap','C2 C1 cap')]:
            with self.subTest(new=new),self.assertRaises(ValueError):gate.circuit(self.text(line.replace(old,new)),'public')
    def test_precision_is_never_rounded_into_default(self):
        self.assertNotEqual(gate.literal('7.00000000000000000000000000000001u'),Decimal('7e-6'))
        for old,new in [('w=7u','w=7.00000000000000000000000000000001u'),('a=49p','a=49.00000000000000000000000000000001p'),('p=28u','p=28.00000000000000000000000000000001u')]:
            line='C0 C1 C2 cap_cmim w=7u l=7u a=49p p=28u m=1'
            with self.subTest(new=new),self.assertRaises(ValueError):gate.circuit(self.text(line.replace(old,new)),'public')
    def test_duplicate_unknown_nonfinite_and_extra_device_fail(self):
        line='C0 C1 C2 cap_cmim w=7u l=7u a=49p p=28u m=1'
        for text in [self.text(line+' w=7u'),self.text(line+' foo=1'),self.text(line.replace('w=7u','w=NaN')),self.text(line.replace('a=49p','a=Inf')),self.text(line+'\n'+line),self.text(line).replace('C1 C2\n','C1 C1\n')]:
            with self.subTest(text=text),self.assertRaises(ValueError):gate.circuit(text,'public')
    def test_simulation_selector_must_not_leak_to_physical(self):
        with self.assertRaises(ValueError):gate.circuit(self.text('X_C1 C1 C2 cap_cmim w=7u l=7u m=1 mm_ok=1'),'magic')
    def test_authentic_raw_native_header_order_does_not_change_device_electrodes(self):
        text='.SUBCKT coupon C2 C1\nC$1 C1 C2 cap_cmim w=7u l=7u A=49p P=28u m=1\n.ENDS coupon\n'
        self.assertEqual(gate.circuit(text,'public',raw_top_order=True)['ordered_nodes'],['C1','C2'])
        with self.assertRaises(ValueError):gate.circuit(text,'public')
        with self.assertRaises(ValueError):gate.circuit(text.replace('C$1 C1 C2','C$1 C2 C1'),'public',raw_top_order=True)


class EvidenceSafetyTests(unittest.TestCase):
    def test_cross_host_paths_preserve_recorded_windows_platform(self):
        launch=dict(platform='Windows')
        self.assertEqual(gate.host_path(launch,r'C:\Program Files\Studio','_internal/icstudio/assets'),r'C:\Program Files\Studio\_internal\icstudio\assets')
        self.assertEqual(gate.host_path(dict(platform='Linux'),'/opt/studio','_internal/icstudio'),'/opt/studio/_internal/icstudio')
    def test_duplicate_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            for text in ['{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}','{"a":1e309}','{"nested":[1e309]}']:
                path.write_text(text)
                with self.assertRaises(ValueError):gate.load(path)
    def test_forbidden_components_rejected_before_metadata(self):
        for name in ['tmpuxoell2b/file','a/tmpuxoell2b/x','../file','/abs','a\\b','a:b']:
            with self.subTest(name=name),self.assertRaises(ValueError):gate.member(name)
    def test_inventory_prunes_forbidden_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'allowed').write_bytes(b'bytes');dirs=[gate.FORBIDDEN]
            with patch.object(gate.os,'walk',return_value=iter([(str(root),dirs,['allowed'])])):
                self.assertEqual(gate.inventory(root),{'allowed':gate.sha(root/'allowed')})
            self.assertEqual(dirs,[])
    def test_source_or_native_claim_cannot_pass_installed_header(self):
        for frozen,native in [(False,False),(True,True)]:
            with self.assertRaisesRegex(ValueError,'frozen GUI-only'):gate.header(dict(schema=1,status='passed',mode='lifecycle',frozen=frozen,native_execution=native,managed=True),{}, {})
    def test_link_endpoints_are_confined_and_regular(self):
        files={'_internal/libfoo.so.1':'a'*64};links={'_internal/libfoo.so':'libfoo.so.1'}
        self.assertEqual(gate.link_endpoint('_internal/libfoo.so',links['_internal/libfoo.so'],files,links),'_internal/libfoo.so.1')
        for target in ['../../escape','/outside','missing.so','libfoo.so',gate.FORBIDDEN+'/x']:
            with self.subTest(target=target),self.assertRaises(ValueError):gate.link_endpoint('_internal/libfoo.so',target,files,links)
    def test_only_exact_root_installer_metadata_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'_internal').mkdir()
            for name in ['ICDesignStudio.exe','unins000.exe','_internal/unins000.exe']:(root/name).write_bytes(name.encode())
            tree=gate.distribution_tree(root,'Windows')
            self.assertEqual(set(tree['installer_metadata']),{'unins000.exe'});self.assertEqual(set(tree['files']),{'ICDesignStudio.exe','_internal/unins000.exe'})


class NativeControlTests(unittest.TestCase):
    def test_raw_netgen_json_rejects_property_and_bool_count_forgery(self):
        good=[dict(name=['coupon','coupon'],devices=[[['cap_cmim',1]],[['cap_cmim',1]]],nets=[2,2],pins=[['C1','C2'],['C1','C2']],badnets=[],badelements=[])]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lvs.json';gate.write(path,good);gate.netgen_json(path)
            bad=[]
            value=copy.deepcopy(good);value[0]['devices'][0][0][1]=True;bad.append(value)
            value=copy.deepcopy(good);value[0]['properties']=[['w','wrong']];bad.append(value)
            value=copy.deepcopy(good);value[0]['pins'][1].reverse();bad.append(value)
            value=copy.deepcopy(good);value[0]['badnets']=['short'];bad.append(value)
            bad.append(good+good)
            for value in bad:
                gate.write(path,value)
                with self.subTest(value=value),self.assertRaises(ValueError):gate.netgen_json(path)
    def test_linux_temporary_names_and_wsl_uuid_have_distinct_contracts(self):
        launch=dict(native_temp_root='/tmp');linux=dict(kind='linux');wsl=dict(kind='wsl')
        self.assertEqual(str(gate.native_directory('/tmp/icstudio-physical-ab_cd123',linux,launch)),'/tmp/icstudio-physical-ab_cd123')
        self.assertEqual(str(gate.native_directory('/var/tmp/icstudio-physical/'+'a'*32,wsl,launch)),'/var/tmp/icstudio-physical/'+'a'*32)
        for path in ['/tmp/icstudio-physical-'+'a'*32,'/elsewhere/icstudio-physical-ab_cd123','/tmp/other-ab_cd123','/tmp/icstudio-physical-a']:
            with self.subTest(path=path),self.assertRaises(ValueError):gate.native_directory(path,linux,launch)
        with self.assertRaises(ValueError):gate.native_directory('/var/tmp/icstudio-physical/not-uuid',wsl,launch)
    def test_stale_source_reuse_cannot_satisfy_normal_ready_record(self):
        runtime=dict(kind='wsl',root=r'\\wsl.localhost\private',distro='private',sha256='a'*64);manifest=dict(platforms=['ihp'],schema=1)
        backend={'module.py':'b'*64};ready=dict(runtime=runtime,manifest=gate.digest(manifest),backend=gate.digest(backend),evidence='checks/current',platforms=['ihp'])
        status=dict(state='ready',runtime=runtime,evidence='checks/current');gate.ready_binding(ready,status,backend,manifest,runtime)
        bad=copy.deepcopy(ready);bad['backend']='c'*64
        with self.assertRaisesRegex(ValueError,'ready record'):gate.ready_binding(bad,status,backend,manifest,runtime)
        bad=copy.deepcopy(status);bad['state']='setup'
        with self.assertRaisesRegex(ValueError,'normally ready'):gate.ready_binding(ready,bad,backend,manifest,runtime)
        bad=copy.deepcopy(ready);bad['platforms']=[]
        with self.assertRaisesRegex(ValueError,'ready record'):gate.ready_binding(bad,status,backend,manifest,runtime)
    def test_stage_coverage_and_bool_count_cannot_pass(self):
        good=dict(stages=[dict(name=name,status='passed') for name in gate.STAGES],status='passed',drc_engine='magic',lvs_extractor='magic',drc_count=0,findings=[])
        self.assertEqual(len(gate.completed_stages(good,'magic')),6)
        mutations=[]
        for key,value in [('drc_count',False),('drc_count',1),('status','failed'),('drc_engine','ihp-public')]:
            d=copy.deepcopy(good);d[key]=value;mutations.append(d)
        d=copy.deepcopy(good);d['stages'][4]['status']='failed';mutations.append(d)
        d=copy.deepcopy(good);d['stages'].append(copy.deepcopy(d['stages'][0]));mutations.append(d)
        for d in mutations:
            with self.subTest(d=d),self.assertRaises(ValueError):gate.completed_stages(d,'magic')
    def test_strict_lvs_requires_completed_unique_match_without_error(self):
        good='Cell pin lists are equivalent.\nFinal result: Circuits match uniquely.\n';gate.strict_lvs(good)
        for text in ['',good+good,good+'Property errors were found.',good+'**Mismatch**',good+'Final result: Top level cell failed pin matching.']:
            with self.subTest(text=text),self.assertRaises(ValueError):gate.strict_lvs(text)
    def test_projection_source_and_changed_flag_are_independent(self):
        lock=dict(files={'libs.tech/xschem/sg13g2_pr/cap_cmim.sym':'a'*64,'libs.tech/ngspice/models/capacitors_mod.lib':'b'*64})
        inputs=dict(files={gate.PUBLIC[0]+'/rule_decks/custom_reader.lvs':'c'*64})
        original='.subckt coupon C1 C2\nX_C1 C1 C2 cap_cmim w=7u l=7u m=1 mm_ok=1\n.ends\n'
        physical=original.replace('X_C1','CX_C1').replace('mm_ok=1','a=49p p=28u')
        proof=dict(source='libs.tech/xschem/sg13g2_pr/cap_cmim.sym',sha256='a'*64,model_source='libs.tech/ngspice/models/capacitors_mod.lib',model_sha256='b'*64,geometry_reader='rule_decks/custom_reader.lvs',geometry_reader_sha256='c'*64,geometry_formula='A=w*l; P=2*(w+l), per unit; m retained separately')
        row=dict(instance='X_C1',physical_instance='CX_C1',changed=True,proof=proof);report=dict(reference_defaults=[row]);gate.projection(report,original,physical,'ihp-klayout',lock,inputs)
        for key,value in [('changed',False),('physical_instance','Cother')]:
            bad=copy.deepcopy(report);bad['reference_defaults'][0][key]=value
            with self.assertRaises(ValueError):gate.projection(bad,original,physical,'ihp-klayout',lock,inputs)
        for key in ('sha256','model_sha256','geometry_reader_sha256'):
            bad=copy.deepcopy(report);bad['reference_defaults'][0]['proof'][key]='d'*64
            with self.assertRaises(ValueError):gate.projection(bad,original,physical,'ihp-klayout',lock,inputs)


class CandidateTests(unittest.TestCase):
    def test_private_immutable_git_rejects_modified_parent_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);env=gate.git_environment();env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
            def git(*args):return subprocess.check_output(['git',*args],cwd=root,env=env,stderr=subprocess.STDOUT)
            git('init','-q')
            names=[*gate.HELPERS,gate.PDK+'/package.json','icstudio/assets/pdks/collection.json',gate.FIXTURE+'/mask-only.json',gate.FIXTURE+'/SOURCE.json',gate.FIXTURE+'/LICENSE',*(p+'/SOURCE.json' for p in gate.PUBLIC),'icstudio/ihp_cmim_desktop_probe.py','icstudio/simulation.py','.github/workflows/build-desktop.yml']
            for name in names:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((gate.ROOT/name).read_bytes() if name in gate.HELPERS else b'fixture source\n')
            git('add','--',*names);git('-c','user.name=CMIM checker test','-c','user.email=cmim-test@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=','commit','-qm','private immutable fixture')
            commit=git('rev-parse','HEAD').decode().strip()
            with patch.object(gate,'ROOT',root):
                self.assertIn('workflow_hash',gate.candidate(commit));(root/gate.HELPERS[0]).write_bytes(b'mutated checker\n')
                with self.assertRaisesRegex(ValueError,'checker differs'):gate.candidate(commit)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        from scripts.qualify_standard_mos import load_technology
        from icstudio.catalog import create_device
        from icstudio.model import example,clone
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.tech,_=load_technology('ihp-sg13g2');self.lock=gate.load(Path(self.tech['package_root'])/'package.json')
        self.tech['package_lock']['manifest_hash']=gate.digest(self.lock)
        asset=gate.ROOT/gate.FIXTURE;fixture=gate.load(asset/'mask-only.json')
        self.inputs=dict(files={gate.FIXTURE+'/'+name:gate.sha(asset/name) for name in ('mask-only.json','SOURCE.json','LICENSE')},package_sha256=gate.sha(Path(self.tech['package_root'])/'package.json'))
        for name,target in [('mask-only.json','fixture-mask.json'),('SOURCE.json','fixture-source.json'),('LICENSE','fixture-LICENSE')]:shutil.copyfile(asset/name,self.root/target)
        p=example('empty');p['name']='IHP CMIM '+'a'*32;p['pdk']=clone(self.tech);cell=p['cells'][0];cell.update(name='coupon',ports=['C1','C2'])
        for field in gate.FIELDS:cell[field]=clone(fixture[field])
        device=create_device(self.tech,'sg13g2_pr/cap_cmim.sym','C1');device['nets']={'c0':'C1','c1':'C2'};device['net_labels']=dict(device['nets']);cell['devices']=[device]
        self.project=p;self.row=dict(top='coupon',cell_id=cell['id'],instance_id=device['id'],nets=device['nets'],project_name=p['name'],default_width_um=7,default_length_um=7,multiplicity=1,mm_ok=1,edit_width_um=8,restored_width_um=7)
        self.report=dict(execution_id='a'*32,source_project_sha256=fixture['source_project_sha256'],lifecycle=self.row)
        self.publish()
    def publish(self):
        from icstudio.model import save_project,load_project
        from icstudio.interchange import export_layout,spice
        from icstudio.catalog_migration import emit
        from icstudio.testbenches import native_subcircuit
        from icstudio.layout_verification import reference
        save_project(self.project,self.root/'catalog.icproj');self.project=load_project(self.root/'catalog.icproj');save_project(self.project,self.root/'catalog-reopened.icproj')
        raw=native_subcircuit(self.project,self.project['top']);(self.root/'captured-reference.spice').write_bytes(raw.encode())
        (self.root/'schematic.spice').write_text(spice(self.project,self.project['top']),encoding='utf-8')
        export_layout(self.project,self.root/'layout.gds');export_layout(self.project,self.root/'layout.oas')
        self.row.update(design_hash=gate.design_hash(self.project),reference_capture=reference(raw,'coupon'),simulation_statement=emit(self.project['cells'][0]['devices'][0],self.tech,'simulation'))
        for key,name in dict(project='catalog.icproj',reopened_project='catalog-reopened.icproj',reference='captured-reference.spice',schematic='schematic.spice',gds='layout.gds',oasis='layout.oas').items():self.row[key]=name;self.row[key+'_sha256']=gate.sha(self.root/name)
    def check(self):return gate.lifecycle(self.root,self.report,self.inputs,self.lock)
    def test_actual_saved_catalog_and_exports_are_read(self):
        project,raw=self.check();self.assertEqual(project,self.project);self.assertIn('X_C1 C1 C2 cap_cmim',raw)
    def test_rehashed_mask_or_port_mutation_fails(self):
        for field in ('shapes','layout_ports'):
            original=copy.deepcopy(self.project)
            if field=='shapes':self.project['cells'][0][field][0]['points'][0][0]+=5
            else:self.project['cells'][0][field][0]['point'][0]+=5
            self.publish()
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'masks/ports'):self.check()
            self.project=original
    def test_rehashed_layer_map_cannot_redefine_geometry_oracle(self):
        self.project['pdk']['layers'][0]['gds']+=1;self.publish()
        with self.assertRaisesRegex(ValueError,'technology'):self.check()
    def test_real_registry_semantic_manifest_hash_is_required(self):
        self.project['pdk']['package_lock']['manifest_hash']='0'*64;self.publish()
        with self.assertRaisesRegex(ValueError,'registry PDK lock'):self.check()
    def test_rehashed_reference_and_saved_width_mutations_fail(self):
        self.project['cells'][0]['devices'][0]['model_params']['w']='8u';self.publish()
        with self.assertRaisesRegex(ValueError,'default parameters'):self.check()
    def test_rehashed_catalog_binding_and_imported_tokens_fail(self):
        self.project['cells'][0]['devices'][0]['native_spice']={'tokens':['Cfake']}
        for key in ('project','reopened_project'):
            gate.write(self.root/self.row[key],self.project);self.row[key+'_sha256']=gate.sha(self.root/self.row[key])
        self.row['design_hash']=gate.design_hash(self.project)
        with self.assertRaisesRegex(ValueError,'imported'):self.check()
    def test_rehashed_actual_gds_mutation_fails(self):
        import klayout.db as db
        path=self.root/'layout.gds';layout=db.Layout();layout.read(str(path));layout.top_cell().shapes(layout.layer(36,0)).insert(db.Box(50000,50000,50100,50100));layout.write(str(path));self.row['gds_sha256']=gate.sha(path)
        with self.assertRaisesRegex(ValueError,'masks or labels'):self.check()


if __name__=='__main__':unittest.main()
