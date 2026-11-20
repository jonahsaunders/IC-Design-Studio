"""Exercise the desktop downloader with real Qt network replies and a slow local release."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QFileDialog
from icstudio import package_download as download


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.payload = bytes(range(256)) * 512
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'desktop-package'
        self.path.write_bytes(b'previous download')
        for mock in (patch.object(download, 'METADATA', self.base+'/metadata'),
                     patch.object(download, 'RELEASE', self.base),
                     patch.object(QFileDialog, 'getSaveFileName', return_value=(str(self.path), ''))):
            mock.start()
            self.addCleanup(mock.stop)
        self.server.bad_digest = False

    def until(self, predicate):
        deadline = time.monotonic()+10
        while not predicate() and time.monotonic()<deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def dialog(self):
        dialog = download.DownloadDialog(None)
        dialog.show()
        self.addCleanup(dialog.close)
        self.until(lambda: dialog.action.isEnabled())
        self.assertTrue(dialog.options,dialog.status.text())
        dialog.action.click()
        return dialog

    def test_percent_eta_and_atomic_completion(self):
        dialog = self.dialog()
        self.until(lambda: 0 < dialog.bar.value() < 100 and 'left' in dialog.status.text())
        self.assertEqual(self.path.read_bytes(), b'previous download')
        self.until(lambda: dialog.bar.value()==100)
        parts = len(dialog.options[dialog.choice.currentData()])
        self.assertEqual(self.path.read_bytes(), self.payload*parts)

    def test_cancel_and_retry_then_checksum_failure_preserve_destination(self):
        self.server.bad_digest = True
        dialog = self.dialog()
        self.until(lambda: dialog.received > 0)
        dialog.dismiss.click()
        self.assertIn('cancelled', dialog.status.text())
        self.assertEqual(self.path.read_bytes(), b'previous download')
        dialog.action.click()
        self.until(lambda: 'checksum' in dialog.status.text())
        self.assertEqual(self.path.read_bytes(), b'previous download')
        self.assertTrue(dialog.action.isEnabled())

    def test_split_package_order_and_missing_part(self):
        assets = list(reversed(Handler.assets(self.base, False)))
        linux = download.packages({'assets':assets}, False)
        parts = next(iter(linux.values()))
        self.assertEqual([a['name'][-3:] for a in parts], ['001','002'])
        incomplete = [a for a in assets if not a['name'].endswith('part002')]
        self.assertFalse(download.packages({'assets':incomplete}, False))

    def test_split_transfer_matches_assembled_manifest(self):
        with patch.object(download, 'sys', SimpleNamespace(platform='linux')):
            dialog = self.dialog()
            self.until(lambda: dialog.bar.value()==100)
            self.assertEqual(self.path.read_bytes(),self.payload*2)

    def test_library_repair_uses_progress_window_and_verifies_content(self):
        from icstudio import xschem_libraries as library
        from icstudio.library_download_ui import RepairDialog
        target=Path(self.temp.name)/'libraries'
        manifest={'libraries':{'gf180mcu':{'raw_base':self.base+'/', 'files':{
            'device.sym':{'source':'device.sym','sha256':hashlib.sha256(self.payload).hexdigest()}}}}}
        measurements=[]
        original=RepairDialog.update_progress
        def observe(dialog,fraction,message):
            original(dialog,fraction,message)
            measurements.append((dialog.bar.value(),message))
        with patch.object(library,'manifest',return_value=manifest),patch.object(library,'cache_root',return_value=target), \
             patch.object(RepairDialog,'update_progress',observe):
            self.assertEqual(library.library_root('gf180mcu'),target)
        self.assertEqual((target/'device.sym').read_bytes(),self.payload)
        self.assertTrue(any('KiB' in message for _,message in measurements))
        self.assertEqual(measurements[-1][0],100)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    @staticmethod
    def assets(base, bad_digest):
        result = []
        for suffix in ('Windows-x64-Setup.exe','Linux-x86_64.tar.gz.part001','Linux-x86_64.tar.gz.part002'):
            name = f'IC-Design-Studio-{download.__version__}-'+suffix
            result.append(dict(name=name, size=len(DownloadTests.payload),
                               browser_download_url=base+'/download/v'+download.__version__+'/'+name,
                               digest='sha256:'+('0'*64 if bad_digest else hashlib.sha256(DownloadTests.payload).hexdigest())))
        filename=result[-1]['name'][:-len('.part002')]+'.parts.json'
        result.append(dict(name=filename,browser_download_url=base+'/download/v'+download.__version__+'/'+filename))
        return result

    def do_GET(self):
        metadata = self.path=='/metadata'
        assets=self.assets(DownloadTests.base,self.server.bad_digest)
        if metadata:
            body=json.dumps({'assets':assets}).encode()
        elif self.path.endswith('.parts.json'):
            part_assets=[a for a in assets if a['name'].endswith(('part001','part002'))]
            name=part_assets[0]['name'][:-len('.part001')]
            body=json.dumps(dict(format='split-tar-gz',schema=1,
                archive=dict(name=name,bytes=len(DownloadTests.payload)*2,sha256=hashlib.sha256(DownloadTests.payload*2).hexdigest()),
                parts=[dict(name=a['name'],bytes=a['size'],sha256=a['digest'][7:]) for a in part_assets])).encode()
        else:
            body=DownloadTests.payload
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            for start in range(0,len(body),8192):
                self.wfile.write(body[start:start+8192])
                self.wfile.flush()
                if not metadata:time.sleep(.12)
        except (ConnectionError,OSError):
            pass  # The cancellation case closes the client socket.


if __name__=='__main__':unittest.main()
