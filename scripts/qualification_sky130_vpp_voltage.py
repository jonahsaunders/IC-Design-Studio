"""Source-defined VPP plate-voltage screen; no simulator or device acceptance.

This numerical check only concerns abs(V(c0)-V(c1)). It does not establish
absolute node ratings, body/shield/common-mode validity or a complete envelope.
"""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path

CONTRACT_SHA256 = '5f859be9fae8a362b76bf8e84960c3326097301f83a00c66006fc38837b598bd'
SOURCE_LOCK_SHA256 = '2051fe4d464f66a3bf92c957da76a11966b5c9d9d77f657508d2f43b663be8d0'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(root, relative, expected):
    root = Path(root).resolve()
    path = (root/relative).resolve()
    require(path.is_relative_to(root) and path != root and path.is_file(),
            'Missing or unsafe VPP resource: '+relative)
    raw = path.read_bytes()
    require(sha(raw) == expected, 'Changed VPP resource: '+relative)
    return raw


def number(value):
    # Bound representation work; these are parser bounds, not physical ratings.
    require(type(value) in (int, float, Decimal), 'VPP coordinates must be finite numeric volts, excluding booleans.')
    if isinstance(value, Decimal):
        require(value.is_finite(), 'VPP coordinates must be finite numeric volts.')
        parts = value.as_tuple()
        require(len(parts.digits) <= 1100 and -1100 <= parts.exponent <= 309 and
                value.adjusted() <= 309, 'VPP numeric literal exceeds parser bounds.')
        return value
    if isinstance(value, int):
        require(value.bit_length() <= 1024, 'VPP numeric literal exceeds parser bounds.')
        return Decimal(value)
    require(math.isfinite(value), 'VPP coordinates must be finite numeric volts.')
    return Decimal.from_float(value)


def decimal_literal(token):
    # Keep JSON decimal coordinates exact, including underflow and values closer
    # to a boundary than one binary-float ULP. Bounds limit parsing, not ratings.
    require(len(token) <= 2048, 'VPP numeric literal exceeds parser bounds.')
    return number(Decimal(token))


def exact_json(value):
    """Emit finite Decimal values as exact JSON numbers, never rounded floats."""
    if isinstance(value, Decimal):
        return str(number(value))
    if isinstance(value, dict):
        return '{'+', '.join(json.dumps(key)+': '+exact_json(item) for key, item in value.items())+'}'
    if isinstance(value, (list, tuple)):
        return '['+', '.join(exact_json(item) for item in value)+']'
    return json.dumps(value, allow_nan=False)


