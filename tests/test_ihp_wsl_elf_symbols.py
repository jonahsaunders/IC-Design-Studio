import tempfile,unittest
from pathlib import Path
from scripts.ihp_wsl_elf_symbols import elf_symbols,resolve_symbols
class ELFSourceTests(unittest.TestCase):
 def test_invalid_binary_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   p=Path(root)/'bad';p.write_bytes(b'not ELF')
   with self.assertRaises(ValueError):elf_symbols(p)
 def test_strong_symbol_missing_rejected(self):
  with self.assertRaisesRegex(ValueError,'Undefined strong'):resolve_symbols({'undefined':{'required':2},'weak_undefined':[],'needed':[]},{})
 def test_symbol_type_mismatch_rejected(self):
  with self.assertRaises(ValueError):resolve_symbols({'undefined':{'required':2},'weak_undefined':[],'needed':[]},{'required':1})
 def test_engine_scope_not_self_contained(self):
  r=resolve_symbols({'undefined':{'pow':2},'weak_undefined':['optional'],'needed':[]},{'pow':10})
  self.assertEqual(r['strong_undefined_count'],1);self.assertIn('NOT_SELF_CONTAINED',r['scope']);self.assertEqual(r['weak_undefined'],['optional'])
