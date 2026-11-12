import json,tempfile,unittest
from pathlib import Path
from icstudio import ihp_klayout_lvs as lvs,ihp_npn_rules as rules
from icstudio.model import file_digest,load_project,save_project
from icstudio.pdks import PDKRegistry
from scripts.qualify_standard_mos import load_technology
from scripts.prepare_ihp_npn_qualification import prepare
from scripts.ihp_tap_source import previous_taps
from scripts.qualify_ihp_npn_layouts import CASES,generate,altered,audit_extracted,selected_reference
from scripts.qualify_ihp_resistor_layouts import regions,same_masks,rotated
ROOT=Path(__file__).resolve().parents[1]


class IHPNpnQualificationTests(unittest.TestCase):
    def test_rule_recipe_retains_all_other_rules_and_rejects_changed_source(self):
        source=(ROOT/'icstudio/assets/pdks/ihp-sg13g2'/rules.RELATIVE_PATH).read_bytes();fixed=rules.corrected(source)
        self.assertEqual(fixed.replace(rules.REPLACEMENT,rules.ORIGINAL),source)
        for content in (source+b'\n',fixed,source.replace(b'grow 100',b'grow 99')):
            with self.assertRaises(ValueError):rules.corrected(content)

    def test_package_preserves_models_and_installs_as_separate_revision(self):
        current=ROOT/'icstudio/assets/pdks/ihp-sg13g2'
        source=self.enterContext(previous_taps(current));before=json.loads((source/'package.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'package';result=prepare(source,out);package=json.loads((out/'package.json').read_bytes())
            self.assertNotEqual(result['revision'],before['revision'])
            self.assertEqual(package['technology']['simulation'],before['technology']['simulation'])
            self.assertEqual({n for n,h in before['files'].items() if package['files'][n]!=h},{rules.RELATIVE_PATH})
            registry=PDKRegistry(Path(tmp)/'registry');key=registry.install(out/'package.json');self.assertEqual(registry.verify(key)['revision'],result['revision'])
            self.assertEqual(before,json.loads((source/'package.json').read_bytes()))
            with self.assertRaises(ValueError):prepare(source,out)
            rebuilt=Path(tmp)/'from-current';prepare(current,rebuilt)
            self.assertEqual((out/'package.json').read_bytes(),(rebuilt/'package.json').read_bytes())

    def test_public_geometry_survives_guard_connection_and_roundtrip(self):
        tech,_=load_technology('ihp-sg13g2')
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for i,item in enumerate(CASES):
                p=generate(tech,item,folder/str(i));save_project(p,folder/f'{i}.icproj');same_masks(p,load_project(folder/f'{i}.icproj'))
                from icstudio.layout_import import read_layout
                from icstudio.catalog import link_technology
                original,_=read_layout(folder/str(i)/'native.gds');link_technology(original,tech)
                labels=lambda project:{(t['layer'],t['text'],t['x'],t['y']) for t in project['cells'][0]['layout_texts']}
                self.assertLessEqual(labels(original),labels(p))
                self.assertTrue(any(t['text']=='E' and t['layer']=='TEXT.drawing' for t in p['cells'][0]['layout_texts']))
                q=p
                for _ in range(4):q=rotated(q)
                same_masks(p,q)
                for fault,layer in [('C-open',(6,0)),('B-open',(6,0)),('E-open',(19,0)),('S-open',(6,0)),('C-B-short',(8,0)),('unrelated-diffusion',(1,0)),('unrelated-well',(31,0))]:
                    a,b=regions(p),regions(altered(p,fault));keys=set(a)|set(b)
                    changed={k for k in keys if k not in a or k not in b or not (a[k]^b[k]).is_empty()}
                    self.assertEqual(changed,{layer},(item[0],fault))

    def test_native_parameter_audit_rejects_swapped_ports_dimensions_and_count(self):
        item=CASES[0];text='.SUBCKT coupon C B E S\nX1 C B E S npn13G2l we=70n le=1000n Nx=1 m=1\n.ENDS coupon\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.cir';path.write_text(text);audit_extracted(path,item)
            for bad in (text.replace('C B E S npn','E B C S npn'),text.replace('we=70n le=1000n','we=1000n le=70n'),text.replace('Nx=1','Nx=2'),text.replace('m=1','m=2'),text+text):
                path.write_text(bad)
                with self.assertRaises(ValueError):audit_extracted(path,item)

    def test_private_extractor_and_comparison_edits_are_limited_and_source_locked(self):
        source=ROOT/'icstudio/assets/pdks/ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl';before=source.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);entry,record=lvs.extraction_assets(folder/'deck');relative=record['path'];original=(lvs.SOURCE/relative).read_bytes();changed=(entry.parent/relative).read_bytes()
            self.assertEqual(changed.replace(lvs.BJT_REPLACEMENT,lvs.BJT_ORIGINAL),original)
            self.assertEqual(file_digest(lvs.SOURCE/relative),lvs.BJT_SOURCE_SHA256)
            setup,record=lvs.comparison_setup(source,folder/'setup.tcl');fixed=setup.read_bytes()
            for side in (1,2):self.assertNotIn(f'property "-circuit{side} $dev" delete Nx Ny'.encode(),fixed)
            self.assertIn(b'property "-circuit1 $dev" tolerance {we 0.01} {le 0.01}',fixed)
            self.assertEqual(source.read_bytes(),before)
            setup.write_bytes(fixed+b'\n')
            with self.assertRaises(ValueError):lvs.comparison_setup(setup,folder/'bad.tcl')


if __name__=='__main__':unittest.main()
