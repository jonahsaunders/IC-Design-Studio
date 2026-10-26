"""Independent negative controls for the bounded hierarchy readback."""
import copy
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest

import klayout.db as db
from icstudio.layout_import import read_layout
from scripts import audit_sky130_metal_resistor_hierarchy as audit
from scripts.audit_sky130_li_case import native_script, tcl_literal


def fixture(root,model='m1',angle=0):
    ly=db.Layout();ly.dbu=.001;child=ly.create_cell('coupon');layer=audit.LAYERS[model]
    child.shapes(ly.layer(layer,20)).insert(db.Box(0,-500,2000,5500))
    child.shapes(ly.layer(layer,13)).insert(db.Box(0,0,2000,5000))
    child.shapes(ly.layer(layer,5)).insert(db.Text('R1',db.Trans(1000,-250)))
    child.shapes(ly.layer(layer,5)).insert(db.Text('R2',db.Trans(1000,5250)))
    leaf=root/'leaf.gds';ly.write(str(leaf));child.name='res_leaf';top=ly.create_cell('res_pair')
    placed=((0,False,0,0),(90,True,40000,0)) if angle==0 else ((90,False,0,0),(180,True,0,40000))
    for index,place in enumerate(placed,1):
        t=db.ICplxTrans(1,*place);top.insert(db.CellInstArray(child.cell_index(),t))
        for name,point in (('A',(1000,-250)),('B',(1000,5250))):
            p=t*db.Point(*point);top.shapes(ly.layer(layer,5)).insert(db.Text(name+str(index),db.Trans(p.x,p.y)))
    path=root/'input.gds';ly.write(str(path));return leaf,path


def extraction(model='m1'):
    return ('.subckt res_pair A1 B1 A2 B2\n'
        f'R0 A1 B1 sky130_fd_pr__res_generic_{model} w=2 l=5\n'
        f'R1 B2 A2 sky130_fd_pr__res_generic_{model} w=2 l=5\n.ends res_pair\n')


