"""Exact observed source selection never treats system libraries as bundled."""
import unittest
from scripts import fetch_linux_ngspice_sources as f


class SourceSelectionTests(unittest.TestCase):
    def test_exact_source_versions_deduplicate_runtime_binaries(self):
        report={'dependencies':{
            'libgcc_s.so.1':{'package':{'source_package':'gcc-14','source_version':'14.2.0-4ubuntu2~24.04.1'}},
            'libgomp.so.1':{'package':{'source_package':'gcc-14','source_version':'14.2.0-4ubuntu2~24.04.1'}},
            'libc.so.6':{'package':{'source_package':'glibc','source_version':'2.39-0ubuntu8.9'}}}}
        self.assertEqual(f.expected_packages(report),{'gcc-14@14.2.0-4ubuntu2~24.04.1':('gcc-14','14.2.0-4ubuntu2~24.04.1')})

    def test_source_argument_injection_and_missing_versions_reject(self):
        for name,version in (('-oAPT::Unsafe=true','1'),('sample',''),('sample','1;touch /tmp/x'),('sample/other','1')):
            report={'dependencies':{'libreadline.so.8':{'package':{'source_package':name,'source_version':version}}}}
            with self.assertRaisesRegex(ValueError,'Unsafe source'):f.expected_packages(report)


if __name__=='__main__':unittest.main()
