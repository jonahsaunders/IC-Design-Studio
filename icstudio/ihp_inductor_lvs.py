"""Preserve IHP inductor geometry and substrate terminals in physical LVS.

The public CDL L records have three/four terminals, unlike a SPICE inductor.
Use explicit X primitives for comparison only. This supplies no electrical
model and does not enable the unavailable simulation catalog entries.
"""
import math
import re

from .model import scalar

MODELS = {'inductor': 3, 'inductor3': 4}


def winding_proof(source, top):
    """Count every IND marker and prove its actual top-metal/via continuity.

    The public recognizer unions metals geometrically to identify a coil. That
    union cannot prove the crossing vias exist. No labels join this audit's nets.
    """
    import klayout.db as k
    from .model import file_digest
    before = file_digest(source)
    ly = k.Layout(); ly.read(str(source)); cell = ly.cell(top)
    if cell is None or any(cell.each_inst()):
        raise ValueError('IHP inductor checking requires the flattened physical stream.')
    def region(pair):
        i = ly.find_layer(*pair)
        return k.Region() if i is None else k.Region([s.polygon for s in cell.shapes(i).each() if not s.is_text()]).merged()
    markers = region((27, 0)); rows = []; failures = []
    texts = []
    for pair in ((27, 25), (63, 0)):
        i = ly.find_layer(*pair)
        if i is not None:
            texts.extend((pair, s.text) for s in cell.shapes(i).each() if s.is_text())
    pins = region((27, 2))
    for pair, text in texts:
        if recognition_label(*pair, text.string) and not any(m.inside(k.Point(text.x,text.y)) for m in markers.each()):
            failures.append(dict(kind='orphan-inductor-recognition',text=text.string))
    if not pins.not_interacting(markers).is_empty():
        failures.append(dict(kind='orphan-inductor-terminal-mask'))
    for number, marker in enumerate(markers.each()):
        area = k.Region(marker)
        names = [t.string for pair, t in texts if pair == (63, 0) and marker.inside(k.Point(t.x, t.y))
                 and recognition_label(*pair, t.string)]
        if len(names) != 1:
            failures.append(dict(marker=number, kind='missing-or-ambiguous-inductor-recognition')); continue
        model = 'inductor3' if names[0].lower().startswith('inductor3') else 'inductor'
        wanted = ('LA', 'LC', 'LB') if model == 'inductor3' else ('LA', 'LB')
        local_pins = pins.interacting(area)
        roles = {}; layers = {name: region(pair) & area for name, pair in (('tm1', (126, 0)), ('tm2', (134, 0)), ('via', (133, 0)))}
        # The public deck also recognizes fill/slit purposes. Until audited for
        # coils, these masks must not be silently omitted by the wire proof.
        for pair in ((126, 22), (126, 24), (134, 22), (134, 24)):
            if not (region(pair) & area).is_empty():
                failures.append(dict(marker=number, kind='unsupported-winding-mask', layer=list(pair)))
        if not (layers['via']-layers['tm1']).is_empty() or not (layers['via']-layers['tm2']).is_empty():
            failures.append(dict(marker=number, kind='crossing-via-without-both-metals'))
        netter = k.LayoutToNetlist('coil', ly.dbu)
        for name, shapes in layers.items():
            netter.register(shapes, name); netter.connect(shapes)
        netter.connect(layers['tm1'], layers['via']); netter.connect(layers['via'], layers['tm2'])
        netter.extract_netlist(); netter.check_extraction_errors()
        nets = {n.cluster_id for circuit in netter.netlist().each_circuit() for n in circuit.each_net()}
        if len(nets) != 1 or list(netter.each_log_entry()):
            failures.append(dict(marker=number, kind='disconnected-winding-metal', components=len(nets)))
        # A winding (including a center tap) is a conductor tree. An extra
        # bridge can bypass turns without changing the public W/S/D/NR_R
        # measurements. Count independent conductive loops on the two metal
        # surfaces. Collapse a via array to its contacted overlap island so
        # redundant cuts at one junction are not mistaken for a shorted turn.
        metals=[layers['tm1'].merged(),layers['tm2'].merged()]
        junctions=(metals[0]&metals[1]).merged().interacting(layers['via']).count()
        holes=sum(p.holes() for metal in metals for p in metal.each())
        cycles=len(nets)-sum(metal.count() for metal in metals)+holes+junctions
        if cycles!=0:
            failures.append(dict(marker=number,kind='shorted-or-ambiguous-winding-loop',cycles=cycles))
        for pin in local_pins.each():
            annotations = [t for pair, t in texts if pair == (27, 25) and pin.inside(k.Point(t.x, t.y))]
            if len(annotations) != 1 or annotations[0].string.upper() not in wanted:
                failures.append(dict(marker=number, kind='missing-or-ambiguous-winding-terminal')); continue
            t = annotations[0]; role = t.string.upper()
            metal = 'tm2' if model == 'inductor' or role == 'LC' else 'tm1'
            net = netter.probe_net(layers[metal], k.Point(t.x, t.y))
            if role in roles or net is None or not (k.Region(pin)-layers[metal]).is_empty():
                failures.append(dict(marker=number, kind='invalid-winding-terminal', role=role))
            roles[role] = None if net is None else net.cluster_id
        if set(roles) != set(wanted) or local_pins.count() != len(wanted):
            failures.append(dict(marker=number, kind='wrong-winding-terminal-set'))
        rows.append(dict(marker=number, model=model, bbox=str(marker.bbox()), terminal_roles=roles,
                         metal_components=len(nets), crossing_vias=layers['via'].count(),
                         contacted_overlap_islands=junctions,metal_holes=holes,winding_cycles=cycles))
    if file_digest(source) != before:
        raise ValueError('IHP inductor geometry changed during wire checking.')
    return dict(schema=1, passed=not failures, gds_sha256=before, coils=rows, failures=failures,
                scope='IND recognition inventory and actual TopMetal1/TopVia2/TopMetal2 continuity; no EM or electrical model qualification.')


