"""Validate the bounded, user-approved public-check completion record."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.digital_sky130_public_baseline import PROFILE, REQUIRED
from icstudio.model import digest

PRIOR_NAMES=('sky130-generic-native-2026-10-16','sky130-generic-density-2026-10-16',
             'sky130-application-lvs-2026-10-16','sky130-density-gate-2026-10-16',
             'sky130-application-antenna-2026-10-14')
SOURCES=('icstudio/digital_sky130_public_baseline.py','icstudio/digital_sky130_frame_scope.py',
         'icstudio/digital_sky130_rules.py','icstudio/digital_sky130_rule_worker.py','icstudio/digital_macro.py')


def require(value,message):
    if not value:raise ValueError('SKY130 public baseline: '+message)


def validate(record,root=ROOT):
    root=Path(root)
    require(record.get('schema')==1 and record.get('chunk')==6 and
        record.get('status')=='public-reference-gate-complete' and record.get('chunk_complete') is True and
        record.get('public_baseline_qualified') is True and record.get('qualified') is False and
        record.get('foundry_signoff') is False,'missing bounded completion claim')
    require(record.get('profile')==PROFILE and record.get('profile_sha256')==digest(PROFILE),
            'changed or incomplete baseline/exclusions')
    require(record.get('acceptance_change')==dict(date='2026-10-16',authorized_by='user',
        decision='Yes—qualify the explicit public-check baseline'), 'missing user-approved acceptance boundary')
    sources=record.get('source_files',{})
    require(set(sources)==set(SOURCES),'incomplete implementation bindings')
    for name,sha in sources.items():
        require(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,'implementation changed: '+name)
    prior=record.get('prior_evidence',{})
    require(set(prior)==set(PRIOR_NAMES),'missing reference/fault evidence')
    previous={}
    for name,item in prior.items():
        require(item.get('path')=='docs/validation/'+name+'.json','misbound prior evidence')
        raw=(root/item['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==item.get('sha256'),'changed prior evidence: '+name)
        previous[name]=json.loads(raw)
    native=previous[PRIOR_NAMES[0]]
    controls=native['controls']['controls']
    require(native['policy']==PROFILE['native_geometry'] and native['controls']['status']=='PASS' and len(controls)==12 and
        all(c['status']==c['expected'] for c in controls) and
        {c['name']:c['combined_status'] for c in controls if 'combined_status' in c}==
        {device+'_parallel_'+case:status for device in ('nmos','pmos') for case,status in
            (('valid','PASS'),('missing_implant','FAIL'))},
            'missing native geometry/implant controls')
    devices=previous[PRIOR_NAMES[1]]['transistor_controls']
    require(devices['status']=='PASS' and len(devices['cases'])==4 and
        all(c['matched']==c['expected_match'] and c['drc_count']==0 for c in devices['cases']),
        'missing 1.8 V transistor and width-fault controls')
    require(previous[PRIOR_NAMES[1]]['wrong_stream_control']['status']=='PASS',
            'missing fill stream-mapping fault control')
    lvs=previous[PRIOR_NAMES[2]]['cases']
    require({(r['library'],r['case']) for r in lvs}=={(v,c) for v in ('retained','pvt') for c in ('counter','uart','apb')}
        and len(lvs)==6 and all(r['lvs_status']=='PASS' and r['fault']['rejected'] is True and
        r['windows_export']['changed_native_evidence_rejected'] is True for r in lvs),
        'missing library/reference/connectivity fault controls')
    densities=previous[PRIOR_NAMES[3]]['native']
    require(densities['large-unfilled']['status']=='PASS' and densities['large-unfilled']['density']['full_window_findings']==72
        and densities['large-filled']['status']=='PASS' and densities['large-filled']['density']['full_window_findings']==0,
        'missing density pass/fault pair')
    antenna=next((c for c in previous[PRIOR_NAMES[4]]['filled_cases'] if c['case']=='controls'),{})
    oracle=antenna.get('controls',{})
    require(antenna.get('status')=='FAIL' and antenna.get('violations')==90 and
        oracle.get('status')=='all-antenna-controls-match' and oracle.get('stages')==13 and
        oracle.get('coupons')==178 and oracle.get('accepted_controls')==88 and
        oracle.get('expected_faults')==oracle.get('observed_faults')==90,
        'missing staged antenna pass/fault controls')
    runs=record.get('fresh_runs',{})
    require(set(runs)=={'counter','uart','apb'},'missing fresh generic reference')
    for case,run in runs.items():
        baseline=run.get('baseline',{});qualification=run.get('qualification',{})
        require(run.get('status')=='PASS' and baseline.get('profile')==PROFILE and
            baseline.get('profile_sha256')==digest(PROFILE) and baseline.get('baseline_checks_passed') is True and
            baseline.get('foundry_signoff') is False and baseline.get('complete_rule_coverage') is False and
            baseline.get('missing_checks')==[] and set(baseline.get('evidence',{}))==set(REQUIRED)|{'sky130_fill'},
            'incomplete fresh baseline: '+case)
        require(baseline.get('status')==('public-checks-passed' if case=='counter' else 'surrounding-layout-required') and
            baseline.get('full_windows')==(9 if case=='counter' else 0) and
            baseline.get('density_context_complete') is (case=='counter'), 'changed density context: '+case)
        require(qualification['sky130_native']['categories']==255 and qualification['sky130_native']['markers']==0 and
            qualification['sky130_antenna']['stages']==13 and qualification['sky130_lvs']['matched'] is True,
            'incomplete native checks: '+case)
    exports=record.get('windows_exports',{})
    require(set(exports)==set(runs),'missing portable reference exports')
    for case,item in exports.items():
        require(item.get('status')=='PASS' and item.get('all_artifact_hashes_verified') is True and
            item.get('all_native_evidence_revalidated') is True and
            item.get('baseline')==runs[case]['baseline'] and item.get('rehashed_frame_exemption_rejected') is True,
            'incomplete portable export: '+case)
    tests=record.get('tests',{})
    require(set(tests)=={'win32','linux'} and all(r.get('status')=='PASS' and r.get('tests',0)>=254 and
        r.get('failures')==0 and r.get('errors')==0 for r in tests.values()),'missing cross-platform regressions')
    require(record.get('historical_catalog')==dict(unresolved=302,dispositions_changed=0),
            'historical catalog was silently promoted')
    require(bool(record.get('archive',{}).get('sha256')),'missing retained execution archive')
    return dict(status='public-reference-gate-complete',chunk_complete=True,public_baseline_qualified=True,
                qualified=False,foundry_signoff=False,profile=PROFILE['id'])


if __name__=='__main__':
    print(json.dumps(validate(json.loads((ROOT/'docs/validation/sky130-public-baseline-2026-10-16.json').read_bytes())),indent=2))
