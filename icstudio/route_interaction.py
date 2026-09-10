"""Bounded two-bend cursor previews; full obstacle search remains a worker job."""
from .layout_routing import Geometry, via_recipes, via_shapes, conductors
from .model import uid, NET
from .wiring import clean


class CursorRoute:
    def __init__(self, p, cid, net, width, layers, locked=()):
        self.grid = p['pdk']['grid']; self.net = net; self.width = width; self.layers = layers
        rules = {l['name']: l for l in p['pdk']['layers']}
        if not layers or not set(layers) <= set(conductors(p['pdk'])) or set(layers) & set(locked):
            raise ValueError('Choose unlocked declared conductor layers.')
        if not NET.fullmatch(net) or type(width) is not int or width % (2*self.grid) or width < max(rules[l]['width'] for l in layers):
            raise ValueError('Use a valid net and an on-grid width above every layer minimum.')
        from .layout_scene import LayoutScene
        if LayoutScene().update(p, cid).expanded_count > 2500:
            raise ValueError('Cursor preview supports 2,500 expanded shapes. Use Plan route for larger cells.')
        self.geometry = Geometry(p, cid, net)
        self.vias = [v for v in via_recipes(p['pdk']) if {v['lower'], v['upper']} <= set(layers) and not {v['lower'], v['upper'], v['cut']} & set(locked)]

    def preview(self, start, end):
        for endpoint in (start, end):
            if endpoint['layer'] not in self.layers or len(endpoint['point']) != 2 or any(type(v) is not int or v % self.grid or abs(v) > 100000000 for v in endpoint['point']):
                raise ValueError('Route endpoints must use allowed layers and on-grid coordinates within ±100 mm.')
        chain = []; queue = [(start['layer'], [])]; seen = set()
        while queue:
            layer, chain = queue.pop(0)
            if layer == end['layer']: break
            if layer in seen: continue
            seen.add(layer)
            for v in self.vias:
                if layer in (v['lower'], v['upper']): queue.append((v['upper'] if layer == v['lower'] else v['lower'], chain+[v]))
        else: return {'shapes': [], 'clear': False, 'message': 'No unlocked declared via stack connects these layers.'}
        a, b = start['point'], end['point']; last = []
        for bend in ([b[0], a[1]], [a[0], b[1]]):
            pts = clean([a, bend, b]); shapes = []
            if len(pts) > 1: shapes.append({'id': uid(), 'kind': 'path', 'layer': start['layer'], 'width': self.width, 'points': pts, 'net': self.net, 'device_id': ''})
            for via in chain: shapes.extend(via_shapes(via, b, self.net))
            last = shapes
            if shapes and all(self.geometry.clear(s) for s in shapes):
                return {'shapes': shapes, 'clear': True, 'message': 'Clear direct route under declared spacing and via rules. Click to plan and review.'}
        return {'shapes': last, 'clear': False, 'message': 'Direct route is blocked. Click to search a detour in the route worker.'}