def geometry(text):
    """Normalize both public L and explicit X references without losing fields."""
    lines = re.sub(r'\n[ \t]*\+[ \t]*', ' ', text).splitlines()
    changes = []
    for i, line in enumerate(lines):
        row = line.split()
        if not row or row[0].startswith(('*', '.')):
            continue
        if row[0][0].upper() not in ('L','X'):
            continue
        j = next((i for i,v in enumerate(row) if '=' in v),len(row))-1
        model = row[j].lower()
        if model not in MODELS:
            continue
        if row[0][0].upper() not in ('L', 'X') or j != MODELS[model] + 1:
            raise ValueError('IHP inductor LVS must retain every winding and substrate terminal.')
        values = {}
        for token in row[j+1:]:
            pair = token.split('=', 1)
            if len(pair) != 2 or pair[0].lower() in values:
                raise ValueError('Duplicate or unresolved IHP inductor LVS parameter.')
            key, raw = pair[0].lower(), pair[1]
            value = scalar(raw)
            if not math.isfinite(value) or value <= 0:
                raise ValueError('IHP inductor LVS parameters must be positive and finite.')
            values[key] = (value, raw)
        if set(values) not in ({'w', 's', 'd', 'nr_r'}, {'w', 's', 'd', 'nr_r', 'm'}):
            raise ValueError('IHP inductor LVS needs W, S, D and NR_R; unknown parameters are not discarded.')
        for key in ('nr_r', 'm'):
            if key in values and not values[key][0].is_integer():
                raise ValueError('IHP inductor turn count and multiplicity must be integers.')
        # Each extracted device represents one physical coil. An explicit M is
        # preserved; omitting it means one, never an ignored arbitrary count.
        values.setdefault('m', (1., '1'))
        name = row[0] if row[0][0].upper() == 'X' else 'XICSTUDIO_IND_' + row[0]
        lines[i] = ' '.join([name, *row[1:j], model,
                             *(key+'='+values[key][1] for key in ('w', 's', 'd', 'nr_r', 'm'))])
        changes.append(dict(instance=row[0], replacement=name, model=model,
                            terminal_count=MODELS[model], original=line, comparison=lines[i],
                            reason='Physical IHP coil primitive; all winding/substrate terminals and W/S/D/NR_R/M retained. No electrical model implied.'))
    if not changes:
        return text, []
    from .ihp_tap_lvs import _names
    _names(lines)
    return '\n'.join(lines)+'\n', changes


