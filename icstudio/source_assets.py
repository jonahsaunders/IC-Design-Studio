"""Lossless text storage for imported schematic and process-model sources."""
import hashlib


def decode(data, kind):
    try:return data.decode('utf-8'),'utf-8'
    except UnicodeDecodeError:
        # Public IHP HBT models contain Latin-1 micro signs in comments. Keep
        # their original bytes for provenance, rather than replacing characters.
        if not kind.startswith('Model') or b'\0' in data:raise
        return data.decode('latin-1'),'latin-1'


def source_bytes(asset):
    encoding=asset.get('encoding','utf-8')
    if encoding not in ('utf-8','latin-1'):raise ValueError('Unsupported imported source encoding.')
    return asset['text'].encode(encoding)


def source_hash(asset):
    return hashlib.sha256(source_bytes(asset)).hexdigest()
