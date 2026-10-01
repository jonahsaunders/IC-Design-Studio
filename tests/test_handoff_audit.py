"""Reopen exported native/captured projects after moving their entire handoff."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from icstudio.interchange import export_handoff, import_layout
from icstudio.model import digest, load_project, file_digest
from icstudio.native_migration import review_path
from tests.test_native_migration import divider


class HandoffAuditTests(unittest.TestCase):
    def test_native_and_capture_handoffs_include_models_and_reopen(self):
        from icstudio.xschem_compat import review_project as capture
        from icstudio.native_exchange import review_project as native_review
        for native in (True, False):
            with self.subTest(native=native), tempfile.TemporaryDirectory() as td:
                root=Path(td); source=divider(root/'source', include=True)
                p=(review_path(source) if native else capture(source))['candidate']
                before=digest(p); export_handoff(p,root/'export')
                self.assertEqual(digest(p),before)
                shutil.rmtree(source.parent)
                shutil.move(root/'export',root/'moved café')
                dest=root/'moved café'; q=load_project(dest/'project.icproj')
                self.assertEqual(q['id'],p['id'])
                self.assertIn('.control',(dest/'simulation.cir').read_text())
                self.assertTrue(list(dest.rglob('*.spice')))
                for suffix in ('gds','oas'):
                    physical,_=import_layout(dest/('layout.'+suffix))
                    self.assertEqual(physical['cells'],q['cells'])
                meta=json.loads((dest/'xschem'/('native-exchange.json' if native else 'capture-exchange.json')).read_text())
                top=dest/'xschem'/meta['top']
                record=(native_review if native else capture)(top)
                self.assertEqual(record['errors'],[])
                self.assertEqual(record['candidate']['id'],p['id'])
                report=json.loads((dest/'preservation-report.json').read_text())
                for relative,sha in report['files'].items():
                    self.assertEqual(file_digest(dest/relative),sha,relative)
                self.assertEqual(json.loads((dest/'dependencies.lock.json').read_text())['engine'],'ngspice')

    def test_locked_native_handoff_rebases_exchange_metadata(self):
        from tests.test_catalog_migration import fixture
        from icstudio.catalog_migration import review
        from icstudio.native_exchange import review_project
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech,path=fixture(root)
            p=review(review_path(path)['candidate'],tech)['candidate']
            export_handoff(p,root/'handoff')
            shutil.rmtree(root/'registry');shutil.rmtree(root/'pdk');shutil.rmtree(path.parent)
            shutil.move(root/'handoff',root/'moved')
            dest=root/'moved';meta=json.loads((dest/'xschem/native-exchange.json').read_text())
            record=review_project(dest/'xschem'/meta['top'])
            self.assertEqual(record['errors'],[])
            self.assertEqual(Path(record['candidate']['pdk']['package_root']),dest/'technology/package')


if __name__=='__main__':unittest.main()
