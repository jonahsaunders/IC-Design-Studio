"""Preserve GF180 antenna-diode CDL geometry in KLayout's SPICE syntax.

This adapter covers positional diode records in the independent GF180 9-track
cell CDL. It does not modify the foundry source, change device values, normalize
other elements, or qualify a device or LVS deck. Unsupported diode records fail.
"""
from decimal import Decimal, DecimalException, localcontext
import math
import re


MODELS = frozenset(('diode_nd2ps_06v0', 'diode_pd2nw_06v0'))
SCALE = {'': '1', 't': '1e12', 'g': '1e9', 'meg': '1e6', 'k': '1e3',
         'm': '1e-3', 'u': '1e-6', 'n': '1e-9', 'p': '1e-12', 'f': '1e-15'}
NUMBER = re.compile(r'([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(meg|[tgkmunpf])?', re.I)

# The native LVS engine runs Ruby. Keep this small guard explicit so the native
# controls can exercise the very same code installed in a staged diagnostic deck.
RUBY_GEOMETRY_GUARD = '''def icstudio_gf180_diode_geometry(nl)
  classes = nl.each_device_class.select { |c| ["diode_nd2ps_06v0", "diode_pd2nw_06v0"].include?(c.name.downcase) }
  classes.each do |c|
    raise "Expected a diode class for #{c.name}" unless c.is_a?(RBA::DeviceClassDiode)
    raise "Unexpected diode parameters" unless c.parameter_definitions.map(&:name).sort == ["A", "P"]
    raise "Unexpected diode terminals" unless c.terminal_definitions.map(&:name).sort == ["A", "C"]
    raise "Custom diode comparer requires review" unless c.equal_parameters.nil?
  end
  classes.each do |c|
    c.enable_parameter("A", true)
    c.enable_parameter("P", true)
  end
  classes.map(&:name).sort
end
'''


def _positive_si(token):
    match = NUMBER.fullmatch(token)
    if not match:
        raise ValueError('Diode geometry requires a positive numeric SI value.')
    try:
        with localcontext() as context:
            context.prec = max(50, len(match[1]))
            value = Decimal(match[1]) * Decimal(SCALE[(match[2] or '').lower()])
        actual = float(value)
    except (DecimalException, OverflowError):
        raise ValueError('Diode geometry must be finite and representable.') from None
    if not math.isfinite(actual) or actual <= 0:
        raise ValueError('Diode geometry must be positive, finite and representable.')
    return value


def _groups(text):
    """Retain every original byte of unrelated physical lines."""
    group = []
    start = 0
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        if line.lstrip().startswith('+'):
            if not group or not group[0].strip() or group[0].lstrip().startswith('*'):
                raise ValueError('Orphan CDL continuation line.')
            group.append(line)
        else:
            if group:
                yield start, group
            start, group = number, [line]
    if group:
        yield start, group


