"""Modeless schematic annotation controls and keyboard-readable values."""

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QLabel,
                               QPlainTextEdit, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from .annotations import DEFAULT_FIELDS, FIELDS


class DeviceAnnotationsPanel(QDialog):
    def __init__(self, studio):
        super().__init__(studio,Qt.Tool)
        self.studio=studio
        self.setWindowTitle('Device Annotations')
        self.setObjectName('deviceAnnotationsPanel')
        self.resize(445,490)
        layout=QVBoxLayout(self)
        tabs=QTabWidget()
        tabs.setAccessibleName('Device annotations')
        layout.addWidget(tabs,1)
        fields_page=QScrollArea()
        fields_page.setWidgetResizable(True)
        fields_widget=QWidget()
        fields_page.setWidget(fields_widget)
        fields_layout=QVBoxLayout(fields_widget)
        self.show_annotations=QCheckBox('Show annotations on the schematic')
        fields_layout.addWidget(self.show_annotations)
        self.selected=QCheckBox('Selected devices only')
        fields_layout.addWidget(self.selected)
        self.fields={}
        for title, keys in (
            ('Design Fields',('dimensions','model','value')),
            ('Simulation Fields',tuple(key for key in FIELDS if key not in ('dimensions','model','value'))),
        ):
            group=QGroupBox(title)
            controls=QVBoxLayout(group)
            for key in keys:
                check=QCheckBox('Output resistance' if key=='ro' else FIELDS[key])
                if key=='ro':
                    check.setAccessibleDescription('Incremental output resistance from the saved output conductance.')
                controls.addWidget(check)
                self.fields[key]=check
                check.toggled.connect(self.fields_changed)
            fields_layout.addWidget(group)
        fields_layout.addStretch()
        tabs.addTab(fields_page,'Fields')

        readings=QWidget()
        readings_layout=QVBoxLayout(readings)
        self.status=QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        readings_layout.addWidget(self.status)
        self.readings=QPlainTextEdit()
        self.readings.setReadOnly(True)
        self.readings.setAccessibleName('Schematic device readings')
        readings_layout.addWidget(self.readings,1)
        tabs.addTab(readings,'Readings')

        buttons=QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.show_annotations.toggled.connect(studio.annotate_check.setChecked)
        self.selected.toggled.connect(self.scope_changed)
        self.sync_choices()
        self.apply_presentation_style()

    def apply_presentation_style(self):
        from .student_hub_ui import student_style
        hub=getattr(self.studio,'_student_hub',None)
        action=getattr(self.studio,'study_share_action',None)
        scale=hub.text_scale if hub else 100
        if action and action.isChecked():
            scale=max(150,scale)
        self.setStyleSheet(student_style(self.studio.dark,scale)+'\nQCheckBox { min-height: 28px; }')

    def sync_choices(self):
        settings=self.studio.settings
        with QSignalBlocker(self.show_annotations),QSignalBlocker(self.selected):
            self.show_annotations.setChecked(self.studio.annotate_check.isChecked())
            self.selected.setChecked(settings.value('view/deviceAnnotationsSelected',False,bool))
        selected=set(settings.value('view/deviceFields',sorted(DEFAULT_FIELDS),list))
        for key,check in self.fields.items():
            with QSignalBlocker(check):
                check.setChecked(key in selected)

    def fields_changed(self,*_):
        settings=self.studio.settings
        settings.setValue('view/deviceFields',[key for key,check in self.fields.items() if check.isChecked()])
        self.studio.update_annotations()

    def scope_changed(self,selected):
        self.studio.settings.setValue('view/deviceAnnotationsSelected',selected)
        self.studio.update_annotations()

    def update_readings(self, rows, status, devices):
        self.sync_choices()
        body='\n\n'.join(f'{device["name"]}\n{rows[device["id"]]}'
                          for device in devices if device['id'] in rows)
        if not self.show_annotations.isChecked():
            status='Schematic annotations are off.'
        elif not any(field.isChecked() for field in self.fields.values()):
            status='Choose at least one annotation field.'
        elif not body and self.selected.isChecked() and not self.studio.selection:
            status='Select a schematic device to see its readings.'
        if not body:
            body='No readings to show.'
        self.status.setText(status.rstrip('. ')+'.' if status else '')
        if self.readings.toPlainText()!=body:
            self.readings.setPlainText(body)
