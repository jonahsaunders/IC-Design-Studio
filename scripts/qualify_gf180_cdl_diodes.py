"""Run the actual GF180 Ruby reader against locked antenna CDL fault controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.gf180_cdl_diodes import RUBY_GEOMETRY_GUARD, normalize


RUBY_RUNNER = '''require "json"
load $reader_source
''' + RUBY_GEOMETRY_GUARD + '''
def read_cdl(path, guarded)
  nl = RBA::Netlist.new
  nl.read(path, RBA::NetlistSpiceReader.new(SubcircuitModelsReader.new))
  enabled = guarded ? icstudio_gf180_diode_geometry(nl) : []
  [nl, enabled]
end
request = JSON.parse(File.read($request))
rows = []
request["cases"].each do |item|
  [false, true].each do |guarded|
    row = {"case" => item["name"], "guarded" => guarded}
    begin
      nl, enabled = read_cdl(item["path"], guarded)
      reference, ref_enabled = read_cdl(request["reference"], guarded)
      row["matched"] = RBA::NetlistComparer.new.compare(nl, reference)
      row["enabled"] = enabled
      row["reference_enabled"] = ref_enabled
      row["devices"] = nl.top_circuit.each_device.map do |d|
        {"name" => d.name, "model" => d.device_class.name,
         "anode" => d.net_for_terminal("A").name, "cathode" => d.net_for_terminal("C").name,
         "area_um2" => d.parameter("A"), "perimeter_um" => d.parameter("P"),
         "primary_parameters" => d.device_class.parameter_definitions.select(&:is_primary?).map(&:name).sort}
      end
    rescue => error
      row["error"] = error.message
    end
    rows << row
  end
end
File.write($output, JSON.pretty_generate({"version" => RBA::Application.instance.version, "cases" => rows}) + "\\n")
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source, lock_path, reader_source, klayout, out):
    out.mkdir(parents=True, exist_ok=False)
    record = dict(status='running', qualified=False, scope='Pinned two-diode antenna CDL reader and dimension-comparison controls; not physical layout, whole-design LVS or tapeout acceptance.')
    def write(path, data):
        path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    def retain():
        write(out / 'record.json', record)
    retain()
    try:
        lock = json.loads(lock_path.read_text())
        relative = source.resolve().relative_to(lock_path.parent.resolve()).as_posix()
        assert lock['revision'] == '3781fd2951da6e3dc4600e52d997398a9463caeb'
        assert sha(source) == lock['files'][relative]['sha256']
        source_text = source.read_text()
        reference, changes = normalize(source_text)
        assert len(changes) == 2
        assert [(r['anode'], r['cathode'], r['model'], r['multiplicity']) for r in changes] == [
            ('VPW', 'I', 'diode_nd2ps_06v0', 1), ('I', 'VNW', 'diode_pd2nw_06v0', 1)]
        assert all(r['area_si'] == '2.034E-13' and r['perimeter_si'] == '0.00000185' for r in changes)
        (out / 'source.cdl').write_bytes(source.read_bytes())
        (out / 'reference.cdl').write_text(reference, encoding='utf-8', newline='\n')
        cases = {'source-positional':source_text, 'positive':reference,
                 'area-fault':reference.replace('A=0.2034p', 'A=0.3034p', 1),
                 'perimeter-fault':reference.replace('P=1.85u', 'P=2.85u', 1),
                 'multiplicity-fault':reference.replace('M=1', 'M=2', 1),
                 'polarity-fault':reference.replace('d0 VPW I', 'd0 I VPW', 1),
                 'model-fault':reference.replace('diode_nd2ps_06v0', 'diode_pd2nw_06v0', 1),
                 'missing-diode':reference.replace(changes[1]['after'] + '\n', '', 1)}
        assert len(set(cases.values())) == len(cases)
        request = dict(reference=str(out / 'reference.cdl'), cases=[])
        for name, text in cases.items():
            path = out / (name + '.cdl')
            path.write_text(text, encoding='utf-8', newline='\n')
            request['cases'].append(dict(name=name, path=str(path), sha256=sha(path)))
        write(out / 'request.json', request)
        (out / 'native-controls.rb').write_text(RUBY_RUNNER, encoding='utf-8', newline='\n')
        command = [str(klayout), '-b', '-r', str(out / 'native-controls.rb'), '-rd', 'request=' + str(out / 'request.json'),
                   '-rd', 'output=' + str(out / 'native-results.json'), '-rd', 'reader_source=' + str(reader_source)]
        record.update(command=command, source_sha256=sha(source), source_lock_sha256=sha(lock_path),
                      reader_source_sha256=sha(reader_source), klayout_launcher_sha256=sha(klayout),
                      adapter_sha256=sha(ROOT / 'scripts/gf180_cdl_diodes.py'), runner_sha256=sha(Path(__file__)),
                      ruby_sha256=sha(out / 'native-controls.rb'), syntax_changes=changes)
        retain()
        with (out / 'engine.log').open('w') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        record.update(exit_code=process.returncode, log_sha256=sha(out / 'engine.log'))
        assert process.returncode == 0
        native = json.loads((out / 'native-results.json').read_text())
        assert len(native['cases']) == 16
        for row in native['cases']:
            if row['case'] == 'source-positional':
                assert 'two nodes' in row['error'] and 'matched' not in row
            else:
                assert 'error' not in row
                expected = row['case'] == 'positive' or (not row['guarded'] and row['case'] in ('area-fault', 'perimeter-fault', 'multiplicity-fault'))
                assert row['matched'] == expected, row
                assert all(d['primary_parameters'] == (['A', 'P'] if row['guarded'] else []) for d in row['devices'])
                if row['case'] == 'positive':
                    assert len(row['devices']) == 2
                    assert all(abs(d['area_um2'] - .2034) < 1e-14 and abs(d['perimeter_um'] - 1.85) < 1e-14 for d in row['devices'])
        record.update(status='native-diode-reader-and-geometry-controls-passed', native_version=native['version'],
                      results_sha256=sha(out / 'native-results.json'), cases=native['cases'],
                      remaining='Run final-layout LVS with a separately retained geometry guard and complete actual post-fill electrical checks.')
        assert sha(source) == record['source_sha256'] and sha(reader_source) == record['reader_source_sha256']
        retain()
    except Exception as exc:
        record.update(status='failed', reason=repr(exc))
        retain()
        raise
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-lock', type=Path, required=True)
    parser.add_argument('--reader-source', type=Path, required=True)
    parser.add_argument('--klayout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source.resolve(), args.source_lock.resolve(), args.reader_source.resolve(), args.klayout.resolve(), args.output.resolve())
    print(json.dumps(dict(status=result['status'], native_version=result['native_version'], checks=len(result['cases']))))
