"""Native worker for the bounded IHP signal-clearance fill recipe."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from .model import atomic_write, file_digest
from .digital_ihp_geometry import (PATTERNS, clearance, conductors, generation,
                                   secondary, electrical_view, compare_native, require)


def execute(request):
    import klayout.db as k
    resources = Path(request['resources']).resolve()
    preparation = resources/'preparation.json'
    require(file_digest(preparation) == request['preparation_sha256'], 'IHP fill resource binding changed.')
    prepared = json.loads(preparation.read_text())
    require(prepared['recipe'] == 'ihp-signal-clearance-block-fill-v1', 'Unsupported fill recipe.')
    for item in prepared['files']:
        path = (resources/item['path']).resolve()
        require(path.is_relative_to(resources) and file_digest(path) == item['sha256'], 'Captured fill input changed.')
    # Helpers are part of the hash-verified platform, copied by the ordinary
    # platform staging path on Windows and Linux.
    sys.path.insert(0,str(resources/'helpers'))
    from scripts.prepare_ihp_block_fill import validate_input, merge_fill, masks
    from scripts.check_ihp_fill_rules import audit
    from scripts.ihp_magic_export import export
    source=Path(request['gds']); inventory_path=Path(request['inventory'])
    require(file_digest(source)==request['gds_sha256'] and file_digest(inventory_path)==request['inventory_sha256'],
            'An IHP fill input changed.')
    inventory=json.loads(inventory_path.read_text()); top=inventory['top']
    output=Path(request['output']);require(not output.exists(),'Use a new fill output directory.');output.mkdir(parents=True)
    pattern=request['pattern']; require(pattern in PATTERNS,'Unknown fill pattern.')
    require(subprocess.check_output([request['klayout'],'-v'],text=True,timeout=30).strip()=='KLayout 0.30.5',
            'IHP fill requires the qualified KLayout 0.30.5 engine.')
    engine_version=subprocess.check_output([request['magic'],'--version'],text=True,timeout=30).strip()
    require(engine_version=='8.3.684','IHP fill requires the captured Magic 8.3.684 extractor.')
    layout=k.Layout();layout.read(str(source))
    before,bounds,_=validate_input(layout,top,inventory['die_nm'])
    require(bounds.width()<800000 and bounds.height()<800000,'Complete-chip density needs separate qualification.')
    record=dict(schema=1,recipe=prepared['recipe'],status='running',qualified=False,pattern=pattern,
                source_gds_sha256=file_digest(source),inventory_sha256=file_digest(inventory_path),
                checkpoint_sha256=inventory['checkpoint_sha256'],preparation_sha256=file_digest(preparation),
                engine_sha256={key:file_digest(request[key]) for key in ('klayout','magic')},
                scope='Original-footprint standard-cell block fill. Circuit and floating-component capacitance are unchanged in the pinned nominal extractor. Field calibration, other interconnect conditions and full-chip acceptance remain separate.')
    record['application_sources']={name:file_digest(Path(__file__).with_name(name)) for name in
                                   ('digital_ihp_fill_worker.py','digital_ihp_geometry.py','digital_ihp_inventory.py')}
    def run(name, settings):
        command=[request['klayout'],'-b','-r',str(output/name)]
        for key,value in settings.items():command.extend(['-rd',key+'='+str(value)])
        with (output/(name+'.log')).open('w') as log:
            process=subprocess.run(command,cwd=output,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        require(process.returncode==0,'Native IHP fill operation failed: '+name)
    options=k.SaveLayoutOptions();options.gds2_write_timestamps=False
    try:
        electrical_view(source,inventory,output/'original-electrical.gds')
        export(output/'original-electrical.gds',top,resources/'magic/ihp-sg13g2.tech',request['magic'],output/'original-native')
        native=conductors(output/'original-native'/(top+'.ext'),inventory)
        excluded=clearance(layout,inventory,native)
        require(not excluded.is_empty() and layout.find_layer(10000,0) is None,'Invalid original fill exclusion.')
        aux=k.Layout();aux.read(str(source));aux.top_cell().shapes(aux.layer(10000,0)).insert(excluded)
        aux.write(str(output/'generation-input.gds'),options)
        atomic_write(output/'generate.drc',generation(resources/'macros',pattern))
        run('generate.drc',dict(in_gds=output/'generation-input.gds',out_gds=output/'fill-only.gds'))
        require('IHP_FILL_GENERATION_COMPLETE' in (output/'generate.drc.log').read_text(),'Incomplete fill generation.')
        fill=k.Layout();fill.read(str(output/'fill-only.gds'))
        if PATTERNS[pattern][-1]:
            existing=k.Region(fill.top_cell().begin_shapes_rec(fill.layer(134,22))).merged()
            aux.top_cell().shapes(aux.layer(134,22)).insert(existing);aux.write(str(output/'secondary-input.gds'),options)
            atomic_write(output/'secondary.drc',secondary(resources/'macros'))
            run('secondary.drc',dict(in_gds=output/'secondary-input.gds',out_gds=output/'secondary.gds'))
            extra=k.Layout();extra.read(str(output/'secondary.gds'))
            added=k.Region(extra.top_cell().begin_shapes_rec(extra.layer(134,22))).merged()
            require(added.interacting(existing.sized(3000)).is_empty(),'Secondary fill violates existing top-metal clearance.')
            fill.top_cell().shapes(fill.layer(134,22)).insert(added)
        for region in masks(fill).values():
            require((region & excluded).is_empty(),'New fill enters a protected circuit clearance.')
        counts,density=merge_fill(layout,fill,output/'filled.gds',before,bounds,'p-substrate')
        shutil.copyfile(resources/'sg13g2_maximal.lydrc',output/'sg13g2_maximal.lydrc')
        run('sg13g2_maximal.lydrc',dict(in_gds=output/'filled.gds',report_file=output/'full.lyrdb',fillerRules='true',densityRules='true'))
        items=ET.parse(output/'full.lyrdb').findall('./items/item')
        supplemental=audit(output/'filled.gds',resources/'manual/SG13G2_os_layout_rules.pdf')
        atomic_write(output/'supplemental.json',json.dumps(supplemental,indent=2)+'\n')
        record.update(markers=len(items),density_percent=density,added_polygons=counts)
        require(not items and supplemental['passed'],'IHP fill rules failed; retain the report and select another pattern or floorplan.')
        electrical_view(output/'filled.gds',inventory,output/'filled-electrical.gds',filled=True)
        export(output/'filled-electrical.gds',top,resources/'magic/ihp-sg13g2.tech',request['magic'],output/'filled-native')
        comparison=compare_native(output/'original-native'/(top+'.ext'),output/'filled-native'/(top+'.ext'),inventory)
        record.update(status='generated_and_verified',capacitance=comparison,
                      physical_devices_identical=True,native_lumped_resistance_identical=True,
                      original_circuit_masks_preserved=True,signal_clearance_nm=9000,
                      protected_poly_nodes=len(native['protected_poly']),filled_gds_sha256=file_digest(output/'filled.gds'))
        require(file_digest(source)==request['gds_sha256'] and file_digest(inventory_path)==request['inventory_sha256'],
                'An IHP source changed during fill.')
        return record
    except BaseException as error:
        record.update(status='failed',error=str(error));raise
    finally:
        record['files']={p.relative_to(output).as_posix():file_digest(p) for p in output.rglob('*') if p.is_file()}
        atomic_write(output/'record.json',json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    print(json.dumps(execute(json.loads(Path(sys.argv[1]).read_text()))))
