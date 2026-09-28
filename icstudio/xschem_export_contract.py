"""Reject native capture semantics that Xschem exchange cannot preserve yet."""


def require_supported(project, *, source_capture=False):
    """Check before creating output files; original Xschem vectors stay supported.

    Studio's explicit ``array`` field has no equivalent in the current capture
    exporters. Native compact buses also need a tested scalar-pin conversion;
    emitting their text as ordinary labels is not an electrical round trip.
    """
    from .native_vectors import signals
    for cell in project['cells']:
        for device in cell['devices']:
            if device.get('array') is not None:
                raise ValueError(cell['name']+'/'+device['name']+
                    ': Xschem export cannot preserve a compact native instance array. '
                    'Materialize its members into explicit devices, or export a SPICE deck.')
    if source_capture:
        return
    expressions = [('Global net', name) for name in project.get('global_nets', [])]
    for cell in project['cells']:
        expressions.extend((cell['name']+' port', name) for name in cell['ports'])
        for device in cell['devices']:
            expressions.extend((cell['name']+'/'+device['name']+' connection', name)
                               for name in device['nets'].values())
            if device['kind'] in ('X', 'SPICE', 'XS'):
                expressions.extend((cell['name']+'/'+device['name']+' terminal', name)
                                   for name in device['nets'])
        expressions.extend((cell['name']+' label', label['name'])
                           for label in cell.get('labels', []))
        expressions.extend((cell['name']+' wire', wire['net'])
                           for wire in cell.get('wires', []) if wire.get('net'))
    for owner, expression in expressions:
        if len(signals(expression)) > 1:
            raise ValueError(owner+' '+expression+
                ': Xschem export cannot preserve a compact native bus or slice. '
                'Use explicit scalar terminals and nets, or export a SPICE deck.')
