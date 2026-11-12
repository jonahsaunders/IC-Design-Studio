"""A saved antenna pass requires complete, unchanged native evidence."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from icstudio import digital, digital_design, digital_identity, digital_platform
from icstudio import digital_sky130_antenna as antenna
from icstudio.digital_flow import artifact, validate_result
from icstudio.digital_macro import export
from icstudio.model import clone, design_digest, digest, file_digest
from scripts import prepare_sky130_antenna as prep, build_digital_runtime
from tests import test_digital_macro as macro_fixtures

ROOT = Path(__file__).resolve().parents[1]


def native(folder, top='counter', markers=0):
    rows = [dict(stage=s, **dict(zip(antenna.FIELDS, p)), markers=markers if i == 0 else 0)
            for i, (s, p) in enumerate(antenna.PARAMETERS.items())]
    metrics = dict(status='all-stages-executed', qualified=False, stages=rows)
    (folder/'metrics.json').write_text(json.dumps(metrics))
    raw = ET.Element('report-database'); ET.SubElement(raw, 'top-cell').text = top
    categories = ET.SubElement(raw, 'categories')
    for stage in antenna.STAGES:
        ET.SubElement(ET.SubElement(categories, 'category'), 'name').text = 'ar_q.'+stage+'.1'
    items = ET.SubElement(raw, 'items')
    for _ in range(markers):
        ET.SubElement(ET.SubElement(items, 'item'), 'category').text = "'ar_q.poly.1'"
    ET.ElementTree(raw).write(folder/'report.lyrdb')
    return antenna.COMPLETE+'\n'


def fixture(root, command=None):
    job, result = macro_fixtures.DigitalMacroTests().fixture(root, name='sky130hd')
    value = digital_design.config(job['project'], job['cell'])
    platform = clone(value['platform']); platform['root'] = str(root/'platform')
    platform = prep.prepare(platform, root/'platform/antenna/check.drc')
    value['platform'] = platform
    digital_design.set_config(job['project'], job['cell'], value)
    (root/'input.json').write_text(json.dumps(job))
    data = result['digital_result']; data['source_hash'] = digital.source_hash(value)
    data['input_key'] = digital_identity.stage_key(value, 'finish')
    result['design_hash'] = design_digest(job['project'])
    data['platform']['fingerprint'] = platform['fingerprint']
    data['environment'] = {'sky130_antenna': clone(platform['sky130_antenna'])}
    data['versions'] = {'klayout': antenna.VERSION}
    # The fake process tests evidence handling only. Separate native audits run the real deck.
    runner = SimpleNamespace(root=root, platform=platform, config={'top':value['top']},
        artifacts=data['artifacts'], tools={'klayout':str(ROOT/'scripts/sky130_staged_antenna.drc')},
        versions=data['versions'])
    data['environment']['executables'] = {'klayout':file_digest(runner.tools['klayout'])}
    runner.add_artifact = lambda k, p, **kw: runner.artifacts.update({k:artifact(root, p, **kw)})
    def save(k, value, name):
        path=root/name;path.write_text(json.dumps(value));runner.add_artifact(k,path)
    runner.save_json = save
    runner.command = command or (lambda *args, **kw: native(kw['cwd']))
    return job, result, runner


def accepted(root):
    job, result, runner = fixture(root)
    report = antenna.execute(runner)
    result['digital_result']['physical'] = {'sky130_antenna':report}
    return job, result, report


def save(root, result, report):
    data=result['digital_result'];path=root/data['artifacts']['sky130_antenna']['path']
    path.write_text(json.dumps(report));data['artifacts']['sky130_antenna']=artifact(root,path)
    data['physical']['sky130_antenna']=clone(report)


class Sky130ApplicationAntennaTests(unittest.TestCase):
    def test_preparation_authenticates_and_relocates(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);job,_,_=fixture(root);platform=job['project']['digital']['platform']
            digital_platform.stage(platform,root/'moved')
            copied=clone(platform);copied['root']=str(root/'moved');digital_platform.verify(copied)
            with self.assertRaisesRegex(ValueError,'once'):prep.prepare(platform,root/'platform/new.drc')
            changed=clone(platform);changed['sky130_antenna']['sha256']='a'*64
            with self.assertRaises(ValueError):digital_platform.validate(changed)
            changed=clone(platform);changed['files']=[r for r in changed['files'] if r['path']!='antenna/check.drc']
            changed['fingerprint']=digest(changed['files'])
            with self.assertRaises(ValueError):digital_platform.validate(changed)

    def test_runtime_context_captures_exact_deck_and_preparer(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);build_digital_runtime.sky130_rule_context(root)
            self.assertEqual(file_digest(root/'scripts/sky130_staged_antenna.drc'),antenna.DECK_SHA256)
            self.assertEqual((root/'scripts/prepare_sky130_antenna.py').read_bytes(),Path(prep.__file__).read_bytes())
            self.assertIn('prepare_sky130_antenna(platforms[', (ROOT/'packaging/digital/bundle_platforms.py').read_text())

    def test_success_exports_raw_evidence_and_relocates(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,report=accepted(root);validate_result(result,root)
            contract=export(result,root,root/'macro.zip')
            self.assertEqual(contract['qualification']['sky130_antenna']['stages'],13)
            self.assertFalse(contract['qualification']['sky130_antenna']['qualified'])
            self.assertIn('checkpoint',contract['artifacts'])
            moved=root/'moved';moved.mkdir()
            with zipfile.ZipFile(root/'macro.zip') as archive:archive.extractall(moved)
            data=clone(result['digital_result']);data['artifacts']=contract['artifacts']
            self.assertEqual(antenna.validate_saved(data,moved),report)

    def test_missing_or_stripped_claim_cannot_overwrite_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,report=accepted(root);destination=root/'macro.zip'
            export(result,root,destination);original=destination.read_bytes()
            for fault in ('policy','declaration','report','deck','metrics','raw','log','request','entire-claim'):
                changed=clone(result);data=changed['digital_result']
                if fault=='policy':data['environment'].pop('sky130_antenna')
                elif fault=='declaration':data['physical'].pop('sky130_antenna')
                elif fault=='entire-claim':
                    data['physical'].pop('sky130_antenna');data['environment'].pop('sky130_antenna')
                    data['artifacts']={k:v for k,v in data['artifacts'].items() if not k.startswith('sky130_antenna')}
                else:
                    key={'report':'sky130_antenna','deck':'sky130_antenna_check','metrics':'sky130_antenna_metrics',
                         'raw':'sky130_antenna_report','log':'sky130_antenna_native','request':'sky130_antenna_request'}[fault]
                    data['artifacts'].pop(key)
                with self.subTest(fault=fault),self.assertRaises(ValueError):export(changed,root,destination)
                self.assertEqual(destination.read_bytes(),original)

    def test_relocked_stale_or_overclaimed_reports_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,report=accepted(root)
            for key,value in [('top','other'),('gds_sha256','a'*64),('checkpoint_sha256','a'*64),
                              ('platform_fingerprint','a'*64),('status','FAIL'),('violations',False),
                              ('qualified',True),('chunk_complete',True),('stages',[])]:
                changed=clone(report);changed[key]=value;save(root,result,changed)
                with self.subTest(field=key),self.assertRaises(ValueError):export(result,root,root/'bad.zip')
            save(root,result,report)

    def test_all_missing_duplicate_changed_and_boolean_stage_settings_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);native(root);metrics=json.loads((root/'metrics.json').read_bytes())
            for i in range(13):
                for fault in ('missing','duplicate','markers',*antenna.FIELDS):
                    bad=clone(metrics)
                    if fault=='missing':bad['stages'].pop(i)
                    elif fault=='duplicate':bad['stages'][i]=bad['stages'][(i+1)%13]
                    elif fault=='markers':bad['stages'][i]['markers']=False
                    else:bad['stages'][i][fault]=False
                    with self.subTest(stage=i,fault=fault),self.assertRaises(ValueError):
                        antenna.measured(bad,root/'report.lyrdb','counter')

    def test_raw_missing_duplicate_and_disagreeing_reports_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);native(root);metrics=json.loads((root/'metrics.json').read_bytes())
            for fault in ('top','category','duplicate','items','marker'):
                native(root);path=root/'report.lyrdb';raw=ET.parse(path)
                if fault=='top':raw.find('top-cell').text='other'
                elif fault=='category':raw.find('categories').remove(raw.find('categories/category'))
                elif fault=='duplicate':raw.find('categories').append(raw.find('categories/category'))
                elif fault=='items':raw.getroot().remove(raw.find('items'))
                else:ET.SubElement(ET.SubElement(raw.find('items'),'item'),'category').text='ar_q.poly.1'
                raw.write(path)
                with self.subTest(fault=fault),self.assertRaises(ValueError):antenna.measured(metrics,path,'counter')

    def test_failed_process_and_nonzero_findings_are_preserved(self):
        for fault in ('engine','markers','sentinel','version','input','deck','changed-input','changed-engine'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as td:
                root=Path(td);_,_,runner=fixture(root)
                def command(*args,**kw):
                    output=native(kw['cwd'],markers=1 if fault=='markers' else 0)
                    if fault=='engine':raise RuntimeError('native engine failed')
                    if fault=='changed-input':(root/runner.artifacts['gds']['path']).write_text('changed')
                    if fault=='changed-engine':Path(runner.tools['klayout']).write_text('changed')
                    return 'incomplete' if fault=='sentinel' else output
                runner.command=command
                if fault=='version':runner.versions['klayout']='KLayout 0.30.4'
                elif fault=='input':(root/runner.artifacts['gds']['path']).write_text('changed')
                elif fault=='deck':(root/'platform/antenna/check.drc').write_text('changed')
                elif fault=='changed-engine':
                    tool=root/'fake-engine';tool.write_text('original');runner.tools['klayout']=str(tool)
                with self.assertRaises((ValueError,RuntimeError)):antenna.execute(runner)
                report=json.loads((root/'sky130-antenna-checks/accepted.json').read_bytes())
                self.assertEqual(report['status'],'FAIL');self.assertFalse(report['qualified'])
                if fault in ('engine','markers','sentinel'):
                    self.assertIn('sky130_antenna_report',runner.artifacts)
                with self.assertRaises(FileExistsError):antenna.execute(runner)

    def test_relocked_raw_settings_cannot_reuse_success(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,report=accepted(root);data=result['digital_result']
            path=root/data['artifacts']['sky130_antenna_metrics']['path']
            metrics=json.loads(path.read_bytes());metrics['stages'][12]['limit']=401
            path.write_text(json.dumps(metrics));data['artifacts']['sky130_antenna_metrics']=artifact(root,path)
            with self.assertRaises(ValueError):export(result,root,root/'bad.zip')

    def test_engine_identity_and_request_bindings_are_checked(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,result,report=accepted(root)
            for fault in ('version','engine','input','invocation'):
                changed=clone(result);data=changed['digital_result']
                path=root/data['artifacts']['sky130_antenna_request']['path'];original=path.read_bytes()
                if fault=='version':data['versions']['klayout']='KLayout 0.30.4'
                elif fault=='engine':data['environment']['executables']['klayout']='a'*64
                else:
                    request=json.loads(original)
                    if fault=='input':request['inputs']['gds']['sha256']='a'*64
                    else:request['command'][7]='top_cell=other'
                    path.write_text(json.dumps(request));data['artifacts']['sky130_antenna_request']=artifact(root,path)
                with self.subTest(fault=fault),self.assertRaises(ValueError):export(changed,root,root/'bad.zip')
                path.write_bytes(original)

    def test_historical_jobs_keep_their_limited_scope(self):
        self.assertIsNone(antenna.validate_saved({'artifacts':{}},Path('.')))
        self.assertIsNone(antenna.execute(SimpleNamespace(platform={'name':'sky130hd'})))


if __name__=='__main__':unittest.main()
