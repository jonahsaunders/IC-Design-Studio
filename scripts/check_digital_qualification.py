"""Require installation evidence for the exact payload and packaging backend."""
from icstudio.model import digest


def validate(record, manifest, backend, system):
    if not isinstance(record,dict) or record.get('sha256')!=manifest['sha256']:
        raise ValueError('The digital runtime acceptance record belongs to another archive.')
    acceptance=record.get('acceptance')
    if not isinstance(acceptance,dict) or acceptance.get('manifest')!=digest(manifest):
        raise ValueError('The digital runtime acceptance record belongs to another manifest.')
    if acceptance.get('backend')!=backend:
        raise ValueError('The digital backend changed after acceptance. Qualify this source before packaging.')
    runtime=acceptance.get('runtime')
    if (not isinstance(runtime,dict) or runtime.get('sha256')!=manifest['sha256']
            or runtime.get('kind')!=('wsl' if system=='Windows' else 'linux')):
        raise ValueError('The digital runtime must pass acceptance on this build platform before packaging.')
    if 'platforms' in manifest and acceptance.get('platforms')!=manifest['platforms']:
        raise ValueError('Not every included digital platform passed acceptance. Qualify the complete package.')
    if 'platform_corners' in manifest:
        from icstudio.digital_platform import validate_coverage
        validate_coverage(manifest['platform_corners'],manifest.get('platforms',[]))
        if acceptance.get('platform_corners')!=manifest['platform_corners']:
            raise ValueError('Not every included timing corner passed acceptance. Qualify the complete package.')
    return acceptance
