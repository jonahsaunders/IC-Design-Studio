"""Reconstructed mocked provenance tests; no downloads or native commands."""
import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from scripts import collect_ihp_wsl_host_provenance as c


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.deb = self.root/'p.deb'; self.deb.write_bytes(b'archive')
        self.row = ('Package: libc6\nVersion: 2.39-0ubuntu8\nArchitecture: amd64\n'
                    'Source: glibc (2.39-0ubuntu8)\nFilename: pool/main/g/glibc/libc6.deb\n'
                    'Size: 7\nSHA256: '+hashlib.sha256(b'archive').hexdigest()+'\n')

    def test_exact_binary_and_source(self):
        row = c.binary_match(self.row, 'libc6', '2.39-0ubuntu8', self.deb)
        self.assertEqual(c.signed_source(row), ('glibc', '2.39-0ubuntu8'))
        self.assertEqual(c.signed_source({'Package':'foo','Version':'1'}), ('foo','1'))
        self.assertEqual(c.signed_source({'Package':'foo','Version':'1','Source':'bar'}), ('bar','1'))

    def test_binary_rejections(self):
        for text in (self.row+'\n'+self.row, self.row+'Package: duplicate\n',
                     self.row.replace('amd64','arm64'), self.row.replace('Size: 7','Size: 8'),
                     self.row.replace('pool/main','pool/../main')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                c.binary_match(text, 'libc6', '2.39-0ubuntu8', self.deb)
        self.deb.write_bytes(b'changed')
        with self.assertRaises(ValueError): c.binary_match(self.row,'libc6','2.39-0ubuntu8',self.deb)

    def test_source_malformed(self):
        for source in ('glibc ()','glibc (1) extra','glibc\nVersion: evil'):
            with self.assertRaises(ValueError): c.signed_source({'Package':'libc6','Version':'1','Source':source})

    def signed_inputs(self):
        release = self.root/'InRelease'; index = self.root/'Packages'; key = self.root/'keyring'
        index.write_text(self.row); key.write_bytes(b'key')
        release.write_text('Origin: Ubuntu\nCodename: noble\nSuite: noble-updates\nSHA256:\n '+
                           c.deps.sha(index)+' '+str(index.stat().st_size)+' main/binary-amd64/Packages\n')
        return release,index,key

    def test_signed_index_and_changed_bytes(self):
        release,index,key = self.signed_inputs()
        with patch.object(c,'UBUNTU_KEYRING',c.deps.sha(key)), patch.object(c.deps,'command',return_value='[GNUPG:] VALIDSIG pinned') as run:
            text,meta=c.binary_index(release,index,'main/binary-amd64/Packages',key)
            self.assertEqual(text,self.row); self.assertEqual(meta['index_sha256'],c.deps.sha(index))
            self.assertEqual(run.call_args.args[0][0],'/usr/bin/gpgv')
            index.write_text(self.row+'\n')
            with self.assertRaises(ValueError): c.binary_index(release,index,'main/binary-amd64/Packages',key)

    def test_signature_origin_and_key_rejections(self):
        for kind in ('signature','origin','key','duplicate'):
            release,index,key=self.signed_inputs()
            if kind=='origin': release.write_text(release.read_text().replace('Ubuntu','Debian'))
            if kind=='duplicate': release.write_text(release.read_text()+'Origin: Ubuntu\n')
            with patch.object(c,'UBUNTU_KEYRING', c.deps.sha(key) if kind!='key' else '0'*64), patch.object(c.deps,'command',return_value='' if kind=='signature' else '[GNUPG:] VALIDSIG pin'):
                with self.assertRaises(ValueError): c.binary_index(release,index,'main/binary-amd64/Packages',key)

    def tar(self, names, link=False):
        path=self.root/'data.tar'
        with tarfile.open(path,'w') as t:
            for name in names:
                m=tarfile.TarInfo(name)
                if link: m.type=tarfile.SYMTYPE; m.linkname='/etc/passwd'; t.addfile(m)
                else: m.size=3; t.addfile(m,io.BytesIO(b'lib'))
        return path

    def test_tar_exact_and_missing(self):
        h=hashlib.sha256(b'lib').hexdigest()
        self.assertEqual(c.prove_tar_members(self.tar(['./usr/lib/libc.so.6']),{'/usr/lib/libc.so.6':h}),{'usr/lib/libc.so.6':h})
        with self.assertRaises(ValueError): c.prove_tar_members(self.tar(['usr/lib/other']),{'/usr/lib/libc.so.6':h})

    def test_tar_alias_duplicate_link_and_hash(self):
        h=hashlib.sha256(b'lib').hexdigest()
        for names in (['usr//lib/x'],['usr/./lib/x'],['usr/lib/x//'],['../x'],['usr/lib/x','usr/lib/x'],['usr/lib/x','USR/lib/x']):
            with self.assertRaises(ValueError): c.prove_tar_members(self.tar(names),{'/usr/lib/x':h})
        with self.assertRaises(ValueError): c.prove_tar_members(self.tar(['usr/lib/x'],True),{'/usr/lib/x':h})
        with self.assertRaises(ValueError): c.prove_tar_members(self.tar(['usr/lib/x']),{'/usr/lib/x':'0'*64})

    def test_driver_isolated_capture_contract(self):
        import ast
        tree = ast.parse(Path(c.__file__).read_text())
        source = ast.get_source_segment(Path(c.__file__).read_text(), next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'capture'))
        self.assertIn('RLIMIT_FSIZE', source)
        self.assertIn('Acquire::AllowInsecureRepositories', source)
        self.assertIn('deps.source_metadata', source)
        self.assertIn('deps.source_package', source)
        self.assertIn('deps.resolution(engine)', source)
        self.assertNotIn('deps.SYSTEM', source)
        literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertNotIn('install', literals)

    def test_tar_link_ancestor(self):
        h=hashlib.sha256(b'lib').hexdigest(); path=self.root/'data.tar'
        with tarfile.open(path,'w') as t:
            m=tarfile.TarInfo('usr');m.type=tarfile.SYMTYPE;m.linkname='/other';t.addfile(m)
            m=tarfile.TarInfo('usr/lib/x');m.size=3;t.addfile(m,io.BytesIO(b'lib'))
        with self.assertRaises(ValueError):c.prove_tar_members(path,{'/usr/lib/x':h})

    def test_mocked_capture_join_and_failure_receipt(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        import json
        engine=self.root/'engine';engine.write_bytes(b'engine')
        lib=self.root/'lib';lib.write_bytes(b'lib')
        key=self.root/'key';key.write_bytes(b'key')
        license=self.root/'copyright';license.write_text('license')
        rows={str(i):{'path':str(lib)+str(i),'sha256':hashlib.sha256(b'lib').hexdigest()} for i in range(8)}
        meta={'binary_package':'libc6:amd64','binary_version':'1','architecture':'amd64',
              'source_package':'glibc','source_version':'1','copyright_path':str(license)}
        original_regular=c.deps.regular;original_sha=c.deps.sha
        def regular(p):
            return key if str(p)=='/usr/share/keyrings/ubuntu-archive-keyring.gpg' else original_regular(p)
        def sha(p):
            return c.ENGINE if Path(p)==engine else original_sha(p)
        def run(args, **kw):
            root=Path(kw.get('cwd', self.root/'capture/downloads')).parent
            if args[0]=='/usr/bin/apt-get':
                if args[1]=='update':
                    for part in ('binary-amd64_Packages','source_Sources'):
                        (root/'apt/lists'/('archive.ubuntu.com_ubuntu_dists_noble_main_'+part)).write_text('index')
                    (root/'apt/lists/archive.ubuntu.com_ubuntu_dists_noble_InRelease').write_text('signed')
                elif args[1]=='download': (root/'downloads/p.deb').write_bytes(b'deb')
                else: (root/'downloads/p.dsc').write_text('dsc')
            else: kw['stdout'].write(b'tar')
            return SimpleNamespace(returncode=0)
        with ExitStack() as st:
            st.enter_context(patch.object(c,'tool_source_identities',return_value={'mock-tool':'mock-hash'}))
            st.enter_context(patch.object(c.deps,'regular',side_effect=regular))
            st.enter_context(patch.object(c.deps,'sha',side_effect=sha))
            st.enter_context(patch.object(c,'UBUNTU_KEYRING',original_sha(key)))
            st.enter_context(patch.object(c.deps,'resolution',side_effect=lambda *a: ({},'ldd',{k:dict(v) for k,v in rows.items()})))
            st.enter_context(patch.object(c.deps,'package_metadata',return_value=meta))
            st.enter_context(patch.object(c,'binary_index',return_value=('packages',{'signature_status':'VALIDSIG'})))
            st.enter_context(patch.object(c.deps,'authenticated_index',return_value=('sources','VALIDSIG')))
            st.enter_context(patch.object(c,'binary_match',return_value={'Package':'libc6','Version':'1','Source':'glibc (1)'}))
            st.enter_context(patch.object(c,'prove_tar_members',return_value={}))
            st.enter_context(patch.object(c.deps,'source_package',side_effect=lambda p,*a:{Path(p).name:Path(p)}))
            st.enter_context(patch.object(c.deps,'source_metadata',return_value='source'))
            st.enter_context(patch.object(c.subprocess,'run',side_effect=run))
            out=self.root/'capture'
            result=c.capture(engine,out,base_archive_sha256='1'*64,image={'id':'pinned'},build_inputs_sha256='2'*64)
            self.assertEqual(len(result['dependencies']),8)
            self.assertEqual(result['source_proofs'][0]['package'],'glibc')
            self.assertEqual(len(json.loads((out/'signature-readbacks.json').read_text())),2)
            self.assertEqual((out/'identity-before.json').read_bytes(),(out/'identity-after.json').read_bytes())
            self.assertIn('report.json',json.loads((out/'files.json').read_text()))
            with patch.object(c.subprocess,'run',side_effect=RuntimeError('synthetic')):
                with self.assertRaises(RuntimeError):
                    c.capture(engine,self.root/'failure',base_archive_sha256='1'*64,image={},build_inputs_sha256='2'*64)
            self.assertEqual(json.loads((self.root/'failure/failure.json').read_text())['type'],'RuntimeError')

    def test_plan_is_not_execution_or_proof(self):
        p=c.acquisition_plan(self.root)
        self.assertFalse(p['qualified']);self.assertFalse(p['system_install'])
        self.assertIn('NOT_EXECUTED',p['status']); self.assertIn('blocker',p)


if __name__ == '__main__': unittest.main()
