"""Reviewed physical specialization and explicit electrical array expansion."""
from .model import clone, scalar


def check_layers(studio, candidate):
    """Recheck editor locks at both preview and apply, including child masters."""
    before_cells={cell['id']:cell for cell in studio.project['cells']}
    after_cells={cell['id']:cell for cell in candidate['cells']}
    def objects(cells,key):
        return {(cell['id'],item['id']):item for cell in cells.values() for item in cell.get(key,[])}
    affected=set()
    before,after=objects(before_cells,'shapes'),objects(after_cells,'shapes')
    for table in (before,after):
        affected.update(shape['layer'] for key,shape in table.items() if before.get(key)!=after.get(key))
    # A placement changes effective geometry even when its reusable master has
    # byte-for-byte identical shapes. Traverse both sides to cover additions,
    # removals, arrays, transforms, and replacement with an existing master.
    def hierarchy_layers(cells,cid,seen):
        if cid in seen:return
        seen.add(cid);cell=cells[cid]
        for key in ('shapes','layout_texts','layout_ports','layout_pins'):
            affected.update(item['layer'] for item in cell.get(key,[]))
        for instance in cell.get('layout_instances',[]):
            hierarchy_layers(cells,instance['cell'],seen)
    before,after=objects(before_cells,'layout_instances'),objects(after_cells,'layout_instances')
    for table,cells in ((before,before_cells),(after,after_cells)):
        seen=set()
        for key,instance in table.items():
            if before.get(key)!=after.get(key):hierarchy_layers(cells,instance['cell'],seen)
    for cid in before_cells.keys()|after_cells.keys():
        old,new=before_cells.get(cid,{}),after_cells.get(cid,{})
        for key in ('layout_texts','layout_ports','layout_pins'):
            if old.get(key,[])!=new.get(key,[]):
                affected.update(item['layer'] for cell in (old,new) for item in cell.get(key,[]))
    locked = affected & studio.layout.locked_layers
    if locked:
        raise ValueError('Unlock affected layers before updating physical hierarchy: ' + ', '.join(sorted(locked)))


def apply_candidate(studio):
    def apply(project, candidate):
        check_layers(studio, candidate)
        project.clear()
        project.update(clone(candidate))
    return apply


def materialize_dialog(studio, cid=None):
    if not studio.idle_edit():
        return
    from .physical_variants import materialize
    cid = cid or studio.cid

    def build():
        candidate, report = materialize(studio.project, cid)
        check_layers(studio, candidate)
        rows = report.get('instances', [])
        details = '\n'.join(row['instance'] + ' → ' + row['variant'] for row in rows)
        details += ('\n\nResolve instance parameters into reusable physical masters and regenerate supported device footprints. '
                    'Resolved electrical values and nets must match the original hierarchy. '
                    'Unsupported geometry blocks the change.\n\n'
                    'Review ports and parent routing, then run process DRC/LVS and extracted verification. '
                    'Apply and undo include all affected masters.')
        if not rows:
            details = 'No differing instance parameters require specialization.\n' + details
        return candidate, details

    studio.review_dialog('Resolve and regenerate physical variants', build,
                         apply_candidate=apply_candidate(studio))
    return studio._review_dialog


def array_dialog(studio):
    if not studio.idle_edit():
        return
    cid = studio.cid
    selected = set(studio.selection)
    selected.update(instance.get('device_id') for instance in studio.cell.get('layout_instances', [])
                    if instance['id'] in selected)
    devices = [device for device in studio.cell['devices'] if device.get('array') and device['id'] in selected]
    if len(devices) != 1:
        raise ValueError('Select one schematic instance array to expand into independently linked members.')
    device = devices[0]

    def submit(values):
        pitch_x = round(scalar(values['pitch_x']) * 1000)
        pitch_y = round(scalar(values['pitch_y']) * 1000)

        def build():
            from .physical_cells import materialize_array
            candidate = clone(studio.project)
            materialize_array(candidate, cid, device['id'], a=[pitch_x, pitch_y])
            check_layers(studio, candidate)
            return candidate, (
                'Expand ' + device['name'] + ' into stable, individually editable schematic members. '
                'Existing linked placement expands using the requested pitch; unplaced members remain unplaced. '
                'Member connectivity follows the saved bus order.\n\n'
                'Independent routes remain in place. Review connections and run DRC/LVS after placement. '
                'Apply is one undoable change.')

        studio.review_dialog('Expand linked instance array', build,
                             apply_candidate=apply_candidate(studio))

    return studio.workflow_form('Expand linked instance array', [
        ('pitch_x', 'Physical pitch X (µm)', '20'),
        ('pitch_y', 'Physical pitch Y (µm)', '0'),
    ], submit, 'The pitch is measured in parent layout coordinates. Scalar members retain their indexed names and terminal connections.')
