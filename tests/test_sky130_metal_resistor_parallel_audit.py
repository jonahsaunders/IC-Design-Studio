"""Independent semantic controls for selected physical parallel arrays."""
from pathlib import Path,PurePosixPath
import math
import tempfile
import unittest
from scripts import audit_sky130_metal_resistor_parallel as audit


def extracted(model='m1',count=3,w=2,l=5):
    return '.subckt coupon R1 R2\n'+''.join(
        f'R{i} R1 R2 sky130_fd_pr__res_generic_{model} w={w} l={l}\n' for i in range(count))+'.ends coupon\n'


def raw_fixture(analysis,mutation=None):
    scale='v(v-sweep)' if analysis=='dc' else 'frequency'
    grid=[-.001+i*.0001 for i in range(21)] if analysis=='dc' else [1000*10**(i/3) for i in range(22)]
    # Direct public LI equation at W2/L5, m3 and27C; no auditor observation call.
    resistance=12.2*5e-6/(2e-6+17e-9)*(1+6.045e-4*(-3)-3.693e-7*9)/3
    data={scale:list(grid),'v(input)':list(grid) if analysis=='dc' else [1.]*len(grid)}
    for tag in ('a','n','c'):
        vin=data['v(input)'];out=[v/(1+resistance) for v in vin] if analysis=='dc' else [1/(1+resistance+2j*math.pi*f*resistance*1e-9) for f in grid]
        data['v(in_'+tag+')']=list(vin);data['v(out_'+tag+')']=out
        data['i(vs_'+tag+')']=[(a-b)/resistance for a,b in zip(vin,out)]
    for name,value in audit.COEFFICIENTS.items():data['v(par_'+name+')']=[value]*len(grid)
    if mutation=='response':data['v(out_n)']=[v*1.1 for v in data['v(out_n)']]
    if mutation=='current':data['i(vs_n)']=[0.]*len(grid)
    if mutation=='coefficient':data['v(par_rl1)']=[13.]*len(grid)
    if mutation=='missing-channel':del data['v(in_n)']
    if mutation=='nan':data['v(out_n)'][2]=float('nan')
    title='* array-independent-fixture'+(' substituted' if mutation=='title' else '')
    names=list(data);rows=[f'Title: {title}','Plotname: '+('AC Analysis' if analysis=='ac' else 'DC transfer characteristic'),
        'Flags: '+('complex' if analysis=='ac' else 'real'),f'No. Variables: {len(names)}',f'No. Points: {len(grid)}','Variables:']
    for i,name in enumerate(names):rows.append(f'{i}\t{name}\t'+('frequency' if name=='frequency' else 'voltage'))
    rows.append('Values:')
    for point in range(len(grid)):
        for channel,name in enumerate(names):
            value=data[name][point]
            rendered=f'{complex(value).real:.17g},{complex(value).imag:.17g}' if analysis=='ac' else f'{value:.17g}'
            rows.append((str(point)+'\t' if channel==0 else '\t')+rendered)
    return '\n'.join(rows)+'\n'


