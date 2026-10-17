"""Explicit local correction of the public IHP NPN connected-region search.

Magic's bloat-all starts at the first intersecting tile on a different plane.
Intersect the seed with active first so every disconnected collector/emitter
component is visited. Keep the original operands, distances and illegal mask.
"""
import hashlib

RELATIVE_PATH = 'libs.tech/magic/ihp-sg13g2-cifout.tech'
BASE_SHA256 = 'b972c6d07557e0147462ad533aaf2f3aea14404437f800a1f8fc96ba13086dc8'
ORIGINAL = b' templayer npnactive npn\n\tbloat-all npngrow (*ndiff,nemit)/a'
REPLACEMENT = b''' # IC Design Studio: seed every intersecting active component separately.
 # bloat-all otherwise starts with only the first tile under a broad seed.
 templayer icstudio_npn_active (*ndiff,nemit)/a
 templayer icstudio_npn_seed npngrow
\tand icstudio_npn_active
 templayer npnactive npn
\tbloat-all icstudio_npn_seed icstudio_npn_active'''


def corrected(content):
    if hashlib.sha256(content).hexdigest() != BASE_SHA256 or content.count(ORIGINAL) != 1:
        raise ValueError('NPN correction requires the exact locked IHP MIM-corrected rule file.')
    return content.replace(ORIGINAL, REPLACEMENT)
