"""Supplement IHP Mn.e/f with transparent subset separation.

The complete original public decks remain separate, unchanged checks. Their
wide-metal subset can shield itself from separation measurements. This recipe
retains the pinned morphology, limits and layer mapping, changing only shielding.
"""
import hashlib
import json
from pathlib import Path

from .model import atomic_write, file_digest

RECIPE = 'ihp-metal-spacing-transparent-v1'
MARKER = 'ICSTUDIO_IHP_METAL_SPACING_COMPLETED_V1'
SOURCE_FILES = ('rule_decks/beol/5_17_metaln.drc', 'rule_decks/layers_def.drc',
                'sg13g2_tech_mod.json', 'rule_decks/sg13g2_tech_default.json')
RULES = ('M2.e', 'M2.f', 'M3.e', 'M3.f', 'M4.e', 'M4.f', 'M5.e', 'M5.f')
DECK = '''# IC Design Studio supplemental IHP Mn.e/f check, version 1.
# Derived from IHP PDK Authors' Apache-2.0 5_17_metaln.drc at
# 5e6d592e4002946a4616f798c357f0f3c06cf3b6. Original notices and license
# remain in the adjacent authenticated public rules bundle.
# Only shielding differs from the selected public expressions.
require 'json'
source($input, $topcell)
report('IC Design Studio IHP metal spacing supplement v1', $report)
flat
threads(1)
rules = JSON.parse(File.read($drc_json_default)).fetch('drc_rules')
rules.merge!(JSON.parse(File.read($drc_json)).fetch('drc_rules'))
[[2, 10], [3, 30], [4, 50], [5, 67]].each do |number, layer|
  metal = input(layer, 0)
  ['e', 'f'].each do |suffix|
    name = "M#{number}.#{suffix}"
    width = rules.fetch("Mn_#{suffix}_w").to_f / 2
    length = rules.fetch("Mn_#{suffix}_cr").to_f
    distance = rules.fetch("Mn_#{suffix}").to_f
    wide = metal.sized(-width.um).sized(width.um)
    findings = metal.sep(wide, distance.um, transparent,
                         projection_limits(length.um + 0.001.um, nil))
    findings.output(name, "Supplemental #{name}: transparent wide-metal separation")
    puts "ICSTUDIO_IHP_METAL_SPACING_RULE #{name}"
  end
end
puts 'ICSTUDIO_IHP_METAL_SPACING_COMPLETED_V1'
'''


def run(executable, source, top, output, bundle):
    from .engines import execute
    from .ihp_klayout_drc import assets, read_report

    source, output, bundle = Path(source).resolve(), Path(output).resolve(), Path(bundle).resolve()
    originals = assets(bundle)
    inputs = {name: file_digest(originals[name]) for name in SOURCE_FILES}
    before = file_digest(source)
    output.mkdir(exist_ok=False)
    deck = output / 'check.drc'
    atomic_write(deck, DECK)
    deck_hash = hashlib.sha256(DECK.encode()).hexdigest()
    if file_digest(deck) != deck_hash:
        raise ValueError('Supplemental IHP metal-spacing recipe differs.')
    report = output / 'findings.lyrdb'
    command = [str(executable), '-b', '-r', str(deck)]
    settings = dict(input=str(source), topcell=top, report=str(report),
                    drc_json=str(bundle / 'sg13g2_tech_mod.json'),
                    drc_json_default=str(bundle / 'rule_decks/sg13g2_tech_default.json'))
    for key, value in settings.items():
        command += ['-rd', key + '=' + str(value)]
    atomic_write(output / 'command.json', json.dumps(command, indent=2))
    try:
        log = execute(command, output, timeout=600)
    except Exception as error:
        atomic_write(output / 'console.log', str(error))
        raise
    atomic_write(output / 'console.log', log)
    if (log.splitlines().count(MARKER) != 1 or
            any(log.splitlines().count('ICSTUDIO_IHP_METAL_SPACING_RULE ' + name) != 1 for name in RULES) or
            not report.is_file()):
        raise ValueError('Supplemental IHP metal-spacing checks did not finish.')
    parsed = read_report(report)
    if parsed['top'] != top:
        raise ValueError('Supplemental IHP metal-spacing report belongs to another top cell.')
    assets(bundle)
    if file_digest(source) != before or file_digest(deck) != deck_hash:
        raise ValueError('Supplemental IHP metal-spacing input or recipe changed.')
    return dict(name='metal-spacing', entry='metal-spacing/check.drc',
                recipe=RECIPE, recipe_sha256=deck_hash, source_inputs=inputs,
                rules=list(RULES), violations=parsed['count'],
                report='metal-spacing/findings.lyrdb', report_sha256=parsed['report_sha256'],
                categories=sorted({f['rule'] for f in parsed['findings']}))
