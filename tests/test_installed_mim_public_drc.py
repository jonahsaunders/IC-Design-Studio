"""Bounded public-DRC raw evidence, scope and native dispatch controls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts import qualify_installed_sky130_mim_public_drc as check


class PublicMimTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.categories=json.loads((check.ROOT/'icstudio/assets/verification/sky130/categories.json').read_text())

    def xml(self, marker=False):
        root=ET.Element('report-database');ET.SubElement(root,'top-cell').text='coupon'
        categories=ET.SubElement(root,'categories')
        for name in self.categories:ET.SubElement(ET.SubElement(categories,'category'),'name').text=name
        items=ET.SubElement(root,'items')
        if marker:ET.SubElement(ET.SubElement(items,'item'),'category').text="'MR_met1.WID.1'"
        return root

    def save(self, root):
        path=self.root/'report.lyrdb';ET.ElementTree(root).write(path);return path

    def test_clean_and_expected_width_raw_counts(self):
        self.assertEqual(check.measured(self.save(self.xml()),'coupon',self.categories),dict(categories=255,markers=0,violations={}))
        self.assertEqual(check.measured(self.save(self.xml(True)),'coupon',self.categories),dict(categories=255,markers=1,violations={'MR_met1.WID.1':1}))

    def test_changed_missing_duplicate_categories_top_and_raw_inventory_reject(self):
        for change in ('top','missing','duplicate','unknown','items','format'):
            with self.subTest(change=change):
                root=self.xml(True)
                if change=='top':root.find('top-cell').text='wrong'
                elif change=='missing':root.find('categories').remove(root.find('categories')[0])
                elif change=='duplicate':root.find('categories')[1].find('name').text=self.categories[0]
                elif change=='unknown':root.find('items/item/category').text='invented'
                elif change=='items':root.remove(root.find('items'))
                else:root.tag='unsupported'
                with self.assertRaises(ValueError):check.measured(self.save(root),'coupon',self.categories)

    def gds(self):
        import klayout.db as db
        layout=db.Layout();layout.dbu=.001;cell=layout.create_cell('coupon')
        cell.shapes(layout.layer(68,20)).insert(db.Box(0,0,2000,2000))
        cell.shapes(layout.layer(68,5)).insert(db.Text('P',1000,1000))
        source=self.root/'original.gds';layout.write(str(source));return source

    def test_fault_changes_only_declared_isolated_shape(self):
        source=self.gds();target=self.root/'fault.gds';check.fault(source,target,'coupon')
        value=check.fault_geometry(source,target,'coupon')
        self.assertEqual(value['width_um'],.1);self.assertEqual(value['required_minimum_um'],.14)
        self.assertEqual(value['required_category'],'MR_met1.WID.1')

    def test_extra_mask_or_label_change_cannot_be_called_width_control(self):
        import klayout.db as db
        source=self.gds();target=self.root/'fault.gds'
        for kind in ('mask','label'):
            with self.subTest(kind=kind):
                check.fault(source,target,'coupon');layout=db.Layout();layout.read(str(target));cell=layout.cell('coupon')
                if kind=='mask':cell.shapes(layout.layer(69,20)).insert(db.Box(0,0,100,100))
                else:cell.shapes(layout.layer(68,5)).insert(db.Text('EXTRA',500,500))
                layout.write(str(target))
                with self.assertRaises(ValueError):check.fault_geometry(source,target,'coupon')

    def test_native_command_keeps_locked_flags_paths_and_wsl_argv(self):
        prefix=['wsl.exe','--distribution','Exact-Distro','--exec']
        args,values=check.command(prefix,'/opt/icstudio/bin/klayout','/var/tmp/stage with spaces/p2-r90','nonce_top')
        self.assertEqual(args[:4],prefix)
        self.assertIn('input=/var/tmp/stage with spaces/p2-r90/input.gds',args)
        self.assertIn('top_cell=nonce_top',args)
        self.assertEqual({k:values[k] for k in check.FLAGS},dict(feol='true',beol='true',offgrid='true',seal='false',floating_met='false',sram_exclude='false',info='false'))
        self.assertEqual(args.count('-rd'),11)
        self.assertIn('/usr/bin/env',args);self.assertIn('-i',args)

    def test_existing_native_stage_is_rejected(self):
        (self.root/'native').mkdir()
        with self.assertRaisesRegex(ValueError,'already exists'):
            check.native_stage(dict(selected=dict(kind='linux',root='/')),self.root,'a'*32)

    def test_mode_does_not_allow_installed_engine_override_or_source_candidate(self):
        for args in ((False,'c'*40,Path('/opt/icstudio/bin/klayout')),(True,'c'*40,Path('/opt/icstudio/bin/klayout')),(False,None,None)):
            with self.subTest(args=args),self.assertRaises(ValueError):
                check.run(self.root,self.root/'new',args[1],args[0],args[2])
        self.assertFalse((self.root/'new').exists())

    def test_rehashed_saved_runtime_cannot_replace_actual_selected_runtime(self):
        binding=dict(mode='source-pilot',supplied_root='irrelevant',expected_commit=None)
        record=dict(schema=1,status='PASS',gate='mim-installed-public-drc',qualified=False,release_ready=False,full_mim_installed=False,
            execution_id='a'*32,execution_root=str(self.root),binding=binding,mode='source-pilot',installed=False,
            policy=dict(flags=check.FLAGS,revision=check.REVISION,scope=check.SCOPE,assets=check.ASSETS),source_files={},assets={},
            runtime_before=dict(selected=dict(kind='linux',root='/wrong')),runtime_after=dict(selected=dict(kind='linux',root='/wrong')),
            source_klayout='/opt/icstudio/bin/klayout')
        (self.root/'record.json').write_text(json.dumps(record))
        with patch.object(check,'sources',return_value={}),patch.object(check,'assets',return_value={}),patch.object(check,'guard'),patch.object(check,'runtime',return_value=dict(selected=dict(kind='linux',root='/actual'))):
            with self.assertRaisesRegex(ValueError,'actual selected GUI runtime'):check.audit(self.root,binding)


if __name__=='__main__':unittest.main()
