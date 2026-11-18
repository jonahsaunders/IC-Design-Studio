"""Editable contacted GF180-B practice layouts shared by the four bandgaps."""

from .getting_started import resource_root
from .layout import kdb, rect, shape_from_polygon
from .model import digest, file_digest, scalar, uid
from .physical_cells import assign_port
from .student_bandgap_lab import core_cell

MASKS = dict(nwell=(21,0), active=(22,0), poly=(30,0), pplus=(31,0), nplus=(32,0),
             contact=(33,0), m1=(34,0), via1=(35,0), m2=(36,0), via2=(38,0),
             via3=(40,0), m3=(42,0), m4=(46,0), salicide_block=(49,0), resistor=(62,0),
             fusetop=(75,0), deep_nwell=(12,0), resistor_id=(110,5),
             mim_id=(117,5), mim_long=(117,10), bjt_lvs=(118,5), bjt_drc=(127,5),
             bjt_aux=(204,0))
MINIMUMS = dict(active=(220,280), poly=(180,240), contact=(220,250), nwell=(860,600),
                m1=(230,230), m2=(280,280), m3=(280,280), m4=(440,460),
                via1=(260,260), via2=(260,260), via3=(260,260))
PRIMITIVES = {
    'npn': ('56b375b6effe5d5272a31d8c89eceaeb4d2d35a774561c3eb8fe578e51baac84',
            {'s': (490,9000), 'c': (5330,9000), 'b': (6070,9000), 'e': (9000,9000)}),
    'pnp': ('59e36ad406b03027054754627051686ea5a605f045d1a8f164e877a4da3008a9',
            {'c': (420,420), 'b': (1150,1150), 'e': (4200,4200)}),
}


def topology_digest(cell):
    return digest([(d['id'], d['kind'], d['model_ref'], d['nets'], d.get('params'), d.get('model_params'))
                   for d in cell['devices']])


