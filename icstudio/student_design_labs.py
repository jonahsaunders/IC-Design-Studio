"""Bounded design exercises. Generic geometry checks are not foundry signoff."""
import math

from .model import device, example, validate


def mos_lab(kind):
    p = example('empty'); p['name'] = 'gm/ID design bench'
    gate = '.85' if kind == 'gmid-bias' else '.65'
    drain = '.1' if kind == 'gmid-headroom' else '1'
    width = '2u' if kind == 'gmid-size' else '10u'
    p['cells'][0]['devices'] = [
        device('V', 'VG', 180, 360, value=gate, nets={'p':'g','n':'0'}),
        device('V', 'VD', 180, 180, value=drain, nets={'p':'d','n':'0'}),
        device('NMOS', 'M1', 500, 270, nets={'d':'d','g':'g','s':'0','b':'0'},
               params={'w':width,'l':'1u','vto':'.45','kp':'100u','lambda':'.02'})]
    p['analysis']['type'] = 'op'
    return validate(p)


def layout_lab(kind):
    from .layout import rect
    p = example('empty'); p['name'] = 'Layout lab · ' + kind
    if kind in ('layout-width', 'layout-spacing'):
        shapes = [rect('metal1', 0, 0, 2000, 100 if kind == 'layout-width' else 200, net='a'),
                  rect('metal1', 0, 300 if kind == 'layout-spacing' else 600, 2000, 200, net='b')]
    elif kind == 'layout-via':
        shapes = [rect('metal1', 0, 0, 500, 500, net='out'),
                  rect('metal2', 0, 0, 500, 500, net='out'),
                  rect('via1', 400, 175, 150, 150, net='out')]
    elif kind == 'layout-centroid':
        shapes = [rect('metal1', x, 0, 400, 400, net=net)
                  for x, net in zip((0, 800, 1600, 2400), ('a','a','b','b'))]
    else:
        raise ValueError('Unknown layout exercise.')
    for i, shape in enumerate(shapes): shape['id'] = 'lab_shape_' + str(i)
    p['cells'][0]['shapes'] = shapes
    return validate(p)


def check_layout(project, exercise):
    """Measure retained rectangles against fixed educational requirements.

    Do not use editable PDK minima, net labels alone, or a count of shapes as
    proof of a repair. All fixture shapes must survive, on the original layer.
    """
    from .layout import drc
    from .model import clone
    reference = layout_lab(exercise)
    expected = reference['cells'][0]['shapes']
    cell = next(c for c in project['cells'] if c['id'] == project['top'])
    shapes = cell['shapes']
    def require(ok, message):
        if not ok: raise ValueError(message)
    require(len(shapes) == len(expected) and not cell['devices'] and len(project['cells']) == 1,
            'Keep the original exercise rectangles in one cell; repair them without adding or deleting shapes.')
    by_id = {s['id']:s for s in shapes}; boxes = []
    for original in expected:
        s = by_id.get(original['id'])
        require(s is not None and s['kind'] == 'rect' and s['layer'] == original['layer'] and s.get('net') == original['net'],
                'Keep each original rectangle, layer and net label. Repair its geometry.')
        xs, ys = zip(*s['points']); box = (min(xs), min(ys), max(xs), max(ys))
        require(box[2] > box[0] and box[3] > box[1], 'Rectangles need positive width and height.')
        boxes.append(box)
    # Run the real generic geometry checker with the fixed teaching deck.
    fixed = clone(project); fixed['pdk'] = reference['pdk']
    issues = drc(fixed, fixed['top'])
    require(not issues, 'Generic geometry check: ' + '; '.join(i['message'] for i in issues[:3]))
    if exercise in ('layout-width', 'layout-spacing'):
        a, b = boxes
        require(all(x[2]-x[0] == 2000 and x[3]-x[1] >= 200 for x in boxes),
                'Keep both routes 2 µm long and at least 0.20 µm thick.')
        require(a[0] == b[0] and b[1]-a[3] >= 200,
                'Keep the routes aligned in X with at least 0.20 µm vertical edge spacing.')
        measurements = {'route_thickness_nm':a[3]-a[1], 'edge_spacing_nm':b[1]-a[3]}
    elif exercise == 'layout-via':
        via = boxes[2]
        require(via[2]-via[0] == via[3]-via[1] == 150, 'Keep the via cut 0.15 × 0.15 µm.')
        margins = [min(via[0]-b[0], via[1]-b[1], b[2]-via[2], b[3]-via[3]) for b in boxes[:2]]
        require(min(margins) >= 75, 'Enclose the via by at least 0.075 µm on all four sides in BOTH metal layers.')
        measurements = {'metal1_enclosure_nm':margins[0], 'metal2_enclosure_nm':margins[1]}
    else:
        require(all(b[2]-b[0] == b[3]-b[1] == 400 for b in boxes), 'Keep four equal 0.40 × 0.40 µm unit tiles.')
        centers = [((b[0]+b[2])/2, (b[1]+b[3])/2) for b in boxes]
        a = tuple((centers[0][i]+centers[1][i])/2 for i in (0,1))
        b = tuple((centers[2][i]+centers[3][i])/2 for i in (0,1))
        require(all(math.isclose(x,y,abs_tol=.01) for x,y in zip(a,b)),
                f'Group centers differ: A {a} nm, B {b} nm. Move tiles into an ABBA arrangement.')
        # A merged/overlapped tile arrangement must not pass as a centroid.
        for i, left in enumerate(boxes):
            for right in boxes[i+1:]:
                dx = max(left[0]-right[2], right[0]-left[2], 0)
                dy = max(left[1]-right[3], right[1]-left[3], 0)
                require(max(dx,dy) >= 200, 'Keep at least 0.20 µm separation between unit tiles.')
        measurements = {'centroid_a_nm':a, 'centroid_b_nm':b}
    return dict(measurements=measurements, deck='fixed generic teaching rules',
                scope='Exercise geometry only; no device extraction, connectivity LVS or foundry signoff.')


