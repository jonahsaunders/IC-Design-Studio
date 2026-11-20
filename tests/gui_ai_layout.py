"""Exercise the layout assistant through the desktop, provider transport and history."""
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
        self.assertTrue(w.fix_button.isHidden())
        w.inspect(False).reject()
        p=layout_lab('layout-via')
        p['cells'][0]['shapes'][0]['points'][1]=[150,500]
        with self.assertRaises(ValueError):
            ai_layout.via_repair(p,p['top'],'lab_shape_2')

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
