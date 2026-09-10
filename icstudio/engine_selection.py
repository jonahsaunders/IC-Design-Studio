"""Project-local engine selection and explicit simulator requirements."""


def requirement(project):
    if project.get('spice',{}).get('version')==1:
        return 'ngspice is required for native SPICE models and saved simulation programs.'
    if project.get('xschem_exchange',{}).get('mode')=='compatible':
        return 'ngspice is required for this preserved Xschem simulation program.'
    from .catalog import binding_for
    if any(binding_for(project['pdk'],d) for c in project['cells'] for d in c['devices']):
        return 'ngspice is required for the linked PDK device models.'
    return ''


def selected(project):
    if requirement(project):return 'ngspice'
    choice=project.get('analysis',{}).get('engine','builtin')
    return choice if choice in ('builtin','ngspice') else 'builtin'
