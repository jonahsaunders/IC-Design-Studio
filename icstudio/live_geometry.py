"""Fast local preview checks plus revision-tagged background physical feedback."""
from .layout import kdb,polygon,drc
from .model import clone,digest
from .spatial import SpatialIndex


def enclosure_rules(tech):
    rules=clone(tech.get('enclosures',[]))
    try:
        from .parametric import rules as pcell_rules
        cfg=pcell_rules(tech).get('contact',{})
        for key in ('lower','upper'):
            if cfg:rules.append({'cut':cfg['cut'],'conductor':cfg[key],'minimum':cfg['enclosure']})
    except ValueError:pass
    try:
        from .layout_edit import via_options
        for a,cut,b,size,pad in via_options(tech).values():
            for layer in (a,b):rules.append({'cut':cut,'conductor':layer,'minimum':(pad-size)//2})
    except ValueError:pass
    return list({(r['cut'],r['conductor'],r['minimum']):r for r in rules}.values())


def check_enclosures(p,cid,shapes):
    db=kdb();out=[];regions={}
    for s in shapes:regions.setdefault(s['layer'],db.Region()).insert(polygon(s))
    for rule in enclosure_rules(p['pdk']):
        cut=rule['cut'];outer=regions.get(rule['conductor'],db.Region());minimum=int(rule['minimum'])
        if minimum<0:raise ValueError('Enclosure must be non-negative.')
        for s in shapes:
            if s['layer']!=cut:continue
            missing=db.Region(polygon(s)).sized(minimum)-outer
            if not missing.is_empty():
                b=polygon(s).bbox();out.append({'severity':'error','code':'ENCLOSURE','cell_id':cid,'object':s['id'],'bbox':[b.left,b.bottom,b.right,b.top],'message':f"{cut} needs {minimum} nm of {rule['conductor']} enclosure.",'fingerprint':digest([p['revision'],s['id'],rule])})
    return out


_near_cache=[]

def preview(p,cid,candidates):
    if not candidates:return []
    db=kdb();c=next(c for c in p['cells'] if c['id']==cid);layers={s['layer'] for s in candidates};rules={l['name']:l for l in p['pdk']['layers']};margin=max([max(l['space'],l['width']) for l in rules.values()]+[1000])*2
    box=polygon(candidates[0]).bbox()
    for s in candidates[1:]:box=box+polygon(s).bbox()
    window=box.enlarged(margin)
    cached=next((index for shapes,index in _near_cache if shapes is c['shapes']),None)
    if cached is None:
        boxes=[]
        for i,s in enumerate(c['shapes']):
            xs,ys=zip(*s['points']);half=s.get('width',0)/2;boxes.append(((min(xs)-half,min(ys)-half,max(xs)+half,max(ys)+half),i))
        cached=SpatialIndex(boxes);_near_cache[:]=[(c['shapes'],cached)]+_near_cache[:1]
    near=[c['shapes'][i] for i in cached.query((window.left,window.bottom,window.right,window.top))]
    if len(near)>2500:raise ValueError('Preview region is dense. Zoom in or run background checks.')
    out=[];ids={s['id'] for s in candidates};base=[s for s in near if s['id'] not in ids]
    for layer in layers:
        if layer not in rules:raise ValueError('Unmapped drawing layer.')
        rule=rules[layer];region=db.Region()
        for s in base+candidates:
            if s['layer']==layer:region.insert(polygon(s))
        region.merge();candidate_region=db.Region()
        for s in candidates:
            if s['layer']==layer:candidate_region.insert(polygon(s))
        for code,checks in [('WIDTH',region.width_check(rule['width'])),('SPACE',region.space_check(rule['space']))]:
            for pair in checks.each():
                b=pair.bbox()
                if not b.touches(box):continue
                out.append({'severity':'error','code':code,'cell_id':cid,'object':candidates[0]['id'],'bbox':[b.left,b.bottom,b.right,b.top],'message':f"{layer}: {code.lower()} below {rule['width' if code=='WIDTH' else 'space']} nm."})
        # Separate net labels must not be electrically shorted by a candidate.
        for candidate in (s for s in candidates if s['layer']==layer and s.get('net')):
            r=db.Region(polygon(candidate))
            for old in (s for s in base if s['layer']==layer and s.get('net') and s['net']!=candidate['net']):
                if not r.interacting(db.Region(polygon(old))).is_empty():out.append({'severity':'error','code':'SHORT','cell_id':cid,'object':old['id'],'message':candidate['net']+' would touch '+old['net']+' on '+layer+'.'})
    for candidate in candidates:
        if any(v%p['pdk']['grid'] for pt in candidate['points'] for v in pt):out.append({'severity':'error','code':'GRID','cell_id':cid,'object':candidate['id'],'message':'Candidate vertices are off the technology grid.'})
    cuts={r['cut'] for r in enclosure_rules(p['pdk'])}
    if any(s['layer'] in cuts for s in candidates):out+=check_enclosures(p,cid,base+candidates)
    return out


def full(p,cid):
    from .design_ops import flatten_layout
    from .physical import connectivity
    from .analog_constraints import findings
    from .parametric import audit
    issues=audit(p,cid)+drc(p,cid)+check_enclosures(p,cid,flatten_layout(p,cid))+findings(p,cid);check=connectivity(p,cid);issues+=check['issues']
    return {'issues':issues,'guides':check['guides'],'qualification':'Declared geometry rules and physical terminal connectivity; process rule decks and extracted device comparison remain separate.'}