class HierarchyAuditTests(unittest.TestCase):
    def test_short_bridge_leaves_143nm_terminal_margin_to_both_resistor_bodies(self):
        marker=db.Region(db.Box(-1000,-2500,1000,2500))
        conductor=db.Region(db.Box(-1000,-2786,1000,2786))
        base=({(68,13):marker,(68,20):conductor},
              [((68,5),'R1',0,-2643),((68,5),'R2',0,2643)])
        clean,labels=audit.expected_flat(base,0)
        changed,_,addition=audit.bridge_masks(base)
        self.assertTrue((addition & clean[68,13]).is_empty())
        self.assertTrue((changed[68,13] ^ clean[68,13]).is_empty())
        terminals=(changed[68,20]-changed[68,13]).merged()
        self.assertEqual(terminals.count(),3)
        points={name:db.Point(x,y) for _,name,x,y in labels}
        joined=[p for p in terminals.each() if p.inside(points['A1'])]
        self.assertEqual(len(joined),1)
        self.assertTrue(joined[0].inside(points['A2']))
        self.assertFalse(joined[0].inside(points['B1']))
        self.assertFalse(joined[0].inside(points['B2']))
        old=db.Region(db.Box(37357-200,-6843,37357+200,200))
        self.assertGreater((old & clean[68,13]).area(),0)

    def test_written_hierarchy_masks_and_four_anchors_both_whole_rotations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for model in audit.MODELS:
                for angle in (0,90):
                    with self.subTest(model=model,angle=angle):
                        leaf,path=fixture(root,model,angle);base=audit.leaf(leaf,model)
                        result=audit.stream(path,model,angle,base)
                        self.assertEqual(result['instances'],2)
                        self.assertEqual({r[2] for r in result['terminal_anchors']},{'A1','B1','A2','B2'})
                        ly=db.Layout();ly.read(str(path));oas=root/'roundtrip.oas';ly.write(str(oas))
                        audit.stream(oas,model,angle,base)
                        top=ly.cell('res_pair');child=ly.cell('res_leaf')
                        for index in ly.layer_indexes():
                            for shape in list(child.shapes(index).each()):
                                if shape.is_text():shape.delete()
                        top.flatten(True);private=root/'private.gds';ly.write(str(private))
                        audit.stream(private,model,angle,base,private=True)

    def test_exact_transform_not_just_flattened_mask_equivalence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);leaf,path=fixture(root);base=audit.leaf(leaf,'m1')
            for change in ('mirror','rotation','translation','multiplicity','flatten'):
                with self.subTest(change=change):
                    ly=db.Layout();ly.read(str(path));top=ly.cell('res_pair');second=list(top.each_inst())[1]
                    if change=='flatten':top.flatten(True)
                    elif change=='multiplicity':second.na=2;second.a=db.Vector(10000,0)
                    else:
                        t=second.cplx_trans
                        second.cplx_trans=db.ICplxTrans(1,0 if change=='rotation' else t.angle,False if change=='mirror' else t.is_mirror(),t.disp.x+(1 if change=='translation' else 0),t.disp.y)
                    bad=root/'bad.gds';ly.write(str(bad))
                    with self.assertRaises(ValueError):audit.stream(bad,'m1',0,base)

    def test_marker_hole_and_unrelated_mask_are_not_a_valid_native_leaf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);leaf,_=fixture(root)
            for change in ('hole','mask','label'):
                ly=db.Layout();ly.read(str(leaf));top=ly.top_cell()
                if change=='hole':
                    index=ly.layer(68,13);top.shapes(index).clear();poly=db.Polygon(db.Box(0,0,2000,5000));poly.insert_hole(db.Box(500,500,1000,1000));top.shapes(index).insert(poly)
                elif change=='mask':top.shapes(ly.layer(69,20)).insert(db.Box(1,1,2,2))
                else:top.shapes(ly.layer(68,5)).insert(db.Text('R1',db.Trans()))
                bad=root/'bad.gds';ly.write(str(bad))
                with self.assertRaises(ValueError):audit.leaf(bad,'m1')

    def test_saved_project_retains_actual_reused_leaf_and_ports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);leaf,path=fixture(root);base=audit.leaf(leaf,'m1');p,_=read_layout(path)
            package=dict(id='sky130A',revision='fixture',files={});p['pdk']['package_lock']=copy.deepcopy(package)
            top=next(c for c in p['cells'] if c['id']==p['top']);top['ports']=list(audit.PORTS)
            saved=root/'saved.json';saved.write_text(json.dumps(p));audit.project(saved,'m1',0,base,package)
            for change in ('ports','cell','mirror','marker','device'):
                q=copy.deepcopy(p);parent=next(c for c in q['cells'] if c['id']==q['top']);child=next(c for c in q['cells'] if c['name']=='res_leaf')
                if change=='ports':parent['ports'][2]='A1'
                elif change=='cell':parent['layout_instances'][1]['cell']=parent['id']
                elif change=='mirror':parent['layout_instances'][1]['mirror']=False
                elif change=='marker':child['shapes'][0]['points'][0][0]+=1
                else:child['devices'].append({'model':'fabricated'})
                saved.write_text(json.dumps(q))
                with self.assertRaises(ValueError):audit.project(saved,'m1',0,base,package)

    def test_native_extraction_requires_exact_graph_model_and_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'extracted.spice';text=extraction();path.write_text(text)
            self.assertEqual(audit.native_circuit(path,'m1')['devices'],2)
            changed=[text.replace('B2 A2','B2 A1'),text.replace('B2 A2','B1 A2'),text.replace('res_generic_m1','res_generic_m2'),
                text.replace('w=2','w=nan'),text.replace('w=2','w=3'),text.replace('l=5','l=4'),text.replace('l=5','l=5 m=2'),
                text.replace('l=5','l=5 w=2'),text.replace('A1 B1 A2 B2','B1 A1 A2 B2'),text+'.include arbitrary\n',
                '\n'.join(text.splitlines()[:2]+text.splitlines()[3:]),text.replace('.ends res_pair','.ends other'),
                text.replace('R1 B2','r0 B2')]
            for value in changed:
                with self.subTest(value=value):
                    path.write_text(value)
                    with self.assertRaises(ValueError):audit.native_circuit(path,'m1')

    def test_cross_instance_fault_requires_only_the_named_A_short(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'extracted.spice';text=extraction().replace('B2 A2','B2 A1')
            for ports in ('A1 B1 A2 B2','A1 B1 B2'):
                path.write_text(text.replace('A1 B1 A2 B2',ports));audit.native_circuit(path,'m1',short=True)
            for value in (extraction(),text.replace('A1 B1 A2 B2','A1 B1 WRONG B2'),text.replace('A1 B1 A2 B2','A1 B2 B1'),
                          extraction().replace('B2 A2','B1 A2'),text.replace('B2 A1','A1 A1')):
                path.write_text(value)
                with self.assertRaises(ValueError):audit.native_circuit(path,'m1',short=True)

    def test_only_exact_reference_fault_is_accepted(self):
        clean=audit.reference_text('m1')
        self.assertEqual(audit.reference_text('m1','physical-cross-instance-short'),clean)
        self.assertEqual(audit.reference_text('m1','merged-reference-terminal'),clean.replace('X2 A2 B2','X2 A1 B2'))
        self.assertEqual(audit.reference_text('m1','missing-reference-instance'),clean.replace('X2 A2 B2 resistor_leaf\n',''))
        changed=audit.reference_text('m1','second-reference-width')
        self.assertEqual(changed.count('w=3'),1);self.assertIn('X1 A1 B1 resistor_leaf',changed);self.assertIn('X2 A2 B2 changed_leaf',changed)

    def test_width_fault_log_requires_exact_native_property_mismatch_for_both_observed_conclusions(self):
        for model in audit.MODELS:
            full='sky130_fd_pr__res_generic_'+model
            common=f'changed_leaf:2/{full}:LEAF vs. {full}:1:\n w circuit1: 3   circuit2: 2   (delta=40%, cutoff=1%)\n'
            tail='\nThe following cells had property errors:\n res_pair\n'
            forms=[common+'\nFinal result: Circuits match uniquely.\nProperty errors were found.\n'+tail,
                   'Netlists match with 2 symmetries with property errors.\n'+common+'\nFinal result: Top level cell failed pin matching.\n'+tail]
            for log in forms:
                audit.width_mismatch(log,model)
                for bad in (log.replace('circuit1: 3','circuit1: 4'),log.replace('circuit2: 2','circuit2: nan'),
                            log.replace(full,'unrelated_model'),log.replace(' res_pair',' different_top'),
                            log.replace(' w circuit1:', ' l circuit1:'),log+common,
                            log.replace('Final result:','Unfinished result:')):
                    with self.assertRaises(ValueError):audit.width_mismatch(bad,model)

    def test_canonical_native_scripts_bind_four_ports_settings_and_original_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);origin=PurePosixPath('/original/run/m1/r0/physical');pdk=PurePosixPath('/original/pdk')
            old=''.join(f'if {{![port "R{n}" exists]}} {{error "Missing layout port R{n}"}}\nport "R{n}" index {n}\n' for n in (1,2))
            new=''.join(f'if {{![port "{name}" exists]}} {{error "Missing layout port {name}"}}\nport "{name}" index {n}\n' for n,name in enumerate(audit.PORTS,1))
            for stage in ('drc','lvs-extraction'):
                folder=root/stage;folder.mkdir();(folder/'run.tcl').write_text(native_script(origin,stage).replace('load "coupon"','load "res_pair"').replace(old,new))
                (folder/'startup.tcl').write_text('tech load '+tcl_literal(pdk/'libs.tech/magic/sky130A.tech')+'\ndrc euclidean on\n')
            audit.scripts(root,origin,pdk)
            for relative,before,after in (('drc/run.tcl','drc ignore none','drc ignore all'),('lvs-extraction/run.tcl','blackbox off','blackbox on'),
                                         ('drc/startup.tcl','/original/pdk','/substituted/pdk'),('drc/run.tcl','port "A2" index 3','port "A2" index 1')):
                path=root/relative;data=path.read_text();path.write_text(data.replace(before,after))
                with self.assertRaises(ValueError):audit.scripts(root,origin,pdk)
                path.write_text(data)


if __name__=='__main__':unittest.main()
