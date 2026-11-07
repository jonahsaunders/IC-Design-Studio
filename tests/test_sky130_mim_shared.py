"""Shared lower plates require an unambiguous local contact direction per cap."""
from pathlib import Path
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import klayout.db as db

from icstudio.interchange import export_layout
from icstudio.layout import polygon, rect
from icstudio.sky130_mim2_extract import MODELS, electrodes, shared_contacts
from scripts.qualify_sky130_mim2 import fixture
from tests.test_sky130_devices import technology
from scripts import audit_sky130_mim_shared as audit


def shared_fixture(plate=2, count=2):
    project = fixture(technology(), (2, 10, count), plate=plate)
    model = f'sky130_fd_pr__cap_mim_m3_{plate}'
    cell = project['cells'][0]
    layer = next(row['name'] for row in project['pdk']['layers']
                 if (row['gds'],row['datatype']) == MODELS[model]['bottom'])
    boxes = sorted((polygon(s).bbox() for s in cell['shapes'] if s['layer'] == layer),
                   key=lambda box:box.bottom)
    for first, second in zip(boxes, boxes[1:]):
        cell['shapes'].append(rect(layer, first.left, first.top, first.width(),
                                   second.bottom-first.top, net='N'))
    return project


class SharedMimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def layout(self, plate=2, count=2):
        path = self.root/'source.gds'
        export_layout(shared_fixture(plate, count), path)
        layout = db.Layout();layout.read(str(path))
        return layout

    def check(self, layout, plate=2):
        path = self.root/'check.gds';layout.write(str(path))
        return electrodes(path, 'device_coupon', f'sky130_fd_pr__cap_mim_m3_{plate}')[1]

    def test_both_constructions_and_all_rigid_transforms_preserve_each_unit_axis(self):
        for plate in (1,2):
            for count in (2,3):
                for mirror in (False,True):
                    for angle in range(4):
                        with self.subTest(plate=plate,count=count,mirror=mirror,angle=angle):
                            layout = self.layout(plate,count)
                            layout.top_cell().transform(db.Trans(angle,mirror,123000,-456000))
                            rows = self.check(layout,plate)
                            self.assertEqual(len(rows),count)
                            for row in rows:
                                self.assertEqual(row['axis'],'y' if angle%2 else 'x')
                                self.assertEqual(row['shared_bottom_electrodes'],count)
                                # Top contacts in every OTHER cap are excluded.
                                self.assertEqual(len(row['bottom_contacts']),9 if plate==1 else 1)

    def test_missing_contacts_cannot_borrow_a_different_units_contacts(self):
        for plate in (1,2):
            layout = self.layout(plate);cell=layout.top_cell();spec=MODELS[f'sky130_fd_pr__cap_mim_m3_{plate}']
            caps = db.Region(cell.shapes(layout.layer(*spec['cap']))).merged()
            cuts = cell.shapes(layout.layer(*spec['cut']))
            # Keep all top cuts, but retain only the first unit's external cuts.
            kept = db.Region()
            for cut in db.Region(cuts).each():
                region = db.Region(cut)
                if (region-caps).is_empty() or cut.bbox().top < 10000:kept.insert(cut)
            cuts.clear();cuts.insert(kept)
            with self.subTest(plate=plate),self.assertRaisesRegex(ValueError,'nonempty collinear'):
                self.check(layout,plate)

    def test_ambiguous_corner_and_straddling_contacts_are_rejected(self):
        cases = {'two-electrodes':db.Box(900,11900,1100,12100),
                 'no-electrode':db.Box(3900,11900,4100,12100),
                 'bottom-straddle':db.Box(-600,11900,-400,12100),
                 'marker-straddle':db.Box(-100,500,100,700)}
        for name, cut in cases.items():
            layout=self.layout(1);layout.top_cell().shapes(layout.layer(70,44)).insert(cut)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'exactly one electrode|straddles'):
                self.check(layout,1)

    def test_collinear_projection_accepts_endpoint_contact_without_nearest_heuristic(self):
        layout=self.layout(1);shapes=layout.top_cell().shapes(layout.layer(70,44))
        shapes.insert(db.Box(3000,-200,3200,0))
        rows=self.check(layout,1)
        self.assertEqual(sorted(len(r['bottom_contacts']) for r in rows),[9,10])
        self.assertTrue(all(r['axis']=='x' for r in rows))
        # Same-distance corner has no unique source-defined axis projection.
        shapes.insert(db.Box(3000,-405,3200,-205))
        with self.assertRaisesRegex(ValueError,'exactly one electrode'):self.check(layout,1)

    def test_unique_ownership_with_conflicting_axes_is_still_ambiguous(self):
        caps=db.Region(db.Box(0,0,2000,10000))+db.Region(db.Box(10000,20000,12000,30000))
        bottom=db.Region(db.Box(-1000,-1000,16000,34000))
        cuts=db.Region(db.Box(3000,4000,3200,4200))+db.Region(db.Box(13000,24000,13200,24200))
        result=shared_contacts(bottom,caps,cuts)
        self.assertEqual({axis for axis,_ in result.values()},{'x'})
        cuts.insert(db.Box(900,11000,1100,11200))
        with self.assertRaisesRegex(ValueError,'nonempty collinear'):
            shared_contacts(bottom,caps,cuts)

    def test_separated_ordinary_units_keep_the_existing_metadata(self):
        for plate in (1,2):
            path=self.root/'isolated.gds';export_layout(fixture(technology(),(2,10,2),plate=plate),path)
            _,rows=electrodes(path,'device_coupon',f'sky130_fd_pr__cap_mim_m3_{plate}')
            self.assertEqual(len(rows),2)
            self.assertTrue(all(r['axis']=='x' and 'shared_bottom_electrodes' not in r for r in rows))


