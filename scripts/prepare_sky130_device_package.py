"""Build default SKY130 device fixes without changing other corner selections.

NPN t/s/f inputs are loaded only inside the existing tt/ss/ff sections. Other
sections retain their exact content: no missing NPN mapping is inferred.
"""
import argparse,hashlib,json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import digest,file_digest
from scripts.prepare_sky130_bipolar_qualification import prepare as prepare_bipolar
from scripts.sky130_qualification_source import original_package


def prepare(source,output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new device package directory.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with original_package(source) as original, tempfile.TemporaryDirectory(prefix='icstudio-device-',dir=output.parent) as tmp:
        stage=Path(tmp)/'package';parent=prepare_bipolar(original,stage)
        base=json.loads((original/'package.json').read_bytes());package=json.loads((stage/'package.json').read_bytes())
        rel='libs.tech/ngspice/sky130.lib.spice';old=(original/rel).read_bytes();updated=old
        for section,npn in [('tt','t'),('ss','s'),('ff','f')]:
            marker=('.lib '+section+'\n').encode()
            if updated.count(marker)!=1:raise ValueError('Unexpected original SKY130 corner definition.')
            addition=('* IC Design Studio: load the public NPN '+npn+' corner parameters.\n.lib "icstudio-npn-corners.lib" '+npn+'\n').encode()
            updated=updated.replace(marker,marker+addition)
        package['technology']['simulation']['includes']=base['technology']['simulation']['includes']
        provenance=dict(schema=1,source_revision=base['revision'],source_manifest_sha256=file_digest(original/'package.json'),
            tested_bipolar_package=parent,original_library_sha256=hashlib.sha256(old).hexdigest(),corrected_library_sha256=hashlib.sha256(updated).hexdigest(),
            change='Keep all original corner selections. Load the same reviewed public NPN t/s/f inputs inside tt/ss/ff, instead of restricting the entire package to these sections. Explicit resistor parallel factors are retained.',
            scope='Deterministic NPN nominal/tt, ss and ff only. Other existing corner contents are unchanged; mixed/mismatch/Monte Carlo NPN behavior remains unqualified. No full device or process qualification.',
            license='Original Apache-2.0 notices and locked source copies retained; changed library identifies the modification.')
        additions={rel:updated,'ICSTUDIO-DEVICE-PACKAGE.json':(json.dumps(provenance,indent=2)+'\n').encode()}
        for rel,data in additions.items():(stage/rel).write_bytes(data);package['files'][rel]=hashlib.sha256(data).hexdigest()
        package['technology']['revision']='';package['revision']=package['technology']['revision']=digest(dict(files=package['files'],technology=package['technology']))[:16]
        (stage/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
        os.rename(stage,output)
    return dict(id=package['id'],revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),files=len(package['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/sky130A');p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
