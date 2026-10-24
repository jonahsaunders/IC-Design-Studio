"""Physical preservation, strict provenance and bounded recognition controls."""
import tempfile
import unittest
from pathlib import Path
import klayout.db as k
from icstudio import ihp_varactor_rules as contact, ihp_varactor_context as context
from icstudio.model import file_digest
from scripts.qualify_ihp_varactor_layouts import stream

ROOT=Path(__file__).resolve().parents[1]
PDK=ROOT/'icstudio/assets/pdks/ihp-sg13g2'


class VaractorContextTests(unittest.TestCase):
    def prepare(self, folder, source):
        magic=PDK/'libs.tech/magic'
        assets=dict(technology=magic/'icstudio-ihp-sg13g2.tech')
        assets.update({p.relative_to(PDK).as_posix():p for p in magic.iterdir() if p.is_file()})
        entry, private, _=contact.prepare(assets,folder/'contact', {name:file_digest(path) for name,path in assets.items()})
        return context.prepare(source,'varactor_coupon',entry,private,{str(path):file_digest(path) for path in private.values()},folder/'context')

    def test_small_and_large_all_rotations_preserve_physical_masks_and_annotations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for size,nx in [('small',1),('small',4),('large',10)]:
                for angle in (0,90,180,270):
                    folder=root/f'{size}-{nx}-{angle}';folder.mkdir()
                    source=folder/'source.gds';stream(source,size,nx,angle);before=file_digest(source)
                    result=self.prepare(folder,source);self.assertIsNotNone(result)
                    tech,private,commands,proof=result
                    self.assertEqual(file_digest(source),before)
                    self.assertEqual(proof['comparison']['status'],'passed')
                    self.assertTrue(proof['comparison']['text_presentation_compared'])
                    self.assertEqual(proof['native_grid_nm'],5)
                    self.assertIn('Unqualified native varactor context grid',commands)
                    self.assertEqual(file_digest(tech),context.SOURCES[tech.name])

    def test_missing_recognition_and_incomplete_oxide_do_not_gain_context(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for fault in ('missing-recognition','oxide-gap'):
                folder=root/fault;folder.mkdir();source=folder/'source.gds';stream(source,'large',10,fault=fault)
                self.assertIsNone(self.prepare(folder,source))
                self.assertFalse((folder/'context').exists())

    def test_private_marker_collision_and_transistor_overlap_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for layer in (250,251,26):
                folder=root/str(layer);folder.mkdir();source=folder/'source.gds';stream(source,'large',10)
                ly=k.Layout();ly.read(str(source));cell=ly.top_cell()
                cell.shapes(ly.layer(layer,0)).insert(cell.bbox());ly.write(str(source))
                with self.assertRaisesRegex(ValueError,'collides|TRANS'):
                    self.prepare(folder,source)
                self.assertFalse((folder/'context').exists())

    def test_changed_native_sources_never_receive_a_context_correction(self):
        for name in context.SOURCES:
            source=PDK/'libs.tech/magic'/name
            data=contact.corrected(source.read_bytes()) if name=='ihp-sg13g2-drc.tech' else source.read_bytes()
            context.corrected(name,data)
            with self.assertRaisesRegex(ValueError,'exact locked'):
                context.corrected(name,data+b'\n')

    def test_context_requires_complete_current_dependency_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.gds';stream(source,'large',10)
            with self.assertRaisesRegex(ValueError,'complete validated'):
                context.prepare(source,'varactor_coupon',Path('bad.tech'),{}, {},root/'out')
            self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