class SharedMimReaderTests(unittest.TestCase):
    """Mutate authentic native output, independently of the orientation code."""
    fixture=Path(__file__).parent/'fixtures/sky130-mim-shared-v1'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'evidence';shutil.copytree(self.fixture,self.root)
        self.directory=self.root/'job/lvs-extraction'

    def test_authentic_native_fixture_and_source_hashes(self):
        source=json.loads((self.root/'SOURCE.json').read_text(encoding='utf-8'))
        for name,digest in source['files'].items():self.assertEqual(audit.sha(self.root/name),digest)
        result=audit.native(self.root,1,90)
        self.assertEqual((result['intrinsic_units'],result['normalization_changes']),(2,2))

    def test_missing_duplicate_or_wrong_native_unit_is_rejected(self):
        source=(self.directory/'native-original.ext').read_text(encoding='utf-8')
        line=next(line for line in source.splitlines(True) if line.startswith('device '))
        for label,text in (('missing',source.replace(line,'')),('duplicate',source+line),
                           ('wrong-width',source.replace('w=1000','w=900',1)),
                           ('wrong-polarity',source.replace('"None" "P"','"None" "N"',1))):
            with self.subTest(label=label):
                (self.directory/'native-original.ext').write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):audit.native(self.root,1,90)
        (self.directory/'native-original.ext').write_text(source,encoding='utf-8')

    def test_changed_non_dimension_values_are_rejected(self):
        path=self.directory/'device_coupon.ext';text=path.read_text(encoding='utf-8')
        path.write_text(text.replace('5991.14','5992.14'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'non-device'):audit.native(self.root,1,90)

    def test_graph_requires_ports_substrate_technology_and_no_unknown_records(self):
        text=(self.directory/'native-original.ext').read_text(encoding='utf-8')
        for label,bad in (
                ('missing-substrate',''.join(line for line in text.splitlines(True) if not line.startswith('substrate '))),
                ('missing-port',''.join(line for line in text.splitlines(True) if not line.startswith('port '))),
                ('duplicate-port-index',text.replace('port "N" 2','port "N" 1')),
                ('unknown-record',text+'resistor "P" "N" 1\n'),
                ('foreign-technology',text.replace('tech sky130A','tech unrelated')),
                ('substrate-capacitance',text.replace('substrate "SUB" 0 0','substrate "SUB" 0 9'))):
            with self.subTest(label=label),self.assertRaises(ValueError):
                audit.raw_graph(bad,'sky130_fd_pr__cap_mim_m3_1',1)

    def test_exported_graph_rejects_wrong_count_duplicate_names_and_opposite_polarity(self):
        path=self.directory/'extracted.spice';original=path.read_text(encoding='utf-8')
        model='sky130_fd_pr__cap_mim_m3_1'
        bodies=(f'X1 P N {model} w=2 l=10',
                f'X1 P N {model} w=2 l=10\nx1 P N {model} w=2 l=10',
                f'X1 N P {model} w=2 l=10 m=2',
                f'X1 P N {model} w=2 l=10 m=3\nX2 P N {model} w=2 l=10 m=-1')
        for body in bodies:
            with self.subTest(body=body):
                path.write_text('.subckt device_coupon P N\n'+body+'\n.ends\n',encoding='utf-8')
                with self.assertRaises(ValueError):audit.native(self.root,1,90)
        path.write_text(original,encoding='utf-8')

    def test_rebound_proof_cannot_hide_an_orientation_or_contact_ownership_change(self):
        path=self.directory/'mim-orientation.json';original=path.read_text(encoding='utf-8')
        for field,value in (('axis','x'),('bottom_contacts',[]),('model','sky130_fd_pr__cap_mim_m3_2')):
            proof=json.loads(original);proof['electrodes'][0][field]=value
            path.write_text(json.dumps(proof),encoding='utf-8')
            with self.subTest(field=field),self.assertRaises(ValueError):audit.native(self.root,1,90)

    def test_counterbalanced_double_owned_and_unowned_contacts_are_rejected(self):
        layout=db.Layout();layout.dbu=.001;top=layout.create_cell('device_coupon')
        for box in (db.Box(0,0,2000,10000),db.Box(10000,0,12000,10000)):
            top.shapes(layout.layer(97,44)).insert(box)
        top.shapes(layout.layer(71,20)).insert(db.Box(-3000,-1000,15000,15000))
        for box in (db.Box(-1000,1000,-800,1200),db.Box(14000,12000,14200,12200)):
            top.shapes(layout.layer(71,44)).insert(box)
        path=self.root/'counterbalanced.gds';layout.write(str(path))
        with self.assertRaisesRegex(ValueError,'exactly one owner'):audit.geometry(path,2,0)

    def test_file_and_source_inventory_fail_closed(self):
        report={'status':'OBSERVED','qualified':False,'installed_acceptance':False,
                'source_files':{'source':'a'},'files':audit.inventory(self.root)}
        path=self.root/'report.json';path.write_text(json.dumps(report),encoding='utf-8')
        with patch.object(audit,'source_files',return_value={'source':'b'}),self.assertRaisesRegex(ValueError,'source guard'):
            audit.verify(self.root)
        (self.directory/'extracted.spice').write_text('changed',encoding='utf-8')
        with patch.object(audit,'source_files',return_value={'source':'a'}),self.assertRaisesRegex(ValueError,'file inventory'):
            audit.verify(self.root)
        report['files']={};path.write_text(json.dumps(report),encoding='utf-8')
        with patch.object(audit,'source_files',return_value={'source':'a'}),self.assertRaisesRegex(ValueError,'file inventory'):
            audit.verify(self.root)

    def test_public_drc_requires_actual_categories_settings_and_command(self):
        from icstudio.digital_sky130_native import resources,FLAGS,DECK_SHA256,REVISION
        folder=self.root/'p1-positive-0';directory=folder/'public-drc';directory.mkdir(parents=True)
        for name in ('sky130A_mr.drc','categories.json','GPL-3.0.txt'):
            shutil.copyfile(resources()/name,directory/name)
        xml=ET.Element('report-database');ET.SubElement(xml,'top-cell').text='device_coupon'
        categories=ET.SubElement(xml,'categories');ET.SubElement(xml,'items')
        for name in json.loads((directory/'categories.json').read_bytes()):
            ET.SubElement(ET.SubElement(categories,'category'),'name').text=name
        xmlpath=directory/'report.lyrdb';ET.ElementTree(xml).write(xmlpath)
        settings=dict(input='/original/p1-positive-0/job/layout.gds',top_cell='device_coupon',
                      report='/original/p1-positive-0/public-drc/report.lyrdb',thr='1',**FLAGS)
        command=['/opt/klayout','-b','-r','/original/p1-positive-0/public-drc/sky130A_mr.drc']
        for key,value in settings.items():command+=['-rd',key+'='+value]
        commandpath=directory/'command.json';commandpath.write_text(json.dumps(command),encoding='utf-8')
        (directory/'console.log').write_text('release 2026.03.30_01.00\n',encoding='utf-8')
        public=dict(violations=0,categories=255,rules={},source_commit=REVISION,deck_sha256=DECK_SHA256,settings=settings)
        audit.public_drc(folder,public,'/opt/klayout')
        command[command.index('beol=true')]='beol=false';commandpath.write_text(json.dumps(command),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'command'):audit.public_drc(folder,public,'/opt/klayout')
        command[command.index('beol=false')]='beol=true';commandpath.write_text(json.dumps(command),encoding='utf-8')
        settings['beol']='false'
        with self.assertRaisesRegex(ValueError,'settings'):audit.public_drc(folder,public,'/opt/klayout')
        settings['beol']='true';categories.clear();ET.ElementTree(xml).write(xmlpath)
        with self.assertRaisesRegex(ValueError,'categories'):audit.public_drc(folder,public,'/opt/klayout')
