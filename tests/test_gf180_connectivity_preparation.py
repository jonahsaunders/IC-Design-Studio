"""Complete collateral capture and C/D profile binding, without native claims."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import klayout.db as k

from icstudio import digital_gf180_checks, digital_platform
from icstudio.model import file_digest
from scripts import prepare_gf180_connectivity as prep


class GF180ConnectivityPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.library=self.root/'library';self.rules=self.root/'rules';self.base=self.root/'platform'
        for p in (self.library,self.rules,self.base):p.mkdir()
        self.master='gf180mcu_fd_sc_mcu9t5v0__inv_1';self.cdl='cells/inv/'+self.master+'.cdl';self.gds='cells/inv/'+self.master+'.gds'
        (self.library/'cells/inv').mkdir(parents=True)
        (self.library/self.cdl).write_text('.SUBCKT '+self.master+' A Z VDD VSS\nM0 Z A VSS VSS nfet_05v0 W=1u L=.5u\n.ENDS\n',encoding='utf-8')
        layout=k.Layout();layout.dbu=.001;cell=layout.create_cell(self.master);cell.shapes(layout.layer(34,0)).insert(k.Box(0,0,1000,1000));layout.write(str(self.library/self.gds))
        for name in ('LICENSE','README.rst'):(self.library/name).write_text('Synthetic fixture attribution',encoding='utf-8')
        self.lock=dict(revision='a'*40,views={self.master:{'.cdl':self.cdl,'.gds':self.gds}},
            files={name:dict(sha256=file_digest(self.library/name)) for name in (self.cdl,self.gds,'LICENSE','README.rst')})
        self.lock_path=self.root/'library-lock.json';self.write_lock()
        self.rule_lock=copy.deepcopy(digital_gf180_checks.LOCK);self.rule_lock['files']={}
        for name in ('LICENSE','AUTHORS','klayout/lvs/gf180mcu.lvs'):
            path=self.rules/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Synthetic rule fixture',encoding='utf-8')
            self.rule_lock['files'][name]=file_digest(path)
        self.addCleanup(patch.stopall)
        patch.object(prep,'LIBRARY_LOCK',self.lock_path).start();patch.object(prep,'RULE_LOCK',self.rule_lock).start()
        patch.object(digital_gf180_checks,'LOCK',self.rule_lock).start()
        (self.base/'cells.lib').write_text('Synthetic captured library',encoding='utf-8')

    def write_lock(self):self.lock_path.write_text(json.dumps(self.lock),encoding='utf-8')

    def platform(self,name='gf180'):
        raw=dict(version=1,name=name,revision='synthetic-test',corner='tt',corners={'tt':['cells.lib']},files=['cells.lib'],
            orfs=dict(variables=dict(TRACK_OPTION='9t',METAL_OPTION='5LM_1TM',POWER_OPTION='5v0',KVALUE='9' if name=='gf180' else '11')))
        path=self.base/'platform.json';path.write_text(json.dumps(raw),encoding='utf-8')
        return digital_platform.read_manifest(path)

    def test_complete_staging_and_both_stack_bindings_preserve_source_profiles(self):
        destination=self.base/'verification';record=prep.prepare(self.library,self.rules,destination)
        self.assertFalse(record['qualified']);self.assertEqual(record['masters'],1)
        original=self.platform();before=copy.deepcopy(original)
        c=prep.attach(original,destination);d=prep.attach(self.platform('gf180d'),destination)
        self.assertEqual(original,before);self.assertEqual(c['fingerprint'],d['fingerprint'])
        self.assertNotEqual(c['fingerprint'],original['fingerprint'])
        self.assertEqual(c['lvs_reference']['masters'][self.master],'verification/library/'+self.cdl)
        self.assertEqual(c['gf180_connectivity']['masters'][self.master],'verification/library/'+self.gds)
        digital_platform.verify(c);digital_platform.verify(d)
        self.assertEqual((destination/'library/LICENSE').read_bytes(),(self.library/'LICENSE').read_bytes())
        with self.assertRaisesRegex(ValueError,'Attach once'):prep.attach(c,destination)

    def test_missing_or_changed_independent_views_fail_before_a_manifest_can_be_created(self):
        path=self.library/self.gds;data=path.read_bytes();destination=self.root/'out'
        path.write_bytes(data+b'changed')
        with self.assertRaisesRegex(ValueError,'differs from its lock'):prep.prepare(self.library,self.rules,destination)
        self.assertFalse(destination.exists());path.unlink()
        with self.assertRaises(FileNotFoundError):prep.prepare(self.library,self.rules,destination)
        self.assertFalse(destination.exists())

    def test_incomplete_or_noncanonical_view_locks_fail(self):
        self.lock['views'][self.master].pop('.gds');self.write_lock()
        with self.assertRaisesRegex(ValueError,'paired views'):prep.prepare(self.library,self.rules,self.root/'out')
        self.lock['views'][self.master]['.gds']='elsewhere.gds';self.lock['files']['elsewhere.gds']=self.lock['files'].pop(self.gds);self.write_lock()
        with self.assertRaisesRegex(ValueError,'canonical'):prep.prepare(self.library,self.rules,self.root/'out')

    def test_existing_destinations_and_source_trees_are_preserved(self):
        destination=self.root/'out';destination.mkdir();marker=destination/'important';marker.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError,'preserve existing'):prep.prepare(self.library,self.rules,destination)
        self.assertEqual(marker.read_bytes(),b'keep')
        with self.assertRaisesRegex(ValueError,'separately'):prep.prepare(self.library,self.rules,self.library/'new')

    def test_changed_rules_and_preparation_metadata_cannot_be_attached(self):
        destination=self.base/'verification';prep.prepare(self.library,self.rules,destination);platform=self.platform()
        report=destination/'preparation.json';text=report.read_text(encoding='utf-8')
        for key,value in [('masters',0),('library_lock_sha256','0'*64)]:
            bad=json.loads(text);bad[key]=value;report.write_text(json.dumps(bad),encoding='utf-8')
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'metadata differs'):prep.attach(platform,destination)
        report.write_text(text,encoding='utf-8');(destination/'rules/LICENSE').write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'differs from its lock'):prep.attach(platform,destination)

    def test_wrong_stack_in_any_corner_or_external_collateral_is_rejected(self):
        destination=self.base/'verification';prep.prepare(self.library,self.rules,destination)
        for key,value in [('TRACK_OPTION','7t'),('METAL_OPTION','3LM'),('POWER_OPTION','3v3'),('KVALUE','11')]:
            p=self.platform();p['orfs']['corners']={'tt':{key:value}}
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'matching 9-track'):prep.attach(p,destination)
        external=self.root/'external';prep.prepare(self.library,self.rules,external)
        with self.assertRaisesRegex(ValueError,'inside the captured'):prep.attach(self.platform(),external)


if __name__=='__main__':unittest.main()
