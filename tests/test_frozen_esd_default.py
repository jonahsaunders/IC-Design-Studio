"""Reject mode substitution and forged bundled-default discovery receipts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import verify_frozen_esd as reader
from scripts import ci_feedback


class DefaultEsdBoundaryTests(unittest.TestCase):
    def test_feedback_binds_default_and_predecessor_manifests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            names=('icstudio/assets/pdks/collection.json','icstudio/assets/pdks/sky130A/package.json',
                   'icstudio/assets/qualification/sky130-esd-predecessor-v1/package.json',
                   'icstudio/assets/qualification/sky130-esd-nvt-source-v1/corrected.sym')
            for name in names:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'original')
            before=ci_feedback.source_identity(root)
            self.assertEqual(set(before),set(names))
            for name in names:
                path=root/name;path.write_bytes(b'changed')
                self.assertNotEqual(before[name],ci_feedback.source_identity(root)[name])
                path.write_bytes(b'original')

    def test_both_platforms_keep_optional_and_require_default_gate(self):
        root=Path(reader.__file__).resolve().parents[1]
        windows=(root/'scripts/verify_windows.ps1').read_text()
        workflow=(root/'.github/workflows/build-desktop.yml').read_text()
        self.assertIn('--out "$evidence/optional-esd"',windows)
        self.assertIn('--bundled-default --timeout 2400 --out "$evidence/default-esd"',windows)
        self.assertIn('default_esd=(Get-Content "$evidence/default-esd/acceptance.json"',windows)
        self.assertIn('--out build/frozen-optional-esd-evidence',workflow)
        self.assertIn('--bundled-default --timeout 2400 --out build/frozen-default-esd-evidence',workflow)
        self.assertEqual(workflow.count('            build/windows-evidence/default-esd\n'),
                         workflow.count('            build/windows-evidence/optional-esd\n'))
        self.assertEqual(workflow.count('            build/frozen-default-esd-evidence\n'),
                         workflow.count('            build/frozen-optional-esd-evidence\n'))

    def test_producer_cannot_select_or_downgrade_the_gate(self):
        self.assertEqual(reader.selection({}), ('optional', reader.OPTIONAL))
        self.assertEqual(reader.selection({'selection':'bundled-default'},
                                         {'selection':'bundled-default'}),
                         ('bundled-default', reader.DEFAULT))
        for expected, report in (({}, {'selection':'bundled-default'}),
                                 ({'selection':'bundled-default'}, {}),
                                 ({'selection':'unknown'}, {})):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                reader.selection(expected, report)

    def test_actual_hub_project_collection_and_registry_must_agree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            resource=root/'resource'
            key='sky130A@fixture'
            current=root/'profile'/key
            package=dict(id='sky130A',revision='fixture',files={},technology={'id':'sky130A'})
            hub=dict(cells=[{'devices':[]}],pdk={**package['technology'],
                     'package_root':str(current),'package_lock':{k:package[k] for k in ('id','revision','files')}})
            hub['pdk']['package_lock']['manifest_hash']=reader.digest(package)
            path=root/'hub.icproj'
            reader.write(path,hub)
            collection=root/'bundled-collection.json'
            reader.write(collection,dict(packages=[dict(variant='sky130A',revision='fixture',
                         manifest_sha256=reader.DEFAULT,assets=0)]))
            expected=dict(selection='bundled-default',collection_sha256=reader.sha(collection))
            report=dict(selection='bundled-default',execution_root=str(root),resource_root=str(resource),
                        registry=dict(current_key=key,current_root=str(current)),
                        default_discovery=dict(source_of_selection='project-hub-bundled',hub_selected=key,
                          source_path=str(resource/'icstudio/assets/pdks/sky130A'),manifest_sha256=reader.DEFAULT,
                          hub_project=dict(project=str(path),project_sha256=reader.sha(path))))
            reader.default_discovery(root,report,package,expected)
            for field,value in (('source_of_selection','imported-file'),('hub_selected','sky130A@other'),
                                ('source_path',str(root/'external')),('manifest_sha256',reader.OPTIONAL)):
                changed=copy.deepcopy(report);changed['default_discovery'][field]=value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    reader.default_discovery(root,changed,package,expected)
            changed=copy.deepcopy(hub);changed['pdk']['package_lock']['revision']='other'
            reader.write(path,changed)
            report['default_discovery']['hub_project']['project_sha256']=reader.sha(path)
            with self.assertRaises(ValueError):reader.default_discovery(root,report,package,expected)
            changed=copy.deepcopy(hub);changed['cells'][0]['devices']=[{'id':'unexpected'}]
            reader.write(path,changed);report['default_discovery']['hub_project']['project_sha256']=reader.sha(path)
            with self.assertRaises(ValueError):reader.default_discovery(root,report,package,expected)
            reader.write(path,hub);report['default_discovery']['hub_project']['project_sha256']=reader.sha(path)
            obj=json.loads(collection.read_bytes());obj['packages'][0]['revision']='other'
            reader.write(collection,obj);expected['collection_sha256']=reader.sha(collection)
            with self.assertRaises(ValueError):reader.default_discovery(root,report,package,expected)


if __name__=='__main__':unittest.main()
