import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import example,device,uid,clone,digest,validate,flatten,save_project,load_project,History
from icstudio.project_manager import ProjectIndex
from icstudio.lifecycle import duplicate_project,relocate_project,relink_assets,replacement,migration_preview
from icstudio.components import configure_component,import_component
from icstudio.spice_import import import_spice
from icstudio.interchange import spice,export_xschem
from icstudio.xschem_io import import_package
from icstudio.osdi import configure,verified,preload
import test_project_pdk

class LifecycleTests(unittest.TestCase):
    def test_copy_is_independent_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            p=example();path=Path(td)/'copy.icproj';q=duplicate_project(p,path)
            self.assertNotEqual(p['id'],q['id']);self.assertEqual(p['cells'],q['cells'])
            q['cells'][0]['devices'][0]['value']='2';self.assertNotEqual(q['cells'],p['cells'])
            before=path.read_bytes()
            with self.assertRaises(FileExistsError):duplicate_project(p,path)
            self.assertEqual(path.read_bytes(),before)

    def test_moved_project_rejects_wrong_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=example();a=root/'a.icproj';b=root/'b.icproj';index=ProjectIndex(root/'index')
            save_project(p,a);index.remember(p,a);a.rename(b);relocate_project(index,a,b)
            self.assertEqual(index.entries()[0]['path'],str(b))
            save_project(example(),a)
            with self.assertRaisesRegex(ValueError,'different project'):relocate_project(index,b,a)

    def test_relocation_and_migration_preserve_connections_and_history(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech=test_project_pdk.ProjectPDKTests().technology(root);p=example('empty');p['pdk']=tech
            d=device('NMOS','M1');bound,_=replacement(tech,d,'nmos_a');p['cells'][0]['devices']=[bound]
            bound['net_labels']={'g':'input'}
            other=clone(tech);other['package_lock']['revision']='r2';other['simulation']['catalog']['nmos_a']['model']='nmos_b'
            original=digest(p);q,report=migration_preview(p,other)
            self.assertEqual(digest(p),original);self.assertEqual(q['cells'][0]['devices'][0]['id'],bound['id'])
            self.assertEqual(q['cells'][0]['devices'][0]['nets'],bound['nets']);self.assertEqual(report[0]['to'],'nmos_b')
            h=History(p);h.commit(lambda c:(c.clear(),c.update(q)));h.undo();self.assertEqual(h.project['pdk']['package_lock']['revision'],'r1')
            relink_assets(p,Path(tech['package_root']))
            with self.assertRaisesRegex(ValueError,'does not match'):relink_assets(p,root/'absent')

    def test_incompatible_model_and_mask_migration_leave_original(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech=test_project_pdk.ProjectPDKTests().technology(root);p=example('empty');p['pdk']=tech
            from icstudio.catalog import create_device
            from icstudio.layout import rect
            p['cells'][0]['devices']=[create_device(tech,'nmos_a','M1')];p['cells'][0]['shapes']=[rect('metal1',0,0,100,100)]
            other=clone(tech);other['package_lock']['revision']='r2';other['layers'][3]['gds']=500
            before=digest(p)
            with self.assertRaisesRegex(ValueError,'mapping'):migration_preview(p,other)
            self.assertEqual(before,digest(p))

    def test_parameterized_spice_component_has_real_electrical_body(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=root/'divider.spice'
            path.write_text('* divider\n.subckt divider in out vss params: r=10k ratio=2\nR1 in out {r * ratio}\nR2 out vss {r}\n.ends divider\n.end\n')
            p=example('empty');cid=import_component(p,path,'divider');child=next(c for c in p['cells'] if c['id']==cid)
            p['cells'][0]['devices']=[device('V','V1',value='3',nets={'p':'supply','n':'0'}),device('X','X1',cell=cid,nets={'in':'supply','out':'out','vss':'0'},parameters={'ratio':'5'})]
            configure_component(p,cid,'divider',['vss','in','out'],child['parameters']);validate(p)
            self.assertEqual(float(flatten(p)[1]['value']),50000)
            from icstudio.simulation import run
            self.assertAlmostEqual(run(p,p['top'],{'type':'op'})['traces']['out'][0],.5,places=6)
            export_xschem(p,root/'x');q,_=import_package(root/'x')
            self.assertEqual(float(flatten(q)[1]['value']),50000)
            self.assertEqual(next(c for c in q['cells'] if c['id']==cid)['ports'],['vss','in','out'])
            self.assertIn('50000',spice(q))
            schematic=root/'x'/'top.sch';schematic.write_text(schematic.read_text().replace('ratio="5"','ratio="3"'))
            edited,_=import_package(root/'x');self.assertEqual(float(flatten(edited)[1]['value']),30000)

    def test_nested_subcircuit_parameters_and_unknown_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'nested.cir';path.write_text('* nested\n.subckt inner a b r=1k\nR1 a b {r}\n.ends\n.subckt outer a b r=2k\nX1 a b inner r={r * 3}\n.ends\nV1 in 0 1\nX1 in 0 outer r=4k\n.op\n.end\n')
            p,_=import_spice(path);self.assertEqual(float(flatten(p)[1]['value']),12000)
            p['cells'][0]['devices'][1]['parameters']['typo']='1'
            with self.assertRaisesRegex(ValueError,'unknown component'):validate(p)

    def test_empty_symbol_is_not_silently_netlisted(self):
        p=example('empty');cid=uid();p['cells'].append({'id':cid,'name':'placeholder','ports':['a'],'devices':[],'shapes':[]});p['cells'][0]['devices']=[device('X','X1',cell=cid,nets={'a':'a'})]
        validate(p)
        with self.assertRaisesRegex(ValueError,'no electrical implementation'):spice(p)

    def test_osdi_missing_modified_and_wrong_platform(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'model with spaces.osdi';path.write_bytes(b'fixture is never loaded')
            p=example('empty');p['pdk']['simulation']={'requires_osdi':True}
            with self.assertRaisesRegex(ValueError,'requires OSDI'):verified(p)
            p['simulation_runtime']={'osdi':configure([path])}
            self.assertIn('pre_osdi runtime-osdi/model-0.osdi',preload(p,'* title\n.end\n',Path(td)))
            self.assertEqual((Path(td)/'runtime-osdi/model-0.osdi').read_bytes(),path.read_bytes())
            with patch('icstudio.osdi.platform.system',return_value='Other'):
                with self.assertRaisesRegex(ValueError,'different platform'):verified(p)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'missing or changed'):verified(p)

    def test_ngspice_does_not_reuse_stale_raw_and_retains_failure_log(self):
        from icstudio.engines import run_ngspice
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=root/'result.raw';raw.write_text('old result')
            p=example();settings={'type':'op'}
            with patch('icstudio.engines.execute',return_value='no simulation output'):
                with self.assertRaisesRegex(ValueError,'no raw file'):run_ngspice(p,p['top'],settings,'ngspice',root)
            self.assertFalse(raw.exists())
            with patch('icstudio.engines.execute',side_effect=RuntimeError('OSDI interface mismatch')):
                with self.assertRaisesRegex(RuntimeError,'interface mismatch'):run_ngspice(p,p['top'],settings,'ngspice',root)
            self.assertIn('OSDI interface mismatch',(root/'engine.log').read_text())
