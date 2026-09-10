"""Fit declared interconnect coefficients to supplied coupon measurements.

No foundry values are invented. A fit is bound to layer mapping, process lock,
corner and a hash of the supplied measurements, with explicit residual limits.
"""
import math
from .model import clone, digest


def technology_key(tech):
    return digest({'lock':tech.get('package_lock'), 'grid':tech['grid'],
                   'layers':[(l['name'],l['gds'],l['datatype']) for l in tech['layers']]})


def positive(row, key, zero=False):
    value = row.get(key)
    if type(value) not in (int,float) or not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(key+': provide a finite '+('non-negative' if zero else 'positive')+' number in the documented units.')
    return value


def calibrate(tech, data):
    source = data.get('source', '').strip(); corner = data.get('corner', '').strip()
    if not source or not corner or len(source)>2000 or len(corner)>80:
        raise ValueError('Supply the measurement source and one named corner.')
    layers = {l['name'] for l in tech['layers']}; rows = data.get('layers')
    if not isinstance(rows,dict) or not rows or len(rows)>64 or not rows.keys()<=layers:
        raise ValueError('Supply measurement rows for one to 64 mapped layers.')
    tolerance = positive(data,'max_relative_error')
    if tolerance>0.25: raise ValueError('Calibration residual limit must be at most 25%.')
    coefficients = {}; residuals = []
    for layer, samples in rows.items():
        for kind, minimum in (('resistance',2),('capacitance',3),('coupling',2)):
            if not isinstance(samples.get(kind),list) or not minimum<=len(samples[kind])<=1000:
                raise ValueError(layer+': supply at least '+str(minimum)+' '+kind+' coupons and at most 1,000.')
        rs = [(positive(r,'length_um')/positive(r,'width_um'),positive(r,'resistance_ohm')) for r in samples['resistance']]
        sheet = sum(x*y for x,y in rs)/sum(x*x for x,y in rs)
        cs = [(positive(r,'length_um')*positive(r,'width_um'),2*(r['length_um']+r['width_um']),positive(r,'capacitance_f')) for r in samples['capacitance']]
        aa = sum(a*a for a,b,y in cs); bb = sum(b*b for a,b,y in cs); ab = sum(a*b for a,b,y in cs)
        ay = sum(a*y for a,b,y in cs); by = sum(b*y for a,b,y in cs); det = aa*bb-ab*ab
        if det<=1e-10*aa*bb: raise ValueError(layer+': vary coupon widths and lengths to separate area and edge capacitance.')
        area, edge = (ay*bb-by*ab)/det, (by*aa-ay*ab)/det
        if min(area,edge)<-1e-25: raise ValueError(layer+': coupon fit produced a negative capacitance coefficient.')
        area, edge = max(0.,area), max(0.,edge)
        ks = [(positive(r,'overlap_um')/positive(r,'gap_um'),positive(r,'capacitance_f')) for r in samples['coupling']]
        coupling = sum(x*y for x,y in ks)/sum(x*x for x,y in ks)
        for kind, fitted in (('resistance',[(sheet*x,y) for x,y in rs]),('capacitance',[(area*a+edge*b,y) for a,b,y in cs]),('coupling',[(coupling*x,y) for x,y in ks])):
            for index,(prediction,actual) in enumerate(fitted):
                error=abs(prediction-actual)/actual
                if not math.isfinite(error) or error>tolerance: raise ValueError(layer+': '+kind+' coupon '+str(index+1)+' exceeds the residual limit.')
                residuals.append({'layer':layer,'kind':kind,'index':index,'relative_error':error})
        coefficients[layer]={'sheet_ohm':sheet,'cap_f_per_um2':area,'edge_f_per_um':edge,'coupling_f_per_um':coupling,'source':source}
    return {'schema':1,'corner':corner,'source':source,'technology_key':technology_key(tech),
            'measurements_hash':digest(data),'measurements':clone(data),'coefficients':coefficients,
            'residuals':residuals,'max_relative_error':max(r['relative_error'] for r in residuals),
            'qualification':'Coupon-fitted declared model only; no field-solver, cross-layer coupling or independent process qualification.'}


def install(tech, result):
    if result['technology_key']!=technology_key(tech): raise ValueError('Calibration belongs to another process lock or layer map.')
    # Recompute the fit so a modified imported result cannot assert calibration.
    verified=calibrate(tech,result['measurements'])
    if verified!=result: raise ValueError('Calibration result differs from its measurement evidence.')
    tech.setdefault('parasitic_corners',{})[result['corner']]=clone(result)


def coefficients(tech, corner):
    profiles=tech.get('parasitic_corners',{})
    if not profiles:return tech.get('parasitics',{}),None
    if corner not in profiles: raise ValueError('No RC calibration for corner '+corner+'. Import that corner or explicitly remove the calibrated profiles to use declared estimates.')
    result=profiles[corner]
    if result['technology_key']!=technology_key(tech): raise ValueError('RC calibration is stale after a process-lock or layer-map change.')
    if digest(result['measurements'])!=result['measurements_hash'] or calibrate(tech,result['measurements'])!=result:
        raise ValueError('RC calibration coefficients or evidence were changed; refit the coupons.')
    return result['coefficients'],{k:clone(v) for k,v in result.items() if k not in ('measurements','coefficients','residuals')}
