"""EM evidence exchange for the selected saved inductor."""
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QFileDialog,QTableWidget,QTableWidgetItem,QHeaderView,QWidget)

from . import inductor_em


class CharacterizationPlot(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.setMinimumHeight(190)
        self.setAccessibleName('Imported inductance and Q versus frequency')

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),self.palette().base())
        if not self.rows:
            painter.setPen(self.palette().text().color());painter.drawText(self.rect(),Qt.AlignCenter,'Import characterization to plot L(f) and Q(f).');return
        low,high=math.log10(self.rows[0]['frequency_hz']),math.log10(self.rows[-1]['frequency_hz'])
        for i,(key,label,scale,color) in enumerate((('inductance_h','L (nH)',1e9,'#348dcc'),('q','Q',1,'#bc7b24'))):
            box=QRectF(55+i*self.width()/2,25,self.width()/2-80,self.height()-70)
            values=[r[key]*scale for r in self.rows if r[key] is not None];ymin=min(values+[0]);ymax=max(values+[0]);span=max(ymax-ymin,1e-12)
            painter.setPen(self.palette().mid().color());painter.drawRect(box);painter.setPen(self.palette().text().color())
            painter.drawText(QPointF(box.left(),17),label)
            painter.drawText(QPointF(box.left()-48,box.top()+8),f'{ymax:.3g}');painter.drawText(QPointF(box.left()-48,box.bottom()),f'{ymin:.3g}')
            painter.drawText(QPointF(box.left(),box.bottom()+19),f"{self.rows[0]['frequency_hz']:.3g} Hz")
            painter.drawText(QPointF(box.right()-80,box.bottom()+19),f"{self.rows[-1]['frequency_hz']:.3g} Hz")
            path=QPainterPath();drawing=False
            for row in self.rows:
                if row[key] is None:drawing=False;continue
                point=QPointF(box.left()+(math.log10(row['frequency_hz'])-low)/(high-low)*box.width(),box.bottom()-(row[key]*scale-ymin)/span*box.height())
                if drawing:path.lineTo(point)
                else:path.moveTo(point);drawing=True
            painter.setPen(QPen(QColor(color),1.8));painter.drawPath(path)
        painter.setPen(self.palette().text().color());painter.drawText(QRectF(0,self.height()-22,self.width(),20),Qt.AlignCenter,'Frequency axis: logarithmic · imported samples only')


class CharacterizationDialog(QDialog):
    def __init__(self,owner,cid,did,parent=None):
        super().__init__(parent or owner);self.owner=owner;self.cid=cid;self.did=did;self.project_id=owner.project['id']
        self.setWindowTitle('Inductor EM characterization')
        screen=owner.screen().availableGeometry();self.resize(min(850,screen.width()-40),min(650,screen.height()-60))
        layout=QVBoxLayout(self);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in (('Load physical stackup…',self.load_stackup),('Export EM bundle…',self.export),('Import results…',self.import_results)):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        self.plot=CharacterizationPlot();layout.addWidget(self.plot)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Frequency (Hz)','L (nH)','R (Ω)','Q'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(self.table,1)
        note=QLabel('Use a physical stackup with a named source. Touchstone files require a matching JSON sidecar. See the inductor creator guide for formats and units.');note.setWordWrap(True);layout.addWidget(note)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        close=QPushButton('Close');close.clicked.connect(self.accept);layout.addWidget(close);self.refresh()

    def project(self):
        if self.owner.project['id']!=self.project_id:raise ValueError('The open project changed. Reopen characterization.')
        if not any(c['id']==self.cid and any(d['id']==self.did for d in c['devices']) for c in self.owner.project['cells']):
            raise ValueError('The inductor was removed. Reopen characterization.')
        return self.owner.project

    def refresh(self):
        self.error.clear();self.plot.rows=[];self.table.setRowCount(0);self.summary.clear()
        try:
            p=self.project();manifest=inductor_em.manifest(p,self.cid,self.did)
            status='Physical stackup declared.' if manifest['stackup_complete'] else 'Incomplete EM stackup: '+', '.join(manifest['missing'])
            result,state=inductor_em.result_status(p,self.cid,self.did);self.status.setText(status+'\n'+state)
            if result:
                self.plot.rows=result['rows'];srf=result['srf_hz']
                bracket=result['srf_bracket_hz']
                self.summary.setText((f'SRF bracket: {bracket[0]:.4g}–{bracket[1]:.4g} Hz · linear estimate {srf:.4g} Hz' if srf is not None else 'Self-resonance is not bracketed in the supplied frequency range.')+'\nSource: '+result['evidence']['source'])
                rows=result['rows'];step=max(1,math.ceil(len(rows)/1000));shown=rows[::step]
                if shown[-1] is not rows[-1]:shown.append(rows[-1])
                self.table.setRowCount(len(shown))
                for i,row in enumerate(shown):
                    values=[f"{row['frequency_hz']:.6g}",f"{row['inductance_h']*1e9:.6g}",f"{row['resistance_ohm']:.6g}",f"{row['q']:.6g}" if row['q'] is not None else '—']
                    for j,value in enumerate(values):self.table.setItem(i,j,QTableWidgetItem(value))
                if step>1:self.summary.setText(self.summary.text()+f'\nTable shows every {step}th sample; the plot and saved evidence retain all {len(rows)} samples.')
        except (ValueError,KeyError,StopIteration) as exc:self.status.setText(str(exc))
        self.plot.update()

    def load_stackup(self):
        file,_=QFileDialog.getOpenFileName(self,'Physical EM stackup','','JSON (*.json)')
        if not file:return
        try:
            self.project();stack=inductor_em.validate_stackup(json.loads(inductor_em._read(file)))
            if not self.owner.idle_edit():return
            self.owner.commit(lambda p:p['pdk'].update(em_stackup=stack),'Load physical EM stackup');self.refresh()
        except (ValueError,OSError,KeyError) as exc:self.error.setText(str(exc))

    def export(self):
        file,_=QFileDialog.getSaveFileName(self,'Export reproducible EM bundle','inductor-em.zip','ZIP (*.zip)')
        if not file:return
        try:
            manifest=inductor_em.export_bundle(self.project(),self.cid,self.did,Path(file));self.refresh()
            self.error.setText('Exported '+Path(file).name+('. Physical stackup is incomplete; load it and re-export before characterization.' if not manifest['stackup_complete'] else '.'))
        except (ValueError,OSError,KeyError) as exc:self.error.setText(str(exc))

    def import_results(self):
        file,_=QFileDialog.getOpenFileName(self,'Import EM characterization','','EM results (*.json *.s1p *.s2p)')
        if not file:return
        try:
            self.project();data=inductor_em.load_results(file)
            if not self.owner.idle_edit():return
            self.owner.commit(lambda p:inductor_em.install_results(p,self.cid,self.did,data),'Import inductor EM characterization');self.refresh()
        except (ValueError,OSError,KeyError,TypeError) as exc:self.error.setText(str(exc))
