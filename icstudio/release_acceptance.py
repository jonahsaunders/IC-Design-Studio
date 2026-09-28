"""Fail-closed review of consumer desktop observations and exact package bytes."""
import re

TASKS = {
    'install': 'Clean install and launch without a preinstalled EDA toolchain; use a path containing spaces',
    'first_design': 'Place components, obtain a waveform, save, close and reopen the project',
    'scaling': 'Check 100%, 150% and 200% display scaling, keyboard focus and control readability',
    'mixed_monitors': 'Move floating windows between differently scaled monitors; resize every edge and corner',
    'monitor_recovery': 'Save the window arrangement, disconnect a monitor, restart and recover reachable windows',
    'interruption': 'Cancel a simulation, run another successfully, and check recovery after an interrupted session',
    'upgrade_accessibility': 'Upgrade from the previous build; retain user settings and projects; check accessibility',
    'offline_vga': 'Use VGA offline: eight presets, actual audio output, keyboard/Gamepad controls, pause, reload and save/reopen',
}


def blockers(report, commit=None, package_sha256=None, platform=None):
    reasons = []
    build = report.get('build', {})
    package = report.get('package') or {}
    if report.get('acceptance_schema') != 1:
        reasons.append('Use the current acceptance form with stable observation identities.')
    if not build.get('frozen') or build.get('dirty') is not False or not re.fullmatch('[0-9a-f]{40}', build.get('commit', '')):
        reasons.append('A frozen package with an exact clean source commit is required.')
    if commit is not None and build.get('commit') != commit:
        reasons.append('Source commit differs from the release being reviewed.')
    if not package.get('name') or not re.fullmatch('[0-9a-f]{64}', package.get('sha256', '')):
        reasons.append('Identify the tested installer or archive.')
    if package_sha256 is not None and package.get('sha256') != package_sha256:
        reasons.append('Package bytes differ from the observed installer or archive.')
    if report.get('host_class') != 'consumer' or not report.get('environment_notes', '').strip():
        reasons.append('Record the consumer machine and display setup.')
    if report.get('display') not in ('windows', 'xcb', 'wayland') or not report.get('screens'):
        reasons.append('A native display is required; offscreen results do not establish consumer acceptance.')
    if platform is not None and report.get('consumer_platform') != platform:
        reasons.append('Consumer operating system differs from the requested platform.')
    if report.get('consumer_platform') not in ('windows', 'ubuntu'):
        reasons.append('Choose consumer Windows or Ubuntu.')
    elif ((report['consumer_platform']=='windows') != (report.get('display')=='windows') or
          'server' in report.get('os','').lower()):
        reasons.append('The native platform must match the declared consumer operating system.')
    if report.get('automated', {}).get('status') != 'passed':
        reasons.append('Automatic desktop checks have not passed.')
    rows = report.get('observations', [])
    if len(rows) != len(TASKS) or {r.get('id') for r in rows} != set(TASKS):
        reasons.append('All required observations must be retained exactly once.')
    for row in rows:
        if row.get('status') != 'Passed':
            reasons.append(str(row.get('id', 'Unknown observation'))+': '+str(row.get('status', 'Not run')))
    return reasons
