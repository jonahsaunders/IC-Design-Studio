"""Reject changed devices, indirect fill coupling and stale delivery evidence."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import klayout.db as k
from icstudio.digital_ihp_geometry import conductors, clearance, compare_native, electrical_view
from icstudio.digital_ihp_fill import abstract, validate, verify, RECIPE
from icstudio.digital_physical import DEFAULTS, validate_settings
from icstudio import digital_identity, digital_rc

EXT = '''scale 1000 1 0.5
node "NET000000" 0 1 0 0 m1
substrate "NET000001" 0 0 0 0 psub
node "NET000002" 12 2 2000 2000 m1
node "poly" 0 3 6000 6000 p
cap "NET000002" "poly" 2
device msubckt sg13_lv_nmos 0 0 1 1 l=200 w=84 "NET000001" "NET000002" 400 0 "NET000000" 0 0 "NET000001" 0 0
'''


def inventory():
    return dict(top='block', checkpoint_sha256='c'*64, die_nm=[0,0,100000,100000],
                instances=[dict(master='sg13g2_inv_1',box_nm=[10000,10000,11000,11000]),
                           dict(master='sg13g2_fill_1',box_nm=[50000,50000,51000,51000])],
                nets=[dict(alias=f'NET{i:06d}', net=name, sig_type=kind,
                           wires=[dict(box_nm=box,layer='Metal1')],
                           pins=[dict(box_nm=box,layer='Metal1')])
                      for i,(name,kind,box) in enumerate([
                          ('VDD','POWER',[70000,70000,71000,71000]),
                          ('VSS','GROUND',[80000,80000,81000,81000]),
                          ('signal','SIGNAL',[10000,10000,11000,11000])])])


class IHPNativeFillTests(unittest.TestCase):
    def test_circuit_and_indirect_floating_components_are_protected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'original.ext';path.write_text(EXT)
            result=conductors(path,inventory())
            self.assertEqual(result['floating'],{'poly'})
            self.assertEqual(result['protected_poly'],{'poly'})
            self.assertEqual(result['protected'],{'NET000002'})
            self.assertEqual(compare_native(path,path,inventory())['status'],'cell-capacitance-subnetwork-identical')
            for text in [EXT.replace('0 3 6000','0 4 6000'),
                         EXT.replace('l=200','l=201'), EXT.replace('12 2 2000','13 2 2000'),
                         EXT+'node "FILL008_000000" 0 2 0 0 m1\ncap "poly" "FILL008_000000" 1\n']:
                changed=Path(td)/'filled.ext';changed.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    compare_native(path,changed,inventory())

    def test_device_connected_poly_is_never_classified_as_unused(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'connected.ext';path.write_text(EXT.replace('"NET000002" 400','"poly" 400'))
            result=conductors(path,inventory())
            self.assertNotIn('poly',result['floating'])
            self.assertIn('poly',result['protected'])

    def test_keepout_covers_signal_routes_cells_and_entire_protected_poly(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'original.ext';path.write_text(EXT)
            layout=k.Layout();layout.dbu=.001;cell=layout.create_cell('block')
            cell.shapes(layout.layer(5,0)).insert(k.Box(30000,30000,40000,31000))
            result=clearance(layout,inventory(),conductors(path,inventory()))
            expected=k.Region(k.Box(1000,1000,20000,20000))+k.Region(k.Box(21000,21000,49000,40000))
            self.assertTrue((result^expected.merged()).is_empty())
            self.assertTrue((result & k.Region(k.Box(70000,70000,71000,71000))).is_empty())

    def test_native_labels_require_actual_checkpoint_pin_geometry(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);layout=k.Layout();layout.dbu=.001;cell=layout.create_cell('block')
            for net in inventory()['nets']:
                cell.shapes(layout.layer(8,0)).insert(k.Box(*net['pins'][0]['box_nm']))
            source=directory/'source.gds';layout.write(str(source))
            electrical_view(source,inventory(),directory/'valid.gds')
            changed=inventory();changed['nets'][2]['pins'][0]['box_nm']=[10000,10000,12000,12000]
            with self.assertRaisesRegex(ValueError,'terminal'):
                electrical_view(source,changed,directory/'bad.gds')

    def test_exported_abstract_retains_ports_and_blocks_all_fill_levels(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);layout=k.Layout();layout.dbu=.001;cell=layout.create_cell('block')
            for layer in (8,10,30,50,67,126,134):
                cell.shapes(layout.layer(layer,22)).insert(k.Box(20000,20000,25000,25000))
            gds=directory/'filled.gds';layout.write(str(gds))
            text='MACRO block\n  SIZE 100 BY 100 ;\n  PIN signal\n    DIRECTION INPUT ;\n  END signal\n  OBS\n    LAYER Metal1 ;\n     RECT 0 0 1 1 ;\n  END\nEND block\nEND LIBRARY\n'
            source=directory/'original.lef';source.write_text(text);target=directory/'filled.lef'
            self.assertEqual(abstract(source,target,gds,inventory()),7)
            self.assertEqual(target.read_text().split('  OBS')[0],text.split('  OBS')[0])
            self.assertEqual(target.read_text().count('RECT 20.000 20.000 25.000 25.000 ;'),7)
            self.assertIn('RECT 0 0 1 1 ;',target.read_text())


class IHPFillIntegrationTests(unittest.TestCase):
    def test_settings_reject_conflicting_or_unbounded_scope(self):
        validate_settings(dict(ihp_fill=True,ihp_fill_pattern='dense'))
        for settings in [dict(ihp_fill=1),dict(ihp_fill=True,gf180_fill=True),
                         dict(ihp_fill=True,pdn_tcl='custom'),dict(ihp_fill=True,macro_placement_tcl='custom'),
                         dict(ihp_fill_pattern='dense'),dict(ihp_fill=True,ihp_fill_pattern={})]:
            with self.subTest(settings=settings), self.assertRaises(ValueError):validate_settings(settings)
        config=dict(top='block',files=[],physical={});before=digital_identity.stage_key(config,'finish')
        config['physical']['ihp_fill']=True
        self.assertNotEqual(before,digital_identity.stage_key(config,'finish'))

    def test_timing_refuses_unfilled_input(self):
        r=SimpleNamespace(settings=dict(upstream=dict(artifacts={'spef':{}})),config=dict(physical=dict(ihp_fill=True)))
        with self.assertRaisesRegex(ValueError,'finish'):digital_rc.timing_sources(r)

    def test_platform_policy_requires_captured_resources(self):
        policy=dict(recipe=RECIPE,directory='ihp/fill',preparation_sha256='a'*64)
        platform=dict(name='ihp-sg13g2',ihp_fill=policy,files=[])
        with self.assertRaises(ValueError):validate(platform)
        platform['files']=[dict(path='ihp/fill/preparation.json',sha256='a'*64)];validate(platform)
        platform['name']='gf180'
        with self.assertRaises(ValueError):validate(platform)

    def test_delivery_rejects_changed_model_geometry_settings_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);settings=dict(ihp_fill=True,ihp_fill_pattern='compact')
            config=dict(physical=settings,platform=dict(fingerprint='platform'))
            artifacts={key:dict(path=key,sha256=key) for key in ('gds','spef','lef','netlist')}
            artifacts.update(ihp_fill=dict(path='fill.json'),ihp_fill_file_0=dict(path='audit',sha256='audit'))
            report=dict(schema=1,recipe=RECIPE,status='generated_and_verified',platform_fingerprint='platform',
                        settings={**DEFAULTS,**settings},source={k:artifacts[k] for k in ('spef','netlist')},
                        **{k:artifacts[k] for k in ('gds','spef','lef')},
                        capacitance=dict(status='cell-capacitance-subnetwork-identical'),
                        model_artifacts={'ihp_fill_file_0':artifacts['ihp_fill_file_0']})
            path=root/'fill.json';path.write_text(json.dumps(report));upstream=dict(root=str(root),artifacts=artifacts)
            verify(upstream,config)
            for key,value in [('gds',{}),('spef',{}),('capacitance',{}),('model_artifacts',{})]:
                with self.subTest(key=key):
                    path.write_text(json.dumps({**report,key:value}))
                    with self.assertRaises(ValueError):verify(upstream,config)
            path.write_text(json.dumps(report));config['physical']['ihp_fill_pattern']='dense'
            with self.assertRaises(ValueError):verify(upstream,config)


if __name__=='__main__':unittest.main()
