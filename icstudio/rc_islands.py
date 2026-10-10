"""Remove only disconnected, unobservable resistor components from a flat deck.

Device-identifier geometry can produce resistor-only islands during all-net
extraction. A component touching any port, device or capacitor is never removed.
Keep the source and record every omitted resistor; never add artificial leakage.
"""
import json
from pathlib import Path
from .model import atomic_write,file_digest,scalar


def prune(source,target,*,physical_devices=(),normalization=None):
    source,target=Path(source).resolve(),Path(target).resolve()
    if target.exists() or source==target:raise ValueError('Use a new electrical RC output file.')
    text=source.read_bytes().decode('utf-8');parent={};anchors=set();resistors=[]
    from .magic_rc import compact_sources, _spice_devices, _spice_lines, _spice_tokens
    lines=_spice_lines(text)
    auxiliary=compact_sources(text,normalization or {})
    active=False;declarations=0;names=set();physical={str(name).casefold() for name in physical_devices}
    def find(name):
        name=name.casefold();parent.setdefault(name,name)
        while parent[name]!=name:
            parent[name]=parent[parent[name]];name=parent[name]
        return name
    for line in lines:
        t=_spice_tokens(line)
        if not t or t[0].startswith('*'):continue
        key=t[0].lower()
        if not key.startswith('.'):
            if key in names:raise ValueError('Duplicate RC element name: '+t[0])
            names.add(key)
        if key=='.subckt':
            if active:raise ValueError('RC island analysis requires one flat subcircuit.')
            declarations+=1;active=True;anchors.update(t[2:])
        elif key=='.ends':active=False
        elif key in auxiliary:
            if not active or t!=auxiliary[key]:raise ValueError('Compact RC helper changed before island analysis.')
            # Authenticated helper R terminate only internal sums. They are not
            # physical wire edges and must never join unrelated islands via 0.
            if key.startswith(('g','e')):anchors.update(t[1:5])
        elif key in physical and key.startswith(('r','c')):
            if not active or len(t)<4:raise ValueError('Unsupported physical RC device.')
            anchors.update(t[1:3])
        elif key.startswith('r') and len(t)>4:
            # Modeled semiconductor resistors are physical anchors, never
            # removable wire edges. Numeric physical R use explicit identities.
            if not active or not any('=' in value for value in t[4:]):raise ValueError('Unsupported physical resistor.')
            anchors.update(t[1:3])
        elif key.startswith('r'):
            if not active or len(t)!=4 or scalar(t[3])<0:raise ValueError('Unsupported RC resistor.')
            parent[find(t[1])]=find(t[2]);resistors.append(t)
        elif key.startswith('c'):
            if not active or len(t)!=4:raise ValueError('Unsupported RC capacitor.')
            anchors.update(t[1:3])
        elif key.startswith('d'):
            if not active:raise ValueError('Out-of-scope native RC diode.')
            _spice_devices(line)  # Two ordered nodes, model, named parameters.
            anchors.update(t[1:3])
        elif key.startswith(('x','m')):
            idx=5 if key.startswith('m') else next((i for i,v in enumerate(t) if '=' in v),len(t))-1
            if not active or idx<2:raise ValueError('Unsupported RC device.')
            anchors.update(t[1:idx])
        else:raise ValueError('Unsupported RC island record: '+key)
    if active or declarations!=1:raise ValueError('RC island analysis requires one complete flat subcircuit.')
    anchored={find(n) for n in anchors}
    dropped={t[0].casefold() for t in resistors if find(t[1]) not in anchored}
    components={find(t[1]) for t in resistors if t[0].casefold() in dropped}
    result=''.join(line for line in lines if not line.split() or line.split()[0].casefold() not in dropped)
    atomic_write(target,result)
    report={'source_sha256':file_digest(source),'electrical_sha256':file_digest(target),
            'removed_resistors':sorted(dropped),'components':len(components),
            'physical_devices':sorted(physical),
            'preserved_compact_sources':sum(n.startswith(('e','g')) for n in auxiliary),
            'preserved_compact_resistors':sum(n.startswith('r') for n in auxiliary),
            'criterion':'Resistor-only connected component with no port, device terminal or capacitor endpoint. All observable circuit lines retained verbatim.'}
    atomic_write(str(target)+'.islands.json',json.dumps(report,indent=2))
    return report
