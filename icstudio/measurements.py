"""Waveform interpolation and explicit point / whole-trace limit checks."""
import bisect, math


def sample_at(result,trace,x,nearest=False):
    if result.get('x_order')=='ascending':
        xs=result.get('x',[]);ys=result.get('traces',{}).get(trace,[])
        if len(xs)!=len(ys):return None
    else:
        pairs=sorted(zip(result.get('x',[]),result.get('traces',{}).get(trace,[])));xs=[p[0] for p in pairs];ys=[p[1] for p in pairs]
    if not xs or not math.isfinite(x) or x<xs[0] or x>xs[-1]:return None
    i=bisect.bisect_left(xs,x)
    if i==0 or (i<len(xs) and xs[i]==x):return ys[i]
    if i==len(xs):return ys[-1]
    x0,y0=xs[i-1],ys[i-1];x1,y1=xs[i],ys[i]
    if nearest:return y0 if x-x0<=x1-x else y1
    settings=result.get('settings',{});kind=settings.get('type');kind=settings.get('analysis',{}).get('type') if kind=='post_layout' else kind
    if kind in ('xschem','program'):kind=result.get('plot_kind')
    if kind in ('ac','noise') or result.get('x_label')=='frequency':
        if x0>0:fraction=(math.log(x)-math.log(x0))/(math.log(x1)-math.log(x0))
        else:fraction=(x-x0)/(x1-x0)
    else:fraction=(x-x0)/(x1-x0)
    return y0+(y1-y0)*fraction


def evaluate(result,marker):
    trace=marker['trace'];values=result.get('traces',{}).get(trace,[])
    if not values:return {'value':None,'verdict':'No trace','crossings':0}
    kind=marker['kind'];rule=marker.get('rule','<=');limit=marker.get('y',0)
    if kind=='Y':value=max(values) if rule=='<=' else min(values)
    else:value=sample_at(result,trace,marker['x'],marker.get('nearest',False))
    if value is None:return {'value':None,'verdict':'Out of range','crossings':0}
    verdict='Readout' if kind=='X' else 'PASS' if (value<=limit if rule=='<=' else value>=limit) else 'FAIL'
    # Count true crossings/touches once across plateaus at the threshold.
    crossings=0;previous=None;on_limit=False
    for y in values:
        side=0 if y==limit else 1 if y>limit else -1
        if side==0:
            if not on_limit:crossings+=1
            on_limit=True
        else:
            if previous is not None and previous!=side and not on_limit:crossings+=1
            on_limit=False;previous=side
    return {'value':value,'verdict':verdict,'crossings':crossings}
