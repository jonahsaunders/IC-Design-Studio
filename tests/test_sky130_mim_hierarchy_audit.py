"""Independent imported MiM graph, stream, execution and EXT corruption checks."""
import copy
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest

import klayout.db as db
from icstudio.layout_import import read_layout
from scripts import audit_sky130_mim_hierarchy as audit
from scripts.audit_sky130_mim_physical_case import execution_scripts


def fixture(root, plate=1, angle=0):
    base = audit.literal_leaf(plate)
    ly = db.Layout(); ly.dbu = .001; child = ly.create_cell('device_coupon')
    for layer, region in base[0].items(): child.shapes(ly.layer(*layer)).insert(region)
    for layer, name, x, y in base[1]: child.shapes(ly.layer(*layer)).insert(db.Text(name,db.Trans(x,y)))
    leaf = root/'leaf.gds'; ly.write(str(leaf)); child.name = audit.LEAF; top = ly.create_cell(audit.TOP)
    for place in audit.placements(angle): top.insert(db.CellInstArray(child.cell_index(),db.ICplxTrans(1,*place)))
    for layer,name,x,y in audit.expected_flat(base,angle)[1]: top.shapes(ly.layer(*layer)).insert(db.Text(name,db.Trans(x,y)))
    path = root/'input.gds'; ly.write(str(path)); return leaf,path,base


def extraction(plate=1, missing=False):
    rows = ['.subckt mim_pair P1 N1 P2 N2',f'X0 P1 N1 sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10']
    if not missing: rows.append(f'X1 P2 N2 sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10 m=1')
    return '\n'.join([*rows,'.ends mim_pair',''])


def normalization_fixture(root, plate):
    _, path, base = fixture(root,plate)
    ly = db.Layout(); ly.read(str(path)); child = ly.cell(audit.LEAF)
    for index in ly.layer_indexes():
        for shape in list(child.shapes(index).each()):
            if shape.is_text(): shape.delete()
    ly.cell(audit.TOP).flatten(True); ly.write(str(root/'layout.gds'))
    masks,_ = audit.cell_regions(ly,ly.top_cell()); capkey = (89,44) if plate == 1 else (97,44)
    cutkey = (69+plate,44); bottomkey = (69+plate,20)
    electrodes = []; original = ['timestamp 1\nscale 1000 1 500\n']; corrected = list(original); changes = []
    for i,cap in enumerate(masks[capkey].each()):
        box = cap.bbox(); bottom = next(p for p in masks[bottomkey].each() if (db.Region(cap)-db.Region(p)).is_empty())
        contacts = []
        for cut in masks[cutkey].each():
            region = db.Region(cut)
            if (region-db.Region(bottom)).is_empty() and not (region-db.Region(cap)).is_empty():
                v = cut.bbox(); contacts.append([v.left,v.bottom,v.right,v.top])
        axis = 'x' if box.width() == 2000 else 'y'
        electrodes.append(dict(model=audit.model(plate),box=[box.left,box.bottom,box.right,box.top],axis=axis,bottom_contacts=contacts))
        line = f'device csubckt {audit.model(plate)} {box.left//5} {box.bottom//5} {box.right//5} {box.top//5} w={box.width()//5} l={box.height()//5} "P{i+1}" "N{i+1}"\n'
        original.append(line)
        changed = line.replace('w=2000 l=400','w=400 l=2000') if axis == 'y' else line
        if changed != line: changes.append(dict(electrode=i,before=line.rstrip(),after=changed.rstrip()))
        corrected.append(changed)
    ext = root/'lvs-extraction'; ext.mkdir()
    (ext/'native-original.ext').write_text(''.join(original)); (ext/'mim_pair.ext').write_text(''.join(corrected))
    (ext/'native-extraction.log').write_text('STUDIO_MIM_SCALE 0.005\nSTUDIO_MAGIC_COMPLETE\n')
    proof = dict(schema=1,model=audit.model(plate),models=[audit.model(plate)],technology_sha256=audit.TECH_SHA,pcell_sha256=audit.PCELL_SHA,
        gds_sha256=audit.sha(root/'layout.gds'),native_sha256=audit.sha(ext/'native-original.ext'),corrected_sha256=audit.sha(ext/'mim_pair.ext'),
        gds_dbu_um=.001,native_coordinate_nm=5,electrodes=electrodes,changes=changes)
    (ext/'mim-orientation.json').write_text(json.dumps(proof)); return ext,proof


