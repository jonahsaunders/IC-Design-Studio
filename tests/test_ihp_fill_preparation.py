"""Captured fill collateral survives relocation and rejects changed sources."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_ihp_fill as prep, build_digital_runtime
from icstudio import digital_platform
from icstudio.model import digest


class IHPFillPreparationTests(unittest.TestCase):
    def fixture(self, root):
        source=root/'source';base=root/'platform';cache=root/'cache';cache.mkdir()
        for name in ('scripts','examples','icstudio/assets/pdks/ihp-sg13g2'):
            (source/name).mkdir(parents=True)
        (source/'icstudio/assets/pdks/ihp-sg13g2/LICENSE').write_text('fixture license')
        for name in prep.HELPERS:(source/'scripts'/name).write_text('"""Captured fixture helper."""\n')
        rows=[]
        for name in ('macro.lym','ihp-sg13g2.tech','manual.pdf'):
            data=('locked '+name).encode();(cache/name).write_bytes(data)
            rows.append(dict(path=name,file=name,sha256=hashlib.sha256(data).hexdigest(),url='https://example.invalid/'+name))
        deck=b'locked native deck\n';folder=base/'ihp-sg13g2/drc';folder.mkdir(parents=True)
        (folder/'sg13g2_maximal.lydrc').write_bytes(deck);(base/'ihp-sg13g2/cells.lib').write_text('library fixture {}')
        (source/'examples'/prep.LOCKS[0]).write_text(json.dumps(dict(revision='fixture',files=[rows[0]],native_drc=dict(sha256=hashlib.sha256(deck).hexdigest()))))
        (source/'examples'/prep.LOCKS[1]).write_text(json.dumps(dict(sources=dict(magic=dict(files=[rows[1]]),manual=dict(files=[rows[2]])))))
        files=digital_platform.inventory(base,['ihp-sg13g2/cells.lib','ihp-sg13g2/drc/sg13g2_maximal.lydrc'])
        platform=dict(version=1,name='ihp-sg13g2',root=str(base),directory='ihp-sg13g2',revision='fixture',corner='typical',corners=dict(typical=['ihp-sg13g2/cells.lib']),files=files,fingerprint=digest(files))
        return source,base,cache,platform

    def test_prepared_inputs_are_locked_and_copied_by_ordinary_platform_staging(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,base,cache,platform=self.fixture(root)
            with patch.object(prep,'ROOT',source), patch.object(prep.urllib.request,'urlopen',side_effect=AssertionError('Unexpected network')):
                result=prep.prepare(platform,base/'ihp-sg13g2/fill',cache=cache)
            self.assertNotEqual(platform['fingerprint'],result['fingerprint'])
            self.assertNotIn('ihp_fill',platform)
            self.assertEqual(result['ihp_fill']['recipe'],prep.RECIPE)
            digital_platform.stage(result,root/'relocated')
            copied={**result,'root':str(root/'relocated')};digital_platform.verify(copied)
            (root/'relocated/ihp-sg13g2/fill/macros/macro.lym').write_text('changed')
            with self.assertRaisesRegex(ValueError,'locked digital platform'):digital_platform.verify(copied)

    def test_changed_source_is_rejected_before_any_resource_directory_is_created(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,base,cache,platform=self.fixture(root)
            (cache/'macro.lym').write_text('different bytes');target=base/'ihp-sg13g2/fill'
            with patch.object(prep,'ROOT',source), self.assertRaisesRegex(ValueError,'Pinned IHP source'):
                prep.prepare(platform,target,cache=cache)
            self.assertFalse(target.exists())

    def test_build_context_contains_all_helpers_and_locks(self):
        self.assertTrue(set(prep.HELPERS)|{'prepare_ihp_fill.py'} <= set(build_digital_runtime.PLATFORM_SCRIPTS))
        self.assertTrue(set(prep.LOCKS) <= set(build_digital_runtime.PLATFORM_LOCKS))
        docker=(prep.ROOT/'packaging/digital/Dockerfile').read_text()
        for name in prep.LOCKS:self.assertIn('examples/'+name,docker)
        for name in prep.HELPERS:self.assertTrue((prep.ROOT/'scripts'/name).is_file())


if __name__=='__main__':unittest.main()
