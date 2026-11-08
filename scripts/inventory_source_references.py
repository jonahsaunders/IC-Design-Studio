"""Exact reviewed documentation/provenance views; no production model claims."""
import hashlib
import re

def require(ok,message):
    if not ok:raise ValueError('Reviewed source reference: '+message)

def reference_facts(text,role):
    """Read source metadata and documentation references without executing text."""
    require(len(text)<=100000 and '\0' not in text,'text size or NUL')
    if role=='version-provenance':
        match=re.fullmatch(r'(\d+\.\d+\.\d+)\n',text);require(match is not None,'unreviewed version record')
        return [dict(kind='source-version-provenance',name='open_pdks',version=match[1],production_model_binding=False)]
    if role=='release-provenance':
        match=re.fullmatch(r'open_pdks ([a-f0-9]{40})\n',text);require(match is not None,'unreviewed release record')
        return [dict(kind='source-release-provenance',name='open_pdks',revision=match[1],independent_build_equivalence=False)]
    require(role in ('release-reference','integration-history','application-help'),'unreviewed reference role')
    rows=[dict(kind='reviewed-documentation-role',name=role,text_sha256=hashlib.sha256(text.encode()).hexdigest(),lines=len(text.splitlines()),production_interface=False,
               scope='Exact reviewed prose/reference source. References and reported values do not establish runtime bindings, measured calibration or qualified device limits.')]
    if role=='release-reference':
        for number,line in enumerate(text.splitlines(),1):
            for match in re.finditer(r'(?<![A-Za-z0-9_./])([A-Za-z][A-Za-z0-9_]*\.(?:va|include|h|txt))(?![A-Za-z0-9_.])',line):
                rows.append(dict(kind='documented-file-reference',name=match[1],line=number,reference_resolved=False))
            for match in re.finditer(r'\b(PSP103VA|PSP103TVA|PSPNQS103VA|JUNCAP200)\b',line):
                rows.append(dict(kind='documented-module-reference',name=match[1],line=number,model_binding_inferred=False))
            diagnostic=re.match(r'(STYLE|WARNING) in file ([A-Za-z0-9_.]+), line (\d+): (.*)',line)
            if diagnostic:
                rows.append(dict(kind='documented-tool-diagnostic',name=diagnostic[1],line=number,referenced_file=diagnostic[2],reported_line=int(diagnostic[3]),
                                 message_sha256=hashlib.sha256(diagnostic[4].encode()).hexdigest(),reproduced=False))
            count=re.fullmatch(r'(Instance parameters|Model parameters|Operating-point variables) \((\d+)\):?',line)
            if count:rows.append(dict(kind='documented-interface-count',name=count[1],line=number,reported_count=int(count[2]),independently_verified=False))
    return rows

REVIEWED = {('ihp-sg13g2', 'IHP-GmbH/IHP-Open-PDK@5e6d592e4002946a4616f798c357f0f3c06cf3b6', 'ihp-sg13g2/libs.tech/verilog-a/psp103/releasenotesPSP103.8.2.txt', 'ihp-sg13g2/libs.tech/verilog-a/psp103/releasenotesPSP103.8.2.txt', None): ('64cd7bc8090e4a2aaa495918f8f9ae44424205934edfd96dde96683135a872be', 'release-reference'), ('gf180-open-pdks', 'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9', 'VERSION', 'VERSION', None): ('6a7d563c85f1020570d94c5b4f40a02a616ac67cab359dc6f8ef465ebaca8744', 'version-provenance'), ('gf180-open-pdks', 'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9', 'gf180mcu/NOTES', 'gf180mcu/NOTES', None): ('86ed244793036b8f6fbc2e8d36a94af5d32f510b9c3f3c894d2b8d65bd1177ba', 'integration-history'), ('gf180-open-pdks', 'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9', 'runtime/characterize_help.txt', 'runtime/characterize_help.txt', None): ('b863ca107babb4d9be15cf09f807fbdeab5a9e1eddd934b64a5a9ee22d1eaea6', 'application-help'), ('gf180-open-pdks', 'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9', 'runtime/lvs_help.txt', 'runtime/lvs_help.txt', None): ('aced12e1607e9020b732d4a5a923773e76ef3fa02e8712d9283f1dadeb1dea7d', 'application-help'), ('gf180-open-pdks', 'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9', 'runtime/manager_help.txt', 'runtime/manager_help.txt', None): ('d0e057e0d2994a0e6f16da6c47a79ed9d0194190446017e44c295f4b9af6523f', 'application-help'), ('gf180-open-pdks', 'fossi-foundation/open-pdks@aa3fc215a80d32437b8cca1cb3fdee819d18c4c9', 'runtime/qflow_help.txt', 'runtime/qflow_help.txt', None): ('aced12e1607e9020b732d4a5a923773e76ef3fa02e8712d9283f1dadeb1dea7d', 'application-help'), ('sky130A', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130A/SOURCES', 'sky130A/SOURCES', 'common.tar.zst'): ('6c1547aacc0cc62da6027853db2c7b0bcd7f380578163b94b0f349f30cffbab4', 'release-provenance'), ('sky130B', 'chipfoundry/volare@sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392', 'sky130B/SOURCES', 'sky130B/SOURCES', 'common.tar.zst'): ('6c1547aacc0cc62da6027853db2c7b0bcd7f380578163b94b0f349f30cffbab4', 'release-provenance')}

def source_reference_views(row,raw):
    """Require exact path, repository, archive and all reviewed source bytes."""
    key=tuple(row.get(k) for k in ('family','repository','repository_path','path','archive'))
    selected=REVIEWED.get(key)
    if selected is None:return None
    require(type(raw) is bytes and hashlib.sha256(raw).hexdigest()==selected[0],'source bytes changed')
    return reference_facts(raw.decode('utf-8'),selected[1])
