"""Private rule provenance and lossless, explicitly contacted varactor coupons."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k
from icstudio import ihp_varactor_rules as rules
from icstudio.model import file_digest
from scripts.qualify_ihp_varactor_layouts import SOURCES, stream

ROOT=Path(__file__).resolve().parents[1]
PDK=ROOT/'icstudio/assets/pdks/ihp-sg13g2'


class VaractorRuleTests(unittest.TestCase):
    def assets(self):
        folder=PDK/'libs.tech/magic'
        return dict({'technology':folder/'icstudio-ihp-sg13g2.tech'},
                    **{p.relative_to(PDK).as_posix():p for p in folder.iterdir() if p.is_file()})

    def test_private_copy_preserves_originals_and_every_other_dependency(self):
        assets=self.assets();before={name:file_digest(p) for name,p in assets.items()}
        with tempfile.TemporaryDirectory() as tmp:
            entry,private,proof=rules.prepare(assets,Path(tmp)/'private',before)
            self.assertEqual(entry.name,assets['technology'].name)
            self.assertEqual(proof['source_sha256'],before[rules.RULE])
            self.assertEqual(proof['minimum_nm'],160)
            for name,p in private.items():
                source=assets['libs.tech/magic/'+name.removeprefix('ihp-magic/')]
                if source==assets[rules.RULE]:
                    self.assertEqual(file_digest(p),proof['corrected_sha256'])
                    self.assertIn(b'width (pc,varc)/m1 160',p.read_bytes())
                else:self.assertEqual(p.read_bytes(),source.read_bytes())
        self.assertEqual(before,{name:file_digest(p) for name,p in assets.items()})

    def test_unknown_source_and_outside_entry_cannot_gain_correction(self):
        with self.assertRaises(ValueError):rules.corrected((PDK/rules.RULE).read_bytes()+b'\n')
        assets=self.assets();assets['technology']=PDK/'outside.tech'
        with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):rules.prepare(assets,Path(tmp)/'private',{})

    def test_private_copy_rejects_traversal_and_changed_locked_dependencies(self):
        for bad in ('../outside','../../outside','..\\outside','/outside','C:outside'):
            assets=self.assets();assets['libs.tech/magic/'+bad]=assets[rules.RULE]
            with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'Unsafe'):
                rules.prepare(assets,Path(tmp)/'private',{name:file_digest(p) for name,p in assets.items()})
        assets=self.assets();expected={name:file_digest(p) for name,p in assets.items()}
        expected['libs.tech/magic/ihp-sg13g2-cifin.tech']='0'*64
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'changed during copying'):
            rules.prepare(assets,Path(tmp)/'private',expected)

    def test_contacted_coupons_only_add_masks_and_preserve_device_and_pin_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for n in range(1,11):
                for rotation in (0,90,180,270):
                    stream(folder/'old.gds','small',n,rotation)
                    proof=stream(folder/'new.gds','small',n,rotation,contacted=True)
                    a=k.Layout();a.read(str(folder/'old.gds'));b=k.Layout();b.read(str(folder/'new.gds'))
                    ac,bc=a.top_cell(),b.top_cell()
                    for layer in a.layer_indexes():
                        info=a.get_info(layer);j=b.find_layer(info)
                        ar=k.Region(ac.shapes(layer));br=k.Region(bc.shapes(j))
                        self.assertTrue((ar-br).is_empty(),(n,rotation,str(info)))
                        if (info.layer,info.datatype) in ((5,0),(8,2),(63,0)):
                            self.assertTrue((ar^br).is_empty())
                    old_text=sorted((str(a.get_info(i)),s.text.string,s.text.x,s.text.y) for i in a.layer_indexes() for s in ac.shapes(i).each() if s.is_text())
                    new_text=sorted((str(b.get_info(i)),s.text.string,s.text.x,s.text.y) for i in b.layer_indexes() for s in bc.shapes(i).each() if s.is_text())
                    self.assertEqual(old_text,new_text)
                    self.assertEqual(len(proof['contact_additions_nm']['well']),10)
                    self.assertEqual(len(proof['contact_additions_nm']['substrate']),2)
            with self.assertRaises(ValueError):stream(folder/'large.gds','large',1,contacted=True)


if __name__=='__main__':unittest.main()
