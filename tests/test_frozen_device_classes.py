import copy,json,shutil,sys,tempfile,types,unittest
from unittest.mock import Mock,patch
from pathlib import Path
from scripts import verify_frozen_device_classes as reader
from scripts.qualify_mos_finger_layouts import selected

FIXTURE=Path(__file__).parent/'fixtures/frozen-device-class-mos-v1'

def row(mode='matching'):
    return dict(name='mos-gf180mcuC-standard-n-'+mode,family='mos',target='gf180mcuC',polarity='n',hv=False,mode=mode,expected='passed' if mode=='matching' else 'failed',settings=dict(type='silicon',verification_mode='drc_lvs',physical_toolchain='included',tools={},reference=selected('gf180mcuC','n',(3.015,1.005,3,2),None if mode=='matching' else 'reference-fingers')))

class FrozenDeviceClassTests(unittest.TestCase):
    def test_frozen_flag_dispatches_through_normal_entrypoint(self):
        from icstudio.__main__ import main
        probe=types.ModuleType('icstudio.device_class_desktop_probe');probe.main=Mock(return_value=19)
        with patch.dict(sys.modules,{'icstudio.device_class_desktop_probe':probe}),patch.object(sys,'argv',['Studio','--device-class-acceptance','--managed']),patch('icstudio.windows_stdio.connect') as connect:
            self.assertEqual(main(),19);probe.main.assert_called_once_with(['--managed']);connect.assert_called_once_with()

    def test_population_names_conditions_and_fault_intent_are_canonical(self):
        names=reader.finite_cases();self.assertEqual(len(names),35);self.assertEqual(len(set(names)),35)
        reader.case_spec(row());reader.case_spec(row('wrong-fingers'))
        for key,value in [('name','mos-gf180mcuC-standard-n-wrong-fingers'),('expected','failed'),('polarity','p'),('target','gf180mcuD'),('hv',True),('family','mos-saved')]:
            changed=row();changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):reader.case_spec(changed)
        changed=row('wrong-fingers');changed['settings']['reference']=row()['settings']['reference']
        with self.assertRaisesRegex(ValueError,'reference/parameter fault'):reader.case_spec(changed)

    def test_authentic_positive_and_complete_raw_graph_controls(self):
        source=reader.load(FIXTURE/'SOURCE.json');reader.file_map(FIXTURE,source['files'])
        positive=reader.mos_readback(FIXTURE,row(),reader.load(FIXTURE/'report.json'))
        self.assertEqual(positive,dict(native_channels=6,physical_groups=2,fingers_per_group=3,grouping='PASS'))
        mutations={
            'ports':lambda text:'\n'.join(x for x in text.splitlines() if not x.startswith('port '))+'\n',
            'nodes':lambda text:'\n'.join(x for x in text.splitlines() if not x.startswith(('node ','substrate ')))+'\n',
            'technology':lambda text:text.replace('tech gf180mcuC','tech unrelated'),
            'duplicate node':lambda text:text+next(x for x in text.splitlines() if x.startswith('node '))+'\n',
            'location':lambda text:'\n'.join(' '.join([*x.split()[:3],str(int(x.split()[3])+100000),x.split()[4],str(int(x.split()[5])+100000),*x.split()[6:]]) if x.startswith('device ') else x for x in text.splitlines())+'\n',
        }
        for name,mutation in mutations.items():
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                folder=Path(td)/'fixture';shutil.copytree(FIXTURE,folder);raw=folder/'mos-grouping/parallel_coupon.ext';raw.write_text(mutation(raw.read_text()),encoding='utf-8')
                proof=reader.load(folder/'mos-grouping/proof.json');proof['files']['parallel_coupon.ext']=reader.sha(raw);reader.write(folder/'mos-grouping/proof.json',proof)
                report=reader.load(folder/'report.json');report['mos_grouping']=proof
                with self.assertRaises(ValueError):reader.mos_readback(folder,row(),report)

    def test_exported_count_and_dimensions_are_read_after_rebinding_hashes(self):
        for text in ('.subckt parallel_coupon D G S B\n.ends\n',None):
            with tempfile.TemporaryDirectory() as td:
                folder=Path(td)/'fixture';shutil.copytree(FIXTURE,folder);path=folder/'lvs-extraction/extracted.spice';path.write_text(text if text is not None else path.read_text().replace('w=1.005u','w=2.01u'),encoding='utf-8')
                proof=reader.load(folder/'mos-grouping/proof.json');proof['native_sha256']=reader.sha(path);reader.write(folder/'mos-grouping/proof.json',proof);report=reader.load(folder/'report.json');report['mos_grouping']=proof
                with self.assertRaisesRegex(ValueError,'Exported MOS'):reader.mos_readback(folder,row(),report)

    def test_complete_stage_population_is_required(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);shutil.copytree(FIXTURE,folder/'physical-flow');report=reader.load(folder/'physical-flow/report.json');report['stages']=[r for r in report['stages'] if r['name']!='integrity'];reader.write(folder/'physical-flow/report.json',report)
            with self.assertRaisesRegex(ValueError,'stage contract'):reader.native_semantics(folder,row())

if __name__=='__main__':unittest.main()
