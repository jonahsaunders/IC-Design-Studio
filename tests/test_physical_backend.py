import json
from pathlib import Path
import tempfile
import unittest
from icstudio.model import example,clone,file_digest
from icstudio.physical_backend import stage,receive


class PhysicalBackendTests(unittest.TestCase):
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
