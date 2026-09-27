import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from icstudio.model import example,clone,file_digest
from icstudio.physical_backend import stage,receive,prepare


class PhysicalBackendTests(unittest.TestCase):
    def test_missing_setup_is_a_queued_blocked_report_with_bench_identity(self):
        from tests.test_silicon import technology
        from icstudio.sky130_layout import reference_project
        from icstudio.ring_oscillator import reference
        from icstudio.silicon_flow import job as run_job
        p,cid=reference_project(technology())
        hierarchy,hcid,bench=reference(technology())
        for project,cell,testbench in ((p,cid,None),(hierarchy,hcid,bench)):
            for locked in (False,True):
                project['pdk']['package_lock']['files']={'dummy.tech':'0'*64} if locked else {}
                settings={'type':'silicon','tools':{}}
                if testbench:settings['testbench']=testbench
                request={'project':project,'cell':cell,'settings':settings}
                with patch('icstudio.physical_backend.os.name','nt'),patch('icstudio.physical_backend.available',return_value=None):
                    self.assertIs(prepare(request),request)
                self.assertNotIn('physical_runtime',settings)
                with tempfile.TemporaryDirectory() as tmp:
                    result=run_job(project,cell,settings,tmp,lambda *_:None)
                    report=result['silicon_report']
                    self.assertEqual(report['status'],'blocked')
                    self.assertEqual(report['error'],settings['physical_blocked_reason'])
                    self.assertTrue(all(s['status']=='not_run' for s in report['stages'][1:]))
                    self.assertEqual(report.get('testbench_id'),testbench)
                    self.assertEqual(len(report['stages']),8 if testbench else 7)

    def test_included_selection_uses_linux_and_wsl_even_with_saved_custom_paths(self):
        p=example('empty');p['pdk']['package_lock']={'files':{'process.tech':'0'*64}}
        for kind in ('linux','wsl'):
            runtime={'kind':kind,'root':'runtime root','sha256':'a'*64}
            for config in ({},{'magic':'saved custom magic','netgen':'saved custom netgen'}):
                job={'project':p,'settings':{'type':'silicon','tools':config,'physical_toolchain':'included'}}
                with patch('icstudio.physical_backend.available',return_value=runtime):
                    self.assertIs(prepare(job),job)
                self.assertEqual(job['settings']['physical_runtime'],runtime)
                self.assertEqual(job['settings']['tools'],config)

    def test_custom_selection_never_reuses_an_included_runtime(self):
        for mode,tools in (('custom',{}),('auto',{'magic':'configured executable'})):
            job={'settings':{'type':'silicon','tools':tools,'physical_toolchain':mode,
                             'physical_runtime':{'kind':'linux'},'physical_blocked_reason':'old failure'}}
            with patch('icstudio.physical_backend.available',side_effect=AssertionError('Custom selection must not inspect the included runtime.')):
                self.assertIs(prepare(job),job)
            self.assertNotIn('physical_runtime',job['settings'])
            self.assertNotIn('physical_blocked_reason',job['settings'])
            self.assertEqual(job['settings']['tools'],tools)

    def test_locked_pdk_transfer_rebases_only_infrastructure(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'PDK with spaces';source.mkdir()
            (source/'process.tech').write_text('locked process')
            p=example('empty');p['pdk'].update(package_root=str(source),package_lock={'files':{'process.tech':file_digest(source/'process.tech')}})
            p['cells'][0]['annotations']=[{'id':'note','x':0,'y':0,'text':'/windows/path is circuit documentation'}]
            job={'project':p,'cell':p['top'],'settings':{'type':'silicon','physical_runtime':{'kind':'wsl'}}}
            original=clone(job)
            actual=stage(job,root/'work','/var/tmp/job','/')
            self.assertEqual(job,original)
            self.assertEqual(actual['project']['cells'],p['cells'])
            self.assertEqual(actual['project']['pdk']['package_root'],'/var/tmp/job/pdk')
            self.assertEqual((root/'work/pdk/process.tech').read_text(),'locked process')
            (source/'process.tech').write_text('changed process')
            with self.assertRaisesRegex(ValueError,'changed'):stage(job,root/'second','/var/tmp/job','/')
            for relative in ('../outside','C:/outside','/outside','nested\\outside'):
                job['project']['pdk']['package_lock']['files']={relative:'0'*64}
                with self.subTest(relative=relative),self.assertRaisesRegex(ValueError,'Unsafe'):
                    stage(job,root/'second','/var/tmp/job','/')

    def test_returned_evidence_cannot_be_changed_added_or_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'native';source.mkdir()
            file=source/'report.json';file.write_text('{"status":"failed"}')
            lock={'report.json':file_digest(file)}
            (source/'physical-artifacts.json').write_text(json.dumps(lock))
            self.assertEqual(receive(source,root/'host'),lock)
            file.write_text('{"status":"passed"}')
            with self.assertRaisesRegex(ValueError,'changed'):receive(source,root/'host')
            file.unlink()
            with self.assertRaisesRegex(ValueError,'changed'):receive(source,root/'host')


if __name__=='__main__':unittest.main()
