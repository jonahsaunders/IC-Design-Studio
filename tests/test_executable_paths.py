import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from icstudio.engines import diagnostics
from icstudio.external_tools import executable_info
from icstudio.model import file_digest


class ExecutablePathTests(unittest.TestCase):
    def test_quoted_engine_paths_remain_available_and_capture_exact_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tool with spaces';path.write_text('fixture executable')
            quoted='"'+str(path)+'"'
            config={name:quoted for name in ('ngspice','klayout','magic','netgen')}
            for row in diagnostics(config):
                self.assertEqual(row['status'],'available')
                self.assertEqual(Path(row['path']),path)
            captured=executable_info(quoted)
            self.assertEqual(captured,{'path':str(path.resolve()),'sha256':file_digest(path)})

    def test_engine_dialog_saves_normalized_paths(self):
        from icstudio.gui import StudioCore
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tool with spaces';path.write_text('fixture executable')
            quoted='"'+str(path)+'"';saved={};logs=[]
            settings=SimpleNamespace(value=lambda key,default='':default,
                                     setValue=lambda key,value:saved.update({key:value}))
            window=SimpleNamespace(settings=settings,
                simple_form=lambda *_:{name:quoted for name in ('ngspice','klayout','magic','netgen')},
                console=SimpleNamespace(appendPlainText=logs.append))
            StudioCore.engine_dialog(window)
            self.assertEqual(saved,{f'engine/{name}':str(path) for name in ('ngspice','klayout','magic','netgen')})
            self.assertTrue(all('available' in line for line in logs[0].splitlines()))


if __name__=='__main__':unittest.main()
