"""Saved signal sets, exact edge/value search and two-cursor measurements."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout,QLineEdit,QComboBox,QPushButton,QInputDialog,QLabel


class WaveTools:
    def __init__(self,window):
        self.w=window
        row=QHBoxLayout();window.wave_layout.insertLayout(1,row)
        self.search=QLineEdit();self.search.setPlaceholderText('Filter signals…');self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter);row.addWidget(self.search)
        self.groups=QComboBox();self.groups.setAccessibleName('Saved waveform signal sets');row.addWidget(self.groups)
        self.groups.activated.connect(self.select_group)
        button=QPushButton('Save set');button.clicked.connect(lambda:window.attempt(self.save));row.addWidget(button)
        find=QHBoxLayout();window.wave_layout.insertLayout(2,find)
        self.match=QComboBox();self.match.addItems(['Any edge','Rising','Falling','Exact binary value']);find.addWidget(self.match)
        self.value=QLineEdit();self.value.setPlaceholderText('e.g. 10xz');self.value.setMaximumWidth(100);find.addWidget(self.value)
        for name,reverse in (('Previous',True),('Next',False)):
            b=QPushButton(name);b.clicked.connect(lambda checked=False,r=reverse:window.attempt(lambda:self.seek(r)));find.addWidget(b)
        note=QLabel('Click: A · Shift-click: B');note.setProperty('role','muted');find.addWidget(note)
        window.wave_layout.setStretch(window.wave_layout.count()-1,1)
        self.restore()

    def key(self): return 'digital/waveforms/'+self.w.project_id+'/'+self.w.cell_id

    def saved(self):
        try:return json.loads(self.w.studio.settings.value(self.key(),'{}'))
        except (ValueError,TypeError):return {}

    def restore(self):
        self.groups.clear();self.groups.addItem('Signal sets…','')
        for name in self.saved():self.groups.addItem(name,name)
        self.filter(self.search.text())

    def filter(self,text):
        for i in range(self.w.signals.count()):
            item=self.w.signals.item(i);item.setHidden(text.casefold() not in item.text().casefold())

    def save(self):
        if not self.w.wave.data:raise ValueError('Open a waveform before saving a signal set.')
        name,ok=QInputDialog.getText(self.w,'Save waveform signal set','Name')
        if not ok or not name.strip():return
        groups=self.saved();groups[name.strip()]={'signals':[s['name'] for s in self.w.wave.signals], 'radix':self.w.radix.currentText()}
        self.w.studio.settings.setValue(self.key(),json.dumps(groups));self.restore()

    def select_group(self,index):
        group=self.saved().get(self.groups.itemData(index))
        if not group:return
        self.w.signals.blockSignals(True)
        for i in range(self.w.signals.count()):
            item=self.w.signals.item(i);item.setCheckState(Qt.Checked if item.text() in group['signals'] else Qt.Unchecked)
        self.w.signals.blockSignals(False);self.w.radix.setCurrentText(group['radix']);self.w.signal_selection()

    def seek(self,reverse):
        from .digital_trace_store import next_event
        wave=self.w.wave;item=self.w.signals.currentItem()
        if not wave.data or not item:raise ValueError('Select a signal in the waveform list.')
        signal=wave.data['signals'][item.data(Qt.UserRole)];match=('', 'rising','falling',self.value.text().strip().lower())[self.match.currentIndex()]
        if self.match.currentIndex()==3 and (len(match)!=signal['width'] or set(match)-set('01xz')):
            raise ValueError('Enter exactly '+str(signal['width'])+' binary digits (0, 1, x or z).')
        if self.match.currentIndex() in (1,2) and signal['width']!=1:raise ValueError('Choose a one-bit signal for rising/falling edge search.')
        tick=next_event(wave.data['changes'][signal['code']],wave.cursor,match,reverse)
        if tick is None:self.w.message.setText('No matching transition in that direction.');return
        wave.cursor=tick;wave.update()
        self.w.message.setText(signal['name']+' · '+str(tick)+' × '+wave.data['timescale'])