def normalize(text):
    """Return (text, changes), preserving diode nodes, model, A, P and M.

    Supported positional form: Dname anode cathode model area perimeter $m=N.
    The explicit A=... P=... M=N form is accepted unchanged after validation.
    Diodes must occur in named subcircuits. Geometry is in SI units, including
    SPICE suffixes. Multiplicity must be an explicit positive integer.
    """
    output, changes = [], []
    subcircuit = None
    names = set()
    for start, group in _groups(text):
        original = ''.join(group)
        logical = group[0].strip() + ''.join(' ' + line.lstrip()[1:].strip() for line in group[1:])
        fields = logical.split()
        if not fields or fields[0].startswith('*'):
            output.append(original)
            continue
        if fields[0].lower() == '.subckt':
            if subcircuit is not None or len(fields) < 2:
                raise ValueError('Diode CDL requires non-nested named subcircuits.')
            subcircuit, names = fields[1], set()
        elif fields[0].lower() == '.ends':
            if subcircuit is None or len(fields) > 2 or (len(fields) == 2 and fields[1].lower() != subcircuit.lower()):
                raise ValueError('Unmatched CDL subcircuit end.')
            subcircuit = None
        elif fields[0][0].lower() == 'd':
            if subcircuit is None:
                raise ValueError('A diode record must be inside a named subcircuit.')
            if len(fields) != 7 or len(fields[0]) < 2:
                raise ValueError('Require two diode nodes, model, area, perimeter and explicit multiplicity.')
            name, anode, cathode, model = fields[:4]
            if model.lower() not in MODELS:
                raise ValueError('Unsupported GF180 diode model: ' + model)
            if name.lower() in names:
                raise ValueError('Duplicate diode instance in subcircuit: ' + name)
            names.add(name.lower())
            positional = '=' not in fields[4] and '=' not in fields[5]
            if positional:
                area, perimeter = fields[4:6]
                multiplicity = re.fullmatch(r'\$m=(\d+)', fields[6], re.I)
            else:
                params = {}
                for token in fields[4:]:
                    pair = token.split('=')
                    if len(pair) != 2 or pair[0].upper() not in ('A', 'P', 'M') or pair[0].upper() in params:
                        raise ValueError('Require exactly A, P and M for named diode geometry.')
                    params[pair[0].upper()] = pair[1]
                if set(params) != {'A', 'P', 'M'}:
                    raise ValueError('Require exactly A, P and M for named diode geometry.')
                area, perimeter = params['A'], params['P']
                multiplicity = re.fullmatch(r'(\d+)', params['M'])
            if not multiplicity or int(multiplicity[1]) < 1:
                raise ValueError('Diode multiplicity must be an explicit positive integer.')
            m = int(multiplicity[1])
            a, p = _positive_si(area), _positive_si(perimeter)
            try:
                native = (float(a * m * Decimal('1e12')), float(p * m * Decimal('1e6')))
            except (DecimalException, OverflowError):
                raise ValueError('Diode geometry is not representable in KLayout units.') from None
            if not all(math.isfinite(value) and value > 0 for value in native):
                raise ValueError('Diode geometry is not representable in KLayout units.')
            if positional:
                after = ' '.join((name, anode, cathode, model, 'A=' + area, 'P=' + perimeter, 'M=' + multiplicity[1]))
                ending = '\r\n' if group[-1].endswith('\r\n') else '\n' if group[-1].endswith('\n') else ''
                output.append(after + ending)
                changes.append(dict(subcircuit=subcircuit, line=start, last_line=start + len(group) - 1,
                                    before=logical, after=after, instance=name, anode=anode, cathode=cathode,
                                    model=model, area_si=str(a), perimeter_si=str(p), multiplicity=m))
                continue
        output.append(original)
    if subcircuit is not None:
        raise ValueError('Unterminated CDL subcircuit.')
    return ''.join(output), changes


def enable_geometry(netlist):
    """Require A and P in comparisons of the supported diode classes.

    KLayout marks diode A/P as secondary by default. Syntax conversion alone
    therefore does not establish that LVS checks dimensions. No geometry value,
    tolerance, terminal mapping or other device class is changed here.
    """
    import klayout.db as k
    classes = [c for c in netlist.each_device_class() if c.name.lower() in MODELS]
    for cls in classes:
        if not isinstance(cls, k.DeviceClassDiode):
            raise ValueError('Expected a diode class for ' + cls.name)
        if {p.name for p in cls.parameter_definitions()} != {'A', 'P'}:
            raise ValueError('Unexpected diode parameters for ' + cls.name)
        if {t.name for t in cls.terminal_definitions()} != {'A', 'C'}:
            raise ValueError('Unexpected diode terminals for ' + cls.name)
        if cls.equal_parameters is not None:
            raise ValueError('An existing custom diode parameter comparer requires separate review.')
    for cls in classes:
        cls.enable_parameter('A', True)
        cls.enable_parameter('P', True)
    return sorted(c.name for c in classes)