def recognition_label(layer, datatype, text):
    """Non-electrical labels used by the pinned public inductor recognition."""
    if (layer, datatype) == (27, 25):
        return text.upper() in ('LA', 'LB', 'LC')
    return (layer, datatype) == (63, 0) and re.fullmatch(r'inductor[23][^\r\n]*', text, re.I) is not None


def extractor_roles(destination):
    """Give native terminals their written LA/LC/LB roles under any rotation.

    Only a checked private run copy changes. The upstream geometry measurements
    and source bundle remain untouched; no extracted nodes are reordered later.
    """
    from pathlib import Path
    from .model import file_digest
    root = Path(destination); records = []
    edits = {
        'custom_extractor.lvs': ('6bde15ff3d3702eac7ab372c74b21752c179b66c21c076350d258397986fc8ba', [
            ("    conn\n  end\n\n  def extract_devices", "    if name.downcase.start_with?('ind')\n      layers[5..7].each { |role| conn.connect(role, dev_mk) }\n    end\n    conn\n  end\n\n  def extract_devices"),
            ('define_and_sort_terminals(device, region_ports, region_sub_mk, local_dev)',
             'define_and_sort_terminals(device, region_ports, region_sub_mk, local_dev, layer_geometry[5..7])'),
            ("      define_layer('sub_mk', 'Substrate Marker')\n    end\n  end", "      define_layer('sub_mk', 'Substrate Marker')\n    end\n    if name.downcase.start_with?('ind')\n      %w[role_a role_b role_c].each { |role| define_layer(role, 'Written IND terminal role') }\n    end\n  end"),
            ('def define_and_sort_terminals(device, ports, sub_mk, core_region = nil)',
             'def define_and_sort_terminals(device, ports, sub_mk, core_region = nil, role_regions = nil)'),
            ("""    # Define sub if exist (should be defined before other terminals)
    if name.downcase.start_with?('ind')
      if sub_mk.is_empty?
        $logger.info("Sub terminal for #{@name} device doesn't exist, please recheck")
        return nil
      else
        define_terminal(device, @reg_dev.terminal_id("#{name}_sub"), 4, sub_mk[0])
      end
    end""",
             """    # IC Design Studio: physical IND annotations, independent of rotation.
    if name.downcase.start_with?('ind')
      raise 'Inductor substrate is missing or ambiguous' unless sub_mk.size == 1
      indices = @num == 2 ? [0, 1] : [0, 2, 1]
      define_terminal(device, @reg_dev.terminal_id("#{name}_sub"), 4, sub_mk[0])
      indices.each_with_index do |index, i|
        selected = ports.interacting(role_regions[index])
        raise 'Inductor terminal role is missing or ambiguous' unless selected.size == 1
        define_terminal(device, @reg_dev.terminal_id("#{name}_#{i + 1}"), 1, selected[0])
      end
      return nil
    end""")]),
        'ind_extraction.lvs': ('bcf182be57689e2571d3748973bad31b4e084837faf3cbcc3a9a72c6acc63a2a', [
            ("'sub_mk' => ind2_sub", "'sub_mk' => ind2_sub,\n                  'role_a' => ind_port_la, 'role_b' => ind_port_lb, 'role_c' => ind_port_lc"),
            ("'sub_mk' => ind3_sub", "'sub_mk' => ind3_sub,\n                  'role_a' => ind_port_la, 'role_b' => ind_port_lb, 'role_c' => ind_port_lc")])}
    for name, (sha, replacements) in edits.items():
        path = root/'rule_decks'/name
        if file_digest(path) != sha:
            raise ValueError('Unexpected public IHP inductor extraction source: '+name)
        content = path.read_bytes()
        for old, new in replacements:
            old, new = old.encode(), new.encode()
            if content.count(old) != 1:
                raise ValueError('Unexpected IHP inductor extraction anchor: '+name)
            content = content.replace(old, new)
        path.write_bytes(content)
        records.append(dict(path='rule_decks/'+name, source_sha256=sha, sha256=file_digest(path),
                            change='Native winding terminal roles follow the written IND LA/LB/LC annotations, independent of rotation. Geometry measurements unchanged.'))
    return records
