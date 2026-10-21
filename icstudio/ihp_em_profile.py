"""Explicit public IHP top-metal EM inputs, separate from compact device models."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET

from . import em_technology

ASSETS = Path(__file__).parent / 'assets/physical/ihp_em'
SOURCE_SHA256 = 'af8ea757aad1733ce7d73359761453dd4f76f84c2824218df84d6dd9628e3c32'
UPSTREAM_LOCK_SHA256 = 'a4fb9307f96eb812864be404f4c4ca72b64a592847ac6835ad30e712450bd220'
LAYERS = {'TopMetal1': (126, 'conductor'), 'TopVia2': (133, 'via'), 'TopMetal2': (134, 'conductor')}
# The upstream "200um" file declares 180 um of bulk substrate; the remaining
# thickness is EPI, oxide and passivation. Preserve its actual material values.
OPTIONS = {280: 'SG13G2.xml', 180: 'SG13G2_200um.xml'}


def applicable(tech):
    """Identify the pinned IHP package and exact drawing masks, not a display name."""
    lock = tech.get('package_lock', {})
    if lock.get('id') != 'ihp-sg13g2' or lock.get('files', {}).get('UPSTREAM-LOCK.json') != UPSTREAM_LOCK_SHA256:
        return False
    rows = {row['name']: row for row in tech['layers']}
    return all((rows.get(name + '.drawing', {}).get('gds'),
                rows.get(name + '.drawing', {}).get('datatype')) == (number, 0)
               for name, (number, _) in LAYERS.items())


def profile(tech, substrate_um=280, *, assets=ASSETS):
    if not applicable(tech):
        raise ValueError('The public IHP profile requires the pinned SG13G2 package and its original top-metal drawing masks.')
    if type(substrate_um) is not int or substrate_um not in OPTIONS:
        raise ValueError('Choose the public 280 or 180 µm bulk-substrate profile.')
    assets = Path(assets)
    raw = (assets / 'SOURCE.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Changed public IHP EM source lock.')
    lock = json.loads(raw)
    for name, entry in lock['files'].items():
        path = (assets / name).resolve()
        if not path.is_relative_to(assets.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Changed public IHP EM source: ' + name)
    filename = OPTIONS[substrate_um]
    document = ET.fromstring((assets / filename).read_bytes())
    if document.tag != 'Stackup' or document.get('schemaVersion') != '2.0' or document.find('ELayers').get('LengthUnit') != 'um':
        raise ValueError('Unexpected public IHP stackup schema or units.')
    materials = {row.get('Name'): row for row in document.findall('Materials/Material')}
    drawn = {row.get('Name'): row for row in document.findall('ELayers/Layers/Layer')}
    layers = []

    def material_layer(row, kind, bottom, thickness):
        material = materials[row.get('Material')]
        return dict(name=row.get('Name'), kind=kind, z_um=float(bottom), thickness_um=float(thickness),
                    conductivity_s_m=float(material.get('Conductivity')),
                    epsilon_r=float(material.get('Permittivity')),
                    loss_tangent=float(material.get('DielectricLossTangent')))

    for name, (number, kind) in LAYERS.items():
        row = drawn[name]
        if int(row.get('Layer')) != number or row.get('Type') != kind:
            raise ValueError('Changed IHP top-metal mapping.')
        bottom = Decimal(row.get('Zmin'))
        layers.append(material_layer(row, kind, bottom, Decimal(row.get('Zmax')) - bottom))
    # Upstream accumulates dielectrics bottom-up and offsets every conductor by
    # Substrate/Offset. Translate the entire stack by -Offset, leaving the
    # published conductor coordinates unchanged. No dielectric is removed.
    z = -Decimal(document.find('ELayers/Layers/Substrate').get('Offset'))
    for row in reversed(document.findall('ELayers/Dielectrics/Dielectric')):
        kind = 'substrate' if materials[row.get('Material')].get('Type') == 'Semiconductor' else 'dielectric'
        thickness = Decimal(row.get('Thickness'))
        layers.append(material_layer(row, kind, z, thickness))
        z += thickness
    if next(row for row in layers if row['name'] == 'Substrate')['thickness_um'] != substrate_um:
        raise ValueError('Public substrate option does not match its source.')
    source = (f'Public IHP SG13G2 top-metal EM inputs; {substrate_um} µm substrate. '
              f"{lock['repository']}/blob/{lock['commit']}/workflow/{filename}; "
              f"SHA256 {lock['files'][filename]['sha256']}. "
              'TopMetal1/TopVia2/TopMetal2 drawing only; all public dielectric/substrate slabs retained. '
              'Nominal material data, no temperature/frequency calibration or compact-device qualification. '
              'Other drawn layers require an explicit physical model; none are excluded automatically.')
    stack = dict(schema=2, source=source, layers=layers,
                 layout_map={name + '.drawing': name for name in LAYERS}, excluded_layers={})
    return em_technology.bind_stackup(tech, stack)
