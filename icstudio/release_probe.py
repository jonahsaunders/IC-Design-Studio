"""Exercise the frozen desktop app; write evidence even for a windowed executable."""
import json,os,platform,sys,time,traceback
from pathlib import Path

def main(output):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtCore import QSettings,QStandardPaths,Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .gui import Studio
    from .model import example,digest,clone,save_project,load_project,atomic_write
    from . import __version__
    report={'version':__version__,'os':platform.platform(),'architecture':platform.machine(),'frozen':bool(getattr(sys,'frozen',False)),'scale':os.environ.get('QT_SCALE_FACTOR','1'),'checks':[],'status':'failed'};window=None;app=None;errors=[]
    sys.excepthook=lambda t,v,tb:errors.append(''.join(traceback.format_exception(t,v,tb)))
    try:
        QStandardPaths.setTestModeEnabled(True)
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
        app=QApplication([]);app.setStyle('Fusion');QSettings('ICDesignStudio','Studio').clear();window=Studio(recover=False);window.resize(1440,940);window.show();QTest.qWait(100)
        assert window.dark;assert window.devicePixelRatioF()>=float(report['scale'])-.05
        report['checks'].append('native dark workspace and requested DPI scale')
        assert window.schematic.grid_style=='lines' and window.layout.grid_style=='lines'
        assert not window.unmapped_commands and 'Window' in window.task_menus
        report['checks'].append('0.14 visible schematic/layout grids and complete reorganized command map')
        grid_dialog=window.grid_settings_dialog();grid_dialog.fields['layout'][0].setCurrentIndex(1)
        assert window.layout.grid_style=='dots';grid_dialog.reject();window.layout.grid_style='lines'
        window.arrange_linked(Qt.Vertical);window.save_editor_workspace('Packaged workspace')
        window.reset_workspace();window.load_editor_workspace('Packaged workspace')
        assert window.canvases.orientation()==Qt.Vertical and window.mode_combo.currentIndex()==2
        window.reset_workspace();dialog=window.configure_windows();QTest.qWait(20)
        assert dialog.isVisible();dialog.grab().save(str(out/'configure-windows.png'));dialog.reject()
        report['checks'].append('0.14 packaged grid controls, configurable windows and saved stacked views')
        p=example();window.set_project(p);p=clone(window.project);path=out/'Round trip with spaces.icproj';save_project(p,path);window.set_project(load_project(path),path)
        assert digest(window.project)==digest(p);report['checks'].append('save and reopen from a path containing spaces')
        d=window.cell['devices'][1];window.select([d['id']]);window.schematic.setFocus();old=d['rotation'];QTest.keyClick(window.schematic,Qt.Key_R);assert window.cell['devices'][1]['rotation']==(old+90)%360;window.undo();assert window.cell['devices'][1]['rotation']==old
        report['checks'].append('native rotation shortcut and undo')
        window.start_job(clone(window.project['analysis']));deadline=time.monotonic()+30
        while window.process and time.monotonic()<deadline:QTest.qWait(20)
        assert not window.process,'Simulation worker timed out'
        assert window.result and len(window.result['x'])==501,window.console.toPlainText();report['checks'].append('background worker simulation returns 501 transient samples')
        window.command_actions['Compatibility matrix'].trigger();QTest.qWait(20)
        assert window._compatibility_dialog.isVisible() and window.compatibility_table.rowCount()==8
        window._compatibility_dialog.close();report['checks'].append('0.15 shipped Help action opens the offline compatibility matrix')
        window.parallel_jobs.setValue(2)
        runs=[window.start_job(clone(window.project['analysis'])) for _ in range(3)]
        assert [r['state'] for r in runs]==['Running','Running','Queued']
        deadline=time.monotonic()+35
        while window.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
        assert all(r['state']=='Complete' for r in runs),window.console.toPlainText()
        assert window.simulation_runs.rowCount()==4
        report['checks'].append('0.15 packaged parallel workers, queued dispatch and run table')
        window.add_spec_row({'name':'Output limit','expression':'final(V("vout"))','min':'0','max':'1.81','unit':'V'});window.save_specifications()
        assert window.result_categories.count()==4 and window.results_tabs.tabBar().isHidden()
        from .wavecalc import evaluate as calculate
        assert calculate('final(V("vout"))',window.result).values[0]>=0
        dialog=window.wavecalc_dialog();assert len(dialog.plots)==1;dialog.close()
        from .parametric import build
        data=build(window.project,window.cid,None,{'kind':'contact','rows':2,'columns':2});assert len(data['shapes'])==6
        from .distributed_rc import extract
        from .exchange_review import review
        from .run_environment import stamp
        report['checks'].append('0.16 packaged specifications, grouped navigation, waveform calculator and parametric geometry')
        from .measurements import evaluate
        marker=window.plot.add_marker('XY',25e-6,1.8,'vout')
        assert evaluate(window.result,marker)['verdict']=='PASS'
        window.waveform_tools.open_manager();dialog=window.waveform_tools.dialog
        assert dialog.isVisible() and 'PASS' in window.waveform_tools.csv_text()
        dialog.close();report['checks'].append('0.15 packaged exact X/Y marker checks and measurement export')
        window.analysis_type.setCurrentIndex(window.analysis_type.findData('tran'));window.add_simulation_setup()
        path=out/'Analysis plan.icproj';save_project(window.project,path);window.set_project(load_project(path),path)
        assert len(window.project['simulation_setups'])==1 and window.simulation_runs.rowCount()==4
        report['checks'].append('0.15 saved analysis plan and durable result history reopen')
        from .lifecycle import duplicate_project
        from .model import uid
        copied=duplicate_project(window.project,out/('Independent copy '+uid()+'.icproj'))
        assert copied['id']!=window.project['id'];report['checks'].append('independent project copy')
        from .components import import_component
        from .model import device,flatten
        source=out/'Reusable component.spice';atomic_write(source,'* reusable divider\n.subckt divider a b r=10k\nR1 a b {r}\n.ends\n.end\n')
        component_project=example('empty');cid=import_component(component_project,source,'divider')
        component_project['cells'][0]['devices']=[device('X','X1',cell=cid,nets={'a':'input','b':'0'},parameters={'r':'20k'})]
        assert float(flatten(component_project)[0]['value'])==20000
        report['checks'].append('parameterized SPICE component import and instance override')
        window.runtime_dialog();QTest.qWait(30);window._runtime_dialog.close()
        report['checks'].append('native simulation runtime dialog')
        window.open_silicon();QTest.qWait(30);assert window.results_tabs.tabText(window.silicon_tab)=='Physical workflow'
        assert window.cell['name'] in window.silicon_status.text() and 'linked technology' in window.silicon_status.text()
        report['checks'].append('native physical workflow workspace')
        from .testbenches import create
        component_project['cells'][0]['devices'][0].pop('parameters',None)
        component_project['cells'][0]['devices'].append(device('V','V1',nets={'p':'input','n':'0'},value='1.8'))
        component_project['testbenches']=[create(component_project,component_project['top'],'saved_fixture')]
        window.set_project(component_project);window.open_testbenches();assert window.bench_table.rowCount()==1
        window.edit_testbench();QTest.qWait(30);assert window._testbench_dialog.isVisible();window._testbench_dialog.close()
        path=out/'Saved testbench.icproj';save_project(window.project,path);window.set_project(load_project(path),path);assert window.project['testbenches'][0]['name']=='saved_fixture'
        report['checks'].append('saved testbench workspace, native editor and project round trip')
        # Exercise the new saved study form even on build hosts without ngspice.
        from .testbenches import get
        t=window.project['testbenches'][0];t['analysis']={'type':'op','corner':'nominal','temperature':27};t['measurements']=[{'name':'supply_current','kind':'current','source':'V1','min':'-200u','max':'0'}];t['characterization']={'kind':'sweep','target':'V1.value','values':['.9','1.8']}
        window.refresh();dlg=window.characterization_dialog();QTest.qWait(30);assert dlg.fields['target'].text()=='V1.value';dlg.close()
        report['checks'].append('native saved-bench characterization workspace and form')
        exe=os.environ.get('ICSTUDIO_PROBE_NGSPICE')
        if exe:
            window.settings.setValue('engine/ngspice',exe);window.cid=t['dut_cell'];window.run_characterization();deadline=time.monotonic()+45
            while window.process and time.monotonic()<deadline:QTest.qWait(20)
            assert not window.process,'Characterization worker timed out'
            r=window._characterization_result;assert r and r['status']=='passed',window.console.toPlainText();assert r['cell_id']==t['bench_cell'] and r['summary']['runs']==2
            window.characterization_table.selectAll();window.characterization_probe.setCurrentIndex(window.characterization_probe.count()-1);window.characterization_waveforms();assert len(window.characterization_plot.overlays)==1
            report['checks'].append('actual ngspice saved-bench worker and current overlay from frozen executable')
        # New capture and symbol modules must also work inside the frozen distribution.
        from . import capture_ops,wiring
        from .symbol_geometry import generated,enriched
        from .symbol_io import default_symbol
        p=example();c=p['cells'][0];wiring.migrate(c,p);resistor=next(d for d in c['devices'] if d['kind']=='R')
        window.set_project(p);cid=window.cid;window.select([resistor['id']]);window.set_capture_profile('Xschem-inspired');window.schematic.setFocus();QTest.keyClick(window.schematic,Qt.Key_M,Qt.ControlModifier);assert window.schematic.tool=='capture_stretch';window.cancel_tool()
        before=clone(window.cell['devices'][1]['nets']);window.capture_commit(lambda q:capture_ops.transform(q,cid,[resistor['id']],20,20),'Packaged stretch');assert window.cell['devices'][1]['nets']==before;window.undo()
        window.capture_commit(lambda q:capture_ops.make_cell(q,cid,[resistor['id']],'capture_cell'),'Packaged cell extraction');inst=next(d for d in window.cell['devices'] if d['kind']=='X');window.select([inst['id']]);window.capture_enter(True);dlg=window._symbol_dialog;dlg.generate();dlg.pad.command('fit');dlg.grab().save(str(out/'symbol-editor.png'));dlg.save();assert dlg.saved,dlg.error.text()
        window.select([inst['id']]);window.capture_enter();assert window.cid==inst['cell'];window.capture_leave();assert window.cid==cid;report['checks'].append('packaged Xschem capture profile, electrical stretch, cell extraction, symbol generator and hierarchy return')
        from .testbenches import create
        bench=create(window.project,cid,'capture_fixture');window.commit(lambda q:q.update(testbenches=[bench]),'Packaged capture fixture');path=out/'Capture fixture.icproj';save_project(window.project,path);window.set_project(load_project(path),path);assert window.project['testbenches'][0]['dut_cell']==inst['cell'];report['checks'].append('packaged symbol metadata and saved capture testbench round trip')
        if exe:
            window.settings.setValue('engine/ngspice',exe);window.run_testbench();deadline=time.monotonic()+45
            while window.process and time.monotonic()<deadline:QTest.qWait(20)
            assert not window.process and window._bench_result,window.console.toPlainText();assert window._bench_result['measurements']['status']=='passed';report['checks'].append('actual ngspice worker simulates newly extracted capture cell in frozen app')
        # Exercise 0.13 review, policy and occurrence navigation in the shipped app.
        from PySide6.QtWidgets import QDialogButtonBox
        root=window.cid;child=capture_ops.cell(window.project,inst['cell']);old=child['ports'][0];new=old+'_v13';before=clone(window.project['cells']);window.open_symbol_editor(child);dialog=window._symbol_dialog;s=clone(dialog.pad.symbol);s['pins'][new]=s['pins'].pop(old);s['pin_meta'][new]=s['pin_meta'].pop(old);s['pin_order']=[new if n==old else n for n in s['pin_order']];dialog.pad.apply(s);dialog.save();review=window._interface_review;assert not dialog.saved and review.apply_button.isEnabled(),review.error.text();review.grab().save(str(out/'interface-review.png'));review.apply();assert dialog.saved and new in capture_ops.cell(window.project,child['id'])['ports'];window.undo();assert window.project['cells']==before;window.redo();path=out/'Reviewed interface.icproj';save_project(window.project,path);window.set_project(load_project(path),path);window.cid=root;window.refresh(True);assert capture_ops.cell(window.project,child['id'])['interface_history'];report['checks'].append('packaged reviewed interface rename, atomic undo/redo and saved multi-view history')
        window.electrical_policy_dialog();dialog=window._electrical_policy;dialog.scope.setCurrentIndex(1);dialog.fields['ERC.DANGLING'].setCurrentText('error');dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click();assert window.project['electrical_rules']['scope']=='project' and window.check_revision==window.project['revision'];report['checks'].append('packaged native electrical rule policy and project-scope checks')
        window.open_cross_probe();dialog=window._cross_probe;row=next(i for i,r in enumerate(dialog.state['rows']) if r['path']==[inst['id']]);dialog.table.selectRow(row);dialog.act('schematic');assert window.cid==child['id'] and window._capture_stack[-1][1]==[inst['id']];dialog.close();window.capture_leave();assert window.cid==root;report['checks'].append('packaged hierarchy occurrence cross-probe and return to parent')
        # Exercise 0.11 through the frozen Qt surface and packaged editor modules.
        from .layout import rect
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',0,0,1000,1000)];sid=c['shapes'][0]['id']
        window.set_project(p);window.mode_combo.setCurrentIndex(1);window.set_keyboard_profile('Classic analog',{});window.activateWindow();window.layout.setFocus();QTest.qWait(30)
        QTest.keyClick(window.layout,Qt.Key_R);assert window.layout.tool=='rect';window.cancel_tool();window.select([sid],'layout');window.editor_execute('copy_ref',{'dx':2000,'dy':0});assert len(window.cell['shapes'])==2;window.undo();assert len(window.cell['shapes'])==1
        window.select([sid],'layout');dlg=window.editor_properties();assert dlg.fields['layer'].count()>1;dlg.close();report['checks'].append('packaged 0.11 keyboard profile, reference copy, undo and bulk property form')
        child={'id':uid(),'name':'context_unit','ports':[],'devices':[],'shapes':[rect('metal2',0,0,1000,1000)]};p['cells'].append(child);inst={'id':uid(),'name':'P1','cell':child['id'],'x':3000,'y':4000,'rotation':90,'mirror':True,'nx':1,'ny':1};c['layout_instances']=[inst]
        window.set_project(p);window.mode_combo.setCurrentIndex(1);window.select([inst['id']],'layout');window.enter_edit_context();assert window.cid==child['id'] and window.layout.context_shapes;window.leave_edit_context();assert window.cid==c['id'];report['checks'].append('packaged rotated and mirrored hierarchy context and return')
        window.save_editor_workspace('Release');window.mode_combo.setCurrentIndex(0);window.load_editor_workspace('Release');assert window.current_mode=='layout';dlg=window.editor_library();assert dlg.fields['cells'].count()==2;dlg.close();assert (Path(__file__).resolve().parents[1]/'docs/CAPABILITY_MATRIX_0.11.md').is_file();report['checks'].append('packaged named workspace, library/cell/view browser and capability guide')
        pdk_root=os.environ.get('ICSTUDIO_PROBE_PDK_ROOT')
        if pdk_root:
            from .analog import reference
            from .analog_layout import generate_mirror,matching_findings
            from .gf180_layout import reference_project,generate_inverter
            from .layout_edit import place_via
            for family in ('sky130A','gf180mcuC'):
                folder=Path(pdk_root).resolve()/family;manifest=json.loads((folder/'package.json').read_text());tech=manifest['technology'];tech.update(package_root=str(folder),package_lock={k:manifest[k] for k in ('id','revision','files')})
                if family=='sky130A':
                    p,cid,key=reference(tech);generate_mirror(p,cid);assert not matching_findings(p,cid)
                else:p,cid=reference_project(tech);generate_inverter(p,cid);key=p['testbenches'][0]['id']
                window.set_project(p);window.cid=cid;window._selected_testbench=key;window.mode_combo.setCurrentIndex(1);window.refresh(True);window.check_linked_layout();assert not window.issues,window.issues
                c=next(c for c in p['cells'] if c['id']==cid);pt=next(v['point'] for v in c['layout_pins'] if v['pin']=='g');before=len(window.cell['shapes'])
                window.commit(lambda q:place_via(q,cid,'M1 to M2',pt),'Probe via');assert len(window.cell['shapes'])==before+3;window.undo();assert len(window.cell['shapes'])==before
                report['checks'].append(family+' native geometry, ports, connectivity and via undo from packaged modules')
                from .layout_edit import via_options
                from PySide6.QtCore import QPointF
                m1,cut,m2,_,_=via_options(window.project['pdk'])['M1 to M2'];window.layer_combo.setCurrentText(m1);window.start_layout_tool('path');window.layout.drawing=[QPointF(*pt)];window.layer_combo.setCurrentText(m2)
                assert len(window.cell['shapes'])==before+3 and window.layout.layer==m2 and window.layout.drawing==[QPointF(*pt)];window.cancel_tool();window.undo();assert len(window.cell['shapes'])==before
                report['checks'].append(family+' native via transition and grouped undo from packaged editor')
                if all(os.environ.get('ICSTUDIO_PROBE_'+name.upper()) for name in ('magic','netgen','ngspice')):
                    for name in ('magic','netgen','ngspice'):window.settings.setValue('engine/'+name,os.environ['ICSTUDIO_PROBE_'+name.upper()])
                    t=window.selected_testbench();t['characterization']={**t['characterization'],'compare_layout':True,'values':t['characterization']['values'][:1]};window.run_characterization();deadline=time.monotonic()+300
                    while window.process and time.monotonic()<deadline:QTest.qWait(30)
                    assert not window.process,'Packaged physical comparison worker timed out'
                    r=window._characterization_result;assert r and r['status']=='passed',window.console.toPlainText();window.characterization_probe.setCurrentIndex(window.characterization_probe.count()-1);window.characterization_waveforms();assert len(window.characterization_plot.overlays)==1
                    report['checks'].append(family+' actual full DRC, LVS, extracted comparison and overlay from packaged worker')
        from .xschem_project import apply_review as apply_direct,review_schematic,export_project
        dialog=window.open_xschem_example();QTest.qWait(50);assert dialog.open_button.isEnabled(),dialog.record['errors'];p=apply_direct(dialog.record);dialog.reject();window.set_project(p);export_project(p,out/'xschem-direct');q=apply_direct(review_schematic(out/'xschem-direct/amplifier.sch'));assert q['id']==p['id'] and len(q['cells'])==2;window.set_project(q);window.mode_combo.setCurrentIndex(0);report['checks'].append('packaged direct Xschem dependency review, editable hierarchy, export and native identity restoration')
        from .xschem_runtime import find_ngspice
        bundled=find_ngspice()
        if bundled:
            window.settings.setValue('engine/ngspice',bundled);window.maybe_save=lambda:True;window.open_xschem_program_example();assert window.current_analysis_settings()['type']=='xschem';window.quick_run();deadline=time.monotonic()+45
            while window.run_manager.busy and time.monotonic()<deadline:QTest.qWait(30)
            assert not window.run_manager.busy,'Xschem program worker timed out';row=window.run_manager.rows[-1];assert row['state']=='Complete',row['log'];assert row['result']['program_status']=='Complete',row['result']['warnings'];assert len(row['result']['xschem_cases'])==6;window.refresh_xschem_cases();assert window.xschem_case_table.rowCount()==6
            window.select_xschem_case_data(2);marker=window.plot.add_marker('XY',.0005,1.01,'out');assert evaluate(window.result,marker)['verdict']=='PASS';window.select_xschem_case_data(5);assert evaluate(window.result,marker)['verdict']=='FAIL';window.select_xschem_case_data(3);assert window.result['plot_kind']=='ac'
            report['checks'].append('0.18 included offline Xschem symbols, bundled ngspice program worker, six cases, waveform selection and exact X/Y checks')
        window.fit_active();QTest.qWait(100);assert window.grab().save(str(out/'desktop.png'));assert not errors,errors;report['status']='passed'
    except Exception:
        report['error']=traceback.format_exc()
        if sys.stderr:print(report['error'],file=sys.stderr)
    finally:
        if window:
            if window.process:window.cancel_job();window.process.waitForFinished(3000)
            window.saved_hash=digest(window.project);window.close()
        atomic_write(out/'release-test.json',json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1
