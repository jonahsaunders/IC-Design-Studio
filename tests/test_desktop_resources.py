"""Verify the offline desktop tree independently of a developer checkout."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from icstudio import getting_started, qualification, simulation
from scripts.desktop_resources import stage_documents

ROOT = Path(__file__).resolve().parents[1]


class DesktopResourceTests(unittest.TestCase):
    def test_staged_help_examples_and_archived_results(self):
        with tempfile.TemporaryDirectory() as folder:
            installed = Path(folder)
            stage_documents(ROOT, installed)
            shutil.copytree(ROOT / 'examples', installed / 'examples')
            self.assertFalse((installed / 'docs/validation').exists())
            self.assertFalse((installed / 'docs/qualification/source-dispositions-2026-11-08-v1.json.gz').exists())
            for name in ('GETTING_STARTED.md', 'USER_GUIDE.md', 'RELEASE_STATUS.md'):
                self.assertEqual((installed / 'docs' / name).read_bytes(), (ROOT / 'docs' / name).read_bytes())
            self.assertTrue((installed / 'docs/images/readme/simulation-dark.png').is_file())
            with patch.object(sys, '_MEIPASS', str(installed), create=True):
                entries = {e['id']: e for e in getting_started.examples()}
                project = getting_started.example_copy(entries['rc'])
                wave = simulation.run(project, project['top'], project['analysis'])
                self.assertGreater(len(wave['x']), 1)
                self.assertGreater(max(wave['traces']['vout']), min(wave['traces']['vout']))
                for name in qualification.catalog():
                    with self.subTest(reference=name):
                        self.assertTrue(qualification.status(name)['valid'])

