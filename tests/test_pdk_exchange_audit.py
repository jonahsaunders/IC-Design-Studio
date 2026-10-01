"""Independent reimport of generated process symbols and portable handoffs."""
from pathlib import Path
import shutil
import tempfile
import unittest

from icstudio.model import clone,load_project,file_digest
from icstudio.interchange import export_xschem,export_handoff,import_layout
from icstudio.native_migration import review
from icstudio.xschem_compat import review_project
from icstudio.pdks import model_lines
from icstudio.student_inverter import profile
from scripts.verify_release_pdks import circuit
from tests.test_student_physical import technology

VARIANTS=('sky130A','gf180mcuC','gf180mcuD','ihp-sg13g2')


def core_projects(tech,root):
    item=profile(tech);p=circuit(tech,item['models']['NMOS'],item['spec']['supply'])
    source=Path(root)/'source';export_xschem(p,source)
    # Remove Studio's round-trip shortcut: the actual exported symbols and
    # schematic must independently describe a usable circuit and LVS format.
    (source/'project.icproj').unlink();path=source/'top.sch'
    text=path.read_text().replace('S {}','S {'+'\n'.join(model_lines(tech))+
                                '\n.control\nlet audit=1\nop\n.endc\n}')
    path.write_text(text)
    record=review_project(path,technology=tech)
    if record['errors']:raise ValueError(record['errors'])
    capture=record['candidate'];record=review(capture)
    if not record['candidate']:raise ValueError(record['items'])
    return item,capture,record['candidate']


class PDKExchangeAuditTests(unittest.TestCase):
    def test_all_variants_reimport_without_metadata_and_survive_moved_handoffs(self):
        from icstudio.native_exchange import review_project as native_review
        from icstudio.source_assets import source_bytes
        import json
        for variant in VARIANTS:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as td:
                root=Path(td);tech=technology(variant);_,capture,native=core_projects(tech,root)
                self.assertEqual(capture['pdk'],tech)
                self.assertEqual(native['pdk'],tech)
                self.assertEqual(capture['xschem_exchange']['mode'],'compatible')
                encoded=[(path,asset) for path,asset in capture['xschem_exchange']['source_files'].items() if asset.get('encoding')=='latin-1']
                if variant=='ihp-sg13g2':self.assertTrue(encoded)
                for path,asset in encoded:self.assertEqual(source_bytes(asset),Path(path).read_bytes())
                shutil.rmtree(root/'source')
                for mode,p,reader in [('capture',capture,review_project),('native',native,native_review)]:
                    export_handoff(p,root/mode);dest=root/(mode+' moved café');shutil.move(root/mode,dest)
                    q=load_project(dest/'project.icproj')
                    for suffix in ('gds','oas'):
                        physical,_=import_layout(dest/('layout.'+suffix));self.assertEqual(physical['cells'],q['cells'])
                    meta=json.loads((dest/'xschem'/(mode+'-exchange.json')).read_text())
                    reopened=reader(dest/'xschem'/meta['top'])
                    self.assertEqual(reopened['errors'],[],reopened['errors'])
                    self.assertEqual(reopened['candidate']['id'],p['id'])
                    report=json.loads((dest/'preservation-report.json').read_text())
                    for rel,sha in report['files'].items():self.assertEqual(file_digest(dest/rel),sha,rel)

    def test_latin1_model_provenance_still_rejects_edits(self):
        from icstudio.xschem_project import Reader
        from icstudio.source_assets import source_hash,source_bytes
        from icstudio.xschem_runtime import netlist
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);model=root/'legacy.lib';original=b'* width in \xb5m\r\n.model n nmos level=1\r\n';model.write_bytes(original)
            reader=Reader(root/'top.sch',[],None);reader.read(model,'Model / include');asset=reader.files[model]
            self.assertEqual(source_bytes(asset),original);self.assertEqual(source_hash(asset),file_digest(model))
            from tests.test_xschem_compatible import fixture
            path=fixture(root/'circuit','.control\nlet audit=1\nop\n.endc')
            p=review_project(path)['candidate'];p['xschem_exchange']['source_files'][str(model)]=clone(asset)
            p['xschem_exchange']['source_files'][str(model)]['text']+='* changed'
            with self.assertRaisesRegex(ValueError,'recorded identity'):netlist(p,root/'run')
            self.assertIsNone(review(p)['candidate'])


if __name__=='__main__':unittest.main()
