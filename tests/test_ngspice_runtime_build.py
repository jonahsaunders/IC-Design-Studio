"""Reject untrusted build inputs and changed startup declarations before editing."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts.build_ngspice_runtime import build,relocate_initializer


class SimulatorBuildInputTests(unittest.TestCase):
    def test_wrong_source_archive_does_not_create_runtime(self):
        with tempfile.TemporaryDirectory() as tmp,patch('scripts.build_ngspice_runtime.sys.platform','linux'):
            root=Path(tmp);archive=root/'source.tar.gz';archive.write_bytes(b'wrong source')
            with self.assertRaisesRegex(ValueError,'locked public release'):build(root/'output',archive)
            self.assertFalse((root/'output').exists())

    def test_unexpected_startup_path_cannot_be_silently_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);script=root/'installed/share/ngspice/scripts/spinit';script.parent.mkdir(parents=True)
            (root/'sources').mkdir();original=b'set num_threads=8\ncodemodel /unreviewed/model.cm\n';script.write_bytes(original)
            with self.assertRaisesRegex(ValueError,'Unexpected'):relocate_initializer(root)
            self.assertEqual(script.read_bytes(),original)
            self.assertFalse((root/'sources/spinit.original').exists())


if __name__=='__main__':unittest.main()
