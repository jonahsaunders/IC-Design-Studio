"""Exact unpromoted pw2dn candidate and predecessor identity controls."""
import os,subprocess,tempfile,unittest
from pathlib import Path
from icstudio.model import file_digest
from scripts import prepare_sky130_pw2dn_default as builder
from scripts import sky130_pw2dn_source as helper
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'icstudio/assets/pdks/sky130A'
class DefaultTests(unittest.TestCase):
    def test_rebuild_and_exact_predecessor(self):
        with tempfile.TemporaryDirectory() as tmp, helper.predecessor(SRC) as original:
            rebuilt=Path(tmp)/'rebuilt';result=builder.prepare(original,rebuilt)
            self.assertEqual(result['manifest_sha256'],helper.CURRENT)
            with helper.predecessor(rebuilt,original/'package.json') as old:
                self.assertEqual(file_digest(old/'package.json'),helper.BASE)
            with helper.predecessor(original) as old:self.assertEqual(old,original.resolve())
            path=rebuilt/(builder.PREFIX+builder.MODEL);path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed current asset'):
                with helper.predecessor(rebuilt,original/'package.json'):pass

    def test_linked_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=Path(tmp)/'linked';out=Path(tmp)/'out'
            if os.name=='nt':
                result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(SRC)],capture_output=True,text=True)
                if result.returncode: self.fail('Could not create ordinary-user test junction: '+result.stderr)
            else:link.symlink_to(SRC,target_is_directory=True)
            try:
                with self.assertRaises(ValueError):builder.prepare(link,out)
                with self.assertRaises(ValueError):
                    with helper.predecessor(link):pass
                self.assertFalse(out.exists())
            finally:
                if os.name=='nt':os.rmdir(link)
                else:link.unlink()

if __name__=='__main__':unittest.main()
