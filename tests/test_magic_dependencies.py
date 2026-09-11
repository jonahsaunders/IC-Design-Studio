import tempfile
import unittest
from pathlib import Path
from icstudio.magic_dependencies import closure


class MagicDependenciesTests(unittest.TestCase):
    def test_missing_leaf_fails_before_conversion_and_repeated_uses_are_hashed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);top=root/'top.mag';top.write_text('magic\nuse leaf a\nuse leaf b\n')
            with self.assertRaisesRegex(ValueError,'Missing Magic child leaf'):closure(top)
            (root/'leaf.mag').write_text('magic\n<< end >>\n')
            first=closure(top);self.assertEqual(set(first),{'top.mag','leaf.mag'})
            (root/'leaf.mag').write_text('magic\n<< metal1 >>\nrect 0 0 2 2\n<< end >>\n')
            self.assertNotEqual(first['leaf.mag'],closure(top)['leaf.mag'])
