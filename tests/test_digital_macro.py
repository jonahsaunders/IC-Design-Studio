"""Macro metadata must describe the design that produced its captured artifacts."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from icstudio import digital, digital_design, digital_identity, digital_platform
from icstudio.digital_flow import artifact
from icstudio.digital_macro import export
from icstudio.model import clone, design_digest, digest


class DigitalMacroTests(unittest.TestCase):
    def fixture(self,root,*,child=False,name='fixture'):
        staged=root/'platform';staged.mkdir()
        (staged/'cells.lib').write_text('unit library')
        (staged/'LICENSE.txt').write_text('captured unit notice')
        raw={'version':1,'name':name,'revision':'unit fixture','corner':'tt',
             'corners':{'tt':['cells.lib']},'files':['cells.lib','LICENSE.txt']}
        manifest=staged/'platform.json';manifest.write_text(json.dumps(raw))
        project=digital.counter_project();cid=project['top']
        value=digital_platform.bind(project['digital'],digital_platform.read_manifest(manifest))
        # Export uses captured notices even after the original PDK is unavailable.
        value['platform']['root']='unavailable/original/platform'
        if child:
            cell=clone(project['cells'][0]);cell['id']='child-cell';cell['name']='Child'
            project['cells'].append(cell);cid=cell['id'];value['top']='child_counter'
            for source in value['files']:source['text']=source['text'].replace('counter','child_counter')
        digital_design.set_config(project,cid,value)
        files={}
        for key in ('gds','lef','netlist','checkpoint','spef','log'):
            path=root/(key+'.txt');path.write_text('unit '+key);files[key]=artifact(root,path)
        path=root/'preview.json';path.write_text(json.dumps({'die':[0,0,2,2],'pins':[]}))
        files['layout_preview']=artifact(root,path)
        job={'project':project,'cell':cid};(root/'input.json').write_text(json.dumps(job))
        result={'result_type':'digital','project_id':project['id'],'cell_id':cid,
            'design_hash':design_digest(project),'settings':{'stage':'finish'},
            'digital_result':{'stage':'finish','source_hash':digital.source_hash(value),
                'input_key':digital_identity.stage_key(value,'finish'),
                'platform':{'name':name,'fingerprint':value['platform']['fingerprint']},
                'summary':'unit physical result, not engine qualification','artifacts':files}}
        return job,result

    def test_valid_export_binds_design_metadata_and_retains_notice_after_relocation(self):
        for child in (False,True):
            with self.subTest(child=child),tempfile.TemporaryDirectory() as td:
                root=Path(td);job,result=self.fixture(root,child=child)
                contract=export(result,root,root/'macro.zip')
                config=digital_design.config(job['project'],job['cell'])
                self.assertEqual(contract['top'],config['top'])
                self.assertEqual(contract['design_hash'],design_digest(job['project']))
                self.assertEqual(contract['source_hash'],digital.source_hash(config))
                with zipfile.ZipFile(root/'macro.zip') as archive:
                    self.assertEqual(archive.read('notices/LICENSE.txt'),b'captured unit notice')
                    for source in config['files']:
                        if source['role']=='constraint':
                            self.assertEqual(archive.read('constraints/'+source['path']).decode(),source['text'])

    def test_changed_inputs_never_replace_an_existing_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result=self.fixture(root);destination=root/'macro.zip'
            export(result,root,destination);original=destination.read_bytes()
            for fault in ('constraint','top','rtl','notice-lock','project-id','cell-id','other-cell','missing-project'):
                changed=clone(job);config=changed['project']['digital']
                if fault=='constraint':next(f for f in config['files'] if f['role']=='constraint')['text']+='\n# changed\n'
                elif fault=='top':config['top']='another_top'
                elif fault=='rtl':next(f for f in config['files'] if f['role']=='rtl')['text']+='\n// changed\n'
                elif fault=='notice-lock':
                    platform=config['platform'];platform['files']=[f for f in platform['files'] if f['path']!='LICENSE.txt']
                    platform['fingerprint']=digest(platform['files'])
                elif fault=='project-id':changed['project']['id']='another-project'
                elif fault=='cell-id':changed['cell']='another-cell'
                elif fault=='other-cell':changed['project']['cells'][0]['name']='Changed name'
                else:changed.pop('project')
                (root/'input.json').write_text(json.dumps(changed))
                with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'captured job inputs'):
                    export(result,root,destination)
                self.assertEqual(destination.read_bytes(),original)
                self.assertFalse((root/'macro.zip.partial').exists())

    def test_inconsistent_result_identities_are_rejected_even_with_valid_input_file(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result=self.fixture(root)
            for field in ('source_hash','input_key','design_hash'):
                bad=clone(result)
                (bad if field=='design_hash' else bad['digital_result'])[field]='0'*64
                with self.subTest(field=field),self.assertRaisesRegex(ValueError,'captured job inputs'):
                    export(bad,root,root/'bad.zip')
                self.assertFalse((root/'bad.zip').exists())

    def test_legacy_result_without_stage_key_still_requires_matching_source_and_design(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,result=self.fixture(root);result['digital_result'].pop('input_key')
            self.assertIsNone(export(result,root,root/'legacy.zip')['input_key'])
            job['project']['digital']['top']='changed_top';(root/'input.json').write_text(json.dumps(job))
            with self.assertRaisesRegex(ValueError,'captured job inputs'):export(result,root,root/'bad.zip')

    def test_release_qualifier_missing_jobs_replaces_stale_pass_with_failure(self):
        from scripts.qualify_macro_exports import qualify
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);output=root/'report.json';output.write_text('{"status":"passed"}')
            with self.assertRaisesRegex(ValueError,'Missing required'):qualify(root,output)
            self.assertEqual(json.loads(output.read_text())['status'],'failed')

    def test_release_qualifier_requires_matching_platform_labels(self):
        from scripts.qualify_macro_exports import qualify
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);directory=root/'sky130hd/gds';directory.mkdir(parents=True)
            _,result=self.fixture(directory,name='gf180');(directory/'result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'another platform'):qualify(root,root/'report.json')
            self.assertEqual(json.loads((root/'report.json').read_text())['status'],'failed')

    def test_release_qualifier_covers_all_cases_without_changing_original_inputs(self):
        from scripts.qualify_macro_exports import qualify
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);before={}
            for name in digital_platform.BUNDLED_PLATFORMS:
                directory=root/name/'gds';directory.mkdir(parents=True)
                _,result=self.fixture(directory,name=name);(directory/'result.json').write_text(json.dumps(result))
                before[name]=(directory/'input.json').read_bytes()
            report=qualify(root,root/'report.json')
            self.assertEqual(len(report['cases']),24)
            self.assertEqual(sum(c['status']=='rejected' for c in report['cases']),20)
            for name,content in before.items():self.assertEqual((root/name/'gds/input.json').read_bytes(),content)


if __name__=='__main__':unittest.main()
