"""Pinned public IHP extraction without comparison alignment or device purging.

Magic still supplies full DRC. Netgen compares the unfiltered extracted circuit.
This selectable route is independent of the PDK's bundled Magic extractor.
"""
import json
from pathlib import Path, PurePosixPath
import re
import shutil

from .model import atomic_write, file_digest

SOURCE = Path(__file__).parent / 'assets/physical/ihp_klayout_lvs'
COMMIT = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
LABEL_LAYERS = (8, 10, 30, 50, 67, 126, 134, 31)
BIPOLARS = {'pnpmpa': 3, 'npn13g2': 4, 'npn13g2l': 4, 'npn13g2v': 4}


def assets(root=None):
    root = Path(root or SOURCE).resolve()
    lock = json.loads((root / 'SOURCE.json').read_text(encoding='utf-8'))
    if lock.get('commit') != COMMIT or lock.get('entry') != 'sg13g2.lvs' or lock.get('modified_upstream_files') is not False:
        raise ValueError('Unknown IHP extraction source revision.')
    result = {'SOURCE.json': root / 'SOURCE.json'}
    for name, record in lock['files'].items():
        part = PurePosixPath(name)
        if part.is_absolute() or '..' in part.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe IHP extraction dependency path.')
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path) != record['sha256']:
            raise ValueError('Missing or changed IHP extraction dependency: ' + name)
        result[name] = path
    if 'sg13g2.lvs' not in result or 'LICENSE' not in result:
        raise ValueError('Incomplete IHP extraction source bundle.')
    return result


def copy_assets(destination):
    """Transfer the same checked bundle to the included Linux/WSL backend."""
    destination = Path(destination)
    for name, path in assets().items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if file_digest(target) != file_digest(path):
            raise ValueError('IHP extraction source changed during transfer.')
    assets(destination)


def label_stream(source, target, top):
    """Copy IHP pin-purpose text to the public verifier's text-purpose layer.

    Keep pin text, every mask and the original user export. KLayout's public
    deck reads text on datatype 25; Magic also reads pin text on datatype 2.
    No net name, anchor or polygon is invented or changed.
    """
    import klayout.db as db
    ly = db.Layout(); ly.read(str(source)); cell = ly.cell(top)
    if cell is None or any(cell.each_inst()):
        raise ValueError('IHP extraction needs the checked, flattened verification stream.')
    def masks(layout, selected):
        result = {}
        for i in layout.layer_indexes():
            region = db.Region()
            for shape in selected.shapes(i).each():
                if shape.is_box() or shape.is_polygon() or shape.is_path():
                    region.insert(shape.polygon)
            if not region.is_empty():result[str(layout.get_info(i))] = region.merged()
        return result
    before = masks(ly, cell); copied = []
    for layer in LABEL_LAYERS:
        pin = ly.find_layer(layer, 2)
        if pin is None:continue
        dest = ly.layer(layer, 25)
        existing = {s.text.to_s() for s in cell.shapes(dest).each() if s.is_text()}
        for shape in list(cell.shapes(pin).each()):
            if shape.is_text() and shape.text.to_s() not in existing:
                cell.shapes(dest).insert(shape.text)
                copied.append(dict(layer=layer, text=shape.text.string, x=shape.text.x, y=shape.text.y))
                existing.add(shape.text.to_s())
    ly.write(str(target)); check = db.Layout(); check.read(str(target))
    after = masks(check, check.cell(top))
    if set(before) != set(after) or any(not (before[k] ^ after[k]).is_empty() for k in before):
        raise ValueError('IHP label conversion changed mask geometry.')
    return dict(source_sha256=file_digest(source), sha256=file_digest(target), copied_pin_texts=copied,
                geometry='Exact region XOR on every polygon layer/datatype; original export retained.')


def bipolar_subcircuits(text):
    """Express the four public BJT LVS primitives as their PDK X subcircuits.

    Public KLayout writes Q records; the public IHP simulation/Magic views use
    X subcircuits with the same model, terminal order and parameters. Only that
    instance prefix changes. Numerical values and connectivity stay verbatim.
    """
    lines = re.sub(r'\n[ \t]*\+[ \t]*', ' ', text).splitlines(); changes = []; devices = 0; names = set()
    for index, line in enumerate(lines):
        tokens = line.split()
        if not tokens or tokens[0].startswith(('*', '.')):continue
        if tokens[0][0].upper() == 'Q':
            before_params = next((i for i, t in enumerate(tokens) if '=' in t), len(tokens))
            model = tokens[before_params - 1].casefold()
            count = BIPOLARS.get(model)
            if count is None or before_params != count + 2:
                raise ValueError('Unreviewed IHP bipolar extraction interface.')
            replacement = 'X' + tokens[0][1:]
            lines[index] = re.sub(r'^(\s*)' + re.escape(tokens[0]), lambda m: m[1] + replacement, line, count=1)
            changes.append(dict(instance=tokens[0], replacement=replacement, model=tokens[before_params - 1], terminal_count=count))
        if tokens[0][0].upper() in 'MXRCDQJBL':
            name = lines[index].split()[0].casefold()
            if name in names:raise ValueError('Duplicate instance after IHP extraction interface conversion.')
            names.add(name);devices += 1
        else:raise ValueError('Unrecognized statement in IHP extracted circuit.')
    if not devices:raise ValueError('IHP extraction produced no circuit devices; an empty circuit cannot pass LVS.')
    return '\n'.join(lines) + '\n', changes


def extract(executable, source, top, ports, technology, folder):
    from .engines import execute
    from .external_tools import check_extracted_interface
    folder = Path(folder); folder.mkdir()
    library = assets(); before = {str(p): file_digest(p) for p in library.values()}
    mapping = label_stream(source, folder / 'labels.gds', top)
    settings = dict(input=folder/'labels.gds', topcell=top, report=folder/'extraction.lvsdb',
                    target_netlist=folder/'native.cir', log=folder/'native.log', run_mode='flat',
                    net_only='true', top_lvl_pins='true', no_simplify='true', combine_devices='false',
                    purge='false', purge_nets='false', purge_devices='false', implicit_nets='',
                    disable_tap_extraction='false')
    args = [str(executable), '-b', '-r', str(library['sg13g2.lvs'])]
    for name, value in settings.items():args.extend(['-rd', name+'='+str(value)])
    atomic_write(folder/'command.json', json.dumps(args, indent=2))
    try:log = execute(args, folder, timeout=300)
    except Exception as error:atomic_write(folder/'console.log', str(error)); raise
    atomic_write(folder/'console.log', log)
    if 'NET_ONLY enabled: apply extraction netlist options and skip comparison.' not in log or 'LVS Total Run time ' not in log:
        raise ValueError('Public IHP extraction did not complete without comparison filtering.')
    native = folder/'native.cir'
    converted, changes = bipolar_subcircuits(native.read_text(encoding='utf-8'))
    output = folder/'extracted.spice'; atomic_write(output, converted)
    check_extracted_interface(output, top, ports, technology)
    if any(file_digest(Path(p)) != h for p, h in before.items()):
        raise ValueError('IHP extraction dependencies changed during execution.')
    return dict(deck='lvs-extraction/extracted.spice', sha256=file_digest(output),
                native_sha256=file_digest(native), source_commit=COMMIT, label_mapping=mapping,
                interface_conversion=changes, settings={k:str(v) for k,v in settings.items()})
