"""Bounded publication retry preserves the completed campaign and existing data."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from icstudio.verification_campaigns import _publish_directory, create, Campaign
from tests.test_verification_campaigns import fixture, prepare_job


class CampaignPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.stage = self.root/'stage'; self.stage.mkdir()
        (self.stage/'evidence.txt').write_bytes(b'complete snapshot'); self.destination = self.root/'published'

    def denied(self, code):
        error = PermissionError('temporary Windows lock'); error.winerror = code
        return error

    def test_transient_windows_errors_retry_same_complete_snapshot(self):
        rename = os.rename; seen = []
        def publish(source, destination):
            self.assertEqual((source/'evidence.txt').read_bytes(), b'complete snapshot')
            seen.append((source, destination))
            if len(seen) < 4: raise self.denied((5, 32, 33)[len(seen)-1])
            rename(source, destination)
        with patch('icstudio.verification_campaigns.os.rename', side_effect=publish), patch('icstudio.verification_campaigns.time.sleep') as sleep:
            _publish_directory(self.stage, self.destination)
        self.assertEqual(seen, [(self.stage, self.destination)]*4)
        self.assertEqual(sleep.call_count, 3); self.assertFalse(self.stage.exists())
        self.assertEqual((self.destination/'evidence.txt').read_bytes(), b'complete snapshot')

    def test_persistent_windows_error_is_bounded_and_preserves_stage(self):
        with patch('icstudio.verification_campaigns.os.rename', side_effect=self.denied(5)) as rename, patch('icstudio.verification_campaigns.time.sleep') as sleep:
            with self.assertRaises(PermissionError): _publish_directory(self.stage, self.destination)
        self.assertEqual(rename.call_count, 6); self.assertEqual(sleep.call_count, 5)
        self.assertTrue(self.stage.exists()); self.assertFalse(self.destination.exists())

    def test_unrelated_errors_are_not_retried(self):
        for error in (PermissionError('permanent POSIX denial'), OSError('disk failure')):
            with patch('icstudio.verification_campaigns.os.rename', side_effect=error) as rename, patch('icstudio.verification_campaigns.time.sleep') as sleep:
                with self.assertRaises(OSError): _publish_directory(self.stage, self.destination)
            self.assertEqual(rename.call_count, 1); sleep.assert_not_called()

    def test_competing_destination_is_never_replaced_after_retry(self):
        def publish(source, destination):
            destination.mkdir(); (destination/'other.txt').write_bytes(b'other campaign')
            raise self.denied(5)
        with patch('icstudio.verification_campaigns.os.rename', side_effect=publish) as rename, patch('icstudio.verification_campaigns.time.sleep'):
            with self.assertRaises(FileExistsError): _publish_directory(self.stage, self.destination)
        self.assertEqual(rename.call_count, 1)
        self.assertEqual((self.destination/'other.txt').read_bytes(), b'other campaign')
        self.assertEqual((self.stage/'evidence.txt').read_bytes(), b'complete snapshot')

    @unittest.skipUnless(os.name == 'nt', 'Requires actual Windows file-sharing semantics.')
    def test_real_windows_reader_lock_delays_campaign_publish_without_losing_cases(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]; kernel.CloseHandle.restype = wintypes.BOOL
        rename = os.rename; handles = []; timers = []; denials = []
        def publish(source, destination):
            if not handles:
                handle = kernel.CreateFileW(str(source/'campaign.sqlite3'), 0x80000000, 3, None, 3, 128, None)
                self.assertTrue(handle)
                self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
                handles.append(handle); timer = threading.Timer(.05, lambda: kernel.CloseHandle(handle)); timers.append(timer); timer.start()
            try: rename(source, destination)
            except OSError as error:
                denials.append(error.winerror); raise
        project, plan = fixture(2)
        try:
            with patch('icstudio.verification_campaigns.os.rename', side_effect=publish):
                campaign = create(self.root/'locked-campaign', project, plan, prepare_job)
            self.assertTrue(denials); self.assertTrue(set(denials) <= {5, 32, 33})
            self.assertEqual(Campaign(campaign.path).counts()['Queued'], 2)
            for index in (1, 2):
                self.assertEqual(campaign.job(index)['case']['index'], index)
        finally:
            for timer in timers: timer.join()


if __name__ == '__main__': unittest.main()
