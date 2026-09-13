"""Grid-snapped spiral centerlines and explicitly scoped DC estimates.

Mohan et al., JSSC 34(10), 1999, eq. (2), Table II supplies the regular
spiral coefficients. Rectangles use a thin-strip Neumann partial-inductance
integral, with geometric mean distance exp(-3/2)*width; no square fit is used.
Neither model includes substrate, skin effect, proximity effect or return leads.
"""
import math

SHAPES = ('square', 'rectangle', 'hexagon', 'octagon', 'circle')
COEFFICIENTS = {
    'square': (1.27, 2.07, .18, .13),
    'hexagon': (1.09, 2.23, 0., .17),
    'octagon': (1.07, 2.29, 0., .19),
    'circle': (1., 2.46, 0., .20),
}
MU0 = 4 * math.pi * 1e-7


def current_sheet(shape, turns, inner_nm, outer_nm):
    c1, c2, c3, c4 = COEFFICIENTS[shape]
    average = (outer_nm + inner_nm) * .5e-9
    rho = (outer_nm - inner_nm) / (outer_nm + inner_nm)
    return MU0 * turns**2 * average * c1 / 2 * (
        math.log(c2 / rho) + c3 * rho + c4 * rho**2)


def rectangular_inductance(points, width):
    """Analytic double integral for finite, axis-aligned filament segments.

    GMD regularizes the self term for a uniform-current thin strip. Opposing
    segments contribute negative mutual terms; perpendicular terms vanish.
    Dimensions enter in nm and the returned partial inductance is in H.
    """
    segments = []
    for a, b in zip(points, points[1:]):
        axis = 0 if a[1] == b[1] else 1
        if a[1-axis] != b[1-axis]:
            raise ValueError('Rectangular estimate requires orthogonal segments.')
        lo, hi = sorted((a[axis], b[axis]))
        if hi > lo:
            segments.append((axis, a[1-axis], lo, hi, 1 if b[axis] > a[axis] else -1))
    integral = 0.
    for i, (axis, offset, a, b, direction) in enumerate(segments):
        for j in range(i, len(segments)):
            other, location, c, d, sign = segments[j]
            if axis != other:
                continue
            distance = math.hypot(location-offset, math.exp(-1.5)*width if i == j else 0.)
            # Collinear non-overlapping segments still have finite mutual terms.
            def primitive(x):
                if distance == 0:
                    return abs(x) * (math.log(abs(x)) - 1) if x else 0.
                return x * math.asinh(x/distance) - math.hypot(x, distance)
            value = primitive(b-c)-primitive(a-c)-primitive(b-d)+primitive(a-d)
            integral += value * direction * sign * (1 if i == j else 2)
    return MU0 / (4*math.pi) * integral * 1e-9


def centerline(spec, grid):
    """Return winding points, P/N positions, dimensions and estimate metadata.

    Legacy squares retain their exact geometry. Regular polygons use a slowly
    contracting sequence of support lines; circles sample an Archimedean spiral
    at 128 segments/turn. Their inner opening is the minimum radial/normal
    clearance, and their outer diameter is computed from the actual centerline.
    """
    shape = spec['shape']; n = spec['turns']; w = spec['width']
    pitch = w + spec['spacing']; inner = spec['inner']; lead = spec['lead']
    snap = lambda x: round(x/grid)*grid
    if shape in ('square', 'rectangle'):
        inner_y = spec.get('inner_y', inner) if shape == 'rectangle' else inner
        outer_x = inner + 2*n*w + 2*(n-1)*spec['spacing']
        outer_y = inner_y + 2*n*w + 2*(n-1)*spec['spacing']
        rx, ry = (outer_x-w)//2, (outer_y-w)//2
        p = [-rx, -ry-lead]; points = [p, [-rx, -ry]]
        for i in range(n):
            left, right = -rx+i*pitch, rx-i*pitch
            bottom, top = -ry+i*pitch, ry-i*pitch
            points.extend([[right,bottom], [right,top], [left,top], [left,bottom+pitch]])
        q = [-rx-lead, points[-1][1]]
        estimate = (current_sheet(shape,n,inner,outer_x) if shape == 'square'
                    else rectangular_inductance(points[1:],w))
        model = 'mohan-current-sheet-square-1' if shape == 'square' else 'neumann-thin-strip-rectangle-1'
    else:
        sides = {'hexagon':6, 'octagon':8, 'circle':128}[shape]
        # Clearance margin bounds grid quantization and radial pitch projection.
        step = pitch + 4*grid
        inner_radius = inner/2+w/2
        if shape == 'circle':
            # Radial separation is slightly greater than normal separation.
            step = math.ceil(step*math.sqrt(1+(pitch/(2*math.pi*inner_radius))**2)/grid)*grid
            radius = inner_radius+n*step
            coil = []
            for i in range(n*sides+1):
                angle = -math.pi/2 + i*2*math.pi/sides
                r = radius - step*i/sides
                coil.append([snap(r*math.cos(angle)), snap(r*math.sin(angle))])
        else:
            radius = inner_radius+n*step
            def support(i):
                angle = -math.pi/2 + i*2*math.pi/sides
                return math.cos(angle), math.sin(angle), radius-step*i/sides
            coil = []
            for i in range(n*sides+1):
                ax,ay,a = support(i-1); bx,by,b = support(i)
                determinant = ax*by-ay*bx
                coil.append([snap((a*by-ay*b)/determinant), snap((ax*b-a*bx)/determinant)])
        if shape == 'circle':
            dx,dy=coil[1][0]-coil[0][0],coil[1][1]-coil[0][1]
            length=math.hypot(dx,dy)
            p=[snap(coil[0][0]-lead*dx/length),snap(coil[0][1]-lead*dy/length)]
        else:p = [coil[0][0], coil[0][1]-lead]
        points = [p] + coil
        q = [snap(min(pt[0] for pt in coil)-lead), coil[-1][1]]
        outer_x = max(pt[0] for pt in coil)-min(pt[0] for pt in coil)+w
        outer_y = max(pt[1] for pt in coil)-min(pt[1] for pt in coil)+w
        # Across-flat bounding dimensions (diameter for the circular recipe).
        estimate = current_sheet(shape,n,inner,(outer_x+outer_y)/2)
        model = 'mohan-current-sheet-'+shape+'-1'
    return dict(points=points,p=p,q=q,outer_x_nm=outer_x,outer_y_nm=outer_y,
                estimate_h=estimate,model=model)
