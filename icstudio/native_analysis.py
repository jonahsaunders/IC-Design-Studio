"""Independent graphical analyses of a native circuit with embedded models."""
import re
from .model import clone, scalar, NET
from .native_spice import netlist, render

ANALYSES = ('op', 'tran', 'dc', 'ac', 'noise')
LIB = re.compile(r'^(\s*\.lib\s+)(?:"(models/[a-f0-9]{24}\.spice)"|\'(models/[a-f0-9]{24}\.spice)\'|(models/[a-f0-9]{24}\.spice))\s+(\S+)\s*$', re.I)


def circuit_text(text):
    """Remove saved analyses, retaining device/model and netlist configuration."""
    output = []; inside = False; skip_continuation = False
    for line in text.splitlines():
        word = line.strip().split(maxsplit=1)[0].casefold() if line.strip() else ''
        if word == '.control':
            if inside: raise ValueError('Nested simulation control blocks are invalid.')
            inside = True; continue
        if word == '.endc':
            if not inside: raise ValueError('Unmatched simulation control block end.')
            inside = False; continue
        if inside: continue
        if word == '+' and skip_continuation: continue
        skip_continuation = word in ('.op', '.tran', '.dc', '.ac', '.noise', '.tf', '.pz', '.sens', '.disto', '.four', '.measure', '.meas', '.save', '.print', '.plot', '.temp', '.end')
        if not skip_continuation: output.append(line)
    if inside: raise ValueError('Unclosed simulation control block.')
    return '\n'.join(output) + '\n'


def sources(p, cid=None):
    from .interchange import spice_name
    c = next(c for c in p['cells'] if c['id'] == (cid or p['top']))
    out = []
    for d in c['devices']:
        info = d.get('native_spice')
        if info and info['type'] == 'device' and d['kind'] != 'X':
            name = render(d).split()[0]
            if name[0].upper() in ('V', 'I'): out.append((d['name'], name, name[0].upper()))
        elif not info and d['kind'] in ('V', 'I'): out.append((d['name'], spice_name(d), d['kind']))
    return out


def dc_parameter(d, value=None):
    """Expose a source's DC level while preserving its AC excitation."""
    info=d.get('native_spice',{})
    if info.get('type')!='device' or d['kind']=='X' or render(d)[0].upper() not in ('V','I'):raise ValueError('Not an independent source.')
    text=info.get('parameters',{}).get('value','')
    m=re.fullmatch(r'(\s*(?:DC\s+)?)([^\s]+)(\s+(?:AC\s+[^\s]+(?:\s+[^\s]+)?)\s*|\s*)',text,re.I)
    if not m:raise ValueError('This source uses a waveform or expression; edit its program parameters.')
    old=scalar(m[2])
    if value is not None:
        info['parameters']['value']=m[1]+str(scalar(value))+m[3]
        d.setdefault('symbol_context',{})['value']=info['parameters']['value']
    return old


def corner_sections(p):
    """Only offer sections actually present in every referenced model library."""
    text = '\n'.join(s for c in p['cells'] for s in c.get('spice_statements', []))
    text += '\n' + '\n'.join(d['native_spice']['text'] for c in p['cells'] for d in c['devices'] if d.get('native_spice', {}).get('type') == 'program')
    sets = []
    for line in circuit_text(text).splitlines():
        m = LIB.fullmatch(line)
        if not m: continue
        path = next(v for v in m.groups()[1:4] if v)
        asset = p['spice']['assets'].get(path[7:-6])
        if not asset: raise ValueError('Missing embedded library: ' + path)
        sections = {m[1] for m in re.finditer(r'^\s*\.lib\s+([A-Za-z0-9_.-]+)\s*$', asset['text'], re.M | re.I)}
        sets.append(sections)
    return sorted(set.intersection(*sets)) if sets else []


