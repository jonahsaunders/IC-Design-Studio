"""Legacy MIM symbols and metal-stack models need different library sections."""
import json,re,unittest
from pathlib import Path
from icstudio.pdk_import import scan_local
from scripts.qualify_standard_mos import load_technology
from icstudio.pdks import model_lines

ROOT=Path(__file__).resolve().parents[1]


class GF180MimModelSelectionTests(unittest.TestCase):
    def test_registered_and_bundled_packages_load_both_mim_families(self):
        for target in ('gf180mcuC','gf180mcuD'):
            folder=ROOT/'icstudio/assets/pdks'/target
            registered=scan_local(folder)['technology']['simulation']['includes']
            tech,_=load_technology(target)
            self.assertEqual(registered,tech['simulation']['includes'])
            for corner,suffix in [('nominal','typical'),('ss','ss'),('ff','ff'),('fs','typical'),('sf','typical')]:
                with self.subTest(target=target,corner=corner):
                    lines=model_lines(tech,corner)
                    self.assertEqual(sum(line.endswith(' cap_mim') for line in lines),1)
                    self.assertEqual(sum(line.endswith(' mimcap_'+suffix) for line in lines),1)

    def test_legacy_section_contains_every_legacy_catalog_model(self):
        for target in ('gf180mcuC','gf180mcuD'):
            folder=ROOT/'icstudio/assets/pdks'/target
            text=(folder/'libs.tech/ngspice/sm141064.ngspice').read_text()
            section=re.search(r'(?ims)^\.lib cap_mim\s*$\n(.*?)^\.endl cap_mim\s*$',text)[1]
            models=set(re.findall(r'(?im)^\.subckt\s+(\S+)',section))
            catalog=json.loads((folder/'package.json').read_bytes())['technology']['simulation']['catalog']
            for symbol in ('cap_mim_1f0fF','cap_mim_1f5fF','cap_mim_2f0fF','cap_mim_2p0fF'):
                self.assertIn(catalog['symbols/'+symbol+'.sym']['model'].lower(),{m.lower() for m in models})
            self.assertNotIn(catalog['symbols/cap_mim_analog.sym']['model'].lower(),{m.lower() for m in models})


if __name__=='__main__':unittest.main()
