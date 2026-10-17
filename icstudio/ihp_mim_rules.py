"""Versioned local correction of IHP's Magic MIM connectivity calculation.

The upstream Apache-2.0 rule and 600 nm limit are retained. Fresh CIF planes
avoid the native tile visitation state shared by full DRC and bloat-all.
This is an explicit new package, never a mutation of an installed revision.
"""
import hashlib

RELATIVE_PATH='libs.tech/magic/ihp-sg13g2-cifout.tech'
BASE_SHA256='e27c499850864e66ef3b8063132bdcf0a002925592bd60d871447fb3759eaa37'
CORRECTED_SHA256='b972c6d07557e0147462ad533aaf2f3aea14404437f800a1f8fc96ba13086dc8'
SOURCE_COMMIT='5e6d592e4002946a4616f798c357f0f3c06cf3b6'
SOURCE_URL=f'https://github.com/IHP-GmbH/IHP-Open-PDK/blob/{SOURCE_COMMIT}/ihp-sg13g2/libs.tech/magic/ihp-sg13g2-cifout.tech'
ORIGINAL=b' templayer metal6_connects_mimcap\n\tbloat-all mimcc/m6 (*metal6)/m6'
REPLACEMENT=b''' # IC Design Studio: isolate this traversal from native DRC tile marks.
 # The same contact and metal sets are copied to fresh CIF planes first.
 templayer icstudio_mim_contact_seed mimcc/m6
 templayer icstudio_mim_top_metal (*metal6)/m6
 templayer metal6_connects_mimcap
\tbloat-all icstudio_mim_contact_seed icstudio_mim_top_metal'''


def corrected(content):
    if hashlib.sha256(content).hexdigest()!=BASE_SHA256 or content.count(ORIGINAL)!=1:
        raise ValueError('The IHP MIM correction requires the exact locked upstream rule file.')
    result=content.replace(ORIGINAL,REPLACEMENT)
    if hashlib.sha256(result).hexdigest()!=CORRECTED_SHA256:
        raise ValueError('IHP MIM correction differs from its locked recipe.')
    return result
