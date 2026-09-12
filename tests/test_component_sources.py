"""Library identity stays separate from electrical identity across native exchange."""
import shutil
import tempfile
import unittest
from pathlib import Path
from icstudio.model import save_project, load_project
from icstudio.native_migration import review_path
from icstudio.native_exchange import export_project, review_project
from icstudio.parametric import electrical_signature
from icstudio.xschem_libraries import ASSETS
from tests.test_xschem_compatible import fixture


class ComponentSources(unittest.TestCase):
    def test_same_named_symbols_keep_distinct_libraries_without_staling_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';path=fixture(source)
            for library in ('Library_A','Library_B'):
                (source/library).mkdir()
                shutil.copyfile(ASSETS/'xschem/devices/res.sym',source/library/'res.sym')
            text=path.read_text().replace('{res.sym}','{Library_A/res.sym}').replace('{capa.sym}','{Library_B/res.sym}')
            path.write_text(text.replace('name="C1"','name="R2"').replace('value="1u"','value="2k"'))
            report=review_path(path);self.assertEqual(report['status'],'Complete',report['items'])
            project=report['candidate'];devices={d['id']:d for c in project['cells'] for d in c['devices'] if d.get('native_spice',{}).get('label')=='res'}
            self.assertEqual({d['component_source'] for d in devices.values()},{'Library_A','Library_B'})
            for d in devices.values():
                without={k:v for k,v in d.items() if k!='component_source'}
                self.assertEqual(electrical_signature(d),electrical_signature(without))
            sources={key:d['component_source'] for key,d in devices.items()}
            shutil.rmtree(source)
            package=export_project(project,root/'exchange');review=review_project(Path(package['directory'])/package['top'])
            self.assertFalse(review['errors'],review['errors'])
            save_project(review['candidate'],root/'reopened.icproj');reopened=load_project(root/'reopened.icproj')
            actual={d['id']:d['component_source'] for c in reopened['cells'] for d in c['devices'] if d['id'] in sources}
            self.assertEqual(actual,sources)


if __name__=='__main__':unittest.main()
