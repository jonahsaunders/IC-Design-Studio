"""Readable per-corner operating points from the captured characterization cases."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHeaderView, QLabel, QVBoxLayout

from .analog_widgets import fill, table
from .student_bias import corner_readings


class BiasCornersDialog(QDialog):
    def __init__(self, studio, project, result):
        super().__init__(studio)
        self.setWindowTitle('Cascode bias across process and temperature')
        self.resize(920, 465)
        layout = QVBoxLayout(self)
        note = QLabel('The same resistor and device sizes are used at 1.8 V supply and 1.4 V output clamp. '
                      'Density is measured on the lower output transistor. Headroom is the smaller VDS − VDSsat in the stack.')
        note.setWordWrap(True)
        layout.addWidget(note)
        view = table(['Process', 'Temperature (°C)', 'Iref (µA)', 'Iout (µA)', 'ID/W (µA/µm)',
                      'gm/ID (V⁻¹)', 'Headroom (mV)', 'Operating target'])
        view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        view.setAccessibleName('Current density, efficiency and saturation margin at nine corners')
        points = corner_readings(project, result)
        fill(view, [[point['corner'], point['temperature'], f'{point["reference_A"]*1e6:.2f}',
                     f'{point["output_A"]*1e6:.2f}', f'{point["density_uA_per_um"]:.3f}',
                     f'{point["gm_over_id"]:.2f}', f'{point["headroom_V"]*1000:.0f}',
                     'Meets target' if point['passes'] else 'Outside target'] for point in points])
        layout.addWidget(view)
        footer = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        footer.rejected.connect(self.close)
        layout.addWidget(footer)
