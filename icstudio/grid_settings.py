"""Layout snap controls separate from grid visibility and process rules."""
from decimal import Decimal,InvalidOperation
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTabWidget,QWidget,QFormLayout,
    QComboBox,QSlider,QCheckBox,QLineEdit,QSpinBox,QDialogButtonBox)


def spacing_nm(text,grid):
    try:value=Decimal(text.strip())*1000
    except InvalidOperation:raise ValueError('Enter a spacing in micrometres, such as 0.05.') from None
    if not value.is_finite() or value<=0 or value>1_000_000_000 or value!=value.to_integral_value():
        raise ValueError('Use a positive spacing from 0.001 to 1000000 µm, in whole nanometres.')
    result=int(value)
    if result%grid:raise ValueError(f'Spacing must be a multiple of the process grid ({grid/1000:g} µm).')
    return result


class GridSettingsMixin:
    def set_grid_snap(self,enabled):
        self.layout.grid_snap_enabled=bool(enabled)
        self.persist_grid(self.layout);self.layout.update();self.update_canvas_footer()

    def toggle_grid_snap(self):
        self.set_grid_snap(not getattr(self.layout,'grid_snap_enabled',True))

    def grid_settings_dialog(self):
        dlg=QDialog(self);dlg.setWindowTitle('Grid Settings');dlg.resize(540,540)
        column=QVBoxLayout(dlg);note=QLabel('Grid visibility and snapping are independent. Layout defaults to snapping to the visible grid.');note.setWordWrap(True);column.addWidget(note)
        tabs=QTabWidget();column.addWidget(tabs);dlg.fields={};dlg.snap_fields={}
        for c in (self.schematic,self.layout):
            page=QWidget();form=QFormLayout(page)
            style=QComboBox()
            for name,key in [('Lines','lines'),('Dots','dots'),('Hidden','off')]:style.addItem(name,key)
            style.setCurrentIndex(style.findData(c.grid_style));style.setAccessibleName(c.mode+' grid style')
            contrast=QSlider(Qt.Horizontal);contrast.setRange(30,100);contrast.setValue(c.grid_contrast)
            contrast.setAccessibleName(c.mode+' grid contrast')
            density=QSlider(Qt.Horizontal);density.setRange(8,32);density.setValue(c.grid_density)
            density.setAccessibleName(c.mode+' minimum grid spacing')
            origin=QCheckBox('Emphasize the document origin');origin.setChecked(c.grid_origin)
            major=QSpinBox();major.setRange(2,100);major.setValue(getattr(c,'grid_major_every',5));major.setAccessibleName(c.mode+' major grid interval')
            if c.mode=='layout':
                enabled=QCheckBox('Snap to grid');enabled.setChecked(getattr(c,'grid_snap_enabled',True));enabled.setAccessibleName('Layout snap to grid')
                mode=QComboBox();mode.addItem('Visible grid — follows zoom','visible');mode.addItem('Fixed spacing','fixed')
                mode.setCurrentIndex(mode.findData(getattr(c,'grid_snap_mode','visible')));mode.setAccessibleName('Layout snap grid mode')
                spacing=QLineEdit(f'{c.fixed_grid_interval()/1000:g}');spacing.setAccessibleName('Layout fixed grid spacing in micrometres')
                error=QLabel();error.setWordWrap(True);error.setStyleSheet('color: #c75c43')
                detail=QLabel(f'Process grid: {c.manufacturing_grid()/1000:g} µm. Fixed spacing must be a multiple.\n'
                    'Fixed snap spacing stays constant while the visible grid thins at distant zoom. Snap off places at 1 nm resolution; process checks still apply.\n'
                    'Settings changed during a drawing take effect on the next shape.');detail.setWordWrap(True)
                form.addRow(enabled);form.addRow('Snap spacing',mode);form.addRow('Fixed spacing (µm)',spacing);form.addRow(error);form.addRow(detail)
                def apply_snap(*_,c=c,enabled=enabled,mode=mode,spacing=spacing,error=error):
                    try:value=spacing_nm(spacing.text(),c.manufacturing_grid()) if mode.currentData()=='fixed' else c.fixed_grid_interval()
                    except ValueError as exc:error.setText(str(exc));return
                    error.clear();c.grid_snap_enabled=enabled.isChecked();c.grid_snap_mode=mode.currentData();c.grid_snap_step=value
                    spacing.setEnabled(c.grid_snap_mode=='fixed');self.persist_grid(c);c.update();self.update_canvas_footer()
                enabled.toggled.connect(self.set_grid_snap);mode.currentIndexChanged.connect(apply_snap);spacing.editingFinished.connect(apply_snap)
                spacing.setEnabled(mode.currentData()=='fixed');dlg.snap_fields[c.mode]=(enabled,mode,spacing,error)
            else:
                fixed=QLabel('Schematic placement uses the 10-unit pin and wire grid. These display controls do not change electrical connections.');fixed.setWordWrap(True);form.addRow(fixed)
            form.addRow('Show grid',style);form.addRow('Contrast',contrast);form.addRow('Minimum screen spacing',density)
            form.addRow('Major line every',major);form.addRow(origin)
            def change(*_,c=c,style=style,contrast=contrast,density=density,origin=origin,major=major):
                c.grid_style=style.currentData();c.grid_contrast=contrast.value();c.grid_density=density.value();c.grid_origin=origin.isChecked();c.grid_major_every=major.value()
                self.persist_grid(c);c.update();self.update_canvas_footer()
            style.currentIndexChanged.connect(change);contrast.valueChanged.connect(change);density.valueChanged.connect(change);origin.toggled.connect(change);major.valueChanged.connect(change)
            tabs.addTab(page,c.mode.title());dlg.fields[c.mode]=(style,contrast,density,origin)
        tabs.setCurrentIndex(1 if self.current_mode=='layout' else 0)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dlg.reject);column.addWidget(buttons)
        self._grid_dialog=dlg;dlg.show();return dlg
