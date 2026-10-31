"""Reader acceptance remains strict under optimization and archive tampering."""
import ast,hashlib,inspect,json,pathlib,subprocess,sys,tempfile,unittest,warnings,zipfile
from scripts import audit_ihp_resistor_vias as audit

class IhpResistorViaAuditorTests(unittest.TestCase):
    def test_strict_json_and_explicit_checks_survive_optimization(self):
        for text in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}'):
            with self.subTest(text=text),self.assertRaises(ValueError):audit.strict_json(text)
        tree=ast.parse(pathlib.Path(inspect.getfile(audit)).read_text())
        self.assertFalse(any(isinstance(node,ast.Assert) for node in ast.walk(tree)))
        code='import importlib.util; s=importlib.util.spec_from_file_location("a",'+repr(inspect.getfile(audit))+'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.require(False,"optimized gate intact")'
        result=subprocess.run([sys.executable,'-O','-c',code],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('optimized gate intact',result.stderr)

    def test_archive_rejects_untrusted_hash_duplicate_extra_and_corrupt_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);blob=b'{}';h=hashlib.sha256(blob).hexdigest()
            manifest=json.dumps(dict(format='sha256-content-addressed-files',files={'proof.json':dict(sha256=h,bytes=len(blob))})).encode()
            for kind,expected in [('hash','Archive hash differs'),('duplicate','Duplicate ZIP member'),('extra','ZIP object inventory differs'),('corrupt','Corrupt declared object')]:
                path=root/(kind+'.zip')
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning)
                    with zipfile.ZipFile(path,'w') as z:
                        z.writestr('manifest.json',manifest);z.writestr('objects/'+h,b'bad' if kind=='corrupt' else blob)
                        if kind=='duplicate':z.writestr('manifest.json',manifest)
                        if kind=='extra':z.writestr('objects/extra',b'bad')
                digest='0'*64 if kind=='hash' else hashlib.sha256(path.read_bytes()).hexdigest()
                result=subprocess.run([sys.executable,'-O',inspect.getfile(audit),'--archive',str(path),'--archive-sha256',digest,
                    '--manifest-sha256',hashlib.sha256(manifest).hexdigest(),'--output',str(root/'never.json')],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0);self.assertIn(expected,result.stderr)
                self.assertFalse((root/'never.json').exists())

if __name__=='__main__':unittest.main()
