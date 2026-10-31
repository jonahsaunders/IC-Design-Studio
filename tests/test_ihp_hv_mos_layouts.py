"""HV process masks, exact interfaces, invalid ranges and editing regressions."""
from pathlib import Path
import tempfile
import unittest
from icstudio.catalog import create_device
from icstudio.ihp_layout import specification,audit,layers
from icstudio.ihp_mos_lvs import subcircuits
from icstudio.interchange import export_layout
from icstudio.layout import kdb,polygon
from icstudio.layout_eco import regenerate
from icstudio.model import clone,save_project,load_project,file_digest
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_ihp_hv_mos_layouts import fixture,sizes,channels,masks,altered,disconnected_body,ordinary_fault,channel_parameters


class IhpHvMosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=load_technology('ihp-sg13g2')[0]

    def test_published_minimum_interior_and_maximum_geometry(self):
        for pol in ('n','p'):
            for size in sizes(pol):
                p=fixture(self.tech,pol,size);c=p['cells'][0];ls=layers(p['pdk'])
                self.assertFalse(any(s['layer']==ls['nsdm'] for s in c['shapes']))
                self.assertEqual(sum(s['layer']==ls['thickox'] for s in c['shapes']),size[3])
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/'hv.gds';export_layout(p,path);proof=masks(path,pol,size)
                    self.assertEqual(proof['channels'],size[2]*size[3])
                if pol=='p':
                    regions={key:kdb().Region() for key in ('diff','nwell','psdm')}
                    for key,r in regions.items():
                        for s in c['shapes']:
                            if s['layer']==ls[key]:r.insert(polygon(s))
                    primary=regions['diff']&regions['psdm']
                    self.assertTrue((primary.sized(620)-regions['nwell']).is_empty())

    def test_contact_pad_transition_has_oxide_and_well_enclosure(self):
        for pol in ('n','p'):
            for width in (.695,.7,.705):
                p=fixture(self.tech,pol,(width,1,1,1))
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/'hv.gds';export_layout(p,path);masks(path,pol,(width,1,1,1))

    def test_invalid_geometry_and_alias_counts_fail_closed(self):
        for pol in ('n','p'):
            p=fixture(self.tech,pol,sizes(pol)[0]);d=p['cells'][0]['devices'][0];minimum=.45 if pol=='n' else .4
            for key,value in (('w','.295u'),('w','10.005u'),('l',str(minimum-.005)+'u'),('l','10.005u'),('w','.301u')):
                other=clone(d);other['params'][key]=value
                with self.subTest(pol=pol,key=key,value=value),self.assertRaises(ValueError):specification(p['pdk'],other)
            for key,value in (('ng','2'),('ng','9'),('ng','1.5'),('m','0'),('m','17'),('m','1.5')):
                other=clone(d);other['model_params'][key]=value
                with self.subTest(pol=pol,key=key,value=value),self.assertRaises(ValueError):specification(p['pdk'],other)

    def test_rf_symbols_cannot_silently_use_standard_mos_geometry(self):
        catalog=self.tech['simulation']['catalog'];found=[]
        for symbol,binding in catalog.items():
            if 'rfmode' not in binding.get('emit_parameters',{}):continue
            if binding.get('model') not in ('sg13_lv_nmos','sg13_lv_pmos','sg13_hv_nmos','sg13_hv_pmos'):continue
            d=create_device(self.tech,symbol,'RF1');found.append(symbol)
            with self.subTest(symbol=symbol),self.assertRaisesRegex(ValueError,'RF geometry'):specification(self.tech,d)
        self.assertEqual(len(found),4)

    def test_regeneration_retains_pins_and_updates_oxide_copies(self):
        for pol in ('n','p'):
            p=fixture(self.tech,pol,(3,1,3,3));c=p['cells'][0];d=c['devices'][0];pins={v['pin']:v['id'] for v in c['layout_pins']}
            for width,fingers,copies in ((8,8,16),(.3,1,1),(3,3,3)):
                d['params']['w']=str(width)+'u';d['model_params'].update(ng=str(fingers),m=str(copies))
                self.assertTrue(audit(p,c['id']));regenerate(p,c['id'],d['id']);self.assertFalse(audit(p,c['id']))
                self.assertEqual({v['pin']:v['id'] for v in c['layout_pins']},pins)
                self.assertEqual(sum(s['layer']==layers(p['pdk'])['thickox'] for s in c['shapes']),copies)
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/'hv.icproj';save_project(p,path);self.assertEqual(load_project(path),p)

    def test_raw_channel_and_group_audits_detect_equivalent_total_width(self):
        text='.subckt parallel_coupon D G S B\n'+''.join(f'X{i} D G S B sg13_hv_nmos w=1u l=1u\n' for i in range(6))+'.ends\n'
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'raw.spice';path.write_text(text,encoding='utf-8');self.assertEqual(channels(path,'n',(3,1,3,2))['channels'],6)
            with self.assertRaises(ValueError):channels(path,'n',(3,1,4,2))
            p=fixture(self.tech,'n',(3,1,3,2));gds=Path(td)/'hv.gds';export_layout(p,gds)
            with self.assertRaisesRegex(ValueError,'group count'):masks(gds,'n',(1,1,1,6))
            for fault in ('missing-oxide','oxide-enclosure'):
                export_layout(altered(p,fault),gds)
                with self.assertRaisesRegex(ValueError,'oxide'):masks(gds,'n',(3,1,3,2))
            for replacement in ('sg13_lv_nmos','sg13_hv_pmos'):
                path.write_text(text.replace('sg13_hv_nmos',replacement),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'model'):channels(path,'n',(3,1,3,2))

    def test_standard_mos_interface_changes_prefix_only(self):
        for model in ('sg13_lv_nmos','sg13_lv_pmos','sg13_hv_nmos','sg13_hv_pmos'):
            text=f'.SUBCKT c D G S B\nM$1 D G S B {model} L=.45u W=.3u\n+ AS=.44p AD=.44p PS=3u PD=3u rfmode=0\n.ENDS c\n'
            result,changes=subcircuits(text)
            self.assertEqual(result,text.replace('M$1','X$1').replace('\n+',''))
            self.assertEqual(changes[0]['terminal_count'],4)
            unchanged,again=subcircuits(result);self.assertEqual(unchanged,result);self.assertFalse(again)

    def test_rf_ambiguous_and_colliding_mos_conversion_is_rejected(self):
        text='.subckt c D G S B\nM1 D G S B sg13_hv_nmos w=.3u l=.45u rfmode=0\n.ends c\n'
        for other in (text.replace('rfmode=0','rfmode=1'),text.replace('rfmode=0','rfmode=NaN'),
                      text.replace('rfmode=0',''),text.replace('rfmode=0','rfmode=0 rfmode=0'),
                      text.replace('rfmode=0','rfmode=0 extra=1'),text.replace('.ends c','X1 D G S B sg13_hv_nmos w=.3u l=.45u\n.ends c')):
            with self.assertRaises(ValueError):subcircuits(other)

    def body_evidence(self,folder):
        def write(name,data):
            path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data,encoding='utf-8');return file_digest(path)
        write('lvs-extraction/console.log','NET_ONLY enabled: apply extraction netlist options and skip comparison.\nLVS Total Run time 1 seconds')
        write('lvs-extraction/native.cir','.SUBCKT parallel_coupon G S D\nM$1 S G D \\$1 sg13_hv_pmos L=0.4u W=0.3u rfmode=0\n.ENDS parallel_coupon\n')
        assets={str(folder/'asset.tech'):write('asset.tech','locked asset')}
        tools={name:dict(path=str(folder/name),sha256=write(name,'locked '+name)) for name in ('magic','netgen','klayout')}
        export=dict(sha256=write('layout.gds','layout bytes'),source_sha256=write('original.gds','original layout bytes'))
        decks=[dict(name=name,categories=["'LU.a'"] if name=='main' else [],violations=int(name=='main'),report=name+'/findings.lyrdb',
                    report_sha256=write('drc/'+name+'/findings.lyrdb',name+' findings')) for name in ('main','maximal')]
        return dict(status='failed',lvs_extractor='ihp-klayout',drc_engine='ihp-public',drc_count=1,
            stages=[dict(name='preflight',status='passed',evidence=dict(assets=assets,tools=tools)),
                dict(name='layout_export',status='passed',evidence=export),dict(name='drc',status='failed'),
                dict(name='lvs_extraction',status='failed',error='IHP extracted port names differ from the schematic.'),
                dict(name='lvs',status='not_run'),dict(name='integrity',status='not_run')],
            klayout_drc=dict(decks=decks,input_sha256=export['source_sha256']))

    def test_missing_body_requires_completed_native_device_and_exact_rule(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);report=self.body_evidence(folder);dest=folder/'lvs-extraction'
            self.assertTrue(disconnected_body(report,folder,'p',(.3,.4,1,1)))
            for change in ('wrong-rule','wrong-size','incomplete-engine','missing-device'):
                report=self.body_evidence(folder)
                bad=clone(report)
                if change=='wrong-rule':bad['klayout_drc']['decks'][0]['categories']=["'M1.a'"]
                if change=='incomplete-engine':(dest/'console.log').write_text('engine failed',encoding='utf-8')
                if change=='missing-device':(dest/'native.cir').write_text('.SUBCKT parallel_coupon G S D\n.ENDS\n',encoding='utf-8')
                with self.subTest(change=change):self.assertFalse(disconnected_body(bad,folder,'p',(.4 if change=='wrong-size' else .3,.4,1,1)))

    def test_body_fault_rejects_duplicate_unknown_and_nonfinite_parameters(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);report=self.body_evidence(folder);path=folder/'lvs-extraction/native.cir';original=path.read_text(encoding='utf-8')
            for value in ('W=999u W=0.3u','W=0.3u extra=1','W=0.3u ignored_token','W=NaN','W=inf','W=0.3u rfmode=0','W=0.3u m=2','W='):
                path.write_text(original.replace('W=0.3u',value),encoding='utf-8')
                with self.subTest(value=value):self.assertFalse(disconnected_body(report,folder,'p',(.3,.4,1,1)))
            for tokens in (['w=1u','w=1u','l=1u'],['w=1u','l=1u','unknown=1'],['w=NaN','l=1u'],['w=1u','l=1u','broken']):
                with self.subTest(tokens=tokens),self.assertRaises(ValueError):channel_parameters(tokens)

    def test_body_fault_rechecks_assets_tools_layouts_and_drc_reports(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            for name in ('asset.tech','magic','netgen','klayout','layout.gds','original.gds','drc/main/findings.lyrdb'):
                report=self.body_evidence(folder);path=folder/name;path.write_bytes(b'changed after extraction')
                with self.subTest(name=name):self.assertFalse(disconnected_body(report,folder,'p',(.3,.4,1,1)))
            report=self.body_evidence(folder)
            for field in ('assets','tools'):
                bad=clone(report);bad['stages'][0]['evidence'][field]={}
                with self.subTest(field=field):self.assertFalse(disconnected_body(bad,folder,'p',(.3,.4,1,1)))
            bad=clone(report);bad['stages'][1]['evidence'].pop('sha256')
            self.assertFalse(disconnected_body(bad,folder,'p',(.3,.4,1,1)))

    def test_body_fault_requires_exact_stage_sequence_and_states(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);report=self.body_evidence(folder)
            for name,status in (('lvs_extraction','passed'),('lvs_extraction','not_run'),('lvs','failed'),('integrity','failed'),('drc','not_run')):
                bad=clone(report);next(s for s in bad['stages'] if s['name']==name)['status']=status
                with self.subTest(name=name,status=status):self.assertFalse(disconnected_body(bad,folder,'p',(.3,.4,1,1)))
            for stages in (report['stages'][:-1],report['stages']+[report['stages'][0]],None):
                bad=clone(report);bad['stages']=stages
                self.assertFalse(disconnected_body(bad,folder,'p',(.3,.4,1,1)))

    def test_ordinary_fault_requires_passed_integrity_and_bound_native_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);report=self.body_evidence(folder);stages={s['name']:s for s in report['stages']}
            (folder/'lvs').mkdir();log=folder/'lvs/lvs.log';log.write_text('Netlists do not match.\n',encoding='utf-8')
            extracted=folder/'lvs-extraction/extracted.spice';extracted.write_text('.subckt c D G S B\n.ends\n',encoding='utf-8')
            stages['lvs_extraction'].clear();stages['lvs_extraction'].update(name='lvs_extraction',status='passed')
            stages['lvs']['status']='failed';stages['integrity'].update(status='passed',evidence=dict(verified=True,
                assets=stages['preflight']['evidence']['assets'],tools=stages['preflight']['evidence']['tools'],
                files={p.relative_to(folder).as_posix():file_digest(p) for p in (log,extracted)}))
            self.assertTrue(ordinary_fault(report,folder))
            for status in ('failed','not_run','blocked'):
                bad=clone(report);next(s for s in bad['stages'] if s['name']=='integrity')['status']=status
                with self.subTest(status=status):self.assertFalse(ordinary_fault(bad,folder))
            bad=clone(report);next(s for s in bad['stages'] if s['name']=='integrity').pop('evidence')
            self.assertFalse(ordinary_fault(bad,folder))
            log.write_text('Netlists do not match.\nchanged',encoding='utf-8');self.assertFalse(ordinary_fault(report,folder))


if __name__=='__main__':unittest.main()
