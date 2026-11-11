import copy,io,json,tempfile,unittest,zipfile,stat
from pathlib import Path
from unittest.mock import patch
from scripts import recover_pw2dn_diagnostics as r

class RecoveryTests(unittest.TestCase):
 def fixture(self):
  run={'id':r.RUN,'head_sha':r.HEAD,'status':'completed','conclusion':'failure','repository':{'id':1,'full_name':r.REPO},'head_repository':{'id':1,'full_name':r.REPO}}
  artifact={'id':r.ARTIFACT,'size_in_bytes':r.SIZE,'digest':'sha256:'+r.DIGEST,'expired':False,'workflow_run':{'id':r.RUN,'head_sha':r.HEAD,'repository_id':1,'head_repository_id':1}}
  return run,artifact
 def test_metadata(self):
  a,b=self.fixture();r.metadata(a,b)
  for obj,key,val in [(a,'id',0),(a,'head_sha','x'),(a,'status','in_progress'),(a,'conclusion','success'),(b,'id',0),(b,'digest','x'),(b,'size_in_bytes',0),(b,'expired',True)]:
   aa,bb=copy.deepcopy(a),copy.deepcopy(b);(aa if obj is a else bb)[key]=val
   with self.assertRaises(ValueError):r.metadata(aa,bb)
  for target,key in [('repository','full_name'),('head_repository','full_name')]:
   aa=copy.deepcopy(a);aa[target][key]='other/repo'
   with self.assertRaises(ValueError):r.metadata(aa,b)
  for key in ['id','head_sha','repository_id','head_repository_id']:
   bb=copy.deepcopy(b);bb['workflow_run'][key]='wrong'
   with self.assertRaises(ValueError):r.metadata(a,bb)
 def archive(self,entries):
  stream=io.BytesIO()
  with zipfile.ZipFile(stream,'w') as z:
   for name,data in entries:z.writestr(name,data)
  stream.seek(0);return stream
 def test_recover_exact_and_missing(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);rows=r.inspect_archive(self.archive([('windows-evidence/'+r.MEMBERS[0],b'Traceback (most recent call last):\nValueError: concrete failure\nsecret=abc\ncommand stuff\nraise RuntimeError(command_literal)'),('unrelated.txt',b'not retained')]),root)
   self.assertEqual([x['status'] for x in rows],['recovered','missing','missing']);text=next(root.iterdir()).read_text();self.assertIn('concrete failure',text);self.assertNotIn('abc',text);self.assertNotIn('command stuff',text);self.assertNotIn('command_literal',text);self.assertEqual(len(list(root.iterdir())),1)
 def test_fallback_prefix(self):
  with tempfile.TemporaryDirectory() as td:
   rows=r.inspect_archive(self.archive([('build/windows-evidence/'+r.MEMBERS[1],b'{"status":"failed","command":["secret"],"returncode":1}')]),Path(td))
   self.assertEqual(rows[1]['status'],'recovered');self.assertNotIn('command',next(Path(td).iterdir()).read_text())
 def test_bad_paths_duplicates_collision_ambiguity(self):
  n='windows-evidence/'+r.MEMBERS[0]
  bad=[[('../bad',b'x')],[('/bad',b'x')],[('a\\b',b'x')],[('C:/bad',b'x')],[('a/./b',b'x')],[('a//b',b'x')],[(n,b''),(n,b'')],[(n,b''),(n.upper(),b'')],[(n,b''),('build/'+n,b'')]]
  for entries in bad:
   with self.subTest(entries=entries),tempfile.TemporaryDirectory() as td:
    with self.assertRaises(ValueError):r.inspect_archive(self.archive(entries),Path(td))
 def test_symlink(self):
  zi=zipfile.ZipInfo('some-link');zi.create_system=3;zi.external_attr=(stat.S_IFLNK|0o777)<<16
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(ValueError):r.inspect_archive(self.archive([(zi,b'target')]),Path(td))
 def test_oversize(self):
  with tempfile.TemporaryDirectory() as td,patch.object(r,'MAX_MEMBER',8):
   with self.assertRaises(ValueError):r.inspect_archive(self.archive([('windows-evidence/'+r.MEMBERS[0],b'x'*9)]),Path(td))
 def test_projection_nested_and_secret(self):
  value=r.project_json(b'{"status":{"token":"abc"},"error":"token=abc","command":"sensitive","env":{"x":"y"},"returncode":1,"seconds":0.1}')
  self.assertEqual(value,{'error':'[redacted sensitive-key line]','returncode':1})
  self.assertNotIn('abc',r.redact('{"token":"abc"}'));self.assertNotIn('private',r.redact('https://example.com/private?q=x'))
 def test_invalid_json_and_output_cap(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);r.inspect_archive(self.archive([('windows-evidence/'+r.MEMBERS[1],b'notjson')]),root);self.assertIn('invalid_json',next(root.iterdir()).read_text());r.write(root/'huge.json',{'x':'z'*(r.TAIL+1)});self.assertLess((root/'huge.json').stat().st_size,r.TAIL)
 def test_download_exact_hash_size_and_failure(self):
  class Response(io.BytesIO):
   def geturl(self):return 'https://example.blob.core.windows.net/signed'
  with tempfile.TemporaryDirectory() as td,patch.object(r,'SIZE',3),patch.object(r,'DIGEST',r.digest(b'abc')):
   with patch.object(r.urllib.request,'build_opener') as opener:
    opener.return_value.open.return_value=Response(b'abc');r.download('https://example.blob.core.windows.net/signed',Path(td)/'good')
   for name,data in [('short',b'ab'),('large',b'abcd'),('hash',b'xyz')]:
    with patch.object(r.urllib.request,'build_opener') as opener:
     opener.return_value.open.return_value=Response(data)
     with self.assertRaises(ValueError):r.download('https://example.blob.core.windows.net/signed',Path(td)/name)
 def test_api_redirect_token_not_forwarded(self):
  url='https://productionresultssa1.blob.core.windows.net/a?sig=private'
  error=r.urllib.error.HTTPError('https://api.github.com/x',302,'Found',{'Location':url},None)
  with patch.object(r.urllib.request,'build_opener') as opener:
   opener.return_value.open.side_effect=error
   self.assertEqual(r.api('/repos/'+r.REPO+'/actions/artifacts/1/zip','ephemeral',True),url)
   request=opener.return_value.open.call_args.args[0]
   self.assertTrue(request.full_url.startswith('https://api.github.com/'));self.assertEqual(request.get_header('Authorization'),'Bearer ephemeral')
   self.assertEqual(opener.return_value.open.call_count,1)
  self.assertIsNone(r.NoRedirect().redirect_request(None,None,None,None,None,None))
 def test_url_host_restrictions(self):
  r.artifact_url('https://productionresultssa1.blob.core.windows.net/a?sig=x')
  r.artifact_url('https://x.actions.githubusercontent.com/a')
  for url in ['http://x.blob.core.windows.net/a','https://evil.com/a','https://x.blob.core.windows.net.evil.com/a','https://user:password@x.blob.core.windows.net/a','https://x.blob.core.windows.net:444/a','https://x.blob.core.windows.net/a#fragment']:
   with self.assertRaises(ValueError):r.artifact_url(url)
 def test_workflow_narrow_permissions_trigger_and_upload(self):
  text=(Path(__file__).resolve().parents[1]/'.github/workflows/recover-pw2dn-once.yml').read_text()
  self.assertIn('branches: [codex/chunk7-blockers-20261108]',text);self.assertIn('actions: read',text);self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text);self.assertNotIn('workflow_dispatch',text);self.assertNotIn('pull_request',text);self.assertNotIn('write',text);self.assertIn('pw2dn-recovered/*.json',text)
if __name__=='__main__':unittest.main()
