"""Generic geometry verification must survive export and reject incomplete evidence."""
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zipfile

from icstudio import digital_sky130_native as native
from icstudio.digital_flow import artifact, validate_result
from icstudio.digital_macro import export
from icstudio.model import clone, file_digest
from tests.test_digital_macro import DigitalMacroTests


def report_xml(path, top, marker=False):
    root=ET.Element('report-database')
    ET.SubElement(root,'top-cell').text=top
    categories=ET.SubElement(root,'categories')
    names=json.loads((native.ASSETS/'categories.json').read_bytes())
    for name in names:
        ET.SubElement(ET.SubElement(categories,'category'),'name').text=name
    items=ET.SubElement(root,'items')
    if marker:
        ET.SubElement(ET.SubElement(items,'item'),'category').text="'MR_mcon.CON.10'"
    ET.ElementTree(root).write(path)


def fixture(root, marker=False):
    job,result=DigitalMacroTests().fixture(root,name='sky130hd')
    data=result['digital_result']
    tool=native.ASSETS/'sky130A_mr.drc'  # Test process identity; no engine qualification claimed.
    data['environment']=dict(sky130_native=clone(native.POLICY),executables={'klayout':file_digest(tool)})
    job['environment']=clone(data['environment'])
    (root/'input.json').write_text(json.dumps(job))
    data['versions']={'klayout':'test-double'}
    runner=SimpleNamespace(root=root, platform={'name':'sky130hd','fingerprint':data['platform']['fingerprint']},
        config={'top':'counter'}, artifacts=data['artifacts'], tools={'klayout':str(tool)}, versions=data['versions'])
    runner.add_artifact=lambda key,path: runner.artifacts.update({key:artifact(root,path)})
    def save(key,value,name):
        (root/name).write_text(json.dumps(value));runner.add_artifact(key,root/name)
    runner.save_json=save
    def command(args,message,**kwargs):
        report_xml(kwargs['cwd']/'report.lyrdb','counter',marker)
        return 'release 2026.03.30_01.00\n'
    runner.command=command
    return job,result,runner


