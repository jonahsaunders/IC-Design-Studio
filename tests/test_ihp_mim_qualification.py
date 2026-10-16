import hashlib,json,tempfile,unittest
from pathlib import Path
from icstudio.ihp_mim_rules import RELATIVE_PATH,BASE_SHA256,CORRECTED_SHA256,ORIGINAL,REPLACEMENT,corrected
from icstudio.layout import rect
from icstudio.model import clone
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_ihp_mim_layout import spacing_oracle,rotate,altered
from scripts.prepare_ihp_mim_qualification import prepare
from icstudio.pdks import PDKRegistry

ROOT=Path(__file__).resolve().parents[1]


class IHPMimQualificationTests(unittest.TestCase):
    def project(self):
        tech,_=load_technology('ihp-sg13g2');ls={(r['gds'],r['datatype']):r['name'] for r in tech['layers']}
        return {'pdk':tech,'cells':[{'shapes':[rect(ls[36,0],-3500,-3500,7000,7000),
            rect(ls[126,0],-3300,-3300,6600,6600),rect(ls[129,0],-210,-210,420,420)],
            'layout_texts':[],'layout_ports':[]}]}

    def test_boundary_oracle_and_rotation(self):
        p=self.project();self.assertEqual(spacing_oracle(p)['status'],'PASS')
        for distance,expected in ((595,'FAIL'),(600,'PASS'),(605,'PASS')):
            for q in (altered(p,'unrelated-'+str(distance)),rotate(altered(p,'unrelated-'+str(distance)))):
                with self.subTest(distance=distance):self.assertEqual(spacing_oracle(q)['status'],expected)

    def test_disconnected_and_missing_contacts_do_not_inherit_connected_exemption(self):
        p=self.project();self.assertEqual(spacing_oracle(altered(p,'missing-contacts'))['status'],'FAIL')
        # Keep one contacted top plate and place a separate conductor over the
        # same MIM. Merely having a valid contact somewhere must not exempt it.
        p['cells'][0]['shapes'][1]['points']=[[-300,-300],[300,-300],[300,300],[-300,300]]
        layer=p['cells'][0]['shapes'][1]['layer'];p['cells'][0]['shapes'].append(rect(layer,2000,2000,500,500))
        self.assertEqual(spacing_oracle(p)['status'],'FAIL')

    def test_missing_input_masks_are_rejected(self):
        p=self.project();p['cells'][0]['shapes']=[]
        with self.assertRaisesRegex(ValueError,'Missing'):spacing_oracle(p)

    def test_exact_correction_preserves_the_rule_and_limit(self):
        source=(ROOT/'icstudio/assets/pdks/ihp-sg13g2'/RELATIVE_PATH).read_bytes();fixed=corrected(source)
        self.assertEqual(hashlib.sha256(source).hexdigest(),BASE_SHA256)
        self.assertEqual(hashlib.sha256(fixed).hexdigest(),CORRECTED_SHA256)
        self.assertEqual(fixed.replace(REPLACEMENT,ORIGINAL),source)
        self.assertIn(b'templayer metal6_spacing_to_mimcap metal6\n\tand-not metal6_connects_mimcap\n\tgrow 600\n\tand mimcap',fixed)
        for bad in (source+b'\n',fixed,source.replace(b'grow 600',b'grow 599')):
            with self.assertRaises(ValueError):corrected(bad)

    def test_package_installs_without_changing_original_models_or_licenses(self):
        source=ROOT/'icstudio/assets/pdks/ihp-sg13g2';original=json.loads((source/'package.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'adapter';result=prepare(source,out);p=json.loads((out/'package.json').read_bytes())
            self.assertNotEqual(result['revision'],original['revision'])
            self.assertEqual(p['technology']['simulation'],original['technology']['simulation'])
            expected=clone(original['technology']);expected['revision']=p['revision']
            self.assertEqual(p['technology'],expected)
            self.assertEqual({k for k,v in original['files'].items() if p['files'][k]!=v},{RELATIVE_PATH})
            registry=PDKRegistry(Path(tmp)/'registry');key=registry.install(out/'package.json');self.assertEqual(registry.verify(key)['revision'],result['revision'])
            self.assertEqual(original,json.loads((source/'package.json').read_bytes()))
            with self.assertRaisesRegex(ValueError,'new'):prepare(source,out)
            (out/RELATIVE_PATH).write_bytes((out/RELATIVE_PATH).read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'checksum'):registry.install(out/'package.json')


if __name__=='__main__':unittest.main()