class MiMHierarchyAuditTests(unittest.TestCase):
    def test_literal_contract_matches_actual_application_leaf_bytes(self):
        # Exercise real application output, without any native tool invocation.
        from scripts.qualify_sky130_mim2 import fixture as app_fixture
        from icstudio.interchange import export_layout
        from icstudio.model import save_project
        package=audit.load(audit.ROOT/'icstudio/assets/pdks/sky130A/package.json')
        tech=copy.deepcopy(package['technology']);tech['package_lock']={k:package[k] for k in ('id','revision','files')}
        with tempfile.TemporaryDirectory() as tmp:
            for plate in audit.PLATES:
                path=Path(tmp)/f'p{plate}.gds';project=app_fixture(tech,(2,10,1),plate);export_layout(project,path)
                base=audit.leaf(path,plate);saved=Path(tmp)/f'p{plate}.icproj';save_project(project,saved)
                audit.leaf_project(saved,plate,package,base)
                project['cells'][0]['layout_instances']=[{'cell':'unrelated'}];saved.write_text(json.dumps(project))
                with self.assertRaises(ValueError):audit.leaf_project(saved,plate,package,base)

    def test_contract_is_pinned_before_native_execution(self):
        self.assertEqual(audit.sha(audit.ROOT/audit.CONTRACT_PATH),audit.CONTRACT_SHA)
        value=audit.load(audit.ROOT/audit.CONTRACT_PATH)
        self.assertEqual(value['acceptance']['clean_cases'],4)
        self.assertEqual(value['acceptance']['native_fault_jobs'],8)
        self.assertEqual(value['acceptance']['exchange_controls'],10)
        self.assertFalse(value['qualified'])

    def test_actual_hierarchy_and_stream_roundtrip_both_models_rotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            for plate in audit.PLATES:
                for angle in (0,90):
                    with self.subTest(plate=plate,angle=angle):
                        leaf,path,base=fixture(root,plate,angle);audit.leaf(leaf,plate)
                        self.assertEqual(audit.stream(path,plate,angle,base)['instances'],2)
                        ly=db.Layout();ly.read(str(path));oas=root/'roundtrip.oas';ly.write(str(oas));audit.stream(oas,plate,angle,base)
                        for index in ly.layer_indexes():
                            for shape in list(ly.cell(audit.LEAF).shapes(index).each()):
                                if shape.is_text():shape.delete()
                        ly.cell(audit.TOP).flatten(True);private=root/'private.gds';ly.write(str(private));audit.stream(private,plate,angle,base,private=True)

    def test_leaf_wrong_mask_contact_polarity_and_dimensions_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();leaf,_,_=fixture(root)
            for change in ('mask','cut','label','dimension'):
                ly=db.Layout();ly.read(str(leaf));cell=ly.top_cell()
                if change=='mask':cell.shapes(ly.layer(68,20)).insert(db.Box(0,0,100,100))
                elif change=='cut':next(cell.shapes(ly.layer(70,44)).each()).delete()
                elif change=='dimension':cell.shapes(ly.layer(89,44)).insert(db.Box(0,0,3000,10000))
                else:
                    shape=next(s for s in cell.shapes(ly.layer(71,5)).each() if s.text.string=='P');text=shape.text;text.string='N';shape.text=text
                bad=root/'bad.gds';ly.write(str(bad))
                with self.subTest(change=change),self.assertRaises(ValueError):audit.leaf(bad,1)

    def test_exact_occurrence_transform_required_even_if_masks_rehashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();_,path,base=fixture(root)
            for change in ('mirror','rotation','translation','array','flatten','top-label'):
                ly=db.Layout();ly.read(str(path));top=ly.cell(audit.TOP);second=list(top.each_inst())[1]
                if change=='flatten':top.flatten(True)
                elif change=='array':second.na=2;second.a=db.Vector(50000,0)
                elif change=='top-label':
                    shape=next(s for s in top.shapes(ly.layer(71,5)).each() if s.text.string=='P2');text=shape.text;text.string='P1';shape.text=text
                else:
                    t=second.cplx_trans;second.cplx_trans=db.ICplxTrans(1,0 if change=='rotation' else t.angle,False if change=='mirror' else t.is_mirror(),t.disp.x+(1 if change=='translation' else 0),t.disp.y)
                bad=root/'bad.gds';ly.write(str(bad))
                with self.subTest(change=change),self.assertRaises(ValueError):audit.stream(bad,1,0,base)

    def test_saved_project_rejects_recreated_devices_wrong_child_and_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();_,path,base=fixture(root);p,_=read_layout(path)
            package=dict(id='sky130A',revision='test',files={});p['pdk']['package_lock']=copy.deepcopy(package)
            next(c for c in p['cells'] if c['name']==audit.TOP)['ports']=list(audit.PORTS)
            dest=root/'saved.icproj';dest.write_text(json.dumps(p));audit.project(dest,1,0,base,package)
            for change in ('device','child','mirror','port','mask'):
                q=copy.deepcopy(p);top=next(c for c in q['cells'] if c['name']==audit.TOP);child=next(c for c in q['cells'] if c['name']==audit.LEAF)
                if change=='device':child['devices'].append({'model':'reconstructed'})
                elif change=='child':top['layout_instances'][1]['cell']=top['id']
                elif change=='mirror':top['layout_instances'][1]['mirror']=False
                elif change=='port':top['ports'][2]='P1'
                else:child['shapes'][0]['points'][0][0]+=1
                dest.write_text(json.dumps(q))
                with self.subTest(change=change),self.assertRaises(ValueError):audit.project(dest,1,0,base,package)

    def test_native_actual_two_x_devices_need_ordered_independent_polarity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.spice'
            for plate in audit.PLATES:
                original=extraction(plate);path.write_text(original);audit.native_circuit(path,plate)
                changes=[original.replace('X1 P2 N2','X1 N2 P2'),original.replace('X1 P2 N2','X1 P1 N2'),original.replace('X1 P2 N2','X1 P2 N1'),
                    original.replace('w=2','w=3'),original.replace('l=10','l=2'),original.replace('m=1','m=2'),original.replace('w=2','w=nan'),
                    original.replace('w=2','w=2 w=2'),original.replace('X1','x0'),original.replace(f'_m3_{plate}',f'_m3_{3-plate}'),
                    original.replace('P1 N1 P2 N2','N1 P1 P2 N2'),original+'.include replaced.spice\n',extraction(plate,True)]
                for changed in changes:
                    path.write_text(changed)
                    with self.subTest(plate=plate,changed=changed),self.assertRaises(ValueError):audit.native_circuit(path,plate)
                missing=extraction(plate,True)
                for header in ('P1 N1 P2 N2','P1 N1'):
                    path.write_text(missing.replace('P1 N1 P2 N2',header));audit.native_circuit(path,plate,True)
                path.write_text(missing.replace('X0 P1 N1','X0 P2 N2'))
                with self.assertRaises(ValueError):audit.native_circuit(path,plate,True)

    def test_only_named_reference_change_accepted(self):
        for plate in audit.PLATES:
            text=audit.reference_text(plate)
            self.assertEqual(audit.reference_text(plate,'physical-missing-instance'),text)
            self.assertEqual(audit.reference_text(plate,'merged-reference-terminal'),text.replace('X2 P2 N2','X2 P1 N2'))
            self.assertEqual(audit.reference_text(plate,'missing-reference-instance'),text.replace('X2 P2 N2 capacitor_leaf\n',''))
            changed=audit.reference_text(plate,'second-reference-width');self.assertEqual(changed.count('w=3'),1)
            self.assertIn('X1 P1 N1 capacitor_leaf',changed);self.assertIn('X2 P2 N2 changed_leaf',changed)

    def test_ext_correction_preserves_every_other_byte_and_all_electrode_sites(self):
        for plate in audit.PLATES:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();ext,proof=normalization_fixture(root,plate);audit.normalization(root,plate,2)
                original=(ext/'mim_pair.ext').read_bytes()
                for change in ('net','width','extra-device','scale','claimed-axis'):
                    altered=copy.deepcopy(proof);(ext/'mim_pair.ext').write_bytes(original)
                    if change=='net':(ext/'mim_pair.ext').write_bytes(original.replace(b'"P1"',b'"P2"'))
                    elif change=='width':(ext/'mim_pair.ext').write_bytes(original.replace(b'w=400',b'w=401',1))
                    elif change=='extra-device':(ext/'mim_pair.ext').write_bytes(original+b'device csubckt fabricated\n')
                    elif change=='scale':altered['native_coordinate_nm']=10
                    else:altered['electrodes'][0]['axis']='y' if altered['electrodes'][0]['axis']=='x' else 'x'
                    altered['corrected_sha256']=audit.sha(ext/'mim_pair.ext');(ext/'mim-orientation.json').write_text(json.dumps(altered))
                    with self.subTest(plate=plate,change=change),self.assertRaises(ValueError):audit.normalization(root,plate,2)

    def test_exact_native_tcl_binds_all_ports_and_no_blackbox_or_ignored_drc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();origin=PurePosixPath('/original/p1/r0/physical');pdk=PurePosixPath('/original/pdk')
            old=''.join(f'if {{![port "{n}" exists]}} {{error "Missing layout port {n}"}}\nport "{n}" index {i}\n' for i,n in enumerate(('P','N'),1))
            new=''.join(f'if {{![port "{n}" exists]}} {{error "Missing layout port {n}"}}\nport "{n}" index {i}\n' for i,n in enumerate(audit.PORTS,1))
            for name,text in execution_scripts(str(origin),str(pdk/'libs.tech/magic/sky130A.tech')).items():
                path=root/name;path.parent.mkdir(exist_ok=True);path.write_text(text.replace('"device_coupon"','"mim_pair"').replace(old,new))
            audit.scripts(root,origin,pdk)
            for relative,before,after in [('drc/run.tcl','drc ignore none','drc ignore all'),('lvs-extraction/run.tcl','blackbox off','blackbox on'),
                ('lvs-extraction/native-extraction.tcl','index 4','index 1'),('drc/startup.tcl','/original/pdk','/substituted/pdk')]:
                path=root/relative;text=path.read_text();path.write_text(text.replace(before,after))
                with self.assertRaises(ValueError):audit.scripts(root,origin,pdk)
                path.write_text(text)

    def test_width_fault_needs_exact_property_model_and_native_conclusion(self):
        for plate in audit.PLATES:
            full=audit.model(plate)
            log=f'changed_leaf:2/{full}:LEAF vs. {full}:1:\n w circuit1: 3 circuit2: 2 (delta=40%, cutoff=1%)\nFinal result: Circuits match uniquely.\nProperty errors were found.\nThe following cells had property errors:\n mim_pair\n'
            audit.width_mismatch(log,plate)
            actual_form=log.replace('Final result: Circuits match uniquely.\nProperty errors were found.',
                'Netlists match uniquely with property errors.\nFinal result: Top level cell failed pin matching.')
            audit.width_mismatch(actual_form,plate)
            with self.assertRaises(ValueError):audit.width_mismatch(actual_form.replace('Netlists match uniquely with property errors.','Netlists match uniquely.'),plate)
            for bad in (log.replace('circuit1: 3','circuit1: 4'),log.replace('circuit2: 2','circuit2: nan'),log.replace(' w circuit1:',' l circuit1:'),
                        log.replace(full,'unrelated'),log.replace(full,'unrelated')+'\n'+full,
                        log.replace(' mim_pair',' another_top'),log.replace('Final result:','unfinished'),log.replace('Property errors were found.','')):
                with self.assertRaises(ValueError):audit.width_mismatch(bad,plate)


if __name__=='__main__':unittest.main()