class NativeSky130Tests(unittest.TestCase):
    def test_backend_staging_includes_authenticated_deck_and_license(self):
        from icstudio.digital_backend import stage_backend
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source';source.mkdir()
            (source/'module.py').write_text('# backend source\n')
            (source/'assets').mkdir();(source/'assets/unrelated').write_text('large unrelated payload')
            staged=root/'backend';stage_backend(source,staged)
            self.assertTrue((staged/'module.py').is_file())
            self.assertFalse((staged/'assets/unrelated').exists())
            for name in ('sky130A_mr.drc','GPL-3.0.txt','categories.json'):
                self.assertEqual(file_digest(staged/'assets/verification/sky130'/name),file_digest(native.ASSETS/name))

    def test_pinned_sources_and_explicit_generic_options(self):
        native.resources()
        self.assertEqual(native.FLAGS['feol'],'true')
        self.assertEqual(native.FLAGS['beol'],'true')
        self.assertEqual(native.FLAGS['offgrid'],'true')
        self.assertEqual(native.FLAGS['sram_exclude'],'false')
        self.assertNotIn('tiles',native.POLICY)

    def test_pass_is_retained_in_generic_export_and_relocates(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,r=fixture(root)
            report=native.execute(r);result['digital_result']['physical']={'sky130_native':report}
            validate_result(result,root)
            contract=export(result,root,root/'macro.zip')
            self.assertEqual(contract['top'],'counter')
            self.assertEqual(contract['qualification']['sky130_native']['status'],'PASS')
            self.assertFalse(contract['qualification']['sky130_native']['qualified'])
            moved=root/'moved';moved.mkdir()
            with zipfile.ZipFile(root/'macro.zip') as archive:
                archive.extractall(moved)
                self.assertEqual(archive.read(contract['artifacts'][report['evidence']['GPL-3.0.txt']]['path']),
                                 (native.ASSETS/'GPL-3.0.txt').read_bytes())
            data=clone(result['digital_result']);data['artifacts']=contract['artifacts']
            self.assertEqual(native.validate_saved(data,moved),report)

    def test_export_executes_the_native_validator_once(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,r=fixture(root)
            report=native.execute(r);result['digital_result']['physical']={'sky130_native':report}
            with patch.object(native,'validate_saved',wraps=native.validate_saved) as checked:
                export(result,root,root/'macro.zip')
                self.assertEqual(checked.call_count,1)

    def test_violation_blocks_execution_and_retains_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,_,r=fixture(root,True)
            with self.assertRaisesRegex(ValueError,'1 violations'):
                native.execute(r)
            saved=json.loads((root/'sky130-native/report.json').read_bytes())
            self.assertEqual(saved['status'],'FAIL')
            self.assertEqual(saved['violations'],{'MR_mcon.CON.10':1})

    def test_changes_during_execution_and_missing_completion_rejected(self):
        for fault in ('gds','checkpoint','deck','engine','completion'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as td:
                root=Path(td);_,_,r=fixture(root)
                engine=root/'engine';shutil.copyfile(r.tools['klayout'],engine);r.tools['klayout']=str(engine)
                original=r.command
                def command(*args,**kwargs):
                    text=original(*args,**kwargs)
                    if fault=='completion':return 'unfinished checker\n'
                    target=(root/r.artifacts[fault]['path']) if fault in ('gds','checkpoint') else (
                        engine if fault=='engine' else root/'sky130-native/sky130A_mr.drc')
                    target.write_bytes(target.read_bytes()+b'changed')
                    return text
                r.command=command
                with self.assertRaises(ValueError):native.execute(r)
                self.assertNotIn('sky130_native',r.artifacts)

    def test_consistently_rehashed_wrong_top_cannot_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,r=fixture(root)
            report=native.execute(r);result['digital_result']['physical']={'sky130_native':report}
            report['top']='unrelated_custom_block'
            raw=root/r.artifacts[report['evidence']['report.lyrdb']]['path'];report_xml(raw,report['top'])
            request_path=root/r.artifacts[report['evidence']['request.json']]['path']
            request=json.loads(request_path.read_bytes())
            request['command']=[x.replace('top_cell=counter','top_cell='+report['top']) for x in request['command']]
            request_path.write_text(json.dumps(request))
            r.save_json('sky130_native',report,'sky130-native/report.json')
            for name in ('report.lyrdb','request.json'):
                key=report['evidence'][name];r.add_artifact(key,root/r.artifacts[key]['path'])
            with self.assertRaisesRegex(ValueError,'another top-level design'):export(result,root,root/'macro.zip')

    def test_missing_duplicate_and_wrong_top_report_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.xml'
            for fault in ('missing-rule','duplicate-rule','wrong-top','missing-items','unknown-category'):
                report_xml(path,'custom_analog_amplifier')
                tree=ET.parse(path);root=tree.getroot();categories=root.find('categories')
                if fault=='missing-rule':categories.remove(categories[0])
                elif fault=='duplicate-rule':categories.append(ET.fromstring(ET.tostring(categories[0])))
                elif fault=='wrong-top':root.find('top-cell').text='tt_um_unrelated'
                elif fault=='missing-items':root.remove(root.find('items'))
                else:ET.SubElement(ET.SubElement(root.find('items'),'item'),'category').text='unknown'
                tree.write(path)
                with self.subTest(fault=fault),self.assertRaises(ValueError):
                    native.measured(path,'custom_analog_amplifier')

    def test_stripped_or_changed_evidence_never_overwrites_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,r=fixture(root)
            report=native.execute(r);result['digital_result']['physical']={'sky130_native':report}
            destination=root/'macro.zip';export(result,root,destination);original=destination.read_bytes()
            for fault in ('policy','declaration','report','deck','license','raw','log','entire-claim'):
                bad=clone(result);data=bad['digital_result']
                if fault=='policy':data['environment'].pop('sky130_native')
                elif fault=='declaration':data['physical'].pop('sky130_native')
                elif fault=='entire-claim':
                    data['environment'].pop('sky130_native');data['physical'].pop('sky130_native')
                    data['artifacts']={k:v for k,v in data['artifacts'].items() if not k.startswith('sky130_native')}
                else:
                    key={'report':'sky130_native','deck':report['evidence']['sky130A_mr.drc'],
                         'license':report['evidence']['GPL-3.0.txt'],'raw':report['evidence']['report.lyrdb'],
                         'log':report['evidence']['native.log']}[fault]
                    data['artifacts'].pop(key)
                with self.subTest(fault=fault),self.assertRaises(ValueError):export(bad,root,destination)
                self.assertEqual(destination.read_bytes(),original)

    def test_rehashed_disabled_check_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,r=fixture(root)
            report=native.execute(r);result['digital_result']['physical']={'sky130_native':report}
            key=report['evidence']['request.json'];path=root/r.artifacts[key]['path']
            request=json.loads(path.read_bytes())
            request['command']=[x.replace('feol=true','feol=false') for x in request['command']]
            path.write_text(json.dumps(request));r.artifacts[key]=artifact(root,path)
            with self.assertRaisesRegex(ValueError,'options changed'):validate_result(result,root)

    def test_other_platform_not_given_sky130_requirements(self):
        self.assertIsNone(native.execute(SimpleNamespace(platform={'name':'gf180d'})))


if __name__=='__main__':unittest.main()
