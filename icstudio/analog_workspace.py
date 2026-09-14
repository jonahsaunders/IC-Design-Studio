"""One entry point for analog setup, regression, layout and saved evidence."""
from .model import clone


def assignments(text):
    rows={}
    for line in text.splitlines():
        if not line.strip():continue
        if '=' not in line:raise ValueError('Enter one name = value assignment per line.')
        name,value=(s.strip() for s in line.split('=',1))
        if not name or not value or name in rows:raise ValueError('Variable names must be unique and values cannot be empty.')
        rows[name]=value
    return rows


def install(studio):
    def show():
        from .analog_workspace_ui import AnalogWorkspace
        window=getattr(studio,'analog_workspace',None)
        if window is None or window.project_id!=studio.project['id']:
            if window:window.close();window.deleteLater()
            window=AnalogWorkspace(studio);studio.analog_workspace=window
        window.refresh_plans();window.show();window.raise_()
        return window
    studio.open_analog_workspace=show
    for menu in ('Simulate','Layout','Verify'):
        studio.action(studio.task_menus[menu],'Analog design workspace…',show)
