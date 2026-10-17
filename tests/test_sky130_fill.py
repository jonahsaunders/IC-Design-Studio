"""Independent stream and spacing controls for the optional local fill recipe."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import klayout.db as k
from icstudio import digital_sky130_fill as fill
from icstudio.digital_sky130_oxide_density import audit as density
from icstudio.digital_flow import artifact
from icstudio.digital_physical import validate_settings

TECH = b'<technology><reader-options><lefdef><layer-map>layer_map(\'met1.drawing : 68/20\')</layer-map><produce-fills>true</produce-fills><special-fills-suffix-string>.FILL</special-fills-suffix-string></lefdef></reader-options></technology>'


class Sky130FillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.layout = k.Layout(); self.layout.dbu = .001; self.top = self.layout.create_cell('arbitrary_block')
        self.gds = self.root/'layout.gds'
        self.inventory = dict(schema=1, top=self.top.name, checkpoint_sha256='a'*64,
                              die_nm=[0,0,20000,20000], fills={n:[] for n in fill.METALS})
        for i, (name, (layer, _)) in enumerate(fill.METALS.items(), 1):
            box = [2000,2000,4000,3000 if i == 1 else 4000]
            self.inventory['fills'][name].append(box); self.top.shapes(self.layout.layer(layer,28)).insert(k.Box(*box))
        self.save()

    def save(self):
        options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False; self.layout.write(str(self.gds),options)

    def test_all_five_layers_have_nonempty_valid_geometry(self):
        report = fill.geometry(self.gds,self.inventory)
        self.assertEqual(set(report),set(fill.METALS))
        self.assertTrue(all(v['rectangles'] == 1 and not any(v['violations'].values()) for v in report.values()))

    def test_wrong_stream_layer_is_rejected_even_when_native_deck_misses_it(self):
        self.top.shapes(self.layout.layer(41,28)).clear()
        self.top.shapes(self.layout.layer(7,28)).insert(k.Box(2000,2000,4000,4000)); self.save()
        with self.assertRaisesRegex(ValueError,'streamed met2'):fill.geometry(self.gds,self.inventory)

    def test_missing_added_or_changed_rectangles_fail(self):
        for fault in ('missing','extra','changed'):
            with self.subTest(fault=fault):
                inv=copy.deepcopy(self.inventory)
                if fault=='missing':inv['fills']['met3']=[]
                elif fault=='extra':inv['fills']['met3'].append([6000,6000,8000,8000])
                else:inv['fills']['met3'][0][2]+=5
                with self.assertRaises(ValueError):fill.geometry(self.gds,inv)

    def test_real_clearance_and_spacing_faults_are_rejected(self):
        for name,(layer,drawing) in fill.METALS.items():
            with self.subTest(name=name):
                self.top.shapes(self.layout.layer(drawing,20)).insert(k.Box(4050,2000,6000,4000));self.save()
                with self.assertRaisesRegex(ValueError,'geometry failed'):fill.geometry(self.gds,self.inventory)
                self.top.shapes(self.layout.layer(drawing,20)).clear()
        self.top.shapes(self.layout.layer(41,28)).insert(k.Box(4200,2000,6200,4000))
        self.inventory['fills']['met2'].append([4200,2000,6200,4000]);self.save()
        with self.assertRaisesRegex(ValueError,'spacing'):fill.geometry(self.gds,self.inventory)

    def test_offgrid_outside_and_unsupported_shapes_fail(self):
        for box in ([2001,2000,4001,3000],[-2000,2000,0,3000],[2000,2000,3995,3000]):
            with self.subTest(box=box):
                self.top.shapes(self.layout.layer(36,28)).clear();self.top.shapes(self.layout.layer(36,28)).insert(k.Box(*box))
                self.inventory['fills']['met1']=[box];self.save()
                with self.assertRaisesRegex(ValueError,'geometry failed'):fill.geometry(self.gds,self.inventory)

    def test_empty_or_duplicate_database_inventory_cannot_pass(self):
        self.inventory['fills']['met1']*=2
        with self.assertRaisesRegex(ValueError,'duplicate'):fill.geometry(self.gds,self.inventory)
        for name,(layer,_) in fill.METALS.items():
            self.inventory['fills'][name]=[];self.top.shapes(self.layout.layer(layer,28)).clear()
        self.save()
        with self.assertRaisesRegex(ValueError,'no fill'):fill.geometry(self.gds,self.inventory)

    def test_hierarchy_is_compared_in_assembly_coordinates(self):
        newtop=self.layout.create_cell('parent');newtop.insert(k.CellInstArray(self.top.cell_index(),k.Trans(10000,10000)))
        inv=copy.deepcopy(self.inventory);inv.update(top='parent',die_nm=[0,0,30000,30000])
        inv['fills']={n:[[v+10000 for v in b] for b in boxes] for n,boxes in inv['fills'].items()};self.save()
        self.assertEqual(sum(v['rectangles'] for v in fill.geometry(self.gds,inv).values()),5)

    def test_stream_mapping_keeps_original_drawn_layers_and_adds_all_fill_layers(self):
        with patch.object(fill,'LYT_SHA256',hashlib.sha256(TECH).hexdigest()):
            text=fill.technology(TECH);mapping=ET.fromstring(text).findtext('.//lefdef/layer-map')
            self.assertIn('met1.drawing : 68/20',mapping)
            for name,(layer,_) in fill.METALS.items():self.assertIn(name+'.FILL : '+str(layer)+'/28',mapping)
            with self.assertRaisesRegex(ValueError,'unsupported stream'):fill.technology(TECH+b' ')

    def test_abstract_keeps_pins_and_covers_every_fill(self):
        source=self.root/'source.lef'
        source.write_text('MACRO arbitrary_block\n  PIN bus[0]\n  END bus[0]\n  OBS\n  END\nEND arbitrary_block\nEND LIBRARY\n')
        text=fill.abstract(source,self.inventory)
        self.assertIn('PIN bus[0]\n  END bus[0]',text);self.assertEqual(text.count('     RECT '),5)
        self.assertIn('2.000 2.000 4.000 3.000',text)

    def test_no_full_windows_never_means_density_pass(self):
        report=density(self.gds,self.inventory['die_nm'])
        self.assertEqual(fill.density_status(report),'surrounding-layout-required')
        report=density(self.gds,[0,0,700000,700000])
        self.assertEqual(fill.density_status(report),'FAIL')

    def test_setting_is_boolean_and_processes_cannot_be_combined(self):
        validate_settings({'sky130_fill':True})
        for settings in ({'sky130_fill':'true'},{'sky130_fill':True,'gf180_fill':True},{'sky130_fill':True,'ihp_fill':True}):
            with self.assertRaises(ValueError):validate_settings(settings)

    def test_captured_request_cannot_be_stripped(self):
        from icstudio.digital import counter_project
        project=counter_project();project['digital']['physical']={'sky130_fill':True}
        (self.root/'input.json').write_text(json.dumps(dict(project=project,cell=project['top'])))
        data=dict(platform={'name':'sky130hd'},artifacts={},physical={'settings':{}})
        with self.assertRaisesRegex(ValueError,'captured inputs'):fill.validate_saved(data,self.root)
        data['physical']['settings']['sky130_fill']=True
        with self.assertRaisesRegex(ValueError,'missing artifact'):fill.validate_saved(data,self.root)

    def runner(self):
        """Process doubles; physical comparisons still use real GDS polygons."""
        source=self.root/'platform';source.mkdir();(source/'sky130hd.lyt').write_bytes(TECH)
        files={'gds':artifact(self.root,self.gds)}
        for key in ('checkpoint','def','netlist'):
            path=self.root/(key+'.txt');path.write_text('fixture '+key);files[key]=artifact(self.root,path)
        self.inventory['checkpoint_sha256']=files['checkpoint']['sha256']
        path=self.root/'abstract.lef';path.write_text('MACRO arbitrary_block\n  OBS\n  END\nEND arbitrary_block\nEND LIBRARY\n')
        files['lef']=artifact(self.root,path)
        reviewed={'oxide_density':density(self.gds,self.inventory['die_nm'])}
        path=self.root/'reviewed.json';path.write_text(json.dumps(reviewed));files['sky130_rules']=artifact(self.root,path)
        r=SimpleNamespace(root=self.root,platform=dict(name='sky130hd',fingerprint='f'*64,sky130_rules={'fixture':True},
            files=[dict(path='sky130hd.lyt',sha256=hashlib.sha256(TECH).hexdigest())]),
            config={'top':self.top.name},artifacts=files,tools={'openroad':'test-double'})
        r.add_artifact=lambda key,path:r.artifacts.update({key:artifact(r.root,path)})
        def save(key,value,path):
            (r.root/path).write_text(json.dumps(value));r.add_artifact(key,r.root/path)
        r.save_json=save
        def command(args,message,**kwargs):
            if args[0]=='test-double':(r.root/'sky130-fill/inventory.json').write_text(json.dumps(self.inventory))
            else:
                report=fill.geometry(self.gds,self.inventory)
                (r.root/'sky130-fill/geometry.json').write_text(json.dumps(report))
        r.command=command
        return r,reviewed

    def test_retained_fill_report_relocates_and_cannot_lose_abstract_or_mapping(self):
        r,reviewed=self.runner();settings={'sky130_fill':True}
        with patch.object(fill,'LYT_SHA256',hashlib.sha256(TECH).hexdigest()):
            options=fill.implementation_options(r,settings);self.assertIn('USE_FILL=1',options)
            report=fill.execute(r,settings,reviewed)
            data=dict(platform=r.platform,artifacts=r.artifacts,physical=dict(settings=settings,sky130_fill=report))
            self.assertEqual(fill.validate_saved(data,self.root),report)
            for fault in ('sky130_fill_rules','sky130_fill_source_technology','sky130_fill_inventory_json','lef'):
                bad=copy.deepcopy(data);bad['artifacts'].pop(fault)
                with self.subTest(fault=fault),self.assertRaises((ValueError,KeyError)):fill.validate_saved(bad,self.root)
            moved=self.root/'moved';moved.mkdir();relocated=copy.deepcopy(data)
            for index,(key,item) in enumerate(relocated['artifacts'].items()):
                target=moved/(str(index)+Path(item['path']).suffix)
                target.write_bytes((self.root/item['path']).read_bytes());item['path']=target.name
            self.assertEqual(fill.validate_saved(relocated,moved),report)

    def test_consistently_rehashed_changed_fill_policy_is_rejected(self):
        r,reviewed=self.runner();settings={'sky130_fill':True}
        with patch.object(fill,'LYT_SHA256',hashlib.sha256(TECH).hexdigest()):
            fill.implementation_options(r,settings);report=fill.execute(r,settings,reviewed)
            data=dict(platform=r.platform,artifacts=r.artifacts,physical=dict(settings=settings,sky130_fill=report))
            name='sky130_fill_rules';path=self.root/r.artifacts[name]['path'];value=json.loads(path.read_bytes())
            value['layers']['met3']['non-opc']['space_to_fill']=.01;path.write_text(json.dumps(value))
            r.artifacts[name]=artifact(self.root,path);report['evidence'][name]=copy.deepcopy(r.artifacts[name])
            report_path=self.root/r.artifacts['sky130_fill']['path'];report_path.write_text(json.dumps(report))
            r.artifacts['sky130_fill']=artifact(self.root,report_path)
            with self.assertRaisesRegex(ValueError,'changed fill recipe'):fill.validate_saved(data,self.root)

    def test_failed_full_density_window_stops_finish_before_publishing_fill(self):
        r,reviewed=self.runner();settings={'sky130_fill':True}
        self.inventory['die_nm']=[0,0,700000,700000]
        reviewed['oxide_density']=density(self.gds,self.inventory['die_nm'])
        with patch.object(fill,'LYT_SHA256',hashlib.sha256(TECH).hexdigest()):
            fill.implementation_options(r,settings)
            with self.assertRaisesRegex(ValueError,'below 80%'):fill.execute(r,settings,reviewed)
        self.assertNotIn('sky130_fill',r.artifacts)
        self.assertFalse((self.root/'sky130-fill/filled.lef').exists())

    def test_editor_saves_and_removes_fill_choice(self):
        import os,subprocess,sys
        root=Path(__file__).resolve().parents[1]
        process=subprocess.run([sys.executable,'-m','tests.gui_physical_settings',
                                'PhysicalSettingsTests.test_fill_choice','-v'],
            cwd=root,env=dict(os.environ,QT_QPA_PLATFORM='offscreen'),
            capture_output=True,text=True,timeout=60)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)



if __name__=='__main__':unittest.main()
