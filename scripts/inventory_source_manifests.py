"""Exact setup-tool manifest and include-only SKY KLayout macro declarations.

No upstream code is executed, no dependency is resolved, and a setup target is
not evidence that a tool is installed or that any device has been qualified.
"""
import hashlib
import re
import xml.etree.ElementTree as ET


def require(ok, message):
    if not ok:
        raise ValueError('Source manifest inventory: '+message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


REVIEWED = {('gf180-open-pdks', 'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9', 'scripts/tools.txt', 'scripts/tools.txt', None, '100644'): ('78dea839533083d87f9ed6d0cc383d00516fcd80c6ee5ab87874e108fae62722', '8c888369c0de3e805a7e7816ca2ad2c21804d629', 59, 'setup-tool-manifest'), ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/libs.tech/klayout/lvs/sky130.lylvs', 'sky130A/libs.tech/klayout/lvs/sky130.lylvs', 'common.tar.zst', 436): ('a233295ff25f15f064580e1d722f624eb77ea70ded5d164c3b6fb7a8900bfaf4', None, 1255, 'include-only-lvs-macro'), ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/libs.tech/klayout/lvs/sky130.lylvs', 'sky130B/libs.tech/klayout/lvs/sky130.lylvs', 'common.tar.zst', 436): ('a233295ff25f15f064580e1d722f624eb77ea70ded5d164c3b6fb7a8900bfaf4', None, 1255, 'include-only-lvs-macro')}


def manifest_facts(text):
    names=text.splitlines()
    require(names and all(re.fullmatch('[a-z][a-z0-9_-]*',name) for name in names),
            'unsupported tool manifest syntax')
    require(len(names)==len(set(names)), 'duplicate setup target')
    return [dict(kind='setup-tool-target',name=name,line=line,installed_capability=False)
            for line,name in enumerate(names,1)]


def include_macro_facts(text):
    require('<!DOCTYPE' not in text and '<!ENTITY' not in text, 'unsupported XML declaration')
    root=ET.fromstring(text)
    require(root.tag=='klayout-macro' and not root.attrib, 'unexpected macro root')
    expected=['description','version','category','prolog','epilog','doc','autorun','autorun-early',
              'shortcut','show-in-menu','group-name','menu-path','interpreter','dsl-interpreter-name','text']
    require([node.tag for node in root]==expected, 'unexpected macro fields')
    require(all(not node.attrib and len(node)==0 for node in root), 'nested macro fields')
    values={node.tag:node.text or '' for node in root}
    require(values['interpreter']=='dsl' and values['dsl-interpreter-name']=='lvs-dsl-xml' and
            values['autorun']=='false' and values['autorun-early']=='false' and
            values['prolog']==values['epilog']=='', 'unexpected macro execution configuration')
    rows=[dict(kind='klayout-macro-metadata',name=key,value=value) for key,value in values.items() if key!='text']
    includes=[]
    for line,value in enumerate(text.splitlines(),1):
        if re.match(r'\s*#\s*%',value):
            require(re.fullmatch(r'\s*#\s*%include sky130\.lvs\s*',value) is not None,
                    'unsupported include directive')
            includes.append(dict(kind='klayout-include-reference',name='sky130.lvs',line=line,
                                 dependency_resolved=False,executed=False))
    body=values['text']
    require(all(not line.strip() or line.lstrip().startswith('#') for line in body.splitlines()),
            'non-comment macro body')
    require(len(includes)==1, 'expected one literal dependency')
    return rows+includes+[dict(kind='reviewed-klayout-wrapper-role',name='include-only-lvs-macro',
                              device_rule_implementation=False,executed=False)]


def source_manifest_views(row, raw):
    key=tuple(row.get(k) for k in ('family','repository','repository_path','path','archive','mode'))
    selected=REVIEWED.get(key)
    if selected is None:return None
    digest,blob,size,role=selected
    require(type(raw) is bytes and len(raw)==size and sha(raw)==digest, 'source bytes changed')
    require(row.get('bytes')==size and row.get('sha256',digest)==digest, 'source ledger identity changed')
    if blob is not None:
        require(row.get('git_blob_sha1')==blob and
                hashlib.sha1(b'blob '+str(size).encode()+b'\0'+raw).hexdigest()==blob,
                'Git source identity changed')
    else:
        require(row.get('git_blob_sha1') is None and row.get('process')==row['family'],
                'release source identity changed')
    text=raw.decode('utf-8')
    return manifest_facts(text) if role=='setup-tool-manifest' else include_macro_facts(text)