class Layout:
    def __init__(self, project, cell):
        self.project, self.cell = project, cell
        self.x = 0
        self.access = []
        self.layers = {}
        self.primitives = {}
        tech = project['pdk']
        pairs = {(layer['gds'], layer['datatype']): layer for layer in tech['layers']}
        def layer_for(key, pair):
            if pair not in pairs:
                pairs[pair] = dict(name='bandgap_'+key, gds=pair[0], datatype=pair[1],
                                   color='#ad8bd4', width=0, space=0)
                tech['layers'].append(pairs[pair])
            return pairs[pair]
        for key, pair in MASKS.items():
            layer = layer_for(key, pair)
            layer['width'], layer['space'] = MINIMUMS.get(key, (0,0))
            self.layers[key] = layer['name']
        ls = self.layers
        tech['connectivity'] = dict(
            conductors=[ls[k] for k in ('m1','m2','m3','m4','fusetop')],
            vias=[[ls[a],ls[cut],ls[b]] for a,cut,b in
                  [('m1','via1','m2'), ('m2','via2','m3'), ('m3','via3','m4'), ('fusetop','via3','m4')]],
            via_blockers=[dict(conductor=ls['m3'], cut=ls['via3'], mask=ls['fusetop'])])
        tech['routing_conductors'] = [ls[k] for k in ('m1','m2','m3','m4')]
        labels = tech.setdefault('interoperability', {}).setdefault('port_layers', {})
        for key in ('m1','m2','m3','m4'):
            labels[ls[key]] = layer_for(key+'_label', (MASKS[key][0],10))['name']

    def box(self, layer, x, y, width, height, net='', owner=''):
        self.cell['shapes'].append(rect(self.layers[layer], x, y, width, height, owner, net))

    def wire(self, layer, x, y, end_x, end_y, net, width=500):
        if (x,y) != (end_x,end_y):
            self.cell['shapes'].append(dict(id=uid(), kind='path', layer=self.layers[layer],
                points=[[x,y],[end_x,end_y]], width=width, net=net, device_id='', generated_route=True))

    def via(self, level, x, y, net, pad=400):
        for layer, side, name in ((f'via{level}',260,''),(f'm{level}',pad,net),(f'm{level+1}',pad,net)):
            self.box(layer,x-side//2,y-side//2,side,side,name)

    def pin(self, part, key, layer, x, y):
        self.cell['layout_pins'].append(dict(id=uid(), device_id=part['id'], pin=key,
                                            layer=self.layers[layer], point=[x,y]))
        self.access.append((layer,x,y,part['nets'][key]))

    def contact(self, part, pin, x, y):
        self.box('contact',x-110,y-110,220,220,owner=part['id'])
        self.box('m1',x-200,y-200,400,400,part['nets'][pin],part['id'])
        self.pin(part,pin,'m1',x,y)

    def bipolar(self, part, polarity):
        if polarity not in self.primitives:
            directory = resource_root()/'examples/gf180-banba/layout/upstream'
            source = directory/(polarity+'_05p00x05p00.gds')
            if file_digest(source) != PRIMITIVES[polarity][0]:
                raise ValueError('The bundled GF180 bipolar layout has changed.')
            db = kdb()
            gds = db.Layout()
            gds.read(str(source))
            top = gds.top_cell()
            self.primitives[polarity] = (gds, top, db)
        gds, top, db = self.primitives[polarity]
        x = self.x
        for index in gds.layer_indexes():
            info = gds.get_info(index)
            if info.datatype == 10:
                continue
            key = next(k for k, mask in MASKS.items() if mask == (info.layer, info.datatype))
            for polygon in db.Region(top.begin_shapes_rec(index)).merged().each():
                shape = shape_from_polygon(polygon.transformed(db.Trans(x,0)), self.layers[key])
                shape['device_id'] = part['id']
                self.cell['shapes'].append(shape)
        for pin, (dx,y) in PRIMITIVES[polarity][1].items():
            self.pin(part,pin,'m1',x+dx,y)
        self.x += 23000 if polarity == 'npn' else 14500

    def mos(self, part):
        from .gf180_layout import mos
        from .sky130_layout import resolved
        element = resolved(self.project, self.cell['id'], part)
        # The historical OTA uses 24 µm. This device fits the same contacted
        # single-finger geometry as the Banba layout at its actual total width.
        w, l = self.size(part['params'])
        if w <= 10000:
            data = mos(self.project['pdk'],element,self.x+4000,0)
            self.cell['shapes'].extend(data['shapes'])
            for pin in data['pins']:
                px,py = pin['point']
                self.pin(part,pin['pin'],'m1',px,py)
            self.x += l+14000
            return
        if w > 24000 or l < 1000:
            raise ValueError('Use a single contacted GF180 MOS finger up to 24 µm wide.')
        x = self.x+4000
        body, diff = ('nplus','pplus') if part['kind']=='PMOS' else ('pplus','nplus')
        owner = part['id']
        cy = 5*round(w/10)
        self.box('active',x-800,0,l+1600,w,owner=owner)
        self.box(diff,x-1100,-300,l+2200,w+600,owner=owner)
        self.box('poly',x,-1100,l,w+1400,owner=owner)
        self.box('active',x-2850,cy-400,800,800,owner=owner)
        self.box(body,x-3050,cy-600,1200,1200,owner=owner)
        if part['kind']=='PMOS':
            self.box('nwell',x-3550,-1600,l+5150,w+2700,owner=owner)
        for key,px,py in [('s',x-500,cy),('d',x+l+500,cy),('g',x+5*round(l/10),-800),('b',x-2450,cy)]:
            self.contact(part,key,px,py)
            if key in ('s','d'):
                self.box('m1',px-200,0,400,w,part['nets'][key],owner)
                for yy in range(250,w-249,500):
                    if abs(yy-py)>=470:
                        self.box('contact',px-110,yy-110,220,220,owner=owner)
        self.x += l+14000

    @staticmethod
    def size(params):
        dims = [scalar(params[key])*1e9 for key in ('w','l')]
        snapped = [5*round(d/5) for d in dims]
        if any(abs(a-b)>1e-6 for a,b in zip(dims,snapped)):
            raise ValueError('Snap the layout dimensions to the GF180 5 nm grid.')
        return snapped

    def resistor(self, part):
        w,l = self.size(part['model_params'])
        if not 800 <= w <= 4000 or not 1000 <= l <= 100000:
            raise ValueError('Use 0.8–4 µm resistor widths and 1–100 µm series sections.')
        x = self.x+4000
        owner = part['id']
        self.box('poly',x-640,0,l+1280,w,owner=owner)
        self.box('resistor_id',x,0,l,w,owner=owner)
        self.box('resistor',x-1040,-400,l+2080,w+800,owner=owner)
        self.box('salicide_block',x-100,-280,l+200,w+560,owner=owner)
        for xx in (x-820,x+l):
            self.box('pplus',xx,-180,820,w+360,owner=owner)
        self.box('active',x-2850,0,700,w,owner=owner)
        self.box('pplus',x-3050,-200,1100,w+400,owner=owner)
        for pin,px in [('p',x-460),('m',x+l+460),('b',x-2500)]:
            self.contact(part,pin,px,5*round(w/10))
        self.x += l+9000

    def mim(self, part):
        w,h = self.size(part['model_params'])
        if min(w,h)<5000 or w*h>10000*1e6:
            raise ValueError('Use MIM tiles between 5 µm per side and 10,000 µm².')
        x = self.x+4000
        a,b = part['nets']['g'], part['nets']['b']
        owner = part['id']
        self.box('m3',x-600,-600,w+1200,h+1200,b,owner)
        self.box('fusetop',x,0,w,h,a,owner)
        self.box('m4',x,0,w,h,a,owner)
        self.box('mim_id',x-600,-600,w+1200,h+1200,owner=owner)
        self.box('mim_long',x,0,w,100,owner=owner)
        for ix in range(4):
            for iy in range(4):
                vx=x+1000+5*round(ix*(w-2000)/15)
                vy=1000+5*round(iy*(h-2000)/15)
                self.box('via3',vx-130,vy-130,260,260,owner=owner)
        bx = x-2500
        self.box('m3',bx-600,1400,3100,1200,b,owner)
        self.via(3,bx,2000,b,pad=1200)
        self.pin(part,'b','m4',bx,2000)
        self.pin(part,'g','m4',x+5*round(w/10),5*round(h/10))
        self.x += w+9000

    def route(self):
        nets = sorted({n for _,_,_,n in self.access})
        tracks = {n:-6000-2400*i for i,n in enumerate(nets)}
        ends = {n:-4000 for n in nets}
        for layer,x,y,net in self.access:
            level = 4 if layer=='m4' else 2
            if layer=='m1':
                self.via(1,x,y,net)
            dest = tracks[net]
            self.wire(f'm{level}',x,y,x,dest,net,500 if level==4 else 400)
            self.via(3 if level==4 else 2,x,dest,net,pad=500 if level==4 else 400)
            ends[net] = max(ends[net],x)
        for net,y in tracks.items():
            self.wire('m3',-4000,y,ends[net]+1000,y,net,1000 if net in ('VDD','VSS') else 600)
            if net in self.cell['ports']:
                assign_port(self.project,self.cell['id'],net,self.layers['m3'],[-4000,y])


def generate(p, replace=False):
    cell = core_cell(p)
    if cell['shapes'] and not replace:
        raise ValueError('Review the existing layout before replacing its geometry.')
    for key in ('shapes','layout_pins','layout_ports','layout_texts','layout_instances','pdk_layouts','analog_constraints'):
        cell[key] = []
    cell['layout_label_mode'] = 'explicit'
    layout = Layout(p,cell)
    # Place the small junction between the two halves of the eight-unit row.
    large = [d for d in cell['devices'] if d['name'].startswith('Q2_')]
    grouped = [*large[:4],*[d for d in cell['devices'] if d['name']=='Q1'],*large[4:]] if len(large)==8 else []
    for part in [*grouped,*[d for d in cell['devices'] if d not in grouped]]:
        model = part['model_ref']['device']
        if part['kind'] in ('NMOS','PMOS'):
            layout.mos(part)
        elif '/ppolyf_u_1k.' in model:
            layout.resistor(part)
        elif '/cap_mim_analog.' in model:
            layout.mim(part)
        elif '/npn_05p00x05p00.' in model or '/pnp_05p00x05p00.' in model:
            layout.bipolar(part,model.split('/')[1][:3])
        else:
            raise ValueError('The bandgap layout does not support ' + part['name'] + ' with its current binding.')
    layout.route()
    if grouped:
        one = grouped[4]['id']
        eight = [part['id'] for part in large]
        cell['analog_constraints'].append(dict(id=uid(), name='Junction array centroid', kind='common_centroid',
                                               members=[one,*eight], groups=[[one],eight]))
    cell['student_layout_digest'] = topology_digest(cell)
    return p


def check(p):
    from .analog_constraints import findings
    from .layout import drc
    from .physical import connectivity

    cell = core_cell(p)
    if not cell['shapes'] or cell.get('student_layout_digest')!=topology_digest(cell):
        raise ValueError('Generate the layout from the current component dimensions and connections.')
    if {port['name'] for port in cell.get('layout_ports',[])}!=set(cell['ports']):
        raise ValueError('Give each circuit port a matching layout port.')
    conn = connectivity(p, cell['id'])
    geometry = drc(p, cell['id'])
    constraint = findings(p, cell['id'])
    if conn['issues'] or geometry or constraint:
        first = (conn['issues']+geometry+constraint)[0]
        raise ValueError('Review layout findings before continuing. '+str(first.get('message', first)))
    return dict(layout_cell=cell['name'], devices=len(cell['devices']), terminals=len(cell['layout_pins']),
                nets=len(conn['net_regions']), scope='Local geometry, linked terminals and placement constraints')
