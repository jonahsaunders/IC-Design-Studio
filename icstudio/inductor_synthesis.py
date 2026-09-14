"""Bounded, cancellable search for approximate target-L spiral candidates."""
import math

from . import inductor
from .inductor_shapes import centerline
from .model import clone


class Cancelled(ValueError):
    pass


def check_cancel(cancel):
    if cancel and cancel():
        raise Cancelled('Search cancelled.')


def search(tech, base, target_h, max_width_nm, max_height_nm, *,
           width_range=None, spacing_range=None, tolerance=.05, max_results=8,
           cancel=None):
    """Search up to 32 turns, three widths/spacings and grid-snapped openings.

    Candidates meet declared isolated geometry checks and footprint bounds.
    Placement/collision checks run when a candidate is selected in the editor.
    A result outside tolerance is explicitly marked; no exact/optimal solution
    or RF accuracy is implied by this finite search.
    """
    if not math.isfinite(target_h) or not 1e-15<=target_h<=1e-3:
        raise ValueError('Target L must be between 1 fH and 1 mH.')
    if not 0<tolerance<=1 or not 1<=max_results<=20:
        raise ValueError('Use a 0–100% nonzero tolerance and 1–20 results.')
    if any(type(v) is not int or not 1000<=v<=5000000 for v in (max_width_nm,max_height_nm)):
        raise ValueError('Maximum footprint dimensions must be 1–5,000 µm.')
    quantum=2*tech['grid']
    def samples(bounds,default):
        lo,hi=bounds or (default,default)
        if any(type(v) is not int for v in (lo,hi)) or not 0<lo<=hi<=2000000:
            raise ValueError('Width/spacing ranges must increase within 0–2,000 µm.')
        lo=math.ceil(lo/quantum)*quantum;hi=hi//quantum*quantum
        if lo>hi:raise ValueError('The requested range contains no legal grid value.')
        return sorted({lo,hi,round((lo+hi)/(2*quantum))*quantum})
    widths=samples(width_range,base['width']);spaces=samples(spacing_range,base['spacing'])
    ranked=[];attempts=0
    aspect=base.get('inner_y',base['inner'])/base['inner'] if base['shape']=='rectangle' else 1.
    def evaluate(spec,opening):
        nonlocal attempts
        attempts+=1;check_cancel(cancel)
        s={**spec,'inner':opening}
        if s['shape']=='rectangle':s['inner_y']=round(opening*aspect/quantum)*quantum
        line=centerline(s,tech['grid']);points=line['points']+[line['q']]
        # Include full-width terminal pads on both ends of every lead.
        width=max(p[0] for p in points)-min(p[0] for p in points)+s['width']
        height=max(p[1] for p in points)-min(p[1] for p in points)+s['width']
        return s,line,width,height
    for width in widths:
        for spacing in spaces:
            for turns in range(1,33):
                check_cancel(cancel)
                spec={**base,'width':width,'spacing':spacing,'turns':turns}
                minimum=inductor.limits(tech,spec)
                if width<minimum['width'] or spacing<minimum['spacing'] or spec['lead']<minimum['lead']:continue
                lo=math.ceil(max(width,spacing,max(width,spacing)/aspect)/quantum)
                hi=int(min(2000000,2000000/aspect,max_width_nm,max_height_nm/aspect)//quantum)
                if hi<lo:continue
                seen=set()
                # L is monotonic with opening for these fixed cross sections.
                # Oversized candidates reduce the upper bound independently.
                for _ in range(20):
                    if lo>hi:break
                    mid=(lo+hi)//2
                    s,line,w,h=evaluate(spec,mid*quantum)
                    if w>max_width_nm or h>max_height_nm:
                        hi=mid-1;continue
                    error=abs(line['estimate_h']/target_h-1)
                    if mid not in seen:
                        ranked.append((error,w*h,s));seen.add(mid)
                    if line['estimate_h']<target_h:lo=mid+1
                    else:hi=mid-1
    from .live_geometry import preview
    from .layout_vias import declare_connections
    # A minimal isolated project is sufficient for mask width/space/enclosure.
    p=dict(pdk=clone(tech),revision=0,cells=[dict(id='search',shapes=[])])
    declare_connections(p['pdk']);results=[];seen=set();families=set()
    for error,area,spec in sorted(ranked,key=lambda v:(v[0],v[1])):
        check_cancel(cancel)
        key=tuple(spec.get(k) for k in ('turns','width','spacing','inner','inner_y'))
        family=key[:3]
        if family in families:continue
        if key in seen:continue
        seen.add(key)
        # Keep verification bounded even when a PDK rejects most coarse hits.
        if len(seen)>160:break
        try:
            data=inductor.geometry(p['pdk'],spec)
            if data['footprint_nm'][0]>max_width_nm or data['footprint_nm'][1]>max_height_nm:continue
            if preview(p,'search',data['shapes']):continue
        except ValueError:continue
        results.append(dict(spec=data['spec'],estimate_h=data['estimate_h'],relative_error=error,
                            within_tolerance=error<=tolerance,footprint_nm=data['footprint_nm'],
                            area_um2=data['footprint_nm'][0]*data['footprint_nm'][1]*1e-6,model=data['model']))
        families.add(family)
        if len(results)>=max_results:break
    return dict(candidates=results,target_h=target_h,tolerance=tolerance,evaluations=attempts,
                qualification='Bounded DC estimate search; candidates require placement checks and process/EM verification.',
                message=('Candidates found.' if any(r['within_tolerance'] for r in results) else
                         'No candidate met tolerance. Closest legal candidates are shown; widen the constraints.' if results else
                         'No legal candidate fits these constraints. Increase the footprint or widen the width/spacing ranges.'))
