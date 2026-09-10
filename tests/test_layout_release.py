import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import clone, History, validate, file_digest, design_digest, uid
from icstudio.analog import reference
from icstudio.analog_layout import generate_mirror, matching_findings
from icstudio.physical import connectivity, erase
from icstudio.physical_cells import transform_selection, ports, assign_port
from icstudio.layout_edit import place_via, stretch_path, align
from icstudio.layout import rect
from icstudio.characterization import run, read_case, csv_text
from icstudio.verification_navigation import collect, device_map, waveform
from test_silicon import technology


class LayoutReleaseTests(unittest.TestCase):
    def mirror(self):
        p,cid,key=reference(technology());generate_mirror(p,cid)
        return p,cid,next(c for c in p['cells'] if c['id']==cid)

    def test_mirror_landed_ports_and_no_opens_or_shorts(self):
        p,cid,c=self.mirror();self.assertFalse(connectivity(p,cid)['issues']);self.assertFalse(matching_findings(p,cid))
        self.assertEqual({v['name'] for v in ports(p,cid)},set(c['ports']))

    def test_matching_checks_actual_asymmetric_polygon_edits(self):
        p,cid,c=self.mirror();shape=next(s for s in c['shapes'] if s['layer']=='poly');shape['points'][1][0]+=50
        self.assertIn('MATCH.GEOMETRY',{i['code'] for i in matching_findings(p,cid)})

    def test_matching_survives_complete_rotation_and_mirror(self):
        p,cid,c=self.mirror();transform_selection(p,cid,[s['id'] for s in c['shapes']],1000,2000,90,True,include_annotations=True)
        self.assertFalse(matching_findings(p,cid));self.assertFalse(connectivity(p,cid)['issues'])

    def test_mirror_rejects_ratio_and_different_axis(self):
        p,cid,c=self.mirror();b=c['devices'][1];b['params']['w']='5u'
        with self.assertRaisesRegex(ValueError,'equal'):generate_mirror(p,cid,True)
        p,cid,c=self.mirror();ids=[s['id'] for s in c['shapes'] if s.get('generated_device')==c['devices'][1]['id']]
        transform_selection(p,cid,ids,0,1000);self.assertIn('MATCH.ALIGNMENT',{i['code'] for i in matching_findings(p,cid)})

    def test_open_has_net_and_guides_for_navigation(self):
        p,cid,c=self.mirror();erase(c,'m2',[3000,-1000,4000,0]);r=connectivity(p,cid)
        finding=next(i for i in r['issues'] if i['code']=='LVS.OPEN');self.assertEqual(finding['net'],'IREF');self.assertEqual(finding['cell_id'],cid);self.assertTrue(any(g['net']=='IREF' for g in r['guides']))

    def test_stretch_preserves_manhattan_and_rejects_collapse(self):
        p,cid,c=self.mirror();s={'id':uid(),'kind':'path','layer':'m1','points':[[0,20000],[1000,20000],[1000,21000],[2000,21000]],'width':340,'net':'','device_id':''};c['shapes'].append(s)
        stretch_path(p,cid,s['id'],1,500);self.assertEqual(s['points'],[[0,20000],[1500,20000],[1500,21000],[2000,21000]])
        old=clone(s)
        with self.assertRaisesRegex(ValueError,'collapses'):stretch_path(p,cid,s['id'],1,500)
        self.assertEqual(s,old)
        with self.assertRaisesRegex(ValueError,'Unlock'):stretch_path(p,cid,s['id'],1,5,['m1'])

    def test_align_first_reference_and_atomic_undo(self):
        p,cid,c=self.mirror();a=rect('m1',0,20000,400,400);b=rect('m1',1000,21000,400,400);c['shapes'] += [a,b];h=History(p)
        h.commit(lambda q:align(q,cid,[a['id'],b['id']],'bottom'),'Align');cc=next(c for c in h.project['cells'] if c['id']==cid)
        self.assertEqual(next(s for s in cc['shapes'] if s['id']==a['id']),a);self.assertEqual(cc['shapes'][-1]['points'][0],[1000,20000]);h.undo();self.assertEqual(h.project['cells'],p['cells'])

    def test_align_rejects_partial_device_selection(self):
        p,cid,c=self.mirror()
        with self.assertRaisesRegex(ValueError,'complete'):align(p,cid,[c['shapes'][0]['id'],c['shapes'][-1]['id']],'left')

    def test_via_requires_assets_and_respects_locks(self):
        p,cid,c=self.mirror();old=clone(p)
        with self.assertRaisesRegex(ValueError,'Unlock'):place_via(p,cid,'M1 to M2',[0,0],'',['via'])
        with self.assertRaisesRegex(ValueError,'PDK lock'):place_via(p,cid,'M1 to M2',[0,0])
        self.assertEqual(p,old)

    def test_via_stack_physically_connects_two_layers(self):
        p,cid,c=self.mirror();c['shapes'] += [rect('m1',20000,20000,1000,340),rect('m2',20000,20000,340,1000)]
        with patch('icstudio.process_adapters.ProcessAdapter.engine_assets',return_value={}):ids=place_via(p,cid,'M1 to M2',[20170,20170])
        groups=connectivity(p,cid)['groups'];self.assertTrue(any(set(ids)<=set(g) for g in groups));self.assertEqual(len({s['via_group'] for s in c['shapes'] if s['id'] in ids}),1)

    def gf_tech(self,root):
        # Synthetic locked assets test adapter mechanics; real engine qualification is separate.
        t=technology();t['package_lock']['id']='gf180mcuC';t['package_root']=str(root);t['layers']=[]
        for kind,model in [('NMOS','nfet_03v3'),('PMOS','pfet_03v3')]:t['simulation']['catalog'][kind]['model']=model
        for rel in ('libs.tech/magic/gf180mcuC.tech','libs.tech/netgen/gf180mcuC_setup.tcl'):
            f=root/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('Synthetic unit-test asset\n');t['package_lock']['files'][rel]=file_digest(f)
        return t

    def test_gf180_layers_ports_units_and_generation(self):
        from icstudio.gf180_layout import reference_project,generate_inverter,specification
        with tempfile.TemporaryDirectory() as tmp:
            tech=self.gf_tech(Path(tmp));tech['layers']=[{'name':'placeholder','gds':1,'datatype':222,'color':'#123456','width':0,'space':0}]
            p,cid=reference_project(tech);lock=clone(p['pdk']['package_lock']);generate_inverter(p,cid);c=next(c for c in p['cells'] if c['id']==cid)
            self.assertFalse(connectivity(p,cid)['issues']);self.assertEqual(p['pdk']['package_lock'],lock)
            self.assertEqual({l['datatype'] for l in p['pdk']['layers'] if l['name'] in {t['layer'] for t in c['layout_texts']}},{10})
            inferred=clone(p);next(cc for cc in inferred['cells'] if cc['id']==cid).pop('layout_ports');self.assertEqual({r['name'] for r in ports(inferred,cid)},set(c['ports']))
            d=clone(c['devices'][0])
            for field,value in [('w','.9u'),('l','.275u'),('l','2.005u')]:
                bad=clone(d);bad['params'][field]=value
                with self.assertRaises(ValueError):specification(p['pdk'],bad)
            d['model_params']['nf']='2'
            with self.assertRaisesRegex(ValueError,'one finger'):specification(p['pdk'],d)

    def test_gf180_does_not_enable_ring_or_mirror(self):
        from icstudio.process_adapters import capabilities
        t=technology();t['package_lock']['id']='gf180mcuC';c=capabilities(t);self.assertEqual(c['native_layout'],['mos','inverter']);self.assertIn('No release',c['physical_evidence'])

    def test_layout_comparison_retains_failed_cases_and_pre_waveforms(self):
        p,cid,c=self.mirror();t=p['testbenches'][0];spec={**t['characterization'],'compare_layout':True};count=[0]
        def verify(sample,key,out,tools,progress):
            count[0]+=1;out.mkdir();status='failed' if count[0]==2 else 'passed';report={'status':status,'stages':[{'evidence':{}}],'comparison':[],'error':'deliberate LVS failure' if status=='failed' else ''}
            for stage in ('schematic',) if status=='failed' else ('schematic','post-layout'):
                work=out/stage;work.mkdir();wave={'project_id':p['id'],'design_hash':design_digest(sample),'cell_id':t['bench_cell'],'x':[0],'traces':{'ref':[.7]},'measurements':{'measurements':[{'name':'output_current','value':50e-6,'unit':'A','status':'passed'}]}};(work/'result.json').write_text(json.dumps(wave))
            (out/'report.json').write_text(json.dumps(report));return report
        with tempfile.TemporaryDirectory() as tmp,patch('icstudio.hierarchical_flow.run',verify):
            r=run(p,t['id'],spec,'fake',Path(tmp)/'study',tools={});self.assertEqual(r['summary'],{'runs':3,'passed':2,'failed':1});self.assertEqual(r['status'],'failed');self.assertEqual(read_case(r,1)['traces'],{'ref':[.7]})
            with self.assertRaisesRegex(ValueError,'LVS'):read_case(r,1,'post-layout')
            self.assertIn('deliberate LVS failure',csv_text(r));self.assertIn('before_value',csv_text(r))
            row=r['characterization_rows'][0];f=Path(r['evidence_directory'])/row['post_result_file'];f.write_text('{}')
            with self.assertRaisesRegex(ValueError,'missing or changed'):read_case(r,0,'post-layout')

    def test_navigation_maps_engine_property_to_shared_child(self):
        from icstudio.ring_oscillator import reference as ring
        p,cid,key=ring(technology());mapping=device_map(p,cid);name='sky130_fd_pr__nfet_01v8_X1_MN1';loc=mapping[name.casefold()]
        self.assertNotEqual(loc['cell_id'],cid)
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);(work/'lvs').mkdir();(work/'lvs/lvs.json').write_text(json.dumps([{'properties':[[[name,[['l','.15']]],['extracted',[['l','.2']]]]]}]))
            r=collect(p,cid,work);self.assertEqual(r[0]['object'],loc['object']);self.assertEqual(r[0]['cell_id'],loc['cell_id'])

    def test_lvs_rejects_unique_match_with_disconnected_or_altered_pins(self):
        from icstudio.engines import require_lvs_match
        good='Cell pin lists are equivalent.\nCircuits match uniquely.\n'
        require_lvs_match(good)
        for bad in ('Cell gf180_nmos disconnected node: B\n',
                    'B | (no matching pin)\n',
                    'Cell pin lists for gf180_nmos and gf180_nmos altered to match.\n',
                    'Property errors were found.\n'):
            with self.subTest(evidence=bad),self.assertRaisesRegex(ValueError,'connected pins'):
                require_lvs_match(bad+good)
        with self.assertRaises(ValueError):require_lvs_match('Circuits match uniquely.\n')

    def test_navigation_maps_missing_body_pin_to_exact_native_net(self):
        p,cid,c=self.mirror();net=c['ports'][0]
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);(work/'lvs').mkdir();(work/'lvs/lvs.json').write_text(json.dumps([{'name':[c['name'],c['name']],'pins':[[net],['(no matching pin)']]}]))
            finding=collect(p,cid,work)[0];self.assertEqual(finding['code'],'NETGEN.PIN');self.assertEqual(finding['cell_id'],cid);self.assertEqual(finding['net'],net)

    def test_navigation_drc_scale_and_unknown_names_are_not_guessed(self):
        p,cid,c=self.mirror()
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);(work/'drc').mkdir();(work/'drc/navigation.tsv').write_text(c['name']+'\tBad width\t0,0,20,40\t0.005\nunknown\tBad width\t0,0,1,1\t1\n');r=collect(p,cid,work)
            self.assertEqual(len(r),1);self.assertEqual(r[0]['bbox'],[0,0,100,200]);self.assertEqual(r[0]['cell_id'],cid)

    def test_single_physical_waveform_requires_checksum_and_identity(self):
        p,cid,c=self.mirror();t=p['testbenches'][0]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'wave.json';path.write_text(json.dumps({'project_id':p['id'],'cell_id':t['bench_cell'],'design_hash':design_digest(p)}));ev={'waveform_file':'wave.json','waveform_sha256':file_digest(path)}
            r={'project_id':p['id'],'design_hash':design_digest(p),'evidence_directory':tmp,'silicon_report':{'testbench':t,'stages':[{'name':'schematic_simulation','evidence':ev}]}}
            self.assertEqual(waveform(r,'schematic')['project_id'],p['id']);path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'checksum'):waveform(r,'schematic')


if __name__=='__main__':unittest.main()
