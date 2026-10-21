"""Retain the full native IHP DRC gate when a layout contains NPN markers.

The public KLayout decks miss an unrelated active island inside TRANS. The
already qualified Magic rule catches it. Run its entire full style on the
layout; do not crop devices, discard findings or infer new thresholds. The
combined public-deck route can supply authenticated SVaricap import context.
"""
import json
from pathlib import Path
import re
from .model import atomic_write,file_digest


def check(executable,technology,style,source,top,ports,output,*,public_context=None):
    import klayout.db as k
    from .engines import tcl_word
    from .silicon_flow import magic_script
    source=Path(source);out=Path(output);ly=k.Layout();ly.read(str(source));cell=ly.cell(top)
    if cell is None:raise ValueError('Missing IHP NPN check top cell.')
    index=ly.find_layer(26,0)
    required=index is not None and not k.Region(cell.begin_shapes_rec(index)).is_empty()
    result=dict(schema=1,required=required,violations=0,layout_sha256=file_digest(source),findings=[],
                scope='Full unfiltered native Magic DRC is additionally required on the entire layout whenever TRANS 26/0 is present.')
    if required:
        native_source=source;context_commands=''
        if public_context is not None:
            from .ihp_varactor_context import prepare
            assets,expected=public_context
            context=prepare(source,top,technology,assets,expected,out/'public-varactor-context')
            if context is not None:
                technology,native_source,context_commands,proof=context
                result['public_varactor_context']=proof
                result['scope']=proof['scope']
        commands='snap internal\nselect top cell\nbox values {*}[select bbox]\nbox grow c 10um\ndrc style '+tcl_word(style)+'\ndrc ignore none\ndrc check\ndrc catchup\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\nputs "STUDIO_MAGIC_SCALE [cif scale out]"\n'
        commands+='set f [open findings.tsv w]\nforeach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\n'
        log=magic_script(executable,technology,native_source,top,ports,out,context_commands+commands)
        counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M);scales=re.findall(r'^STUDIO_MAGIC_SCALE ([0-9.eE+-]+)$',log,re.M)
        if len(counts)!=1 or len(scales)!=1 or re.findall(r'^STUDIO_DRC_STYLE (.+)$',log,re.M)!=[style]:
            raise ValueError('The full native IHP NPN DRC check did not finish.')
        result.update(violations=int(counts[0]),style=style,technology_sha256=file_digest(technology))
        for line in (out/'findings.tsv').read_text().splitlines():
            reason,box=line.split('\t');coords=[round(float(v)*float(scales[0])*1000) for v in box.split(',')]
            if len(coords)!=4:raise ValueError('Malformed native IHP NPN DRC finding.')
            result['findings'].append(dict(reason=reason,bbox_nm=coords))
    out.mkdir(parents=True,exist_ok=True);atomic_write(out/'result.json',json.dumps(result,indent=2));return result
