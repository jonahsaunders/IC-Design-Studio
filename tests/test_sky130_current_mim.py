"""Fresh source Qt integration tests; no retained external evidence or native engine."""
import copy, hashlib, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from scripts.installed_mim_inputs import ROOT
from icstudio.model import design_digest, file_digest, load_project
from scripts import sky130_esd_revision_bridge as bridge
from scripts import qualify_sky130_current_mim as producer
from scripts import audit_sky130_current_mim as reader

NONCE='0123456789abcdef0123456789abcdef'
def encoded(value): return (json.dumps(value,indent=2)+'\n').encode()
class CurrentQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='current-mim-test-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.base=Path(cls.tmp.name)
        from scripts.prepare_sky130_esd_nvt import predecessor
        cls.previous=predecessor(ROOT/'icstudio/assets/pdks/sky130A'); cls.source=cls.previous.__enter__()
        cls.addClassCleanup(cls.previous.__exit__,None,None,None)
        cls.contract=ROOT/'docs/qualification/sky130-mim-contract-v1.json'
        cls.candidate=cls.base/'candidate'; bridge.prepare(cls.source,cls.candidate)
        cls.root=cls.base/'evidence'
        # Capture trusted current identities before the separate Qt process runs.
        cls.expected=producer.sources()
        env={**os.environ, 'QT_QPA_PLATFORM':'offscreen'}
        command=[sys.executable, '-m', 'scripts.qualify_sky130_current_mim',
                 '--package', str(cls.candidate), '--predecessor', str(cls.source/'package.json'),
                 '--out', str(cls.root), '--nonce', NONCE]
        # Preserve child output after class cleanup, outside the evidence tree.
        with tempfile.NamedTemporaryFile(mode='w',prefix='current-mim-producer-',suffix='.log',
                                         encoding='utf-8',delete=False) as log:
            cls.child_log=Path(log.name)
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        if result.returncode:
            raise AssertionError('Fresh Qt producer failed: '+cls.child_log.read_text(encoding='utf-8'))
        cls.ident=dict(report_sha256=file_digest(cls.root/'report.json'),nonce=NONCE,root=str(cls.root))
    def audit(self, sha=None, expected=None):
        return reader.read(self.root,sha or self.ident['report_sha256'],NONCE,self.contract,self.expected if expected is None else expected)
    def test_actual_and_rehashed_negative_controls(self):
        self.assertEqual(self.audit()['corners'],['tt','ll','hh','hl','lh'])
        report_path=self.root/'report.json'; original=report_path.read_bytes(); report=json.loads(original)
        with self.assertRaises(ValueError): self.audit(sha='0'*64)
        with self.assertRaises(ValueError): self.audit(expected={})
        wrong=dict(self.expected); wrong[next(iter(wrong))]='0'*64
        with self.assertRaises(ValueError): self.audit(expected=wrong)
        for key in ('current_revision','predecessor','old_design','source_files'):
            changed=copy.deepcopy(report)
            if key=='current_revision': changed['current']['revision']='b26f7f28e659ddc1'
            if key=='predecessor': changed['predecessor']['manifest_sha256']='0'*64
            if key=='old_design': changed['old_after']['design_hash']='0'*64
            if key=='source_files': changed['source_files']=wrong
            try:
                report_path.write_bytes(encoded(changed))
                with self.subTest(key=key), self.assertRaises(ValueError): self.audit(sha=hashlib.sha256(report_path.read_bytes()).hexdigest())
            finally: report_path.write_bytes(original)
        row=report['current_projects'][0]; target=Path(row['reference']); original_export=target.read_bytes()
        try:
            altered=original_export.replace(b'cap_mim_m3_1',b'cap_mim_m3_2')
            self.assertNotEqual(altered,original_export); target.write_bytes(altered)
            changed=copy.deepcopy(report);changed['current_projects'][0]['export_sha256']['reference']=hashlib.sha256(altered).hexdigest()
            report_path.write_bytes(encoded(changed))
            with self.assertRaises(ValueError): self.audit(sha=hashlib.sha256(report_path.read_bytes()).hexdigest())
        finally: target.write_bytes(original_export); report_path.write_bytes(original)
        identity_path=self.root/'shared-models/source-identity.json'; identity_bytes=identity_path.read_bytes()
        try:
            identity=json.loads(identity_bytes); identity['staged']['tt']=identity['staged']['hh']
            identity_path.write_bytes(encoded(identity))
            with self.assertRaises(ValueError): self.audit()
        finally: identity_path.write_bytes(identity_bytes)
        with patch.object(reader,'sources',return_value=wrong):
            with self.assertRaises(ValueError): self.audit()
    def test_changed_old_project_rehashed_identity(self):
        report_path=self.root/'report.json'; original_report=report_path.read_bytes()
        report=json.loads(original_report); project=Path(report['old_after']['project'])
        original_project=project.read_bytes()
        try:
            changed=json.loads(original_project)
            changed['cells'][0]['devices'][0]['name']='C_STALE_EDIT'
            project.write_bytes(encoded(changed))
            report['old_after']['project_sha256']=file_digest(project)
            report['old_after']['design_hash']=design_digest(load_project(project))
            self.assertNotEqual(report['old_before']['design_hash'],report['old_after']['design_hash'])
            report_path.write_bytes(encoded(report))
            with self.assertRaisesRegex(ValueError,'Old saved design changed'):
                self.audit(sha=file_digest(report_path))
        finally:
            project.write_bytes(original_project); report_path.write_bytes(original_report)
    def test_old_registry_duplicate_key(self):
        report=json.loads((self.root/'report.json').read_bytes())
        old=load_project(report['old_before']['project'])
        package=Path(old['pdk']['package_root'])/'package.json'; original=package.read_bytes()
        try:
            package.write_bytes(original.replace(b'{',b'{"id":"forged",',1))
            with self.assertRaisesRegex(ValueError,'Duplicate JSON key'):
                self.audit()
        finally: package.write_bytes(original)
    def test_registry_duplicate_key(self):
        report=json.loads((self.root/'report.json').read_bytes()); registry=Path(report['current']['path'])
        package=registry/'package.json'; original=package.read_bytes()
        try:
            package.write_bytes(original.replace(b'{',b'{"id":"forged",',1))
            with self.assertRaisesRegex(ValueError,'Duplicate JSON key'):
                bridge.compare_registry(registry,self.candidate,self.source/'package.json')
        finally: package.write_bytes(original)
if __name__=='__main__': unittest.main()
