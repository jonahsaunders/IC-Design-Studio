"""EM exchange acceptance using explicitly synthetic electrical references."""
import json
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

from icstudio import inductor,inductor_em as em
from icstudio.model import example,clone,save_project,load_project
from icstudio.layout import rect,kdb,polygon


def stackup():
    return dict(source='Synthetic test stack; not a physical process',layers=[
        dict(name='metal1',kind='conductor',z_um=1,thickness_um=.5,conductivity_s_m=3e7),
        dict(name='via1',kind='via',z_um=1.5,thickness_um=.5,conductivity_s_m=3e7),
        dict(name='metal2',kind='conductor',z_um=2,thickness_um=1,conductivity_s_m=3e7),
        dict(name='oxide',kind='dielectric',z_um=0,thickness_um=10,epsilon_r=3.9,loss_tangent=0),
        dict(name='substrate',kind='substrate',z_um=-100,thickness_um=100,epsilon_r=11.7,conductivity_s_m=10)])


def results(manifest):
    # Synthetic series RL shunted by C. Its zero reactance crosses within sweep.
    frequencies=[1e8,5e8,1e9,2e9,3e9,4e9,5e9,6e9,8e9,1e10]
    impedances=[1/(1/complex(2,2*math.pi*f*2e-9)+2j*math.pi*f*.5e-12) for f in frequencies]
    return dict(schema=1,fingerprint=manifest['fingerprint'],port_definition=manifest['port_definition'],
                source='Synthetic analytic 2 ohm / 2 nH parallel 0.5 pF fixture; no EM accuracy claim',
                frequency_hz=frequencies,z_real_ohm=[z.real for z in impedances],z_imag_ohm=[z.imag for z in impedances])


