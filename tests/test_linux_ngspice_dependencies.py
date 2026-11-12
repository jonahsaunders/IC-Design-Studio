"""Dependency provenance rejects plausible but unbound release evidence."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import linux_ngspice_dependencies as d


def listing(paths):
    return '\n'.join((str(path)+' (0x1234)' if name.startswith('ld-linux') else
                       name+' => '+str(path)+' (0x1234)') for name,path in paths.items())+'\n'


class DependencyProvenanceTests(unittest.TestCase):
    def test_debian_copyright_path_punctuation_preserves_license_versions(self):
        self.assertEqual(d.license_names('See /usr/share/common-licenses/GPL. Also /usr/share/common-licenses/LGPL-2.1 and /usr/share/common-licenses/GPL-3.'),{'GPL','LGPL-2.1','GPL-3'})

    def test_exact_resolver_rejects_missing_extra_and_unresolved_libraries(self):
        paths={name:'/lib/'+name for name in d.SONAMES};text=listing(paths)
        self.assertEqual(d.parse_ldd(text),paths)
        for bad in (text.replace('libreadline.so.8 => /lib/libreadline.so.8 (0x1234)\n',''),
                    text+'libextra.so => /lib/libextra.so (0x1234)\n',
                    text.replace('libreadline.so.8 => /lib/libreadline.so.8 (0x1234)','libreadline.so.8 => not found'),
                    text+text.splitlines()[0]+'\n'):
            self.assertNotEqual(text,bad)
            with self.assertRaises(ValueError):d.parse_ldd(bad)

    def test_environment_cannot_inherit_preload_or_host_library_override(self):
        with patch.dict(os.environ,{'LD_PRELOAD':'/tmp/evil.so','LD_LIBRARY_PATH':'/tmp/host','GIT_CONFIG':'bad'}):
            self.assertEqual(d.environment(),{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
            env=d.environment(Path.cwd());self.assertNotIn('LD_PRELOAD',env)
            self.assertEqual(env['LD_LIBRARY_PATH'],str(Path.cwd().resolve()))

    @unittest.skipIf(os.name == 'nt', 'Actual POSIX dependency path confinement is checked on native Linux.')
    def test_deployment_rejects_host_fallback_system_copy_and_wrong_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);resource=root/'_internal';engine=resource/'icstudio/assets/runtime/ngspice/ngspice'
            engine.parent.mkdir(parents=True);engine.write_bytes(b'\x7fELFfixture')
            paths={}
            for name in d.SONAMES:
                p=(root/'system'/name) if name in d.SYSTEM else resource/name
                p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode());paths[name]=p
            with patch.object(d,'ENGINE',d.sha(engine)),patch.object(d,'command',return_value=listing(paths)):
                _,_,rows=d.resolution(engine,resource);self.assertEqual(set(rows),d.SONAMES)
            outside=root/'system/libreadline.so.8';outside.write_bytes(b'host');bad=dict(paths);bad['libreadline.so.8']=outside
            with patch.object(d,'ENGINE',d.sha(engine)),patch.object(d,'command',return_value=listing(bad)):
                with self.assertRaisesRegex(ValueError,'required origin'):d.resolution(engine,resource)
            inside=resource/'libc.so.6';inside.write_bytes(b'system copy');bad=dict(paths);bad['libc.so.6']=inside
            with patch.object(d,'ENGINE',d.sha(engine)),patch.object(d,'command',return_value=listing(bad)):
                with self.assertRaisesRegex(ValueError,'required origin'):d.resolution(engine,resource)
            with patch.object(d,'ENGINE',d.sha(engine)):
                with self.assertRaisesRegex(ValueError,'resource layout'):d.resolution(engine,root/'different')

    def descriptor(self, root):
        member=root/'sample_1.orig.tar.gz';member.write_bytes(b'fixture source archive')
        checksum=f' {d.sha(member)} {member.stat().st_size} {member.name}\n'
        path=root/'sample_1.dsc';path.write_text('Format: 3.0 (quilt)\nSource: sample\nVersion: 1\nChecksums-Sha256:\n'+checksum,encoding='utf8')
        metadata='Package: sample\nVersion: 1\nChecksums-Sha256:\n'+checksum+f' {d.sha(path)} {path.stat().st_size} {path.name}\n'
        return path,member,metadata

    def test_signed_index_hash_and_repository_are_checked_after_signature_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);index=root/'Sources';index.write_bytes(b'Package: sample\nVersion: 1\n')
            keyring=root/'keys';keyring.write_bytes(b'fixture trusted keys')
            release=root/'InRelease';release.write_text('Origin: Ubuntu\nSuite: noble-updates\nCodename: noble\nSHA256:\n '+d.sha(index)+' '+str(index.stat().st_size)+' main/source/Sources\n')
            entry=dict(release=str(release),index=str(index),keyring=str(keyring),index_path='main/source/Sources')
            with patch.object(d,'UBUNTU_KEYRING',d.sha(keyring)),patch.object(d,'command',return_value='[GNUPG:] VALIDSIG fixture\n') as sig:
                d.authenticated_index(entry);self.assertEqual(sig.call_args.args[0][0],'/usr/bin/gpgv')
                index.write_bytes(b'changed source index')
                with self.assertRaisesRegex(ValueError,'signed Ubuntu release'):d.authenticated_index(entry)

    def test_untrusted_keyring_and_failed_signature_cannot_authenticate_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('Sources','InRelease','keys'):(root/name).write_bytes(b'fixture')
            entry=dict(release=str(root/'InRelease'),index=str(root/'Sources'),keyring=str(root/'keys'),index_path='main/source/Sources')
            with patch.object(d,'command') as sig:
                with self.assertRaisesRegex(ValueError,'keyring'):d.authenticated_index(entry)
                sig.assert_not_called()
            with patch.object(d,'UBUNTU_KEYRING',d.sha(root/'keys')),patch.object(d,'command',side_effect=ValueError('signature invalid')):
                with self.assertRaisesRegex(ValueError,'signature invalid'):d.authenticated_index(entry)

    def test_source_requires_complete_matching_package_and_apt_checksum_closure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path,member,metadata=self.descriptor(root)
            members=d.source_package(path,'sample','1');d.source_metadata(metadata,'sample','1',members)
            with self.assertRaisesRegex(ValueError,'package/version'):d.source_package(path,'sample','2')
            for bad in (metadata.replace('Version: 1','Version: 2'),metadata.replace(d.sha(path),'0'*64),metadata+'\n'+metadata):
                with self.assertRaises(ValueError):d.source_metadata(bad,'sample','1',members)
            member.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed source'):d.source_package(path,'sample','1')
            member.unlink()
            with self.assertRaisesRegex(ValueError,'Missing regular'):d.source_package(path,'sample','1')

    def receipt(self, root):
        (root/'copyright').write_bytes(b'exact notice')
        meta=dict(binary_package='sample',binary_version='1',architecture='amd64',source_package='sample',source_version='1',query='sample\t1\tamd64\tsample\t1\n')
        report=dict(schema=1,engine_sha256=d.ENGINE,phase='build',dependencies={n:dict(package=meta,licenses={'copyright':d.sha(root/'copyright')}) for n in d.SONAMES},sources={},missing_sources=['sample@1'],release_source_ready=False,files=d.inventory(root))
        d.write(root/'report.json',report);d.write(root/'files.json',d.inventory(root));return report,d.sha(root/'report.json')

    def test_metadata_only_source_provenance_cannot_authorize_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,anchor=self.receipt(root)
            d.verify(root,anchor)
            with self.assertRaisesRegex(ValueError,'Public release blocked'):d.verify(root,anchor,release=True)

    def test_rehashed_inventory_cannot_hide_changed_notice_or_extra_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,anchor=self.receipt(root)
            (root/'copyright').write_bytes(b'changed');files=d.inventory(root);files.pop('files.json');d.write(root/'files.json',files)
            with self.assertRaisesRegex(ValueError,'inventory differs'):d.verify(root,anchor)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,anchor=self.receipt(root);(root/'extra').write_bytes(b'extra')
            files=d.inventory(root);files.pop('files.json');d.write(root/'files.json',files)
            with self.assertRaisesRegex(ValueError,'inventory differs'):d.verify(root,anchor)

    def test_rehashed_report_cannot_claim_missing_sources_are_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);report,_=self.receipt(root);report['release_source_ready']=True
            d.write(root/'report.json',report);files=d.inventory(root);files.pop('files.json');d.write(root/'files.json',files)
            with self.assertRaisesRegex(ValueError,'Overclaimed'):d.verify(root,d.sha(root/'report.json'))

    def test_rehashed_build_receipt_cannot_claim_deployment(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);report,_=self.receipt(root);report['phase']='deployment'
            d.write(root/'report.json',report);files=d.inventory(root);files.pop('files.json');d.write(root/'files.json',files)
            with self.assertRaisesRegex(ValueError,'resource/predecessor'):d.verify(root,d.sha(root/'report.json'))

    def test_duplicate_json_keys_and_escaped_sources_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'dup';p.write_bytes(b'{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError,'Duplicate'):d.load(p)
            for name in ('../outside','/absolute','C:/outside','nested\\outside','a/./b'):
                with self.assertRaises(ValueError):d.confined(root,name)


if __name__ == '__main__':unittest.main()
