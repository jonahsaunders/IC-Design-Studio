"""Execute the KLayout CLI, including the Ruby API required by the IHP deck."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .engines import execute
from .model import atomic_write, file_digest

DECK = '''source($input)
report("Runtime width control", $report)
class RuntimeProbeEdges < RBA::EdgePairToEdgeOperator
  def initialize
    self.is_isotropic_and_scale_invariant
  end
  def process(pair)
    [pair.first]
  end
end
errors = input(1, 0).width(0.5)
converted = errors.data.processed(RuntimeProbeEdges.new)
raise "Edge conversion mismatch" unless converted.size == errors.data.size
errors.output("runtime.width", "Width below 0.5 um")
puts "PROBE_KLAYOUT #{errors.data.size} #{converted.size} #{RBA::Application.instance.version}"
'''


def check_result(log, report, expected):
    matches = re.findall(r'^PROBE_KLAYOUT (\d+) (\d+) (KLayout [^\r\n]+)\s*$', log, re.M)
    if len(matches) != 1:
        raise ValueError('KLayout CLI did not report the actual Ruby rule control.')
    count, converted, version = matches[0]
    try:
        tree = ET.parse(report)
    except (OSError, ET.ParseError) as exc:
        raise ValueError('KLayout CLI omitted or damaged its native rule report.') from exc
    if tree.getroot().tag != 'report-database':
        raise ValueError('KLayout CLI returned an unexpected native rule report.')
    if (tree.findtext('./top-cell') != 'runtime_probe'
            or tree.findall('./categories/category/name') == []
            or [n.text for n in tree.findall('./categories/category/name')] != ['runtime.width']):
        raise ValueError('KLayout CLI native report has missing or unexpected rule/cell coverage.')
    items = tree.findall('./items/item')
    if (int(count), int(converted), len(items)) != (expected, expected, expected):
        raise ValueError('KLayout CLI rule control or native report count differs from the expected geometry.')
    if any((item.findtext('category') or '').strip("'") != 'runtime.width' for item in items):
        raise ValueError('KLayout CLI reported an unexpected rule category.')
    return {'markers': len(items), 'converted_edges': int(converted), 'version': version}


def qualify(executable, directory):
    import klayout.db as db
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    deck = root / 'runtime-width.drc'
    atomic_write(deck, DECK)
    checks = []
    for name, width, expected in (('legal', 1000, 0), ('narrow', 100, 1)):
        layout = db.Layout(); layout.dbu = 0.001
        cell = layout.create_cell('runtime_probe')
        cell.shapes(layout.layer(1, 0)).insert(db.Box(0, 0, width, 2000))
        gds = root / (name + '.gds'); layout.write(str(gds))
        report = root / (name + '.lyrdb')
        command = [str(executable), '-b', '-r', str(deck), '-rd', 'input=' + str(gds),
                   '-rd', 'report=' + str(report)]
        atomic_write(root / (name + '-command.json'), json.dumps(command, indent=2))
        lines = []
        try:
            log = execute(command, root, timeout=120, on_line=lines.append)
        finally:
            atomic_write(root / (name + '.log'), '\n'.join(lines) + '\n')
        measured = check_result(log, report, expected)
        checks.append({'name': 'klayout-' + name, 'status': 'passed', **measured,
                       'input_sha256': file_digest(gds), 'report_sha256': file_digest(report)})
    if len({check['version'] for check in checks}) != 1:
        raise ValueError('KLayout CLI changed between runtime controls.')
    atomic_write(root / 'checks.json', json.dumps({
        'scope': 'CLI width-rule and Ruby edge-operator controls only; not PDK rule or design qualification.',
        'deck_sha256': file_digest(deck), 'checks': checks}, indent=2))
    return checks