class EMTests(unittest.TestCase):
    def setUp(self):
        self.p=example('empty');self.p['pdk']['em_stackup']=stackup()
        self.cid=self.p['top'];r=inductor.plan(self.p,self.cid,{**inductor.defaults(self.p),'shape':'octagon'})
        inductor.install(self.p,r);self.did=r['device_id']

    def test_bundle_exact_mask_ports_context_and_no_invented_stackup(self):
        self.p['cells'][0]['shapes'].append(rect('metal1',400000,0,1000,1000))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'em.zip';manifest=em.export_bundle(self.p,self.cid,self.did,path)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(set(archive.namelist()),{'geometry.gds','manifest.json','results-template.json','README.txt'})
                data=json.loads(archive.read('manifest.json'));self.assertEqual(data,manifest)
                gds=Path(folder)/'geometry.gds';gds.write_bytes(archive.read('geometry.gds'))
                layout=kdb().Layout();layout.read(str(gds));self.assertEqual(layout.dbu,.001)
                for name,key in [('INDUCTOR','geometry'),('CONTEXT','context_geometry')]:
                    cell=layout.cell(name);self.assertIsNotNone(cell)
                    for layer in self.p['pdk']['layers']:
                        expected=kdb().Region()
                        for shape in data[key]:
                            if shape['layer']==layer['name']:expected.insert(polygon(shape))
                        index=layout.find_layer(layer['gds'],layer['datatype'])
                        actual=kdb().Region(cell.begin_shapes_rec(index)) if index is not None else kdb().Region()
                        self.assertTrue((expected^actual).is_empty())
            self.assertEqual({pin['pin'] for pin in data['pins']},{'p','n'})
        self.p['pdk'].pop('em_stackup');self.p['pdk']['stack_3d']={'metal1':{'z_um':100,'thickness_um':10}}
        manifest=em.manifest(self.p,self.cid,self.did)
        self.assertIsNone(manifest['stackup']);self.assertFalse(manifest['stackup_complete'])
        with self.assertRaisesRegex(ValueError,'stackup'):em.validate_results(results(manifest),manifest)

    def test_impedance_results_l_q_srf_and_save_reopen(self):
        m=em.manifest(self.p,self.cid,self.did);data=results(m);r=em.install_results(self.p,self.cid,self.did,data)
        self.assertGreater(r['srf_hz'],4e9);self.assertLess(r['srf_hz'],6e9)
        for row,f,real,imag in zip(r['rows'],data['frequency_hz'],data['z_real_ohm'],data['z_imag_ohm']):
            self.assertEqual(row['inductance_h'],imag/(2*math.pi*f))
            self.assertEqual(row['q'],imag/real if imag>0 else None)
        self.assertEqual(em.result_status(self.p,self.cid,self.did)[0],r)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'em.icproj';save_project(self.p,path);loaded=load_project(path)
            self.assertEqual(em.result_status(loaded,self.cid,self.did)[0],r)
        low={**data,**{k:data[k][:3] for k in ('frequency_hz','z_real_ohm','z_imag_ohm')}}
        self.assertIsNone(em.validate_results(low,m)['srf_hz'])

    def test_wrong_geometry_context_stackup_ports_and_tampering_fail(self):
        data=results(em.manifest(self.p,self.cid,self.did));em.install_results(self.p,self.cid,self.did,data)
        for change in ('stack','context','recipe','port'):
            q=clone(self.p)
            if change=='stack':q['pdk']['em_stackup']['layers'][0]['conductivity_s_m']*=2
            elif change=='context':q['cells'][0]['shapes'].append(rect('metal1',400000,0,1000,1000))
            elif change=='recipe':
                s=inductor.defaults(q);s.update(shape='octagon',inner=100000)
                inductor.install(q,inductor.plan(q,self.cid,s,did=self.did))
            else:q['cells'][0]['layout_pins'][0]['point'][0]+=5
            self.assertIsNone(em.result_status(q,self.cid,self.did)[0],change)
            before=clone(q)
            with self.assertRaises(ValueError):em.install_results(q,self.cid,self.did,data)
            self.assertEqual(q,before)
        self.p['cells'][0]['parametric_devices'][0]['em_characterization']['rows'][0]['q']=1e6
        self.assertIsNone(em.result_status(self.p,self.cid,self.did)[0])

    def test_malformed_samples_and_materials_are_rejected_atomically(self):
        m=em.manifest(self.p,self.cid,self.did);good=results(m)
        for key,value in [('frequency_hz',[1,1]),('frequency_hz',[2,1]),('frequency_hz',[float('nan')]*10),
                          ('z_real_ohm',[-1]*10),('z_imag_ohm',[float('inf')]*10),('source','REPLACE me'),
                          ('port_definition','other'),('fingerprint','other')]:
            with self.subTest(key=key),self.assertRaises(ValueError):em.validate_results({**good,key:value},m)
        for key,value in [('thickness_um',0),('z_um',float('nan')),('conductivity_s_m',-1)]:
            s=stackup();s['layers'][0][key]=value
            with self.assertRaises(ValueError):em.validate_stackup(s)

    def test_touchstone_one_port_ri_ma_db_and_wrapped_two_port_conversion(self):
        for fmt in ('RI','MA','DB'):
            import cmath
            lines=['# MHz S '+fmt+' R 50']
            for f in (100,200,300):
                z=complex(2,2*math.pi*f*1e6*2e-9);s=(z-50)/(z+50)
                a,b=(s.real,s.imag) if fmt=='RI' else (abs(s) if fmt=='MA' else 20*math.log10(abs(s)),math.degrees(cmath.phase(s)))
                lines.append(f'{f} {a:.16g} {b:.16g} ! synthetic RL')
            rows=em.touchstone('\n'.join(lines),1)
            for f,r,x in zip(rows['frequency_hz'],rows['z_real_ohm'],rows['z_imag_ohm']):
                self.assertAlmostEqual(r,2,places=10);self.assertAlmostEqual(x/(2*math.pi*f),2e-9,places=18)
        # Diagonal Z=25+j10 per port, zero mutual -> Zdiff=50+j20.
        s=(complex(25,10)-50)/(complex(25,10)+50)
        text=f'# Hz S RI R 50\n100 {s.real} {s.imag} 0 0\n0 0 {s.real} {s.imag}\n200 {s.real} {s.imag} 0 0 0 0 {s.real} {s.imag}'
        rows=em.touchstone(text,2)
        self.assertAlmostEqual(rows['z_real_ohm'][0],50);self.assertAlmostEqual(rows['z_imag_ohm'][0],20)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.s2p';path.write_text(text)
            with self.assertRaises(OSError):em.load_results(path)
            metadata=results(em.manifest(self.p,self.cid,self.did));path.with_suffix('.json').write_text(json.dumps(metadata))
            loaded=em.load_results(path);self.assertEqual(loaded['frequency_hz'],[100,200]);em.validate_results(loaded,em.manifest(self.p,self.cid,self.did))

    def test_touchstone_rejects_singular_nonfinite_and_unsupported_formats(self):
        for text in ('# Hz Z RI R 50\n1 2 3','# Hz S RI R -50\n1 0 0',
                     '# Hz S RI R 50\n1 1 0','# Hz S RI R 50\n1 nan 0','[Version] 2.0',
                     '# Hz S RI R 50\n1 0','# Hz S RI R 50\n1 0 0\n# Hz S RI R 50'):
            with self.assertRaises(ValueError):em.touchstone(text,1)


if __name__=='__main__':unittest.main()
