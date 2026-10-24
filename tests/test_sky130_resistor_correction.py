import hashlib,json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from icstudio.sky130_resistor_models import BASE_SHA256,NOTICE,corrected,relative
from icstudio.pdks import PDKRegistry
from scripts.prepare_sky130_resistor_qualification import prepare
from scripts.sky130_qualification_source import original_package,BASE
from scripts.check_resistor_unit_reference import check
from tests import test_resistor_family_qualification as families
ROOT=Path(__file__).resolve().parents[1]


class SKY130ResistorCorrectionTests(unittest.TestCase):
    def test_only_parallel_arguments_and_modification_notice_are_added(self):
        for name in BASE_SHA256:
            original=(BASE/relative(name)).read_bytes();fixed=corrected(name,original)
            self.assertEqual(fixed.replace(NOTICE.encode(),b'').replace(b' m=1\n',b'\n').replace(b' m={m}\n',b'\n'),original)
            self.assertIn(b'Licensed under the Apache License, Version 2.0',fixed)
            for bad in (original+b'\n',fixed):
                with self.assertRaises(ValueError):corrected(name,bad)

    def test_package_preserves_all_other_assets_and_installs(self):
        with original_package(ROOT/'icstudio/assets/pdks/sky130A') as source,tempfile.TemporaryDirectory() as tmp:
            old=json.loads((source/'package.json').read_bytes())
            out=Path(tmp)/'adapter';result=prepare(source,out);p=json.loads((out/'package.json').read_bytes())
            expected=deepcopy(old['technology']);expected['revision']=result['revision'];self.assertEqual(p['technology'],expected)
            self.assertEqual({k for k,v in old['files'].items() if p['files'][k]!=v},{relative(n) for n in BASE_SHA256})
            registry=PDKRegistry(Path(tmp)/'registry');key=registry.install(out/'package.json');self.assertEqual(registry.verify(key)['revision'],result['revision'])
            self.assertEqual(old,json.loads((source/'package.json').read_bytes()))
            (out/relative('res_high_po')).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):registry.install(out/'package.json')

    def test_independent_original_units_reject_wrong_single_or_parallel_values(self):
        ref=families.ResistorFamilyQualificationTests().response('sky130A');self.assertEqual(check(ref,ref)['vectors'],80)
        for suffix in ('m1','m3'):
            actual=deepcopy(ref);key=next(k for k in actual['currents'] if k.endswith(suffix));actual['currents'][key]=[v*1.2 for v in actual['currents'][key]]
            with self.assertRaisesRegex(ValueError,'original parallel'):check(actual,ref)


if __name__=='__main__':unittest.main()
