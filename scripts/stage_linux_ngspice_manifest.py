"""Bind the packaged Linux simulator to its reviewed executable and inputs."""
import hashlib
import json
from pathlib import Path

ENGINE_SHA256 = '820658317b0b54035208da41936fd6871ce924036e5ea4113a4168b821b7fc45'
SPINIT_SHA256 = 'cef1e2ffa61cf0fae3afe80afa94800df8fadc67df3178aa7f1e3216ccfb0e91'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_hash(engine):
    engine = Path(engine)
    from scripts import stage_linux_ngspice as corrected
    if engine.is_file() and sha(engine) == corrected.ENGINE_SHA256:
        corrected.verify(engine.parent.parent)
        if engine != engine.parent.parent/'runtime/ngspice':
            raise ValueError('Corrected engine is outside its verified input layout.')
        return corrected.ENGINE_SHA256
    if (engine.is_symlink() or engine.is_junction() or not engine.is_file() or
            engine.read_bytes()[:4] != b'\x7fELF' or sha(engine) != ENGINE_SHA256):
        raise ValueError('Unreviewed Linux ngspice source executable.')
    return ENGINE_SHA256


def stage(folder, source_sha256):
    """Write a manifest for the actual frozen runtime, after PyInstaller."""
    folder = Path(folder)
    if any(path.is_symlink() or path.is_junction() for path in (folder, *folder.parents)):
        raise ValueError('Linked Linux runtime directory.')
    from scripts import stage_linux_ngspice as corrected
    if source_sha256 == corrected.ENGINE_SHA256:
        files = corrected.verify_deployed(folder)
        record = dict(schema=2, platform='linux', source_engine_sha256=source_sha256,
                      final_engine_sha256=files['ngspice'], files=files,
                      source_archive_sha256=corrected.ARCHIVE_SHA256,
                      source_manifest_sha256=corrected.MANIFEST_SHA256)
        (folder/'runtime-manifest.json').write_bytes(json.dumps(record, indent=2).encode())
        return record
    if source_sha256 != ENGINE_SHA256:
        raise ValueError('Unreviewed Linux ngspice source identity.')
    files = {}
    for path in sorted(folder.iterdir()):
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise ValueError('Linked or non-file Linux runtime input: ' + path.name)
        if path.name != 'runtime-manifest.json':
            files[path.name] = sha(path)
    if files.get('ngspice') != ENGINE_SHA256 or (folder/'ngspice').read_bytes()[:4] != b'\x7fELF':
        raise ValueError('Frozen Linux ngspice executable differs from reviewed source.')
    if files.get('spinit') != SPINIT_SHA256:
        raise ValueError('Frozen Linux ngspice initializer differs from reviewed source.')
    record = dict(schema=1, platform='linux', source_engine_sha256=source_sha256,
                  final_engine_sha256=files['ngspice'], files=files)
    (folder/'runtime-manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record
