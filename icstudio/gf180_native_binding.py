"""Source-locked correction for the public native-threshold symbol typo."""
import hashlib

SYMBOL_SHA256 = 'ab5c69d892be9acba70cbcbf2788dc5a8601be90a11565c9507bae6c74e91fad'
MODEL_SHA256 = frozenset({
    'c08ee93073665b6c1f43a3523bb38d5b561bcee2b7e056a927175f5da8e96ba9',
    '69a7ab877344a6d477fdd11440457f64e7ad88a624504a737a161da463de8bc8',
})


def reviewed_model(symbol, model):
    if hashlib.sha256(symbol).hexdigest() != SYMBOL_SHA256 or hashlib.sha256(model).hexdigest() not in MODEL_SHA256:
        raise ValueError('Unreviewed native-MOS source; select an explicit model adapter.')
    return 'nfet_06v0_nvt'
