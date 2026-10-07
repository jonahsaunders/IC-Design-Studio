"""Corner identity, independent extraction evidence and Cartesian timing coverage."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import patch

from icstudio import digital, digital_identity, digital_platform, digital_rc
from icstudio.digital_flow import artifact
from icstudio.model import clone, design_digest, digest


SPEF='''*SPEF "IEEE 1481-1998"
*DESIGN "counter"
*C_UNIT 1 PF
*R_UNIT 1 OHM
*D_NET n1 0.2
*CONN
*P a I
*CAP
1 n1 0.2
*RES
1 a n1 2.5
*END
'''


class DigitalRCTests(unittest.TestCase):
    def fixture(self,root):
        names=('cells.lib','cells.lef','min.tlef','nom.tlef','max.tlef','min.rules','nom.rules','max.rules')
        for name in names:(root/name).write_text('captured '+name)
        manifest={'version':1,'name':'fixture','revision':'unit fixture','corner':'tt',
            'corners':{'tt':['cells.lib'],'ss':['cells.lib']},'files':list(names),
            'extraction':{'cell_lefs':['cells.lef'],'coupling_threshold_ff':0.1,
                'corners':{c:{'rules':c+'.rules','technology_lef':c+'.tlef'} for c in ('min','nom','max')}}}
        (root/'platform.json').write_text(json.dumps(manifest))
        config=digital_platform.bind(digital.counter_project()['digital'],digital_platform.read_manifest(root/'platform.json'))
        return config

    def test_captured_corner_definition_and_selection_reject_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            config=self.fixture(Path(td));self.assertEqual(digital_rc.selected(config),['min','nom','max'])
            for names in ([],['min','min'],['unknown'],[{}],None):
                bad=clone(config);bad['rc_corners']=names
                with self.subTest(names=names),self.assertRaises(ValueError):digital.validate_config(bad)
            for changed in ('missing','empty','case','threshold'):
                bad=clone(config);definition=bad['platform']['extraction']
                if changed=='missing':definition['corners']['min']['rules']='absent.rules'
                elif changed=='empty':definition['cell_lefs']=[]
                elif changed=='case':definition['corners']['MIN']=clone(definition['corners']['min'])
                else:definition['coupling_threshold_ff']=float('nan')
                with self.subTest(changed=changed),self.assertRaises(ValueError):digital_platform.validate(bad['platform'])

    def test_corner_changes_invalidate_finish_and_timing_without_discarding_placement(self):
        with tempfile.TemporaryDirectory() as td:
            config=self.fixture(Path(td));changed=clone(config);changed['rc_corners']=['nom']
            for stage in ('finish','timing'):
                self.assertNotEqual(digital_identity.stage_key(config,stage),digital_identity.stage_key(changed,stage))
            for stage in ('mapped','equivalence','floorplan','place','cts','route','simulate'):
                self.assertEqual(digital_identity.stage_key(config,stage),digital_identity.stage_key(changed,stage))
            # A changed deck association is a technology edit even with unchanged file bytes.
            changed=clone(config);changed['platform']['extraction']['corners']['min']['rules']='max.rules'
            self.assertNotEqual(digital_identity.logic_key(config),digital_identity.logic_key(changed))
            legacy=clone(config['platform']);legacy.pop('extraction')
            rebound=digital_platform.bind(config,legacy)
            self.assertNotIn('rc_corners',rebound)

    def test_extraction_requires_finite_nonempty_rc_and_matching_design(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'data.spef';path.write_text(SPEF)
            self.assertEqual(digital_rc.spef_metrics(path,'counter')['resistors'],1)
            for bad in (SPEF.replace('counter','other'),SPEF.replace('2.5','nan'),
                SPEF.replace('0.2','-1'),SPEF.replace('*R_UNIT 1 OHM',''),SPEF.replace('2.5','0')):
                path.write_text(bad)
                with self.assertRaises(ValueError):digital_rc.spef_metrics(path,'counter')

    def test_missing_or_stale_extraction_cannot_borrow_nominal_spef(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);config=self.fixture(root);artifacts={}
            for key,name in (('def','final.def'),('netlist','final.v'),('spef','legacy.spef'),
                ('spef_min','min.spef'),('spef_nom','nom.spef'),('spef_max','max.spef')):
                path=root/name;path.write_text(SPEF);artifacts[key]=artifact(root,path)
            report={'schema':1,'status':'complete','platform_fingerprint':config['platform']['fingerprint'],
                'definition_sha256':digest(config['platform']['extraction']),'def':artifacts['def'],
                'netlist':artifacts['netlist'],'corners':{c:{'spef_key':'spef_'+c,'spef':artifacts['spef_'+c]} for c in ('min','nom','max')}}
            path=root/'extraction.json';path.write_text(json.dumps(report));artifacts['extraction']=artifact(root,path)
            runner=SimpleNamespace(config=config,platform=config['platform'],settings={'upstream':{'root':str(root),'artifacts':artifacts}})
            with patch('icstudio.digital_implementation.verify_upstream'):
                self.assertEqual(digital_rc.timing_sources(runner),[('min','spef_min'),('nom','spef_nom'),('max','spef_max')])
                for change in ('missing-corner','wrong-geometry','wrong-definition','missing-report'):
                    changed=clone(report)
                    if change=='missing-corner':del changed['corners']['max']
                    elif change=='wrong-geometry':changed['def']['sha256']='0'*64
                    elif change=='wrong-definition':changed['definition_sha256']='0'*64
                    else:del artifacts['extraction']
                    path.write_text(json.dumps(changed))
                    with self.subTest(change=change),self.assertRaises(ValueError):digital_rc.timing_sources(runner)

    def test_every_library_rc_pair_runs_and_last_corner_failure_is_retained(self):
        from icstudio.digital_implementation import timing
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);config=self.fixture(root);seen=[]
            runner=SimpleNamespace(root=root,config=config,platform=config['platform'],settings={},tools={'sta':'fixture'},artifacts={})
            def command(*args,**kwargs):
                pair=(runner.timing_corner,runner.timing_spef_key);seen.append(pair)
                bad=pair==('ss','spef_max')
                contents={'timing_units.txt':'time 1ns\n','timing_checks.txt':'','electrical_checks.txt':'',
                    'timing_paths.tsv':'setup\ta\tb\t2\ta|b\nhold\ta\tb\t'+('-0.2' if bad else '0.2')+'\ta|b\n',
                    'timing_totals.txt':'tns 0','timing_hold_totals.txt':'tns '+('-0.2' if bad else '0'),
                    'timing_full.txt':'fixture','power.txt':'Total 0.1 0.1 0.1 0.3'}
                for name,text in contents.items():(root/name).write_text(text)
            runner.command=command;runner.add_artifact=lambda *a,**kw:None;runner.save_json=lambda *a:None
            sources=[(c,'spef_'+c) for c in ('min','nom','max')]
            with patch('icstudio.digital_implementation.mapped',return_value={}), \
                patch('icstudio.digital_implementation.timing_script',return_value='fixture'), \
                patch('icstudio.digital_rc.timing_sources',return_value=sources):
                result=timing(runner)
            self.assertEqual(seen,[(p,'spef_'+c) for p in ('tt','ss') for c in ('min','nom','max')])
            self.assertEqual(result['verdict'],'FAIL')
            self.assertEqual(result['timing']['rc_corners'],['min','nom','max'])
            self.assertEqual(result['timing']['corners'][-1]['scenario'],'ss / max')
            self.assertEqual(result['timing']['summary']['hold_worst_slack_ns'],-0.2)
            self.assertTrue((root/'timing-corners/ss/max/timing_paths.tsv').is_file())

    def test_installation_requires_the_complete_passing_extracted_matrix(self):
        from icstudio.digital_qualification import require_timing_coverage
        with tempfile.TemporaryDirectory() as td:
            config=self.fixture(Path(td));platform=config['platform']
            cases=[{'corner':p,'rc_corner':c,'status':'PASS','parasitics':'extracted SPEF'}
                for p in ('tt','ss') for c in ('min','nom','max')]
            result={'digital_result':{'verdict':'PASS','timing':{'corners':cases}}}
            self.assertEqual(require_timing_coverage(result,platform)['interconnect_corners'],['min','nom','max'])
            for fault in ('missing','duplicate','failed','estimate','wrong-rc','summary-fail'):
                bad=clone(result);rows=bad['digital_result']['timing']['corners']
                if fault=='missing':rows.pop()
                elif fault=='duplicate':rows.append(clone(rows[0]))
                elif fault=='failed':rows[-1]['status']='FAIL'
                elif fault=='estimate':rows[-1]['parasitics']='pre-layout estimate'
                elif fault=='wrong-rc':rows[-1]['rc_corner']='other'
                else:bad['digital_result']['verdict']='FAIL'
                with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'every declared'):require_timing_coverage(bad,platform)

    def test_macro_bundle_retains_all_corner_files_and_rejects_a_missing_one(self):
        from icstudio.digital_macro import export
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);project=digital.counter_project();artifacts={}
            for key in ('gds','lef','netlist','checkpoint','def','spef','spef_min','spef_max','log'):
                path=root/(key+'.txt');path.write_text('fixture '+key);artifacts[key]=artifact(root,path)
            path=root/'preview.json';path.write_text(json.dumps({'die':[0,0,2,2],'pins':[]}));artifacts['layout_preview']=artifact(root,path)
            extraction={'schema':1,'status':'complete','def':artifacts['def'],'netlist':artifacts['netlist'],
                'corners':{c:{'spef_key':'spef_'+c,'spef':artifacts['spef_'+c],'inputs':{}} for c in ('min','max')}}
            path=root/'extraction.json';path.write_text(json.dumps(extraction));artifacts['extraction']=artifact(root,path)
            result={'result_type':'digital','project_id':project['id'],'cell_id':project['top'],
                'design_hash':design_digest(project),
                'settings':{'stage':'finish'},'digital_result':{'stage':'finish','source_hash':digital.source_hash(project['digital']),
                    'summary':'fixture','artifacts':artifacts}}
            (root/'input.json').write_text(json.dumps({'project':project,'cell':project['top']}))
            manifest=export(result,root,root/'macro.zip')
            self.assertEqual(set(manifest['interconnect_corners']),{'min','max'})
            with zipfile.ZipFile(root/'macro.zip') as archive:
                for key in ('spef_min','spef_max','extraction','def'):
                    self.assertEqual(archive.read(manifest['artifacts'][key]['path']),(root/artifacts[key]['path']).read_bytes())
            del artifacts['spef_max']
            with self.assertRaisesRegex(ValueError,'missing a captured'):export(result,root,root/'broken.zip')
            self.assertFalse((root/'broken.zip').exists())

    def test_macro_notices_use_captured_files_and_reject_changed_or_missing_notice(self):
        from icstudio.digital_macro import captured_notices
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);staged=root/'platform';staged.mkdir();config=self.fixture(staged)
            names=['LICENSE-Apache.txt','THIRD_PARTY_NOTICES.md','upstream-lock.json']
            for name in names:(staged/name).write_text('captured '+name)
            manifest=config['platform'];manifest['files']+=digital_platform.inventory(staged,names)
            manifest['fingerprint']=digest(manifest['files']);manifest['root']='unavailable/original/pdk'
            project=digital.counter_project();project['digital']=config
            job={'project':project,'cell':project['top']}
            notices=captured_notices(job,root)
            self.assertEqual({r['source_path'] for p,r in notices},set(names))
            self.assertTrue(all(r['path'].startswith('notices/') for p,r in notices))
            path=staged/names[0];path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'missing or changed'):captured_notices(job,root)
            path.unlink()
            with self.assertRaisesRegex(ValueError,'missing or changed'):captured_notices(job,root)


if __name__=='__main__':unittest.main()