class ParallelAuditTests(unittest.TestCase):
    def test_parallel_native_comparison_requires_exact_aggregated_width_and_real_property_failure(self):
        for fault,pair in (('missing-unit',(6,4)),('one-unit-width',(6,7)),('reference-count',(4,6))):
            text=('Netlists match uniquely with property errors.\n'
                'sky130_fd_pr__res_generic_l1:_RES vs. sky130_fd_pr__res_generic_l1:0:\n'
                f' w circuit1: {pair[0]}   circuit2: {pair[1]}   (delta=40%, cutoff=1%)\n'
                'Final result: Circuits match uniquely.\nProperty errors were found.\n'
                'The following cells had property errors:\n coupon\n')
            audit.parallel_property_mismatch(text,'l1',fault)
            for changed in (text.replace(f'circuit2: {pair[1]}','circuit2: 2'),text.replace('generic_l1','generic_m1'),
                text.replace(' coupon',' unrelated'),text.replace('Property errors were found.',''),
                text.replace('Final result: Circuits match uniquely.','Final result: Netgen input failed.'),
                text+' w circuit1: 6   circuit2: 4   (delta=40%, cutoff=1%)\n'):
                with self.subTest(fault=fault),self.assertRaises(ValueError):audit.parallel_property_mismatch(changed,'l1',fault)

    def test_native_gds_presentation_is_distinct_from_oasis_terminal_semantics(self):
        import klayout.db as db
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);masks,labels=audit.expected_geometry('m1',2,5,3,90)
            for name,angle in (('original',1),('changed',0)):
                layout=db.Layout();layout.dbu=.001;cell=layout.create_cell('coupon')
                for pair,region in masks.items():cell.shapes(layout.layer(*pair)).insert(region)
                for pair,label,x,y in labels:cell.shapes(layout.layer(*pair)).insert(db.Text(label,db.Trans(angle,False,x,y)))
                layout.write(str(root/(name+'.gds')))
            audit.array_geometry(root/'changed.gds','m1',2,5,3,90)
            self.assertNotEqual(audit.text_presentation(root/'original.gds'),audit.text_presentation(root/'changed.gds'))

    def test_actual_input_deck_binding_rejects_path_count_corner_and_stimulus_substitution(self):
        from scripts import qualify_sky130_metal_resistor_parallel as producer
        spec=producer.contract();origin=PurePosixPath('/retained/original-run');selected={'tt':'.lib pdk-models/exact.spice tt'}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.cir'
            for row in audit.electrical_cases():
                for analysis in ('dc','ac'):
                    text=producer.deck(spec,row,row['rotation'],analysis,selected,origin);path.write_text(text)
                    audit.check_deck(path,origin,row,row['rotation'],analysis,selected)
            row=audit.electrical_cases()[0];text=producer.deck(spec,row,0,'dc',selected,origin)
            changes=(text.replace('extracted.spice','replacement.spice'),text.replace('X_BODY a b coupon','X_BODY a b coupon m=2',1),
                text.replace('exact.spice tt','exact.spice ff'),text.replace('.temp 27','.temp 30'),
                text.replace('VS_n input in_n DC 0 AC 0','VS_n input in_n DC 1 AC 0'),
                text.replace('CL_n out_n 0 1n','CL_n out_n 0 2n'),text.replace('.dc VDRIVE -.001 .001 .0001','.dc VDRIVE 0 .001 .0001'))
            for changed in changes:
                path.write_text(changed)
                with self.subTest(changed=changed[:120]),self.assertRaises(ValueError):audit.check_deck(path,origin,row,0,'dc',selected)

    def test_each_native_fault_requires_its_actual_unit_graph_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'extracted.spice'
            for model in audit.MODELS:
                good=extracted(model)
                variants={'missing-unit':extracted(model,2),'broken-branch':good.replace('R2 R1 R2','R2 floating R2'),
                    'bus-short':good.replace('.subckt coupon R1 R2','.subckt coupon R1').replace('R1 R2 sky130','R1 R1 sky130'),
                    'one-unit-width':good.replace('w=2','w=3',1),'reference-count':good}
                for fault,text in variants.items():
                    path.write_text(text);audit.native_fault_array(path,model,fault)
                    for altered in (text.replace('l=5','l=6',1),text.replace('res_generic_'+model,'res_generic_unknown',1),
                                    text.replace('R1 R1 R2','r0 R1 R2'),text+'.include synthetic.spice\n'):
                        if altered==text:continue
                        path.write_text(altered)
                        with self.subTest(model=model,fault=fault),self.assertRaises(ValueError):audit.native_fault_array(path,model,fault)
                path.write_text('.subckt coupon R1\n.ends coupon\n')
                with self.assertRaises(ValueError):audit.native_fault_array(path,model,'bus-short')

    def test_fault_masks_change_only_predeclared_units_or_bus_routes(self):
        import klayout.db as db
        for model in audit.MODELS:
            base,_=audit.expected_geometry(model,2,5,3);pair=(audit.LAYERS[model],13)
            for fault in audit.FAULTS:
                masks,labels=audit.fault_geometry(model,fault)
                self.assertEqual(labels,audit.expected_geometry(model,2,5,3)[1])
                if fault=='missing-unit':self.assertEqual(masks[pair].count(),2)
                elif fault=='one-unit-width':self.assertEqual(masks[pair].area(),35_000_000)
                else:self.assertTrue((masks[pair]^base[pair]).is_empty())
                if fault=='bus-short':self.assertEqual((masks[audit.LAYERS[model],20]-masks[pair]).merged().count(),1)
                if fault=='broken-branch':self.assertEqual((masks[audit.LAYERS[model],20]-masks[pair]).merged().count(),3)

    def test_actual_native_path_coefficients_currents_and_titles_are_all_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.raw'
            for analysis in ('dc','ac'):
                path.write_text(raw_fixture(analysis));result=audit.electrical_observation(path,'* array-independent-fixture',analysis,'l1',2,5,3)
                self.assertEqual(result['samples'],21 if analysis=='dc' else 22)
                for mutation in ('response','current','coefficient','missing-channel','nan','title'):
                    path.write_text(raw_fixture(analysis,mutation))
                    with self.subTest(analysis=analysis,mutation=mutation),self.assertRaises(ValueError):
                        audit.electrical_observation(path,'* array-independent-fixture',analysis,'l1',2,5,3)

    def test_fixed_physical_and_electrical_scope_is_complete_without_duplicates(self):
        cases=audit.physical_cases();self.assertEqual(len(cases),140)
        self.assertEqual(len({r['name'] for r in cases}),140)
        for model in audit.MODELS:
            selected=[r for r in cases if r['model']==model]
            self.assertEqual(len(selected),28)
            self.assertEqual([r['multiplicity'] for r in selected if (r['width_um'],r['length_um'])==(2,5)],list(range(1,17)))
        electrical=audit.electrical_cases();self.assertEqual(len(electrical),30)
        self.assertEqual({r['multiplicity'] for r in electrical},{2,3,16})
        self.assertEqual({r['rotation'] for r in electrical},{0,90})

    def test_expected_array_has_individual_bodies_and_only_two_buses_at_all_counts(self):
        import klayout.db as db
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'array.gds'
            for model in audit.MODELS:
                for count in range(1,17):
                    for rotation in (0,90):
                        masks,labels=audit.expected_geometry(model,2,5,count,rotation)
                        ly=db.Layout();ly.dbu=.001;cell=ly.create_cell('coupon')
                        for pair,region in masks.items():cell.shapes(ly.layer(*pair)).insert(region)
                        for pair,name,x,y in labels:cell.shapes(ly.layer(*pair)).insert(db.Text(name,db.Trans(x,y)))
                        ly.write(str(path));checked=audit.array_geometry(path,model,2,5,count,rotation)
                        self.assertEqual(checked['marker_count'],count)

    def test_single_unit_has_no_bus_extension_and_array_rejects_rehashed_geometry_changes(self):
        import klayout.db as db
        masks,_=audit.expected_geometry('m1',2,5,1)
        self.assertTrue((masks[68,20]^db.Region(db.Box(0,-500,2000,5500))).is_empty())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'array.gds'
            for mutation in ('marker','bridge','bus-gap','label'):
                masks,labels=audit.expected_geometry('m1',.5,.5,3)
                if mutation=='marker':masks[68,13]-=db.Region(db.Box(7000,0,7500,500))
                if mutation=='bridge':masks[68,20]+=db.Region(db.Box(-400,-250,250,750))
                if mutation=='bus-gap':masks[68,20]-=db.Region(db.Box(2000,-500,2100,0))
                if mutation=='label':labels[1]=((68,5),'R2',*labels[0][2:])
                ly=db.Layout();ly.dbu=.001;cell=ly.create_cell('coupon')
                for pair,region in masks.items():cell.shapes(ly.layer(*pair)).insert(region)
                for pair,name,x,y in labels:cell.shapes(ly.layer(*pair)).insert(db.Text(name,db.Trans(x,y)))
                ly.write(str(path))
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):audit.array_geometry(path,'m1',.5,.5,3)

    def test_each_supported_count_requires_separate_native_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'extracted.spice'
            for model in audit.MODELS:
                for count in range(1,17):
                    p.write_text(extracted(model,count));self.assertEqual(audit.native_array(p,model,2,5,count)['unit_count'],count)

    def test_missing_synthetic_merged_wrong_model_width_and_graph_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'extracted.spice';good=extracted()
            changed=(extracted(count=2),extracted(count=1).replace('l=5','l=5 m=3'),
                good.replace('R2 R1 R2','r0 R1 R2'),good.replace('R1 R2 sky130','R1 R1 sky130',1),
                good.replace('res_generic_m1','res_generic_l1',1),good.replace('w=2','w=2.4',1),
                good.replace('l=5','l=nan',1),good.replace('l=5','l=5 w=2',1),
                good+'.include replacement.spice\n',good.replace('.subckt coupon R1 R2','.subckt coupon R2 R1'))
            for text in changed:
                p.write_text(text)
                with self.subTest(text=text),self.assertRaises(ValueError):audit.native_array(p,'m1',2,5,3)

    def test_application_count_is_distinct_from_native_unit_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'reference.spice';good='.subckt coupon R1 R2\nR_R1 R1 R2 sky130_fd_pr__res_generic_l1 l=5 m=3 w=2\n.ends coupon\n'
            p.write_text(good);self.assertEqual(audit.application_reference(p,'l1',2,5,3)['multiplicity'],3)
            with self.assertRaises(ValueError):audit.native_array(p,'l1',2,5,3)
            for text in (good.replace('m=3','m=2'),good.replace('m=3','m=nan'),good.replace('w=2','w=2 w=2')):
                p.write_text(text)
                with self.assertRaises(ValueError):audit.application_reference(p,'l1',2,5,3)


if __name__=='__main__':unittest.main()
