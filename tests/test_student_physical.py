"""Contracts guarding the real GF180/IHP qualification exercised separately."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.model import clone, digest, file_digest
from icstudio.student_inverter import profile,create,build_layout,context


def technology(variant):
    root=Path(__file__).resolve().parents[1]/'icstudio/assets/pdks'/variant
    m=json.loads((root/'package.json').read_text(encoding='utf-8'));t=m['technology']
    t.update(package_root=str(root),package_lock=dict(id=m['id'],revision=m['revision'],files=m['files'],manifest_hash=digest(m)))
    return t


class StudentPhysicalTests(unittest.TestCase):
    def test_variant_specific_decks_geometry_and_editable_vias(self):
        from icstudio.process_adapters import adapter,audit
        from icstudio.physical_cells import ports
        from icstudio.layout_edit import via_options
        hashes=[]
        for variant in ('gf180mcuC','gf180mcuD','ihp-sg13g2'):
            with self.subTest(variant=variant):
                item=profile(technology(variant));p=create(item);build_layout(p);_,cell=context(p)
                self.assertEqual(p['student_inverter']['profile'],profile(p['pdk'])['token'])
                self.assertEqual({r['name'] for r in ports(p,cell['id'])},{'A','Y','VPWR','VGND'})
                self.assertEqual(audit(p,cell['id']),[])
                self.assertEqual(cell['inverter_layout']['process'],variant)
                self.assertIn('M1 to M2',via_options(p))
                assets=adapter(p['pdk']).engine_assets(p['pdk'])
                self.assertEqual(assets['technology'].name,variant+'.tech')
                hashes.append(file_digest(assets['technology']))
                cell['devices'][0]['params']['w']='1.3u'
                self.assertEqual(audit(p,cell['id'])[0]['code'],'PDK.STALE')
        self.assertEqual(len(set(hashes)),3)

    def test_ihp_rejects_multiple_fingers_and_preserves_lvs_dimensions(self):
        from icstudio.ihp_layout import specification
        from icstudio.native_spice import lvs_defaults
        t=technology('ihp-sg13g2');p=create(profile(t));_,c=context(p);d=c['devices'][0]
        d['model_params']['ng']='2'
        with self.assertRaisesRegex(ValueError,'one finger'):specification(t,d)
        text='Xn Y A 0 0 sg13_lv_nmos w=1u l=.13u ng=1 m=3 mm_ok=1\n'
        actual,changes=lvs_defaults(text,t)
        self.assertNotIn('mm_ok',actual);self.assertIn('w=1u l=.13u ng=1 m=3',actual)
        self.assertEqual(changes[0]['proof']['sha256'],t['package_lock']['files'][changes[0]['proof']['source']])
        for other in (text.replace('mm_ok=1','mm_ok=2'),text.replace('sg13_lv_nmos','unknown'),text.replace('mm_ok=1','mm_ok=1 mm_ok=0')):
            self.assertEqual(lvs_defaults(other,t),(other,[]))
        self.assertEqual(lvs_defaults(text),(text,[]))

    def test_managed_models_require_matching_source_and_generic_cpu(self):
        from icstudio.osdi import managed_models
        t=technology('ihp-sg13g2');rel='psp103/psp103.va'
        report=dict(system='Linux',machine='x86_64',cpu_target='generic',models=[
            dict(output=name+'.osdi',sha256='a'*64,dependencies={rel:t['package_lock']['files']['libs.tech/verilog-a/'+rel]})
            for name in ('psp103','psp103_nqs','r3_cmc','mosvar','cap_cmomi','cap_cmomf')])
        manifest={'osdi':{'ihp-sg13g2':report}}
        self.assertEqual(len(managed_models(t,manifest)),6)
        other=clone(t);other['package_lock']['files']['libs.tech/verilog-a/'+rel]='b'*64
        with self.assertRaisesRegex(ValueError,'do not match'):managed_models(other,manifest)
        report['cpu_target']='native'
        with self.assertRaises(ValueError):managed_models(t,manifest)
        with self.assertRaises(ValueError):managed_models(technology('gf180mcuD'),manifest)

    def test_legacy_encoding_is_allowed_only_in_model_comments(self):
        from icstudio.pdks import stage_model_deck
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'model.spice'
            for data,valid in ((b'* width in \xb5m\n.model n nmos\n',True),(b'.model n\xb5 nmos\n',False)):
                source.write_bytes(data)
                t=dict(package_root=str(root),package_lock={'files':{'model.spice':file_digest(source)}},simulation={'includes':[]})
                text='.include "'+source.as_posix()+'"\n'
                if valid:
                    staged=stage_model_deck(t,text,root/'out');self.assertIn('pdk-models/',staged)
                else:
                    with self.assertRaises(UnicodeDecodeError):stage_model_deck(t,text,root/'bad')


if __name__=='__main__':unittest.main()
