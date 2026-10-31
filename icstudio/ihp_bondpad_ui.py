"""Reviewable physical bondpad attachment to an existing IHP cell port."""
from fractions import Fraction

from .ihp_bondpad import install, layers
from .model import clone
from .native_vectors import ports
from .sky130_devices_ui import check_layers, apply_candidate


def nanometres(value):
    try:
        result = Fraction(str(value))*1000
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('Enter a finite dimension in micrometres.') from exc
    if result.denominator != 1:
        raise ValueError('Dimensions must be exact integer nanometres.')
    return int(result)


def dialog(studio):
    if not studio.idle_edit():
        return
    layers(studio.project['pdk']); cid = studio.cid
    assigned = {r['name'] for r in studio.cell.get('layout_ports', [])}
    available = [name for name in ports(studio.cell['ports']) if name not in assigned]
    if not available:
        raise ValueError('Declare a cell port without a physical anchor before attaching an IHP bondpad.')
    fields = [('port', 'Cell port', available), ('diameter', 'Diameter (µm)', '80'),
              ('quota', 'Height / width', '1'), ('x', 'Center X (µm)', '0'),
              ('y', 'Center Y (µm)', '0'), ('rotation', 'Rotation', ['0', '90', '180', '270'])]
    def submit(values):
        parameters = dict(diameter_nm=nanometres(values['diameter']), hwquota=values['quota'],
                          x_nm=nanometres(values['x']), y_nm=nanometres(values['y']),
                          rotation=int(values['rotation']))
        def build():
            q = clone(studio.project); result = install(q, cid, values['port'], parameters)
            check_layers(studio, q, cid)
            rx, ry = result['specification']['radii_nm']
            return q, (f"Attach one {2*rx/1000:g} × {2*ry/1000:g} µm square IHP bondpad to {values['port']}.\n"
                       'The pad uses top metal 2 with a passivation opening and one named center anchor.\n\n'
                       'This adds physical geometry. The electrical bondpad model remains unavailable. '
                       'Run process checks in the complete chip context before using the layout.')
        return studio.review_dialog('Generate IHP bondpad', build, apply_candidate=apply_candidate(studio, cid))
    return studio.workflow_form('IHP square bondpad', fields, submit,
                                'Attach a pad to an existing cell port. This recipe uses one top-metal layer with no stacked metals, fill or flip-chip option.')
