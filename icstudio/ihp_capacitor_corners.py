"""Opt-in project-local capacitor sections for the reviewed bundled IHP PDK."""
import json
from .bundled_pdks import bundle_root
from .model import clone, file_digest
from .pdks import model_lines

MANIFEST_SHA256='da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0'
CAP='libs.tech/ngspice/models/cornerCAP.lib'
CHOICES={
    'icstudio_cap_typ_others_nominal':('cap_typ','Capacitors: cap_typ; other models nominal'),
    'icstudio_cap_bcs_others_nominal':('cap_bcs','Capacitors: cap_bcs; other models nominal'),
    'icstudio_cap_wcs_others_nominal':('cap_wcs','Capacitors: cap_wcs; other models nominal'),
}
PROVENANCE={'schema':1,'scope':'project-local capacitor sections; other models nominal',
            'source_manifest_sha256':MANIFEST_SHA256,'capacitor_library':CAP,
            'sections':{key:value[0] for key,value in CHOICES.items()}}
KEY='ihp_capacitor_corner_profiles_v1'

def labels(technology):
    if technology.get(KEY)!=PROVENANCE:return {}
    try:
        manifest=reviewed_manifest();lock=technology.get('package_lock',{})
        if any(lock.get(k)!=manifest[k] for k in ('id','revision','files')):return {}
        includes=prepared_includes(manifest)
        if technology.get('simulation',{}).get('includes')!=includes:return {}
    except (OSError,ValueError,KeyError,TypeError):return {}
    return {key:label for key,(_,label) in CHOICES.items()}

def reviewed_manifest():
    path=bundle_root()/'ihp-sg13g2/package.json'
    if file_digest(path)!=MANIFEST_SHA256:raise ValueError('The reviewed bundled IHP package has changed.')
    return json.loads(path.read_bytes())

def prepared_includes(manifest):
    base=manifest['technology']['simulation']['includes']
    if len([x for x in base if x.get('path')==CAP])!=1:raise ValueError('The reviewed capacitor library is ambiguous.')
    wanted=clone(base)
    for item in wanted:
        sections=item.get('sections',{})
        if 'nominal' not in sections:raise ValueError('A model library lacks its nominal section.')
        if item['path']==CAP and any(sections.get(section)!=section for section,_ in CHOICES.values()):
            raise ValueError('The capacitor sections do not match the reviewed package.')
        for key,(section,_) in CHOICES.items():
            if key in sections:raise ValueError('A capacitor-only corner name already exists.')
            sections[key]=section if item['path']==CAP else sections['nominal']
    return wanted

def add_profiles(technology):
    """Return an independent technology copy; never change its package lock."""
    manifest=reviewed_manifest();lock=technology.get('package_lock',{})
    if any(lock.get(k)!=manifest[k] for k in ('id','revision','files')):
        raise ValueError('This action requires the exact reviewed IHP package lock.')
    base=manifest['technology']['simulation']['includes'];wanted=prepared_includes(manifest)
    result=clone(technology);includes=result.get('simulation',{}).get('includes')
    if includes is None:raise ValueError('Missing model include mapping.')
    previous=technology.get(KEY)
    if previous is None:
        if includes!=base:raise ValueError('The project model include mapping differs from the reviewed package.')
    elif previous!=PROVENANCE or includes!=wanted:
        raise ValueError('Existing project-local capacitor corner mapping conflicts.')
    model_lines(technology,'nominal')
    result['simulation']['includes']=wanted;result[KEY]=clone(PROVENANCE)
    return result
