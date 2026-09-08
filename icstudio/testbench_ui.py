"""Native forms for reusable testbenches; fixtures remain editable schematics."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,QCheckBox,QLabel,QTabWidget,QWidget,QTableWidget,QTableWidgetItem,QPushButton,QDialogButtonBox,QHeaderView
from .model import clone,validate
from .testbenches import create


def editor(studio,original=None):
    p=studio.project;choices=[c for c in p['cells'] if len([d for d in c['devices'] if d['kind']=='X'])==1]
    if not choices:raise ValueError('Create a bench schematic containing one circuit instance, supplies and loads first.')
    selected=next((c for c in choices if c['id']==(original or {}).get('bench_cell',studio.cid)),choices[0]);seed=clone(original) if original else create(p,selected['id'],'bench'+str(len(p.get('testbenches',[]))+1))
    dlg=QDialog(studio);dlg.setWindowTitle('Edit saved testbench' if original else 'Save testbench');dlg.resize(1020,760);dlg.setWindowModality(Qt.WindowModal);v=QVBoxLayout(dlg);tabs=QTabWidget();v.addWidget(tabs);general=QWidget();g=QVBoxLayout(general);form=QFormLayout();g.addLayout(form);dlg.fields={}
    def field(key,label,value):
        w=QLineEdit(str(value));w.setAccessibleName(label);dlg.fields[key]=w;form.addRow(label,w);return w
    field('name','Name',seed['name']);bench=QComboBox();dlg.bench=bench
    for c in choices:bench.addItem(c['name'],c['id'])
    bench.setCurrentIndex(next(i for i,c in enumerate(choices) if c['id']==selected['id']));form.addRow('Fixture schematic',bench)
    note=QLabel('Edit supplies, stimulus and R/C/L loads in this fixture schematic. Its single circuit instance defines the layout being verified.');note.setWordWrap(True);g.addWidget(note)
    a=seed['analysis'];kind=QComboBox();kind.addItems(['tran','op','ac','dc']);kind.setCurrentText(a['type']);dlg.analysis_type=kind;form.addRow('Analysis',kind)
    for key,label,default in [('corner','Model corner','nominal'),('temperature','Temperature (°C)',27),('step','Transient step','2p'),('stop','Transient stop','8n'),('start','AC start (Hz)','10'),('end','AC end (Hz)','10G'),('points','AC points / decade',100),('source','DC source name','VDD'),('dc_start','DC start','0'),('dc_stop','DC stop','1.8'),('dc_step','DC step','.01')]:field(key,label,a.get(key,default))
    dlg.uic=QCheckBox('Start transient from the initial conditions below (UIC)');dlg.uic.setChecked(a.get('uic',False));form.addRow(dlg.uic)
    def mode():
        typ=kind.currentText()
        for key in ('step','stop','start','end','points','source','dc_start','dc_stop','dc_step'):
            visible=key in {'tran':['step','stop'],'op':[],'ac':['start','end','points'],'dc':['source','dc_start','dc_stop','dc_step']}[typ];dlg.fields[key].setVisible(visible);form.labelForField(dlg.fields[key]).setVisible(visible)
        dlg.uic.setVisible(typ=='tran')
    kind.currentTextChanged.connect(mode);mode();tabs.addTab(general,'Analysis and fixture')
    page=QWidget();nv=QVBoxLayout(page);nv.addWidget(QLabel('Check the nets to save as waveforms. Blank initial voltage leaves the node unspecified.'));nets=QTableWidget(0,2);nets.setHorizontalHeaderLabels(['Observe net','Initial voltage (V)']);nets.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);nv.addWidget(nets);dlg.nets=nets;tabs.addTab(page,'Probes and startup')
    def fill_nets():
        c=next(c for c in choices if c['id']==bench.currentData());names=sorted({n for d in c['devices'] for n in d['nets'].values()}-{'0'});nets.setRowCount(len(names))
        for row,n in enumerate(names):
            item=QTableWidgetItem(n);item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if n in seed['probes'] else Qt.Unchecked);nets.setItem(row,0,item);nets.setItem(row,1,QTableWidgetItem(str(seed.get('initial_conditions',{}).get(n,''))))
    bench.currentIndexChanged.connect(fill_nets);fill_nets()
    page=QWidget();mv=QVBoxLayout(page);note=QLabel('Frequency checks settled rising-edge periods. Delay measures an inverting response. Range checks every sample in the window. Voltage reads the last sample or the At coordinate. Reference net gives a voltage difference. Current reads a fixture voltage source, positive from + to −; AC uses magnitude. Optional limits fail the measurement when exceeded.');note.setWordWrap(True);mv.addWidget(note)
    keys=['name','kind','node','reference','source','input','threshold','start','stop','at','min','max'];table=QTableWidget(0,len(keys));table.setHorizontalHeaderLabels(['Name','Measure','Output net','Reference net','Voltage source','Input net','Threshold','Start','Stop','At','Minimum','Maximum']);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);mv.addWidget(table);dlg.measurements=table;records=[]
    def add(m=None):
        m=clone(m) if m else {'name':'measure'+str(table.rowCount()+1),'kind':'frequency' if kind.currentText()=='tran' else 'voltage','node':seed['probes'][0],'threshold':'.9'};records.append(m);row=table.rowCount();table.insertRow(row)
        for col,key in enumerate(keys):
            if key=='kind':w=QComboBox();w.addItems(['frequency','delay','range','voltage','current']);w.setCurrentText(m[key]);table.setCellWidget(row,col,w)
            else:table.setItem(row,col,QTableWidgetItem(str(m.get(key,''))))
    for m in seed.get('measurements',[]):add(m)
    row=QHBoxLayout();b=QPushButton('Add measurement');b.clicked.connect(lambda:add());row.addWidget(b);b=QPushButton('Remove selected');row.addWidget(b)
    def remove():
        i=table.currentRow()
        if i>=0:table.removeRow(i);records.pop(i)
    b.clicked.connect(remove);row.addStretch();mv.addLayout(row);tabs.addTab(page,'Measurements')
    error=QLabel();error.setWordWrap(True);error.setProperty('role','error');v.addWidget(error);dlg.error=error;buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);dlg.buttons=buttons;v.addWidget(buttons)
    def save():
        try:
            if not studio.flush_inspector():return
            t=clone(seed);t['name']=dlg.fields['name'].text().strip();c=next(c for c in choices if c['id']==bench.currentData());instance=next(d for d in c['devices'] if d['kind']=='X');t.update(bench_cell=c['id'],dut_cell=instance['cell'],dut_instance=instance['id'])
            typ=kind.currentText();active={'corner','temperature'}|set({'tran':['step','stop'],'op':[],'ac':['start','end','points'],'dc':['source','dc_start','dc_stop','dc_step']}[typ]);t['analysis']={k:w.text().strip() for k,w in dlg.fields.items() if k in active};t['analysis'].update(type=typ,uic=dlg.uic.isChecked() if typ=='tran' else False)
            if typ=='ac':t['analysis']['points']=int(t['analysis']['points'])
            t['probes']=[nets.item(i,0).text() for i in range(nets.rowCount()) if nets.item(i,0).checkState()==Qt.Checked];t['initial_conditions']={nets.item(i,0).text():nets.item(i,1).text().strip() for i in range(nets.rowCount()) if nets.item(i,1).text().strip()};t['measurements']=[]
            for row in range(table.rowCount()):
                m=clone(records[row])
                for col,key in enumerate(keys):
                    value=table.cellWidget(row,col).currentText() if key=='kind' else table.item(row,col).text().strip()
                    if value:m[key]=value
                    else:m.pop(key,None)
                t['measurements'].append(m)
            q=clone(studio.project);q['testbenches']=[b for b in q.get('testbenches',[]) if b['id']!=t['id']]+[t];validate(q)
            studio._selected_testbench=t['id'];studio.commit(lambda p:p.update(testbenches=q['testbenches']),'Save testbench');dlg.accept();studio.open_testbenches()
        except Exception as e:error.setText(str(e))
    buttons.accepted.connect(save);buttons.rejected.connect(dlg.reject);studio._testbench_dialog=dlg;dlg.show();return dlg
