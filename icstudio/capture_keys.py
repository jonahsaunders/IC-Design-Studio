"""Canvas-scoped, user-editable command maps shared by schematic and symbol views."""
import json
from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog,QVBoxLayout,QComboBox,QTableWidget,QTableWidgetItem,QDialogButtonBox,QLabel,QHeaderView,QCheckBox
SCHEMATIC={
 'Studio':{'place':'I','wire':'W','label':'L','ground':'G','move':'M','stretch':'Shift+S','copy':'C','properties':'Q','rotate':'R','mirror':'Shift+F','fit':'F','enter':'E','symbol':'Shift+E','leave':'Ctrl+B','undo':'Ctrl+Z','redo':'Ctrl+Shift+Z','check':'Shift+X','cut':'Shift+W','repeat':'F4'},
 'Xschem-inspired':{'place':'Shift+I','wire':'W','label':'L','ground':'G','move':'M','stretch':'Ctrl+M','copy':'C','properties':'Q','rotate':'Shift+R','mirror':'Shift+F','fit':'F','enter':'E','symbol':'I','leave':'Backspace','undo':'U','redo':'Shift+U','check':'Shift+X','cut':'Shift+W','zoom_out':'Ctrl+Z','zoom_in':'Shift+Z','repeat':'F4'},
 'Virtuoso-inspired':{'place':'I','wire':'W','label':'L','ground':'G','move':'M','stretch':'S','copy':'C','properties':'Q','rotate':'R','mirror':'Shift+F','fit':'F','enter':'Shift+E','symbol':'Ctrl+E','leave':'Ctrl+B','undo':'U','redo':'Shift+U','check':'Shift+X','cut':'Shift+W','repeat':'F4'}}
SYMBOL={name:{**{k:v for k,v in keys.items() if k in ('move','stretch','copy','properties','rotate','mirror','fit','undo','redo','zoom_in','zoom_out')},'line':'L','rect':'B','polygon':'P','arc':'A','text':'T','pin':'I','delete':'Delete'} for name,keys in SCHEMATIC.items()}

def bindings(settings,view,name):
    presets=SCHEMATIC if view=='schematic' else SYMBOL
    defaults=presets.get(name,presets['Studio'])
    try:custom=json.loads(settings.value('capture/'+view+'/'+name,'{}'));return {key:custom.get(key,value) for key,value in defaults.items()}
    except (ValueError,TypeError):return dict(defaults)

def command_for(event,keys):
    if event.type() not in (QEvent.ShortcutOverride,QEvent.KeyPress):return None
    sequence=QKeySequence(event.keyCombination()).toString(QKeySequence.PortableText)
    return next((k for k,v in keys.items() if v and QKeySequence(v).toString(QKeySequence.PortableText)==sequence),None)

def profile_dialog(parent,settings,view,changed):
    dlg=QDialog(parent);dlg.setWindowTitle(view.title()+' command profile');dlg.resize(520,620);v=QVBoxLayout(dlg);profile=QComboBox();profile.addItems(SCHEMATIC);profile.setCurrentText(settings.value('capture/'+view+'/profile','Studio'));v.addWidget(profile);table=QTableWidget();table.setColumnCount(2);table.setHorizontalHeaderLabels(['Command','Shortcut']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);v.addWidget(table);error=QLabel();error.setWordWrap(True);v.addWidget(error);v.addWidget(QLabel('Canvas only. Middle drag pans; wheel zooms. Esc cancels.\nSchematic: Alt + right click cuts a wire.'))
    mouse_cut=QCheckBox('Alt + right click cuts a wire');mouse_stretch=QCheckBox('Ctrl + left drag stretches selected devices')
    if view=='schematic':v.addWidget(mouse_cut);v.addWidget(mouse_stretch)
    def populate():
        mouse_cut.setChecked(settings.value('capture/mouse/'+profile.currentText()+'/cut',True,type=bool));mouse_stretch.setChecked(settings.value('capture/mouse/'+profile.currentText()+'/stretch',True,type=bool))
        values=bindings(settings,view,profile.currentText());table.setRowCount(len(values))
        for row,(key,value) in enumerate(values.items()):
            a=QTableWidgetItem(key);a.setFlags(a.flags()&~__import__('PySide6.QtCore',fromlist=['Qt']).Qt.ItemIsEditable);table.setItem(row,0,a);table.setItem(row,1,QTableWidgetItem(value))
    def save():
        values={table.item(i,0).text():QKeySequence(table.item(i,1).text()).toString(QKeySequence.PortableText) for i in range(table.rowCount())};used=[v for v in values.values() if v]
        if len(used)!=len(set(used)):error.setText('Each shortcut may belong to only one command.');return
        if any(table.item(i,1).text().strip() and not values[table.item(i,0).text()] for i in range(table.rowCount())):error.setText('Invalid shortcut.');return
        if view=='schematic':
            settings.setValue('capture/mouse/'+profile.currentText()+'/cut',mouse_cut.isChecked());settings.setValue('capture/mouse/'+profile.currentText()+'/stretch',mouse_stretch.isChecked())
        settings.setValue('capture/'+view+'/profile',profile.currentText());settings.setValue('capture/'+view+'/'+profile.currentText(),json.dumps(values));changed(profile.currentText());dlg.accept()
    profile.currentIndexChanged.connect(populate);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(save);buttons.rejected.connect(dlg.reject);v.addWidget(buttons);populate();dlg.show();return dlg