class VppVoltageContract:
    def __init__(self, contract_root, package_root):
        self.root, self.package_root = Path(contract_root).resolve(), Path(package_root).resolve()
        raw = checked(self.root, 'contract.json', CONTRACT_SHA256)
        self.contract = json.loads(raw)
        self.lock = json.loads(checked(self.root, 'source-lock.json', SOURCE_LOCK_SHA256))
        self.authenticated = self._authenticate()
        self.models = {row['model']: key for key, row in self.contract['bindings'].items()}
        require(len(self.models) == len(self.contract['bindings']) == 9,
                'Ambiguous VPP catalog identities.')

    def _authenticate(self):
        require(json.loads(checked(self.root, 'contract.json', CONTRACT_SHA256)) == self.contract and
                json.loads(checked(self.root, 'source-lock.json', SOURCE_LOCK_SHA256)) == self.lock,
                'VPP contract facts changed after loading.')
        for relative, identity in self.lock['files'].items():
            raw = checked(self.root/'sources', relative, identity['sha256'])
            git_blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            require(len(raw) == identity['bytes'] and git_blob == identity['git_blob_sha1'],
                    'Changed VPP primary-source identity.')
        raw = (self.package_root/'package.json').read_bytes()
        package_sha = sha(raw)
        allowed = {self.contract['package_manifest_sha256']: self.contract['package_revision'],
                   self.contract['corrected_package_manifest_sha256']: self.contract['corrected_package_revision']}
        require(package_sha in allowed, 'Unreviewed VPP application package.')
        package = json.loads(raw)
        require(package['revision'] == allowed[package_sha], 'Changed VPP package revision.')
        catalog = package['technology']['simulation']['catalog']
        for key, row in self.contract['bindings'].items():
            binding = catalog[key]
            require(not binding['unavailable'] and binding['model'] == row['model'] and
                    binding['model_source'] == row['model_source'] and
                    binding['pin_order'] == row['catalog_pins'] and
                    binding['parameters'] == row['parameters'], 'Changed VPP catalog binding: '+key)
            for relative, expected in ((row['model_source'], row['model_source_sha256']),
                                       (row['symbol'], row['symbol_sha256'])):
                require(package['files'][relative] == expected, 'Changed VPP manifest asset.')
                checked(self.package_root, relative, expected)
        for key, row in self.contract['unavailable'].items():
            require(catalog[key]['model'] == row['model'] and catalog[key]['unavailable'] == row['reason'],
                    'Required unavailable VPP binding changed.')
        return dict(package_manifest_sha256=package_sha, package_revision=package['revision'])

    def screen(self, point):
        require(isinstance(point, dict), 'Expected one VPP point object.')
        identifiers = set(point) & {'model', 'catalog_key'}
        require(len(identifiers) == 1 and set(point) == identifiers | {'vc0', 'vc1'},
                'Require exactly one model/catalog_key and vc0/vc1 in volts; no inferred body/shield limits.')
        field = next(iter(identifiers)); identifier = point[field]
        require(isinstance(identifier, str), 'VPP identifier must be exact text.')
        if identifier in self.contract['unavailable'] or identifier in {
                row['model'] for row in self.contract['unavailable'].values()}:
            raise ValueError('Required VPP model is unavailable; no substitute or alias is selected.')
        key = self.models.get(identifier) if field == 'model' else identifier
        require(key in self.contract['bindings'], 'Unreviewed exact VPP identity; no name-based alias.')
        first, second = number(point['vc0']), number(point['vc1'])
        # Preserve representable one-ULP violations and common-mode subtraction;
        # no voltage tolerance or conversion to a lower-precision float is used.
        with localcontext() as context:
            # Include every decimal position in the subtraction, not merely
            # 1100 significant digits: a tiny opposite plate can cross 5.5 V.
            context.prec = max(1100, max(first.adjusted(), second.adjusted()) -
                               min(first.as_tuple().exponent, second.as_tuple().exponent) + 2)
            differential = first-second
            within = abs(differential) <= Decimal(self.contract['quantity']['upper'])
        current = self._authenticate()
        require(current == self.authenticated, 'VPP package changed after loading the contract.')
        row = self.contract['bindings'][key]
        return dict(schema=1, catalog_key=key, model=row['model'],
            coordinates_v={'c0': point['vc0'], 'c1': point['vc1']},
            signed_plate_difference_v=str(differential),
            plate_voltage_status='WITHIN_DOCUMENTED_LIMITS' if within else 'OUTSIDE_DOCUMENTED_LIMITS',
            applied_quantity=self.contract['quantity'], source=self.contract['source'],
            source_model_pins=row['source_pins'], catalog_pins=row['catalog_pins'],
            model_source=row['model_source'], model_source_sha256=row['model_source_sha256'],
            **current, contract_sha256=CONTRACT_SHA256, source_lock_sha256=SOURCE_LOCK_SHA256,
            evidence_kind='DECLARED_POINT_STATIC_SCREEN', native_execution=False,
            body_voltage_status='NOT_ESTABLISHED', shield_voltage_status='NOT_ESTABLISHED',
            common_mode_status='NOT_ESTABLISHED', temperature_status='NOT_ESTABLISHED',
            reliability_status='NOT_ESTABLISHED', absolute_ratings_status='NOT_ESTABLISHED',
            full_operating_envelope_status='NOT_ESTABLISHED',
            capacitance_accuracy_status='NOT_ESTABLISHED', simulator_restriction=False,
            qualified=False, chunk_complete=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    require(args.input.stat().st_size <= 1024*1024, 'VPP point input exceeds parser bounds.')
    points = json.loads(args.input.read_bytes(), parse_float=decimal_literal)
    require(isinstance(points, list) and 0 < len(points) <= 1000, 'Expected 1–1000 VPP points.')
    contract = VppVoltageContract(args.contract, args.package)
    results = [contract.screen(point) for point in points]
    print(exact_json(dict(schema=1, results=results, qualified=False, chunk_complete=False)))
    raise SystemExit(0 if all(row['plate_voltage_status'] == 'WITHIN_DOCUMENTED_LIMITS' for row in results) else 2)
