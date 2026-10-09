"""Validate the chunk-4 reference gate without promoting process qualification."""
import hashlib
import json
from pathlib import Path
import re

if __package__:
    from .check_gf180_geometry_acceptance import timing
else:
    from check_gf180_geometry_acceptance import timing


def require(ok, message):
    if not ok: raise ValueError('GF180 density acceptance: '+message)


def identity(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate(record, root):
    root=Path(root)
    require(record.get('schema')==1 and record.get('chunk')==4 and
            record.get('status')=='passed_reference_scope' and record.get('qualified') is False,
            'missing bounded reference acceptance.')
    require(record.get('scope') and record.get('limitations'), 'missing scope boundaries.')
    require(isinstance(record.get('source_commit'), str) and
            re.fullmatch('[0-9a-f]{40}', record['source_commit']) is not None,
            'missing implementation commit.')
    files=record.get('source_files', {})
    require(files and all(identity(h) for h in files.values()), 'missing application source identities.')
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(digest==record.get('backend_sha256'), 'backend source identity differs.')
    require(identity(record.get('runtime_sha256')), 'missing exact runtime.')
    for evidence in record.get('dependencies', []):
        require(identity(evidence.get('sha256')) and
            hashlib.sha256((root/evidence['path']).read_bytes()).hexdigest()==evidence['sha256'],
            'a required evidence dependency changed.')
    require(len(record.get('dependencies', []))>=2, 'missing baseline and independent model evidence.')
    rows=record.get('references', [])
    require(len(rows)==6 and {r['case'] for r in rows}=={v+'-'+d for v in ('c','d') for d in ('counter','uart','apb')},
            'require all six C/D references.')
    for row in rows:
        require(row['rules']=={'main':0,'antenna':0,'density':0} and
                all(type(n) is int for n in row['rules'].values()), 'native findings remain.')
        require(row['fill_squares']=={'counter':911,'uart':2123,'apb':2119}[row['case'].split('-')[1]] and
                row['supplement_checks']==104, 'reference fill or rule coverage changed.')
        for field in ('unchanged_masks','unchanged_inputs','identical_independent_finite_rc_model',
                      'reduced_model_matches','filled_lef_coverage'):
            require(row.get(field) is True, 'missing independent verification: '+field)
        require(row['connectivity']==row['equivalence']=='PASS' and row['logic_fault']=='FAIL',
                'connectivity/function controls are incomplete.')
        require(identity(row.get('record_sha256')) and identity(row.get('macro_sha256')), 'unbound native reference.')
        # Native reports retain the actual paths; the older compact geometry
        # schema retained only their count. Derive it from the captured list.
        native = row['timing']
        for result in [native, *native['corners']]:
            require(isinstance(result.get('paths'), list) and result['paths'],
                    'missing captured timing paths.')
        compact = {**native, 'path_count':len(native['paths']),
            'corners':[{**c, 'path_count':len(c['paths'])} for c in native['corners']]}
        timing(compact, 'gf180' if row['case'].startswith('c-') else 'gf180d')
        require(all(isinstance(c.get('parasitic_annotation'),dict) and
                    c['parasitic_annotation'].get('connected_unannotated_drivers')==[] and
                    c['parasitic_annotation'].get('partially_unannotated_drivers')==[]
                    for c in row['timing']['corners']),
                'post-fill timing annotation is incomplete.')
    audits=record.get('audits', {})
    require(set(audits)=={'windows','linux'}, 'both OS audits are required.')
    for system,audit in audits.items():
        require(audit.get('status')=='six-integrated-fill-references-independently-audited' and
                audit.get('backend')==record['backend_sha256'] and identity(audit.get('sha256')) and
                audit.get('case_digest')==hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'audit scope or source differs: '+system)
    installed=record.get('installed', {})
    require(set(installed)=={'windows','linux'}, 'both installation checks are required.')
    for system,item in installed.items():
        require(item.get('status')=='included-runtime-installation-acceptance-passed' and
                item.get('backend')==record['backend_sha256'] and item.get('runtime_sha256')==record['runtime_sha256'] and
                item.get('digital_checks')==34 and item.get('timing_pairs')==18 and item.get('tool_controls')==7 and
                identity(item.get('sha256')), 'incomplete installed acceptance: '+system)
        require(item.get('audit_status')=='installed-checks-and-six-connectivity-controls-audited' and
                identity(item.get('audit_sha256')) and identity(item.get('archive_sha256')) and
                item.get('archive_verified') is True,
                'missing independent installed audit/archive: '+system)
    archive=record.get('archive', {})
    require(identity(archive.get('sha256')) and archive.get('verified') is True and archive.get('logical_files',0)>0,
            'missing preserved, read-back evidence.')
    hosted=record.get('hosted_runtime', {})
    require(hosted.get('head_sha')==record['source_commit'] and hosted.get('status')=='completed' and
            hosted.get('conclusion')=='success' and identity(hosted.get('sha256')),
            'hosted runtime acceptance is missing or belongs to another source.')
    tests=record.get('tests', {})
    require(tests.get('status')=='passed' and tests.get('count',0)>=1657 and identity(tests.get('sha256')),
            'missing full application validation.')
    return {'status':'reference_gate_complete','chunk':4,'process_qualification':'unqualified'}
