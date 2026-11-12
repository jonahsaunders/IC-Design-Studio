"""Actual source Qt multiplicity preview/apply, routes, history and reopen."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    out=ap.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from icstudio.gui import Studio
    from icstudio.model import clone,save_project,load_project
    from icstudio.physical import connectivity
    from icstudio.sky130_metal_resistors import layers
    from icstudio.layout_eco import inventory
    from scripts.qualify_sky130_metal_resistor_parallel import editor_project,application_reference,contract
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication([]);studio=Studio(recover=False);studio.maybe_save=lambda:True;studio.live_check.setChecked(False)
    errors=[];studio.error=lambda text:errors.append(str(text));studio.show()
    report=dict(schema=1,status='RUNNING',mode='source-qt',installed_acceptance=False,qualified=False,scope=__doc__,models=[])
    original_review=studio.review_dialog;capture={'path':None}
    def capture_review(title,build,controls=None,apply_candidate=None):
        def captured_build():
            candidate,description=build()
            if capture['path'] is not None:save_project(candidate,capture['path'])
            return candidate,description
        return original_review(title,captured_build,controls,apply_candidate)
    studio.review_dialog=capture_review
    def save(name):save_project(studio.project,name)
    def verify(model,count,pins,routes,first):
        c=studio.cell;d=c['devices'][0];ls=layers(studio.project['pdk'],model)
        assert pins=={v['pin']:v['id'] for v in c['layout_pins']}
        assert [s for s in c['shapes'] if s['id'] in ('route-a','route-b')]==routes
        generated=[s for s in c['shapes'] if s.get('device_id')==d['id']]
        assert len(generated)==(2 if count==1 else 2*count+2)
        assert sum(s['layer']==ls['marker'] for s in generated)==count
        assert first=={s['generator_role']:s['id'] for s in generated if s['generator_role'] in first}
        assert inventory(studio.project,studio.cid)['devices'][0]['status']=='current'
        assert not connectivity(studio.project,studio.cid)['issues']
    try:
        spec=contract();package_path=root/spec['package']['path']/'package.json';package=json.loads(package_path.read_bytes())
        tech=clone(package['technology']);tech.update(package_root=str(package_path.parent),package_lock={k:package[k] for k in ('id','revision','files')})
        for model in spec['models']:
            folder=out/model;folder.mkdir();row=dict(model=model,width_um=2,length_um=5,multiplicity=1,name=model)
            p=editor_project(tech,row);c=p['cells'][0];did=c['devices'][0]['id'];ls=layers(tech,model)
            pins={v['pin']:v['id'] for v in c['layout_pins']};first={s['generator_role']:s['id'] for s in c['shapes']}
            routes=[dict(id='route-a',kind='path',layer=ls['conductor'],points=[[1000,-250],[-2000,-250]],width=400,net='R1',device_id=''),
                    dict(id='route-b',kind='path',layer=ls['conductor'],points=[[1000,5250],[-2000,5250]],width=400,net='R2',device_id='')]
            c['shapes'].extend(clone(routes));studio.set_project(p);studio.selection=[did];studio.refresh();save(folder/'before.icproj')
            events=[]
            for count in (3,16,2,1):
                stage=folder/f'm{count}';stage.mkdir();save(stage/'before.icproj')
                studio.commit(lambda project:project['cells'][0]['devices'][0]['model_params'].update(mult=count),'Change resistor multiplicity')
                studio.selection=[did];studio.refresh();save(stage/'requested.icproj');requested=clone(studio.project)
                capture['path']=stage/'proposed.icproj';dialog=studio.mos_layout_dialog()
                if dialog is not None:dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
                app.processEvents();assert studio.project==requested
                review=studio._review_dialog;button=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
                assert button.isEnabled(),errors
                if count==3:
                    studio.layout.locked_layers.add(ls['conductor']);button.click();app.processEvents()
                    assert review.isVisible() and studio.project==requested
                    save(stage/'late-locked.icproj');studio.layout.locked_layers.discard(ls['conductor'])
                button.click();app.processEvents();assert not review.isVisible(),errors
                verify(model,count,pins,routes,first);save(stage/'applied.icproj');applied=clone(studio.project)
                studio.undo();app.processEvents();assert studio.project['cells']==requested['cells'];save(stage/'undo.icproj')
                studio.redo();app.processEvents();assert studio.project['cells']==applied['cells'];save(stage/'restored.icproj')
                reopened=load_project(stage/'restored.icproj');assert reopened['cells']==studio.project['cells']
                studio.set_project(reopened);studio.selection=[did];studio.refresh();verify(model,count,pins,routes,first)
                (stage/'application.spice').write_text(application_reference(studio.project,{**row,'multiplicity':count}),encoding='utf-8',newline='\n')
                events.append(dict(multiplicity=count,folder=stage.name,status='PASS',late_lock_rejected=count==3))
            report['models'].append(dict(model=model,status='PASS',events=events,initial_pin_ids=pins,initial_shape_roles=first,routes=routes))
        assert not errors,errors
        report.update(status='PASS',platform=app.platformName(),simulation_manifest_sha256=hashlib.sha256(package_path.read_bytes()).hexdigest(),late_lock_rejections=5)
    except Exception:report.update(status='FAIL',errors=errors,error=traceback.format_exc())
    finally:studio.close();app.processEvents()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'files.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2));return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
