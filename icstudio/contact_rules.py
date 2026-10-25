"""Explicit mask-dependent contact rules for physical device layers.

A via blocker removes only the named conductor/cut contact under its mask.
For SKY130 MiM, capm separates metal3 from via3 while the via contacts the
capacitor top electrode. Raw exported and extracted geometry is unchanged.
"""
from .layout import kdb, polygon


def conductive_shapes(shapes, technology):
    """Split conductors at explicit resistor masks for the contact graph only.

    Derive the split from actual polygons, never a generated-device tag. A
    deleted, displaced or narrowed marker therefore exposes the real short.
    Native export/extraction continues to receive the original shapes.
    """
    rules = technology.get('connectivity', {}).get('resistive_masks', [])
    if not rules:
        return shapes
    from .layout import shape_from_polygon
    from .model import clone
    names = {layer['name'] for layer in technology['layers']}
    conductors = set(technology.get('connectivity', {}).get('conductors', []))
    masks = {}
    for rule in rules:
        if (not isinstance(rule, dict) or set(rule) != {'conductor', 'mask'}
                or rule['conductor'] not in conductors or rule['mask'] not in names
                or rule['mask'] == rule['conductor'] or rule['mask'] in conductors):
            raise ValueError('A resistive mask needs distinct mapped conductor and nonconducting marker layers.')
        region = masks.setdefault(rule['conductor'], kdb().Region())
        for shape in shapes:
            if shape['layer'] == rule['mask']:
                region.insert(polygon(shape))
    masks = {key: region.merged() for key, region in masks.items() if not region.is_empty()}
    result = []
    for shape in shapes:
        mask = masks.get(shape['layer'])
        original = kdb().Region(polygon(shape)) if mask is not None else None
        if mask is None or (original & mask).is_empty():
            result.append(shape)
            continue
        remaining = (original-mask).merged()
        def order(poly):
            box = poly.bbox()
            return box.left, box.bottom, box.right, box.top, poly.to_s()
        for index, poly in enumerate(sorted(remaining.each(), key=order)):
            fragment = clone(shape)
            fragment.update(shape_from_polygon(poly, shape['layer'], shape.get('net', ''), shape.get('device_id', '')))
            fragment['id'] = shape['id']+':resistive:'+str(index)
            fragment['source_id'] = shape.get('source_id', shape['id'])
            fragment['_contact_source_key'] = (shape['id'], shape.get('source_id', ''), shape.get('instance_path', ''))
            result.append(fragment)
    return result


def blocked_regions(shapes, technology):
    rules=technology.get('connectivity',{}).get('via_blockers',[])
    if not rules:return {}
    names={layer['name'] for layer in technology['layers']}
    vias=technology.get('connectivity',{}).get('vias',[])
    pairs={frozenset((a,cut)) for a,cut,b in vias}|{frozenset((cut,b)) for a,cut,b in vias}
    by_mask={};result={}
    for rule in rules:
        if not isinstance(rule,dict) or set(rule)!={'conductor','cut','mask'} or any(rule[key] not in names for key in rule):
            raise ValueError('A via blocker needs mapped conductor, cut and mask layers.')
        pair=frozenset((rule['conductor'],rule['cut']))
        if len(pair)!=2 or pair not in pairs or rule['mask'] in pair:
            raise ValueError('A via blocker must identify an existing conductor/cut contact and a distinct mask.')
        if rule['mask'] not in by_mask:
            region=kdb().Region()
            for shape in shapes:
                if shape['layer']==rule['mask']:region.insert(polygon(shape))
            by_mask[rule['mask']]=region.merged()
        result[pair]=result.get(pair,kdb().Region())+by_mask[rule['mask']]
    return {key:region.merged() for key,region in result.items()}


def interacts(first,second,first_region,second_region,blockers):
    """Actual polygon contact after subtracting explicitly insulated overlap."""
    mask=blockers.get(frozenset((first['layer'],second['layer'])))
    if mask is not None and not mask.is_empty():first_region=first_region-mask
    return not first_region.interacting(second_region).is_empty()
