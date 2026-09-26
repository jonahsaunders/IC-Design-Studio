"""Verify real reference layouts after Studio, KLayout and Magic exchange.

Use the output of qualify_open_project.py for the locked detector schematic,
original GDS and corrected extraction technology. Every layout is re-extracted;
no saved LVS verdict or Studio sidecar supplies an electrical result.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import atomic_write, file_digest, load_project, save_project
from icstudio.engines import tcl_word
from scripts.qualification_evidence import Report, Blocked, command, magic_verify, compare_lvs
from scripts.qualify_open_project import geometry_equal

SKY130_PIN_LAYERS=tuple((layer,16) for layer in range(64,73))
SKY130_LABEL_LAYERS=tuple((layer,5) for layer in range(64,73))


def external_stream(source, target, executable, output, edit=False):
    """Use the standalone KLayout process; make a reversible, visible text edit."""
    output.mkdir(parents=True, exist_ok=True)
    script = output / 'exchange.py'
    atomic_write(script, '''import pya
layout = pya.Layout()
layout.read(input_path)
if edit_mode == 'true':
    layer = layout.layer(200, 99)
    layout.top_cell().shapes(layer).insert(pya.Text('EXCHANGE_REVIEW', pya.Trans(1000, 1000)))
layout.write(output_path)
''')
    command([executable, '-b', '-r', script, '-rd', 'input_path=' + str(source),
             '-rd', 'output_path=' + str(target), '-rd', 'edit_mode=' + str(edit).lower()], output)
    if not target.is_file():
        raise ValueError('KLayout did not write its exchange file.')


def layout_routes(source, output, klayout):
    from icstudio.layout_import import read_layout
    from icstudio.interchange import export_layout
    output.mkdir(parents=True, exist_ok=True)
    project, warnings = read_layout(source)
    save_project(project, output / 'imported.icproj')
    reopened = load_project(output / 'imported.icproj')
    paths = {'original': source}
    comparisons = {}
    for suffix in ('gds', 'oas'):
        exported = output / ('studio.' + suffix)
        export_layout(reopened, exported)
        # Standard OASIS cannot carry text presentation. Geometry, label
        # strings and anchor points must still match, independently of metadata.
        comparisons[suffix] = geometry_equal(source, exported, text_presentation=suffix != 'oas')
        external = output / ('klayout.' + suffix)
        external_stream(exported, external, klayout, output / ('external-' + suffix))
        geometry_equal(exported, external)
        # read_layout is deliberately metadata-independent; no sidecar recovery.
        again, _ = read_layout(external)
        native = output / ('reimported-' + suffix + '.icproj')
        save_project(again, native)
        final = output / ('reimported-' + suffix + '.gds')
        export_layout(load_project(native), final)
        geometry_equal(source, final, text_presentation=suffix != 'oas')
        paths['studio-' + suffix] = exported
        paths['klayout-' + suffix] = external
        paths['reimported-' + suffix] = final
    edited = output / 'external-edit.gds'
    external_stream(paths['studio-gds'], edited, klayout, output / 'external-edit', edit=True)
    changed, _ = read_layout(edited)
    if not any(t['text'] == 'EXCHANGE_REVIEW' for c in changed['cells'] for t in c['layout_texts']):
        raise ValueError('The external text edit was lost.')
    for cell in changed['cells']:
        cell['layout_texts'] = [t for t in cell['layout_texts'] if t['text'] != 'EXCHANGE_REVIEW']
    restored = output / 'restored-edit.gds'
    export_layout(changed, restored)
    geometry_equal(source, restored)
    paths['restored-edit'] = restored
    return paths, dict(warnings=warnings, paths={k: str(v) for k, v in paths.items()},
                       source_sha256=file_digest(source), comparisons=comparisons,
                       comparison='per-cell/layer XOR, label strings/anchors, hierarchy, arrays, database units',
                       limits=['OASIS does not preserve text orientation, size, font or alignment; GDS presentation is compared strictly.'],
                       sidecars_used=False, external_edit='add text, reimport, remove text, compare original')


def physical_faults(source, output):
    """Mutate real detector geometry, independently of its schematic reference."""
    import klayout.db as db
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name in ('narrow-metal', 'missing-vias', 'shorted-pins', 'wrong-resistor-width', 'missing-pin', 'extra-pin'):
        ly = db.Layout(); ly.read(str(source)); top = ly.top_cell()
        if name == 'narrow-metal':
            x, y = top.bbox().right + 5000, top.bbox().top + 5000
            top.shapes(ly.layer(68, 20)).insert(db.Box(x, y, x + 100, y + 100))
        elif name == 'missing-vias':
            count = 0
            for pair in ((66, 44), (67, 44), (68, 44), (69, 44)):
                index = ly.find_layer(*pair)
                if index is not None:
                    for cell in ly.each_cell():
                        count += cell.shapes(index).size(); cell.shapes(index).clear()
            if count == 0: raise ValueError('No contact/via geometry found for the fault.')
        elif name == 'shorted-pins':
            # Cover the physical footprint on M1. Existing contacts join rails/signals.
            top.shapes(ly.layer(68, 20)).insert(top.bbox())
        elif name == 'wrong-resistor-width':
            # On the flattened stream, require poly inside the actual URPM
            # recognition mask. Widen one long resistor while keeping contacts.
            index = ly.find_layer(66, 20)
            marker = ly.find_layer(79, 20)
            if index is None or marker is None:raise ValueError('Missing resistor mask layers.')
            urpm=db.Region(top.shapes(marker))
            before=db.Region(top.shapes(index))
            changed = 0
            for shape in list(top.shapes(index).each()):
                if shape.is_text():continue
                box=shape.bbox()
                if not (db.Region(shape.polygon)&urpm).is_empty() and max(box.width(),box.height())>10000:
                    shape.polygon=shape.polygon.sized(100,0,2) if box.height()>box.width() else shape.polygon.sized(0,100,2)
                    changed=1;break
            if not changed: raise ValueError('No resistor body qualified for a dimensional fault.')
            if (before ^ db.Region(top.shapes(index))).is_empty():raise ValueError('The dimensional fault changed no physical geometry.')
        elif name == 'extra-pin':
            # Promote the existing internal label on the stream's pin purpose.
            # The pin-purpose bridge must not erase this real interface defect.
            index=ly.find_layer(69,5)
            labels=[s.text for s in top.shapes(index).each() if s.is_text() and s.text.string=='vin'] if index is not None else []
            if len(labels)!=1:raise ValueError('Expected the detector internal vin label.')
            for shape in list(top.shapes(index).each()):
                if shape.is_text() and shape.text.string=='vin':shape.delete()
            top.shapes(ly.layer(69,16)).insert(labels[0])
        else:
            count = 0
            for index in ly.layer_indexes():
                for shape in list(top.shapes(index).each()):
                    if shape.is_text() and shape.text.string == 'ena':
                        shape.delete(); count += 1
            if not count: raise ValueError('No top-level enable label found.')
        path = output / (name + '.gds'); ly.write(str(path)); paths[name] = path
    return paths


def magic_roundtrip(source, target, top, technology, executable, directory):
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory / 'startup.tcl', 'tech load ' + tcl_word(technology) + '\n')
    # Save native cells, reopen in a separate process, then write the stream.
    for stage in ('save', 'reopen'):
        body = ('cif istyle sky130()\ngds read ' + tcl_word(source) + '\n' if stage == 'save' else '')
        body += 'load ' + tcl_word(top) + '\nselect top cell\n'
        if stage == 'save':
            from scripts.qualification_evidence import stream_pin_contract
            contract=stream_pin_contract(source,top,SKY130_PIN_LAYERS,SKY130_LABEL_LAYERS)
            atomic_write(directory/'stream-pin-contract.json',json.dumps(contract,indent=2)+'\n')
            for name in contract['labels']:
                word=tcl_word(name)
                body+='if {[port '+word+' exists]} {port '+word+' remove}\n'
        body += ('writeall force\n' if stage == 'save' else 'gds write ' + tcl_word(target) + '\n')
        script = 'if {[catch {\n' + body + 'puts QUAL_EXCHANGE_COMPLETE\n} err]} {puts "QUAL_EXCHANGE_ERROR $err"}\nquit -noprompt\n'
        atomic_write(directory / (stage + '.tcl'), script)
        log = command([executable, '-dnull', '-noconsole', '-rcfile', directory / 'startup.tcl', directory / (stage + '.tcl')], directory, stage)
        if 'QUAL_EXCHANGE_COMPLETE' not in log or 'QUAL_EXCHANGE_ERROR' in log:
            raise ValueError('Magic native save/reopen failed.')
    if not target.exists(): raise ValueError('Magic did not export a stream.')
    return dict(source_sha256=file_digest(source), output_sha256=file_digest(target))


def qualify(args):
    report = Report(args.out, 'reference-exchange')
    inputs = args.detector.resolve()
    state = {}
    def preflight():
        upstream = json.loads((inputs / 'qualification.json').read_text())
        if upstream.get('status') != 'passed':
            raise Blocked('Run the strict detector source qualification successfully first.')
        if not upstream.get('artifacts'):
            raise Blocked('Rerun source qualification to bind its exchanged artifacts to checksums.')
        for relative, expected in upstream['artifacts'].items():
            path = (inputs / relative).resolve()
            if not path.is_relative_to(inputs) or not path.is_file() or file_digest(path) != expected:
                raise ValueError('Source-qualified artifact changed: ' + relative)
        # The saved reference must still equal the source-qualified input.
        manifest = inputs / 'native-lvs.spice'
        if not manifest.is_file(): raise Blocked('Missing independently compared detector reference.')
        state['magic'] = report.tool('magic', args.magic, ['--version'])
        state['netgen'] = report.tool('netgen', args.netgen, ['-batch'])
        state['klayout'] = report.tool('klayout', args.klayout, ['-b', '-v'])
        state['xschem'] = report.tool('xschem', args.xschem, ['-x', '-q', '--version'])
        state['reference'] = manifest
        state['technology'] = inputs / 'technology/sky130A.tech'
        if not state['technology'].exists():
            candidates = list((inputs / 'technology').glob('*.tech'))
            if len(candidates) != 1: raise ValueError('Ambiguous detector technology.')
            state['technology'] = candidates[0]
        state['top'] = upstream['source']['top']
        lock=json.loads((ROOT/'examples/open-projects/overvoltage-lock.json').read_text())
        for relative,expected in lock['files'].items():
            if relative.startswith('mag/'):
                path=inputs/'source-layout'/relative.removeprefix('mag/')
                if not path.is_file() or file_digest(path)!=expected:
                    raise ValueError('The copied native source changed: '+relative)
        state['setup'] = inputs / 'setup.tcl'
        return dict(source_qualification=file_digest(inputs / 'qualification.json'),
                    reference_sha256=file_digest(manifest), process=upstream['process'])
    report.case('detector-prerequisites', preflight)
    if 'setup' not in state:
        report.blocked('detector-exchange', 'Detector prerequisites failed.', True)
        return report.finish()
    def schematic_exchange():
        from icstudio.external_tools import xschem_netlist
        from scripts.qualify_open_project import normalized_diodes
        dest=report.output/'independent-xschem'
        source=inputs/'xschem-roundtrip'/(state['top']+'.sch')
        record=xschem_netlist(source,dest,state['xschem'],mode='lvs')
        decks=list((dest/'netlists').glob('*.spice'))
        if len(decks)!=1:raise ValueError('Expected one independent Xschem netlist.')
        text=decks[0].read_text()
        # Xschem comments the root subcircuit for standalone simulation. Its
        # own ordered interface becomes the explicit LVS root, unmodified.
        text=re.sub(r'(?im)^\*\*\s*(\.subckt\s+'+re.escape(state['top'])+r'\b[^\n]*)',r'\1',text)
        text=re.sub(r'(?im)^\*\*\s*(\.ends\b[^\n]*)',r'\1',text)
        target=dest/'independent-lvs.spice';atomic_write(target,normalized_diodes(text))
        return dict(engine=record['tool'],comparison=compare_lvs(state['netgen'],state['reference'],target,
            state['top'],state['setup'],dest/'comparison'))
    report.case('detector-independent-xschem-netlisting',schematic_exchange)
    def routes():
        from icstudio.engines import magic_import
        native_source=inputs / 'source-layout' / (state['top'] + '.mag')
        flat=report.output / 'explicit-flat-import'
        project=magic_import(state['magic'],native_source,state['technology'],flat,flatten=True)
        state['flat_source']=flat / 'imported.gds'
        state['paths'], details = layout_routes(state['flat_source'], report.output / 'detector', state['klayout'])
        details.update(hierarchy_mode='explicitly flattened before stream conversion', native_project=project)
        return details
    report.case('detector-layout-exchange', routes)
    def magic_exchange():
        if 'paths' not in state:raise Blocked('Layout exchange did not complete.')
        target = report.output / 'detector/magic-roundtrip.gds'
        result = magic_roundtrip(state['flat_source'], target, state['top'],
                                 state['technology'], state['magic'], report.output / 'magic-native')
        # Magic may normalize cell geometry. Record its physical comparison
        # independently below; do not silently declare bit/geometry identity.
        state['paths']['magic-roundtrip'] = target
        try:
            result['geometry'] = geometry_equal(state['flat_source'], target)
        except ValueError as exc:
            result['geometry'] = dict(status='changed', reason=str(exc))
        return result
    report.case('detector-magic-save-reopen', magic_exchange)
    state.setdefault('paths', {})['source-mag'] = inputs / 'source-layout' / (state['top'] + '.mag')
    def verify(name, path, expect=True):
        folder = report.output / 'physical' / name
        # Magic consumes GDS. Convert OASIS independently before reading it.
        if path.suffix == '.oas':
            target = report.output / 'physical' / (name + '.gds')
            external_stream(path, target, state['klayout'], report.output / ('convert-' + name))
            geometry_equal(path, target, text_presentation=False)
            path = target
        result = magic_verify(path, state['top'], state['technology'], folder, state['magic'],input_style='sky130()',
                              pin_layers=SKY130_PIN_LAYERS,label_layers=SKY130_LABEL_LAYERS)
        comparison = compare_lvs(state['netgen'], state['reference'], folder / 'extracted.spice',
                                 state['top'], state['setup'], folder / 'lvs', expect_match=expect)
        result['lvs'] = comparison
        return result
    for name, path in state.get('paths', {}).items():
        def action(name=name, path=path):
            result = verify(name, path)
            # Separate the geometry/electrical exchange verdict from source-rule closure.
            state.setdefault('physical', {})[name] = result
            return result
        report.case('detector-' + name + '-fresh-lvs', action)
    def full_drc():
        records = state.get('physical', {})
        if len(records) != len(state.get('paths', {})) or not records:
            raise Blocked('Not every exchanged layout completed verification.')
        bad = {name: row['drc'] for name, row in records.items() if row['drc']['count']}
        if bad:
            atomic_write(report.output / 'drc-findings.json', json.dumps(bad, indent=2))
            raise ValueError('Full DRC found violations: ' + ', '.join(f'{n}={r["count"]}' for n, r in bad.items()))
        return dict(layouts=len(records), violations=0)
    report.case('detector-full-drc', full_drc)
    def hierarchical_diagnostic():
        result=verify('hierarchical-diagnostic',inputs / 'geometry-roundtrip.gds')
        if result['drc']['count']:raise ValueError('Hierarchical stream conversion has DRC findings; inspect physical/hierarchical-diagnostic.')
        return result
    report.case('detector-studio-hierarchical-stream',hierarchical_diagnostic)
    def raw_magic_stream():
        folder=report.output/'physical/raw-magic-stream'
        result=magic_verify(inputs/'magic-import/imported.gds',state['top'],state['technology'],folder,state['magic'],
                            input_style='sky130()',pin_layers=SKY130_PIN_LAYERS,label_layers=SKY130_LABEL_LAYERS)
        if result['drc']['count']:
            raise ValueError(f"Raw hierarchical Magic stream has {result['drc']['count']} DRC findings. See physical/raw-magic-stream/physical.json.")
        result['lvs']=compare_lvs(state['netgen'],state['reference'],folder/'extracted.spice',state['top'],state['setup'],folder/'lvs')
        return result
    report.case('detector-raw-magic-hierarchical-stream',raw_magic_stream,required=False)
    def fault_inputs():
        if 'original' not in state.get('physical',{}) or state['physical']['original']['drc']['count']:
            raise Blocked('The physical baseline must pass DRC and LVS before injecting faults.')
        state['faults'] = physical_faults(state['flat_source'], report.output / 'faults')
        return {k: file_digest(p) for k, p in state['faults'].items()}
    report.case('detector-physical-fault-inputs', fault_inputs)
    for name, path in state.get('faults', {}).items():
        def action(name=name, path=path):
            folder = report.output / 'physical' / ('fault-' + name)
            result = magic_verify(path, state['top'], state['technology'], folder, state['magic'],input_style='sky130()',
                                  pin_layers=SKY130_PIN_LAYERS,label_layers=SKY130_LABEL_LAYERS)
            if name == 'narrow-metal':
                if not any('width' in rule.lower() for rule in result['drc']['rules']):
                    raise ValueError('The narrow-metal fault did not produce a width-rule finding.')
            else:
                result['lvs'] = compare_lvs(state['netgen'], state['reference'], folder / 'extracted.spice',
                                           state['top'], state['setup'], folder / 'lvs', expect_match=False)
            return result
        report.case('detector-reject-' + name, action)
    report.blocked('virtuoso-exchange', 'Requires an actual licensed Virtuoso installation and matching PDK; open-source results do not qualify this route.')
    report.blocked('installed-windows-physical-tools', 'Magic/Netgen execution is qualified on Linux here. Native Windows/managed remote execution must be exercised separately.')
    return report.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detector', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    for name in ('magic', 'netgen', 'klayout', 'xschem'):
        parser.add_argument('--' + name, default=shutil.which(name))
    return qualify(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