def validate_settings(p, cid, s):
    typ = s.get('type')
    if typ not in ANALYSES: raise ValueError('Choose operating point, transient, DC, AC or noise.')
    if scalar(s.get('temperature', 27)) <= -273.15: raise ValueError('Temperature must exceed absolute zero.')
    if typ == 'tran':
        step, stop = scalar(s['step']), scalar(s['stop'])
        if not 0 < step <= stop or stop / step > 20000: raise ValueError('Use a positive time step and at most 20,000 steps.')
    if typ == 'dc':
        delta = scalar(s['dc_stop']) - scalar(s['dc_start']); step = scalar(s['dc_step'])
        if not step or not 0 <= delta / step <= 5000: raise ValueError('Use at most 5,001 DC points and a step toward the stop value.')
    if typ in ('ac', 'noise'):
        if not 0 < scalar(s['start']) < scalar(s['end']) or not 2 <= int(s['points']) <= 1000: raise ValueError('Use increasing positive frequencies and 2–1,000 points per decade.')
    if typ in ('dc', 'noise'):
        source = next((v for v in sources(p, cid) if v[0] == s.get('noise_source', s.get('source'))), None)
        if not source or typ == 'noise' and source[2] != 'V': raise ValueError('Choose an independent source in this cell; noise requires a voltage source.')
    if typ == 'noise' and not NET.fullmatch(s.get('output', '')): raise ValueError('Enter the output net for the noise analysis.')
    corner = s.get('corner', 'nominal')
    if corner != 'nominal' and corner not in corner_sections(p): raise ValueError('This corner is not a common section in the embedded libraries: ' + corner)


def deck(p, cid, settings, directory):
    validate_settings(p, cid, settings)
    q = clone(p); q['top'] = cid
    text = circuit_text(netlist(q, directory)); typ = settings['type']; corner = settings.get('corner', 'nominal')
    if corner != 'nominal':
        text = '\n'.join(LIB.sub(lambda m: m[1] + '"' + next(v for v in m.groups()[1:4] if v) + '" ' + corner, line) for line in text.splitlines()) + '\n'
    s = settings; command = '.op'
    if typ == 'tran': command = f'.tran {scalar(s["step"]):.12g} {scalar(s["stop"]):.12g}'
    if typ in ('dc', 'noise'):
        source = next(v[1] for v in sources(p, cid) if v[0] == s.get('noise_source', s.get('source')))
        if typ == 'dc': command = f'.dc {source} {scalar(s["dc_start"]):.12g} {scalar(s["dc_stop"]):.12g} {scalar(s["dc_step"]):.12g}'
        else: command = f'.noise v({s["output"]}) {source} dec {int(s["points"])} {scalar(s["start"]):.12g} {scalar(s["end"]):.12g}'
    if typ == 'ac': command = f'.ac dec {int(s["points"])} {scalar(s["start"]):.12g} {scalar(s["end"]):.12g}'
    aliases = {}; vectors = []
    cell = next(c for c in p['cells'] if c['id'] == cid)
    for d in cell['devices']:
        if d.get('model_ref'):
            from .catalog_migration import emit
            alias=emit(d,p['pdk']).split()[0];aliases[alias.casefold()]=d['name']
            if alias[0].upper()=='M':vectors+=['@'+alias+'['+k+']' for k in ('id','gm','vgs','vds','vdsat')]
        if d.get('native_spice', {}).get('type') == 'device' and d['kind'] != 'X':
            alias = render(d).split()[0]; aliases[alias.casefold()] = d['name']
            # Subcircuit models have no portable internal MOS path; never invent one.
            if alias[0].upper() == 'M': vectors += ['@' + alias + '[' + k + ']' for k in ('id', 'gm', 'vgs', 'vds', 'vdsat')]
    if typ == 'op': text += '.save all ' + ' '.join(vectors) + '\n'
    return text + f'.temp {scalar(s.get("temperature", 27)):.12g}\n' + command + '\n.end\n', aliases
