"""Text files are UTF-8 on every platform.

Windows desktop builds do not run Python in UTF-8 mode, so a read or write
without an explicit encoding uses the ANSI code page there. Project files, run
logs and the included guides are written as UTF-8; decoding them with the ANSI
code page corrupts non-ASCII text and fails outright for byte sequences that
code page does not define. Hosted source feedback sets PYTHONUTF8=1, which
hides the difference, so this contract is checked from the source itself.
"""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'icstudio'


# These modules still inherit the locale encoding because their exact bytes are
# bound to retained acceptance records. Most of them read ASCII-escaped JSON or
# run inside the Linux runtime, where the locale encoding is already UTF-8. The
# rest, such as Xschem text import and the language-server working copy, still
# use the ANSI code page for non-ASCII text on Windows. Convert a module when
# its bound source is next retained; never add to this set.
BOUND_HISTORICAL_SOURCES = frozenset((
    'characterization.py', 'digital_design.py', 'digital_fill_odb.py', 'digital_fill_spef.py',
    'digital_gf180_fill.py', 'digital_ihp_fill.py', 'digital_ihp_fill_worker.py',
    'digital_ihp_geometry.py', 'digital_layout.py', 'digital_lsp.py', 'digital_macro.py',
    'digital_odb.py', 'digital_physical_checks.py', 'digital_physical_engine.py',
    'digital_planning.py', 'digital_qualification.py', 'digital_rc.py', 'digital_reports.py',
    'digital_runtime.py', 'digital_setup_ui.py', 'digital_sky130_pins.py', 'digital_trace_store.py',
    'digital_workspace.py', 'exchange_review.py', 'feature_cli.py', 'hierarchy_ui.py',
    'inductor_design_probe.py', 'interop_cli.py', 'job_store.py', 'layout_comparison.py',
    'layout_development_ui.py', 'layout_exchange.py', 'magic_rc.py', 'mixed_signal.py',
    'native_exchange.py', 'physical_desktop_probe.py', 'project_manager.py', 'release_probe.py',
    'sar_example.py', 'sdk.py', 'symbol_editor.py', 'variation_runs.py', 'vga_probe.py',
    'waveform_tools.py', 'xschem_compat.py', 'xschem_libraries.py', 'xschem_project.py',
))


def default_encoding_calls(source):
    """Yield (line, call) for text file access that inherits the locale encoding."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if any(keyword.arg == 'encoding' for keyword in node.keywords):
            continue
        name = node.func.attr
        if name == 'read_text' and not node.args:
            yield node.lineno, name
        elif name == 'write_text' and len(node.args) < 2:
            yield node.lineno, name


class SourceContractTests(unittest.TestCase):
    def test_detector_recognizes_implicit_and_explicit_calls(self):
        sample = ("a=p.read_text()\nb=p.read_text(encoding='utf-8')\nc=p.read_text(errors='replace')\n"
                  "p.write_text(x)\np.write_text(x,encoding='utf-8')\nd=p.read_text('utf-8')\n")
        self.assertEqual(list(default_encoding_calls(sample)), [(1, 'read_text'), (3, 'read_text'), (4, 'write_text')])

    def test_application_text_files_name_their_encoding(self):
        implicit = {path.name for path in sorted(PACKAGE.glob('*.py'))
                    if list(default_encoding_calls(path.read_text(encoding='utf-8')))}
        self.assertEqual(sorted(implicit - BOUND_HISTORICAL_SOURCES), [],
                         'Pass encoding="utf-8" so Windows reads and writes the same bytes as Linux.')
        self.assertEqual(sorted(BOUND_HISTORICAL_SOURCES - implicit), [],
                         'Remove converted modules from BOUND_HISTORICAL_SOURCES.')

    def test_user_facing_readers_are_converted(self):
        for name in ('gui.py', 'editor_workspace.py', 'run_manager.py', 'engines.py', 'interchange.py'):
            self.assertNotIn(name, BOUND_HISTORICAL_SOURCES)


class IncludedGuideTests(unittest.TestCase):
    def guides(self):
        names = set()
        for path in PACKAGE.glob('*.py'):
            names.update(re.findall(r"open_editor_doc\('([^']+\.md)'\)", path.read_text(encoding='utf-8')))
        return sorted(names | {'USER_GUIDE.md'})

    def test_every_guide_opened_from_the_application_exists_and_is_utf8(self):
        guides = self.guides()
        self.assertIn('ROADMAP.md', guides)
        self.assertIn('STUDENT_HUB.md', guides)
        for name in guides:
            with self.subTest(guide=name):
                text = (ROOT / 'docs' / name).read_bytes().decode('utf-8')
                self.assertTrue(text.strip())

    def test_guides_contain_text_the_windows_code_page_cannot_decode(self):
        """Keep the reason for this contract observable: these guides failed to open on Windows."""
        failing = []
        for name in self.guides():
            try:
                (ROOT / 'docs' / name).read_bytes().decode('cp1252')
            except UnicodeDecodeError:
                failing.append(name)
        self.assertIn('ROADMAP.md', failing)
        self.assertIn('STUDENT_HUB.md', failing)


class RunLogRoundTripTests(unittest.TestCase):
    def test_saved_log_text_survives_a_utf8_round_trip_that_cp1252_rejects(self):
        import tempfile
        from icstudio.model import atomic_write
        log = 'Saved “result” to C:\\Users\\Ánh\\回路\\run — 10 kΩ, 2.2 µF\n'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'output.log'
            atomic_write(path, log)
            self.assertEqual(path.read_text(encoding='utf-8', errors='replace'), log)
            with self.assertRaises(UnicodeDecodeError):
                path.read_bytes().decode('cp1252')


if __name__ == '__main__':
    unittest.main()