# Reference RTL and independently specified benches. Starters below inject one
# fault into RTL only; the normal digital checkpoint protects the reference bench.
DIGITAL_LABS = {
    'mux_repair': (
        'input wire a,b,select, output reg y',
        'always @* begin if(select) y=b; else y=a; end',
        'reg a,b,select; wire y; integer i,j;', 'a,b,select,y',
        '''for(j=0;j<2;j=j+1) for(i=0;i<8;i=i+1) begin
          {select,b,a}=(j==0 ? i : 7-i); #2;
          if(y !== (select ? b : a)) $fatal(1,"Combinational output retained old state");
        end'''),
    'saturating_sum': (
        'input wire clk,reset,valid, input wire [3:0] data, output reg [3:0] sum',
        '''wire [4:0] total={1'b0,sum}+{1'b0,data};
        always @(posedge clk) if(reset) sum<=0;
        else if(valid) sum <= total > 5'd15 ? 4'd15 : total[3:0];''',
        'reg clk=0,reset=1,valid=0; reg [3:0] data=0; wire [3:0] sum; integer i,expected; always #5 clk=~clk;',
        'clk,reset,valid,data,sum',
        '''repeat(2) @(negedge clk); reset=0; expected=0;
        for(i=0;i<30;i=i+1) begin
          valid=(i%4!=0); data=(i%16); reset=(i==14);
          if(reset) expected=0;
          else if(valid) begin expected=expected+data; if(expected>15) expected=15; end
          @(posedge clk); #1; if(sum !== expected[3:0]) $fatal(1,"Saturation, hold or reset mismatch");
          @(negedge clk);
        end'''),
    'pipeline_valid': (
        'input wire clk,reset,valid_in, input wire [3:0] data, output reg valid_out, output reg [3:0] result',
        '''reg [3:0] stage; reg stage_valid;
        always @(posedge clk) begin
          if(reset) begin stage<=0; stage_valid<=0; result<=0; valid_out<=0; end
          else begin stage<=data+4'd1; stage_valid<=valid_in;
            result<=stage; valid_out<=stage_valid; end
        end''',
        'reg clk=0,reset=1,valid_in=0; reg [3:0] data=0; wire valid_out; wire [3:0] result; integer i; reg prev_valid; reg [3:0] prev_data; always #5 clk=~clk;',
        'clk,reset,valid_in,data,valid_out,result',
        '''repeat(2) @(negedge clk); reset=0; prev_valid=0; prev_data=0;
        for(i=0;i<36;i=i+1) begin
          valid_in=(i%4!=0); data=i%16; reset=(i==17);
          @(posedge clk); #1;
          if(reset) begin
            if(valid_out!==0) $fatal(1,"Reset must flush validity");
            prev_valid=0; prev_data=0;
          end else begin
            if(valid_out !== prev_valid) $fatal(1,"Valid latency or bubble mismatch");
            if(prev_valid && result !== prev_data) $fatal(1,"Pipeline data ordering mismatch");
            prev_valid=valid_in; prev_data=data+4'd1;
          end
          @(negedge clk);
        end'''),
}

FAULTS = {
    'mux_repair': ('else y=a;', ''),
    'saturating_sum': ("total > 5'd15 ? 4'd15 : total[3:0]", 'total[3:0]'),
    'pipeline_valid': ('valid_out<=stage_valid;', 'valid_out<=valid_in;'),
}


def faulty_digital(kind):
    from .student_projects import digital_project
    p = digital_project(kind)
    old, new = FAULTS[kind]
    source = p['cells'][0]['digital']['files'][0]
    source['text'] = source['text'].replace(old, new)
    return p
