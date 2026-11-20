"""Exercise the layout assistant through the desktop, provider transport and history."""
import json
import tempfile
import unittest
from pathlib import Path

from icstudio import ai_layout
from icstudio.layout import drc, rect
from icstudio.model import clone, device, example, load_project, save_project
from icstudio.student_design_labs import layout_lab
from tests import gui_ai_assistant as desktop


class LayoutAssistant(unittest.TestCase):
    setUpClass = classmethod(desktop.AssistantDesktop.setUpClass.__func__)
    tearDownClass = classmethod(desktop.AssistantDesktop.tearDownClass.__func__)
    setUp = desktop.AssistantDesktop.setUp
    wait = desktop.AssistantDesktop.wait
    ask = desktop.AssistantDesktop.ask

    def start_via(self):
        s = self.studio
        s.set_project(layout_lab('layout-via'))
        s.activate_circuit_view(1)
        s.select(['lab_shape_2'],'layout')
        panel = s.ask_layout()
        self.assertEqual(panel.action.currentData(),'layout')
        return panel.layout_tools

    def test_enclosure_explain_preview_apply_undo(self):
        w = self.start_via()
        self.assertEqual(w.marker['measured_nm'],-50)
        self.assertEqual(len(w.marker['edges']),2)
        self.assertIn('enclosure rules',w.details.toPlainText())
        s = self.studio
        before = clone(s.cell['shapes'])
        self.panel.note.setText('Fix the via enclosure.')
        self.ask('The cut overhangs the landing pad.\n```layout\n{"action":"preview_via_move"}\n```')
        self.assertEqual(s.cell['shapes'],before)
        dialog=w.geometry_windows[-1]
        self.assertTrue(dialog.apply.isEnabled())
        dialog.apply.click()
        self.assertNotEqual(s.cell['shapes'][-1]['points'],before[-1]['points'])
        self.assertEqual(s.cell['shapes'][:-1],before[:-1])
        self.assertFalse(w.marker)
        s.undo()
        self.assertEqual(s.cell['shapes'],before)

    def test_locked_stale_and_cancelled_repairs(self):
        w=self.start_via()
        s=self.studio
        before=clone(s.cell['shapes'])
        w.inspect(True).reject()
        self.assertEqual(s.cell['shapes'],before)
        dialog=w.inspect(True)
        s.layout.locked_layers.add('via1')
        dialog.apply.click()
        self.assertIn('Unlock',dialog.status.text())
        s.layout.locked_layers.clear()
        s.commit(lambda p:p.update(name='New revision'),'Rename')
        dialog.apply.click()
        self.assertIn('changed',dialog.status.text())
        self.assertEqual(s.cell['shapes'],before)
        dialog.reject()

    def test_marker_edges_and_unsupported_repairs(self):
        s = self.studio
        s.set_project(layout_lab('layout-spacing'))
        marker=next(i for i in drc(s.project,s.cid) if i['code']=='SPACE')
        w=s.ask_layout(marker).layout_tools
        self.assertEqual(w.marker['measured_nm'],100)
        self.assertEqual(len(w.marker['edges']),2)
        self.assertIn('0.1 µm',w.details.toPlainText())
        self.assertEqual(w.fix_button.text(),'Preview spacing fix')
        w.inspect(False).reject()
        p=layout_lab('layout-via')
        p['cells'][0]['shapes'][0]['points'][1]=[150,500]
        with self.assertRaises(ValueError):
            ai_layout.via_repair(p,p['top'],'lab_shape_2')

    def test_width_and_spacing_review_apply_match_preview_and_undo(self):
        from PySide6.QtWidgets import QCheckBox
        from icstudio.student_design_labs import check_layout
        s=self.studio
        for kind,index in [('width',0),('spacing',1)]:
            with self.subTest(kind=kind):
                lab='layout-'+kind
                s.set_project(layout_lab(lab))
                s.activate_circuit_view(1)
                w=s.ask_layout().layout_tools
                self.assertIsNone(w.marker)
                w.finding.setCurrentIndex(1)
                self.assertEqual(w.fix_button.text(),f'Preview {kind} fix')
                original=clone(s.cell['shapes'])
                revision=s.project['revision']
                w.fix_button.click()
                dialog=w.geometry_windows[-1]
                self.assertIn('100 → 200 nm',dialog.summary.text())
                self.assertIn(original[index]['id'],dialog.summary.text())
                dialog.mode.setCurrentText('After')
                dialog.mode.setCurrentText('Before')
                dialog.findChild(QCheckBox).click()
                self.assertFalse(dialog.exact.isHidden())
                dialog.reject()
                self.assertEqual(s.cell['shapes'],original)
                self.assertEqual(s.project['revision'],revision)
                # A direct shape selection also finds the second edge of a gap.
                s.select([original[index]['id']],'layout')
                w=s.ask_layout().layout_tools
                self.assertEqual(w.marker['code'],'WIDTH' if kind=='width' else 'SPACE')
                self.panel.note.setText('Preview the proposed fix.')
                self.ask('Review the geometry.\n```layout\n{"action":"preview_'+kind+'_fix"}\n```')
                self.assertEqual(s.cell['shapes'],original)
                dialog=w.geometry_windows[-1]
                exact=dialog.exact.toPlainText()
                dialog.apply.click()
                self.assertEqual(s.project['revision'],revision+1)
                self.assertEqual(w.geometry_windows,[])
                self.assertIn('After   '+json.dumps(s.cell['shapes'][index]['points']),exact)
                self.assertEqual(s.cell['shapes'][1-index],original[1-index])
                check_layout(s.project,lab)
                self.assertFalse(drc(s.project,s.cid))
                s.undo()
                self.assertEqual(s.cell['shapes'],original)

    def test_spacing_cannot_apply_a_stale_locked_or_mismatched_request(self):
        s=self.studio
        s.set_project(layout_lab('layout-spacing'))
        marker=drc(s.project,s.cid)[0]
        w=s.ask_layout(marker).layout_tools
        before=clone(s.cell['shapes'])
        with self.assertRaises(ValueError):
            w.receive('```layout\n{"action":"preview_width_fix"}\n```')
        dialog=w.inspect(True)
        s.layout.locked_layers.add('metal1')
        dialog.apply.click()
        self.assertIn('Unlock',dialog.status.text())
        s.layout.locked_layers.clear()
        s.commit(lambda p:p.update(name='Changed revision'),'Rename')
        dialog.apply.click()
        self.assertIn('changed',dialog.status.text())
        self.assertEqual(s.cell['shapes'],before)
        dialog.reject()

    def test_picker_targets_only_the_selected_violation(self):
        p=layout_lab('layout-width')
        second=rect('metal1',5000,0,100,1000,net='second')
        p['cells'][0]['shapes'].append(second)
        s=self.studio
        s.set_project(p)
        w=s.ask_layout().layout_tools
        self.assertEqual(w.finding.count(),3)
        w.finding.setCurrentIndex(1)
        first=w.inspect(True)
        target=next(i for i,f in enumerate(w.scope.findings,1) if f['object']==second['id'])
        w.finding.setCurrentIndex(0)
        self.assertFalse(first.isVisible())
        w.finding.setCurrentIndex(target)
        self.assertEqual(w.nets(),['second'])
        review=w.inspect(True)
        self.assertIn(second['id'],review.summary.text())
        before=clone(s.cell['shapes'])
        review.apply.click()
        self.assertEqual(s.cell['shapes'][:2],before[:2])
        self.assertEqual([i['object'] for i in drc(s.project,s.cid)],['lab_shape_0'])

    def test_background_selection_and_superseded_result(self):
        s=self.studio
        p=example('empty')
        cell=p['cells'][0]
        cell['shapes']=[rect('metal1',i*1200,0,250,250,net='routed' if i else '') for i in range(500)]
        s.live_check.setChecked(False)
        s.set_project(p)
        s.select([cell['shapes'][0]['id']],'layout')
        w=s.ask_layout().layout_tools
        self.assertIsNotNone(w.pending)
        self.wait(lambda:w.scope is not None)
        self.assertEqual(w.nets(),[])
        self.assertEqual(w.evidence()['selected_geometry'][0]['bbox_um'],[0,0,.25,.25])
        w.show_object()
        self.assertEqual(s.selection,[cell['shapes'][0]['id']])
        w.reload()
        s.set_project(layout_lab('layout-via'))
        s.select(['lab_shape_2'],'layout')
        s.ask_layout()
        from PySide6.QtCore import QThreadPool
        self.assertTrue(QThreadPool.globalInstance().waitForDone(6000))
        self.app.processEvents()
        self.assertEqual(w.marker['measured_nm'],-50)

    def test_cross_probe_compare_waveform_and_reopen_pin(self):
        s=self.studio
        p=example()
        c=p['cells'][0]
        dev=next(d for d in c['devices'] if d['name']=='R1')
        for net,length,width,offset in [('vin',2000,200,0),('vout',3000,300,1000)]:
            shape=rect('metal1',0,offset,length,width,device_id=dev['id'],net=net)
            shape.update(kind='path',points=[[0,offset],[length,offset]],width=width)
            c['shapes'].append(shape)
        s.set_project(p)
        from icstudio.simulation import run
        wave=run(s.project,s.cid,s.project['analysis'])
        row=dict(id='wave',name='RC transient',state='Complete',job=dict(project=clone(s.project),cell=s.cid,
                 settings=s.project['analysis'],engine='builtin'),log='',result=wave)
        s.run_manager.rows=[row]
        s.select([dev['id']],'schematic')
        w=s.ask_layout().layout_tools
        w.net.setCurrentText('vin')
        w.other.setCurrentText('vout')
        self.assertEqual(w.evidence()['second_minus_first']['path_length_um'],1)
        self.assertIn('R1',w.details.toPlainText())
        for kind in ('device current','device operating point'):
            i=next(i for i,(_,k,t) in enumerate(w.sources) if k==kind and t=='R1')
            w.source.setCurrentIndex(i)
            w.open_run()
            inspector=self.panel.windows[-1]
            if kind=='device current':
                self.assertEqual(tuple(inspector.probe.currentData()),('current','R1'))
                self.assertEqual(w.evidence()['waveform']['unit'],'A')
            else:
                self.assertIn(dev['id'],inspector.schematic.selection)
                self.assertIn('current',w.evidence()['operating_point']['values'])
            inspector.close()
        w.navigate(True)
        self.assertEqual(s.current_mode,'layout')
        self.assertEqual(s.selection,[s.cell['shapes'][0]['id']])
        w.navigate(False)
        self.assertIn(dev['id'],s.selection)
        i=next(i for i in range(w.target.count()) if w.target.itemData(i)[0]=='shape')
        w.target.setCurrentIndex(i)
        w.show_object()
        self.assertEqual(s.selection,[s.cell['shapes'][0]['id']])
        w.open_run()
        self.assertEqual(self.panel.windows[-1].row['name'],'RC transient')
        w.follow_wave(row,'vout')
        self.assertEqual(w.net.currentText(),'vout')
        w.net.setCurrentText('vin')
        w.save_pin('Match the output length and compare again.')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'review.icproj'
            save_project(s.project,path)
            s.set_project(load_project(path))
            w=s.ask_layout().layout_tools
            w.pins.setCurrentIndex(1)
            self.assertIn('Match the output length',w.details.toPlainText())
            self.assertEqual(len(w.evidence()['pinned_review']['routes']),2)
            self.assertEqual(w.nets(),['vin','vout'])

    def test_saved_extraction_provenance_and_per_net_values(self):
        from icstudio.distributed_rc import extract
        p=example('empty')
        c=p['cells'][0]
        cid=c['id']
        d=device('R','R1',nets={'p':'plus','n':'minus'})
        c['devices']=[d]
        c['layout_pins']=[]
        for pin,net,y in [('p','plus',0),('n','minus',4000)]:
            shape=rect('metal1',0,y,1,1,net=net)
            shape.update(kind='path',points=[[0,y],[20000,y]],width=1000)
            c['shapes'].append(shape)
            c['layout_pins'].append(dict(id='pin_'+pin,device_id=d['id'],pin=pin,layer='metal1',point=[0,y]))
        p['pdk']['parasitics']={'metal1':dict(sheet_ohm=2,cap_f_per_um2=1e-15)}
        self.studio.set_project(p)
        p=self.studio.project
        ext=extract(p,cid)
        row=dict(id='extracted',name='Interconnect RC',state='Complete',job=dict(project=p,cell=cid),
                 result=dict(extraction=ext,provenance=dict(network_hash=ext['network_hash'])))
        scope=ai_layout.LayoutScope(p,cid,[])
        nets=[m['net'] for m in ext['terminal_mapping'] if m['net']!='0']
        self.assertEqual(scope.sources([row],nets),[(row,'extraction','')])
        for n in nets:
            self.assertAlmostEqual(ai_layout.net_rc(ext,n)['segment_resistance_ohm'],40)
            self.assertAlmostEqual(ai_layout.net_rc(ext,n)['ground_cap_fF'],20)
        self.studio.run_manager.rows=[row]
        w=self.studio.ask_layout().layout_tools
        w.net.setCurrentText('plus')
        w.other.setCurrentText('minus')
        self.assertIn('Ground C difference',w.details.toPlainText())
        w.save_pin('Check pair symmetry.')
        self.studio.run_manager.rows=[]
        w.choose()
        self.assertIn('Pinned plus · Segment R sum 40 Ω · Ground C 20 fF',w.details.toPlainText())
        with self.assertRaisesRegex(ValueError,'unavailable'):
            w.open_pinned()
        ext['resistors'][0]['value']*=2
        self.assertEqual(scope.sources([row],nets),[])
        self.assertIsNone(ai_layout.net_rc(ext,'unrecorded'))
