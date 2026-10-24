"""Summarize the explicitly bounded public checks after native evidence validation.

This is an export contract, not a replacement for the underlying validators.
Missing historical checks cannot inherit a baseline pass. Unknown foundry rules
remain excluded explicitly; a small block still needs surrounding layout.
"""
from . import digital_sky130_native as native
from . import digital_sky130_lvs as lvs
from . import digital_sky130_density as density
from . import digital_sky130_antenna as antenna
from . import digital_sky130_rules_lock as rules
from . import digital_sky130_frame_scope as frame
from . import digital_sky130_fill as fill
from .model import clone, digest

PROFILE = dict(
    id='sky130a-hd-public-checks-v1', version=1,
    target='SKY130A five-metal aluminium HD digital blocks; reviewed 1.8 V MOS/diode libraries',
    native_geometry=native.POLICY,
    supplemental_geometry=dict(recipe=rules.RECIPE, source_revision=rules.REVISION,
        source_lock_sha256=rules.SOURCE_LOCK_SHA256, profiles=rules.PROFILES,
        frame_scope_revision=frame.REVIEW['revision']),
    antenna=dict(recipe=antenna.RECIPE, deck_sha256=antenna.DECK_SHA256, stages=list(antenna.STAGES)),
    lvs=lvs.POLICY, density=density.POLICY, optional_fill=fill.RECIPE,
    boundaries='Full public 700 um windows at 70 um steps. Clipped samples are diagnostic; zero full windows requires surrounding layout.',
    exclusions=[
        'Unresolved periphery applicability and x.20 pin-center spacing; no numeric limit is inferred.',
        'Unresolved generated-mask definitions and the historical 302 catalog records.',
        'Final-mask and metal-5 density, clipped-window acceptance and complete-chip density boundaries.',
        'Seal/frame/scribe and complete-chip assembly; upstream native cell filters remain explicit.',
        'Other device families, electrical/corner/timing acceptance, fill coupling, ERC, ESD, IR drop and electromigration.',
        'Foundry signoff, manufacturing acceptance and installer/public-release qualification.',
    ],
)
REQUIRED = ('sky130_native', 'sky130_rules', 'sky130_antenna', 'sky130_lvs',
            'sky130_density', 'physical_checks', 'sky130_isolation')
STATUSES = dict(sky130_native=('PASS',), sky130_rules=('reviewed-profiles-pass',),
    sky130_antenna=('PASS',), sky130_lvs=('PASS',),
    sky130_density=('sampled-full-windows-pass','surrounding-layout-required'),
    physical_checks=('PASS',), sky130_isolation=('PASS','NOT_REQUESTED'),
    sky130_fill=('generated-and-checked',))


def summarize(data, verified, config):
    """Consume only reports returned by digital_flow.validate_result.

    The caller has already re-read native databases, remeasured geometry and
    authenticated each report. Never call this on unvalidated saved PASS fields.
    """
    if data.get('platform', {}).get('name') != 'sky130hd':
        return None
    required = REQUIRED + (('sky130_fill',) if config.get('physical', {}).get('sky130_fill', False) else ())
    missing = [key for key in required if verified.get(key) is None]
    files = data['artifacts']
    evidence = {}
    for key in required:
        report = verified.get(key)
        if report is None:
            continue
        if report.get('status') not in STATUSES[key] or key not in files:
            raise ValueError('SKY130 public baseline has a failed or unbound check: '+key)
        evidence[key] = dict(artifact=key, sha256=files[key]['sha256'], status=report['status'])
    observation = verified.get('sky130_density')
    needs_context = observation is not None and observation['status'] == 'surrounding-layout-required'
    full_windows = observation['full_windows'] if observation is not None else None
    if observation is not None and (type(full_windows) is not int or full_windows < 0 or
            needs_context != (full_windows == 0) or observation.get('full_window_findings') != 0):
        raise ValueError('SKY130 public baseline has inconsistent density evidence.')
    status = ('incomplete' if missing else 'surrounding-layout-required' if needs_context else 'public-checks-passed')
    return dict(schema=1, profile=clone(PROFILE), profile_sha256=digest(PROFILE), status=status,
        baseline_checks_passed=not missing, density_context_complete=not missing and not needs_context,
        foundry_signoff=False, complete_rule_coverage=False,
        top=config['top'], platform_fingerprint=data['platform']['fingerprint'],
        gds_sha256=files['gds']['sha256'], checkpoint_sha256=files['checkpoint']['sha256'],
        missing_checks=missing, full_windows=full_windows, evidence=evidence)
