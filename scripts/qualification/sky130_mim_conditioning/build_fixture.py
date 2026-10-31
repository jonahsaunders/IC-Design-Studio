"""Reconstruct a pinned, self-contained finite MiM qualification fixture."""
from pathlib import Path
import argparse,zipfile,json
from replay import strict_json,sha,unlinked,child,load_fixture,fail
def build(bundle,bundle_sha,fixture_sha,output):
 bundle=unlinked(bundle);out=unlinked(output)
 if sha(bundle.read_bytes())!=bundle_sha:fail('fixture bundle identity differs')
 if out.exists():fail('fixture output must be fresh')
 with zipfile.ZipFile(bundle) as z:
  names=z.namelist()
  if len(names)!=len(set(names)) or 'manifest.json' not in names or any(n.endswith('/') for n in names):fail('fixture bundle inventory differs')
  if z.getinfo('manifest.json').file_size>1_000_000 or sum(z.getinfo(n).file_size for n in names)>100_000_000:fail('fixture bundle too large')
  manifest=z.read('manifest.json')
  if sha(manifest)!=fixture_sha:fail('fixture manifest identity differs')
  m=strict_json(manifest)
  if set(m)!={'schema','kind','sources','decks'}:fail('fixture manifest structure differs')
  expected={'manifest.json'}|set(m['sources'])|set(m['decks'])
  if set(names)!=expected:fail('fixture bundle file inventory differs')
  files={}
  for name in names:
   child(out,name);data=z.read(name)
   if name!='manifest.json' and sha(data)!=(m['sources'].get(name) or m['decks'].get(name)):fail('fixture file identity differs')
   files[name]=data
 out.mkdir(parents=True)
 for name,data in files.items():
  dest=child(out,name);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
 load_fixture(out,fixture_sha);return {'fixture_sha256':fixture_sha,'files':len(files)}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('bundle','bundle-sha','fixture-sha','output'):p.add_argument('--'+name,required=True)
 a=p.parse_args(argv);print(json.dumps(build(a.bundle,a.bundle_sha,a.fixture_sha,a.output),allow_nan=False))
if __name__=='__main__':main()
