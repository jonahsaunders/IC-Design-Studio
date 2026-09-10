"""Direct plot tools and an exact-coordinate measurement editor."""
import csv, io, json, math
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QCheckBox,QPushButton,QDialog,QTableWidget,QTableWidgetItem,QHeaderView,
    QAbstractItemView,QLineEdit,QDialogButtonBox,QFileDialog)
from .human_workspace import FlowLayout
from .model import atomic_write,digest,scalar,uid
from .measurements import evaluate


def coordinate_units(result):
    from .plot import analysis_kind
    if not result:return 'X','Y'
    kind=analysis_kind(result)
    x={'tran':'s','ac':'Hz','fft':'Hz','noise':'Hz','dc':'source V/A','op':'index'}.get(kind,result.get('x_label','X'))
    y=result.get('plot_unit','V/√Hz' if kind=='noise' else 'V')
    return x,y


class WaveformTools(QWidget):
    def __init__(self,plot,studio):
        super().__init__();self.plot=plot;self.studio=studio;self.path=None;self.dialog=None
        row=FlowLayout(self);self.mode=QComboBox();self.mode.addItems(['Inspect','X cursor','Y limit','X/Y check']);self.mode.setAccessibleName('Waveform marker tool');row.addWidget(self.mode)
        self.trace=QComboBox();self.trace.setMinimumWidth(100);self.trace.setAccessibleName('Measurement trace');row.addWidget(QLabel('Trace'));row.addWidget(self.trace)
        self.rule=QComboBox();self.rule.addItem('At or below','<=');self.rule.addItem('At or above','>=');self.rule.setAccessibleName('Pass condition');row.addWidget(self.rule)
        self.nearest=QCheckBox('Nearest sample');self.nearest.setToolTip('Off: interpolate at the exact X coordinate. On: read the closest stored sample.');row.addWidget(self.nearest)
        for title,fn in [('Markers…',self.open_manager),('Fit plot',plot.fit_plot)]:
            button=QPushButton(title);button.clicked.connect(fn);row.addWidget(button)
        self.mode.currentIndexChanged.connect(self.change_mode);self.trace.currentTextChanged.connect(lambda value:setattr(plot,'marker_trace',value));self.rule.currentIndexChanged.connect(lambda *_:setattr(plot,'marker_rule',self.rule.currentData()));self.nearest.toggled.connect(lambda value:setattr(plot,'nearest_sample',value))
        plot.markers_changed.connect(self.changed);plot.result_changed.connect(self.load_result)
        self.setToolTip('Click to place; drag a marker to adjust. Wheel zooms X, Shift+wheel zooms Y, Ctrl+wheel zooms both. Middle drag pans; F fits. Delete removes a selected marker. Esc returns to Inspect.')

    def change_mode(self,index):self.plot.marker_mode=['Inspect','X','Y','XY'][index];self.plot.setCursor(Qt.CrossCursor)

    def load_result(self):
        self.path=None;result=self.plot.result;current=self.trace.currentText();self.trace.clear();self.trace.addItems(list(result['traces']) if result else [])
        if self.trace.findText(current)>=0:self.trace.setCurrentText(current)
        if result:
            self.path=self.studio.data_dir/'measurements'/(digest(result)+'.json')
            if self.path.exists():
                try:
                    markers=json.loads(self.path.read_text())
                    self.plot.markers=[m for m in markers[:200] if m.get('kind') in ('X','Y','XY') and m.get('rule') in ('<=','>=') and all(math.isfinite(float(m[k])) for k in ('x','y')) and isinstance(m.get('id'),str) and isinstance(m.get('trace'),str)]
                except (ValueError,KeyError,TypeError,OSError):self.plot.markers=[]
        self.refresh_table()

    def changed(self):
        if self.path:
            try:self.path.parent.mkdir(parents=True,exist_ok=True);atomic_write(self.path,json.dumps(self.plot.markers,allow_nan=False))
            except OSError as exc:self.studio.statusBar().showMessage('Markers could not be saved: '+str(exc),10000)
        if self.plot.marker_mode=='Inspect' and self.mode.currentIndex()!=0:self.mode.setCurrentIndex(0)
        self.refresh_table();self.plot.marker_readout()

    def open_manager(self):
        if self.dialog and self.dialog.isVisible():self.dialog.raise_();self.dialog.activateWindow();return
        dlg=QDialog(self.studio);dlg.setWindowTitle('Waveform markers and limits');dlg.resize(1040,630);v=QVBoxLayout(dlg)
        xu,yu=coordinate_units(self.plot.result)
        hint=QLabel(f'X reads the trace at a coordinate. Y checks the entire trace against a horizontal limit. X/Y checks the trace at X against the Y limit. Enter X in {xu} and Y in {yu}; engineering suffixes are accepted. PASS includes equality.');hint.setWordWrap(True);v.addWidget(hint)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['Marker','Type','Trace',f'X ({xu})',f'Y limit ({yu})','Condition',f'Measured Y ({yu})','Result']);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection);self.table.verticalHeader().hide();self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.table.horizontalHeader().setStretchLastSection(True);v.addWidget(self.table,1)
        fields=QHBoxLayout();v.addLayout(fields);self.kind=QComboBox();self.kind.addItems(['X','Y','XY']);self.edit_trace=QComboBox();self.x=QLineEdit('0');self.y=QLineEdit('0');self.condition=QComboBox();self.condition.addItem('≤ limit','<=');self.condition.addItem('≥ limit','>=');self.sample=QCheckBox('Nearest sample')
        for title,widget in [('Type',self.kind),('Trace',self.edit_trace),(f'X ({xu})',self.x),(f'Y limit ({yu})',self.y),('Pass when',self.condition)]:
            column=QVBoxLayout();column.addWidget(QLabel(title));column.addWidget(widget);fields.addLayout(column)
        fields.addWidget(self.sample);self.error=QLabel();self.error.setWordWrap(True);self.error.setProperty('role','error');v.addWidget(self.error)
        self.detail=QLabel('Coordinates accept engineering suffixes, for example 25u or 1.8. Y-limit checks use every saved sample, including samples outside the zoomed view.');self.detail.setWordWrap(True);v.addWidget(self.detail)
        bar=QHBoxLayout();v.addLayout(bar)
        for title,fn in [('Add marker',lambda:self.apply_marker(True)),('Apply changes',lambda:self.apply_marker(False)),('Remove',self.remove_marker),('Clear markers',self.clear_markers),('Export CSV',self.export_csv)]:
            button=QPushButton(title);button.clicked.connect(fn);bar.addWidget(button)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dlg.close);bar.addWidget(buttons);self.table.itemSelectionChanged.connect(self.load_marker);self.kind.currentTextChanged.connect(self.field_visibility);self.dialog=dlg;self.refresh_table();self.field_visibility();dlg.show()

    def field_visibility(self):
        self.x.setEnabled(self.kind.currentText()!='Y');self.y.setEnabled(self.kind.currentText()!='X');self.condition.setEnabled(self.kind.currentText()!='X');self.sample.setEnabled(self.kind.currentText()!='Y')

    def refresh_table(self):
        if not self.dialog:return
        selected=self.plot.selected_marker;self.table.blockSignals(True);self.table.setRowCount(len(self.plot.markers));self.edit_trace.clear();self.edit_trace.addItems(list(self.plot.result['traces']) if self.plot.result else [])
        for i,m in enumerate(self.plot.markers):
            check=evaluate(self.plot.result,m) if self.plot.result else {'value':None,'verdict':'No result'}
            values=[f'M{i+1}',m['kind'],m['trace'],f"{m['x']:.9g}" if m['kind']!='Y' else 'All X',f"{m['y']:.9g}" if m['kind']!='X' else '—',m['rule'] if m['kind']!='X' else 'Read',f"{check['value']:.9g}" if check['value'] is not None else '—',check['verdict']]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value);item.setData(Qt.UserRole,m['id']);self.table.setItem(i,j,item)
                if j==7 and value in ('PASS','FAIL'):item.setForeground(QColor('#38a283' if value=='PASS' else '#d35d79'))
            if m['id']==selected:self.table.selectRow(i)
        self.table.blockSignals(False);self.load_marker()

    def selected(self):return next((m for m in self.plot.markers if m['id']==self.plot.selected_marker),None)

    def load_marker(self):
        items=self.table.selectedItems()
        if items:self.plot.selected_marker=items[0].data(Qt.UserRole)
        marker=self.selected()
        if not marker:return
        self.kind.setCurrentText(marker['kind']);self.edit_trace.setCurrentText(marker['trace']);self.x.setText(f"{marker['x']:.12g}");self.y.setText(f"{marker['y']:.12g}");self.condition.setCurrentIndex(self.condition.findData(marker['rule']));self.sample.setChecked(marker.get('nearest',False));check=evaluate(self.plot.result,marker) if self.plot.result else None
        xu,yu=coordinate_units(self.plot.result)
        if check:self.detail.setText(('Whole trace: maximum' if marker['rule']=='<=' else 'Whole trace: minimum')+f" checked; {check['crossings']} threshold crossings/touches." if marker['kind']=='Y' else ('Nearest saved sample' if marker.get('nearest') else 'Interpolated at the exact X coordinate')+f' · X in {xu}; Y in {yu}.')
        self.plot.update()

    def apply_marker(self,new):
        try:
            if not self.plot.result or not self.edit_trace.currentText():raise ValueError('Run an analysis and choose a trace first.')
            marker=None if new else self.selected()
            if not new and marker is None:raise ValueError('Select a marker to edit.')
            values={'kind':self.kind.currentText(),'trace':self.edit_trace.currentText(),'x':scalar(self.x.text()),'y':scalar(self.y.text()),'rule':self.condition.currentData(),'nearest':self.sample.isChecked()}
            if new:
                if len(self.plot.markers)>=200:raise ValueError('Remove an existing marker before adding more than 200.')
                marker={'id':uid(),**values};self.plot.markers.append(marker)
            else:marker.update(values)
            self.plot.selected_marker=marker['id'];self.plot.markers_changed.emit();self.plot.update();self.error.clear()
        except (ValueError,TypeError) as exc:self.error.setText(str(exc))

    def remove_marker(self):
        self.plot.markers=[m for m in self.plot.markers if m['id']!=self.plot.selected_marker];self.plot.selected_marker=None;self.plot.markers_changed.emit();self.plot.update()

    def clear_markers(self):self.plot.markers=[];self.plot.selected_marker=None;self.plot.markers_changed.emit();self.plot.update()

    def csv_text(self):
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['marker','kind','trace','x','y_limit','condition','sampling','measured_y','verdict','threshold_crossings','x_unit','y_unit'])
        for i,m in enumerate(self.plot.markers):
            check=evaluate(self.plot.result,m);writer.writerow([f'M{i+1}',m['kind'],m['trace'],m['x'] if m['kind']!='Y' else '',m['y'] if m['kind']!='X' else '',m['rule'] if m['kind']!='X' else '', 'nearest' if m.get('nearest') else 'interpolated',check['value'],check['verdict'],check['crossings'],*coordinate_units(self.plot.result)])
        return stream.getvalue()

    def export_csv(self):
        path,_=QFileDialog.getSaveFileName(self.dialog,'Export marker measurements','waveform-markers.csv','CSV (*.csv)')
        if path:
            try:atomic_write(path,self.csv_text())
            except OSError as exc:self.error.setText(str(exc))
