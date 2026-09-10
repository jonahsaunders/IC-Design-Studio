"""Regressions for the reported Windows model-library path failure."""
import os,re,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_xschem_compatible import fixture
from icstudio.xschem_project import apply_review
from icstudio.xschem_compat import review_project
from icstudio.xschem_runtime import find_ngspice,netlist,run,runtime_environment


class NgspicePathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'IC Design Studio café';self.root.mkdir()
        program='.lib "first library/models with spaces.lib" typical\n.lib "second library/models with spaces.lib" typical\n.control\nop\n.endc'
        self.path=fixture(self.root/'project with spaces',program)
        self.path.write_text(self.path.read_text().replace('value="1k"','value="{r_a+r_b}"',1).replace('{capa.sym}','{res.sym}').replace('name="C1"','name="R2"').replace('value="1u"','value="1k"'))
        for folder,param,value in [('first library','r_a','1k'),('second library','r_b','2k')]:
            lib=self.path.parent/folder;lib.mkdir();(lib/'models with spaces.lib').write_text('.lib typical\n.include "value.spice"\n.endl typical\n');(lib/'value.spice').write_text('.param '+param+'='+value+'\n')
        review=review_project(self.path);self.assertFalse(review['errors']);self.project=apply_review(review)
    def tearDown(self):self.tmp.cleanup()

    def test_nested_models_have_safe_distinct_relative_references(self):
        target=self.root/'run with spaces';deck=netlist(self.project,target)
        models=list((target/'models').glob('*.spice'));self.assertEqual(len(models),4)
        for text in [deck]+[p.read_text() for p in models]:
            for reference in re.findall(r'(?im)^\.(?:include|lib)\s+(\S+)',text):
                if reference=='typical':continue
                self.assertRegex(reference,r'^models/model_[0-9a-f]+\.spice$');self.assertTrue((target/reference).is_file())
        self.assertNotIn(str(target),deck)

    def test_runtime_discovery_configuration_environment_and_bundled_console(self):
        shipped=self.root/'icstudio/assets/runtime/ngspice';shipped.mkdir(parents=True);(shipped/'ngspice_con.exe').write_bytes(b'fixture')
        configured=self.root/'my ngspice.exe';configured.write_bytes(b'fixture')
        with patch('sys._MEIPASS',str(self.root),create=True),patch('sys.platform','win32'),patch('shutil.which',return_value=None),patch.dict(os.environ,{'ICSTUDIO_NGSPICE':str(configured)}):
            self.assertEqual(find_ngspice(),str(configured.resolve()));self.assertEqual(find_ngspice('"'+str(configured)+'"'),str(configured.resolve()))
            configured.unlink();self.assertEqual(find_ngspice(),str((shipped/'ngspice_con.exe').resolve()))

    def test_upgrade_uses_current_bundled_runtime(self):
        old=self.root/'old release/icstudio/assets/runtime/ngspice/ngspice.exe';old.parent.mkdir(parents=True);old.touch()
        current=self.root/'icstudio/assets/runtime/ngspice/ngspice.exe';current.parent.mkdir(parents=True);current.touch()
        with patch('sys._MEIPASS',str(self.root),create=True),patch('sys.platform','win32'),patch('shutil.which',return_value=None),patch.dict(os.environ,{'ICSTUDIO_NGSPICE':''}):
            self.assertEqual(find_ngspice(str(old)),str(current.resolve()))

    def test_initializer_environment_is_child_local(self):
        engine=self.root/'engine';engine.mkdir();exe=engine/'ngspice';exe.touch()
        self.assertIsNone(runtime_environment(exe));(engine/'spinit').write_text('* initializer\n')
        with patch.dict(os.environ,{'SPICE_SCRIPTS':'parent choice'}):
            self.assertEqual(runtime_environment(exe)['SPICE_SCRIPTS'],str(engine.resolve()));self.assertEqual(os.environ['SPICE_SCRIPTS'],'parent choice')

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Set ICSTUDIO_TEST_NGSPICE for the actual simulator regression')
    def test_actual_ngspice_nested_libraries_spaces_and_moved_export(self):
        engine=self.root/'engine with spaces';engine.mkdir();exe=engine/Path(os.environ['ICSTUDIO_TEST_NGSPICE']).name;shutil.copy2(os.environ['ICSTUDIO_TEST_NGSPICE'],exe)
        for dependency in Path(os.environ['ICSTUDIO_TEST_NGSPICE']).parent.glob('*.dll'):shutil.copy2(dependency,engine/dependency.name)
        shutil.copy2(Path(__file__).parents[1]/'icstudio/assets/ngspice/spinit',engine/'spinit')
        result=run(self.project,self.project['top'],{'type':'xschem','probes':'v(out)','timeout':30},str(exe),self.root/'run with spaces')
        self.assertEqual(result['program_status'],'Complete');self.assertAlmostEqual(result['traces']['out'][0],.25,places=9);self.assertNotIn("can't find the initialization file",result['log'])
        exported=self.root/'export with spaces';netlist(self.project,exported);moved=self.root/'moved export';shutil.move(exported,moved)
        from icstudio.engines import execute
        log=execute([str(exe),'-n','-b','source.cir'],moved,env=runtime_environment(exe));self.assertIn('No. of Data Rows : 1',log)


if __name__=='__main__':unittest.main()
