"""Narrow, recorded adapters for the pinned GF180 B Banba RC reference."""
import re


def sparse_solver(text):
    """Set the solver for both ordinary and diagnostic decks, including EOF END."""
    if re.search(r'(?im)^\s*\.control\b',text):raise ValueError('Reference deck already has a control program.')
    text,count=re.subn(r'(?im)^[ \t]*\.end[ \t]*(?:\r?\n|$)',
                      '.option klu\n.control\nset num_threads=1\n.endc\n.end\n',text)
    if count!=1:raise ValueError('Reference deck needs exactly one END statement.')
    return text


def technology(text):
    pattern=r'(device msubcircuit pnp_\S+ pnp) pwell,space/w \*pdiff error a2>([\d.]+) a2<([\d.]+)'
    result,count=re.subn(pattern,r'\1 *pdiff pwell,space/w a1>\2 a1<\3',text)
    if count!=4:raise ValueError('Pinned GF180 PNP declarations changed.')
    old=' layer mimcc VIA3\n and MET4\n and CAPM\n and CAPDEF\n grow 260\n shrink 250'
    if result.count(old)!=1 or 'squares-grid 40 260 500' not in result:
        raise ValueError('Pinned GF180 MIM cut/border declarations changed.')
    # 260 nm cut + two 40 nm borders = 340 nm internal contact.
    # Upstream imports 280 nm, then warns while assuming one via. Preserve
    # the actual cut count by making the input inverse agree with the output.
    return result.replace(old,old.replace('shrink 250','shrink 220'))


def collapsed(text,normalization):
    """Contract every named wire-R component, preserving all device parameters."""
    owner={n:net for net,data in normalization['nets'].items() for n in data['nodes']}
    lines=[]
    for line in text.splitlines():
        fields=line.split()
        if fields and fields[0][0].upper() in ('R','C'):continue
        if fields and fields[0][0].upper()=='X':
            idx=next((i for i,v in enumerate(fields) if '=' in v),len(fields))-1
            fields[1:idx]=[owner[n] for n in fields[1:idx]];line=' '.join(fields)
        lines.append(line)
    return '\n'.join(lines)+'\n'
