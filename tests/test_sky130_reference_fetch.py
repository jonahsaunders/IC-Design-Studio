"""Pinned PDK downloads recover from transient failures without accepting bad data."""
import hashlib
import http.client
import io
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from fetch_sky130_reference import download_archive


class InterruptedResponse(io.BytesIO):
    def read(self, size=-1):
        if self.tell():
            raise TimeoutError('interrupted archive body')
        return super().read(4)


class Sky130ArchiveDownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'sky130_fd_pr.tar.zst'
        self.partial = self.path.with_suffix('.zst.part')
        self.payload = b'complete pinned archive contents'
        self.expected = hashlib.sha256(self.payload).hexdigest()
        self.url = 'https://example.invalid/pinned/sky130_fd_pr.tar.zst'

    def download(self):
        download_archive(self.url, self.path, self.expected)

    def test_connection_failures_retry_the_same_pinned_url(self):
        for error in (TimeoutError('read timed out'),
                      urllib.error.URLError('connection unavailable'),
                      http.client.IncompleteRead(b'partial')):
            with self.subTest(error=type(error).__name__), \
                    patch('fetch_sky130_reference.urllib.request.urlopen',
                          side_effect=[error, io.BytesIO(self.payload)]) as open_url, \
                    patch('fetch_sky130_reference.time.sleep') as sleep:
                self.download()
                self.assertEqual(open_url.call_count, 2)
                self.assertTrue(all(call.args == (self.url,) and call.kwargs == {'timeout': 60}
                                    for call in open_url.call_args_list))
                sleep.assert_called_once_with(1)
                self.assertEqual(self.path.read_bytes(), self.payload)
                self.assertFalse(self.partial.exists())

    def test_interrupted_body_is_restarted_without_appending_partial_bytes(self):
        with patch('fetch_sky130_reference.urllib.request.urlopen',
                   side_effect=[InterruptedResponse(self.payload), io.BytesIO(self.payload)]), \
                patch('fetch_sky130_reference.time.sleep'):
            self.download()
        self.assertEqual(self.path.read_bytes(), self.payload)
        self.assertFalse(self.partial.exists())

    def test_temporary_http_error_recovers(self):
        error = urllib.error.HTTPError(self.url, 503, 'Unavailable', {}, None)
        with patch('fetch_sky130_reference.urllib.request.urlopen',
                   side_effect=[error, io.BytesIO(self.payload)]) as open_url, \
                patch('fetch_sky130_reference.time.sleep'):
            self.download()
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(self.path.read_bytes(), self.payload)

    def test_permanent_http_error_is_not_retried(self):
        error = urllib.error.HTTPError(self.url, 404, 'Not Found', {}, None)
        with patch('fetch_sky130_reference.urllib.request.urlopen', side_effect=error) as open_url, \
                patch('fetch_sky130_reference.time.sleep') as sleep, \
                self.assertRaises(urllib.error.HTTPError) as caught:
            self.download()
        self.assertIs(caught.exception, error)
        open_url.assert_called_once()
        sleep.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.partial.exists())

    def test_exhausted_failures_preserve_cache_and_remove_partial_data(self):
        self.path.write_bytes(b'previous cached data')
        with patch('fetch_sky130_reference.urllib.request.urlopen',
                   side_effect=lambda *args, **kwargs: InterruptedResponse(self.payload)) as open_url, \
                patch('fetch_sky130_reference.time.sleep') as sleep, \
                self.assertRaisesRegex(TimeoutError, 'interrupted archive body'):
            self.download()
        self.assertEqual(open_url.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
        self.assertEqual(self.path.read_bytes(), b'previous cached data')
        self.assertFalse(self.partial.exists())

    def test_checksum_mismatch_fails_without_replacing_cache(self):
        self.path.write_bytes(b'previous cached data')
        with patch('fetch_sky130_reference.urllib.request.urlopen',
                   return_value=io.BytesIO(b'corrupt archive')) as open_url, \
                patch('fetch_sky130_reference.time.sleep') as sleep, \
                self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
            self.download()
        open_url.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b'previous cached data')
        self.assertFalse(self.partial.exists())


if __name__ == '__main__':
    unittest.main()
