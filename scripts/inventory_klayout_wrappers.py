"""Six exact reviewed KLayout wrappers/stubs, never a Ruby/DSL execution claim.

Only pinned source identities are accepted. Literal include references are not
resolved or executed; logging/empty stubs do not supply device rules. The macro
reuses the existing static declaration reader, not a Ruby interpreter.
"""
import hashlib
from pathlib import PurePosixPath
import posixpath
import re
import xml.etree.ElementTree as ET


def require(ok, message):
    if not ok:
        raise ValueError('KLayout wrapper inventory: '+message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


REVIEWED = {('ihp-sg13g2', 'IHP-GmbH/IHP-Open-PDK@5e6d592e4002946a4616f798c357f0f3c06cf3b6', 'ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/devices_connections.lvs', 'ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/devices_connections.lvs', None, '100644'): ('f8ddc90801d104b0a517ca90773c7f03b13b95f4bac95b77ebcf96f53513801b', '0d9c923fbc51997add381aaf8977ff5879a110c7', 2447, 'dependency-wrapper'), ('ihp-sg13g2', 'IHP-GmbH/IHP-Open-PDK@5e6d592e4002946a4616f798c357f0f3c06cf3b6', 'ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/mos_connections.lvs', 'ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/mos_connections.lvs', None, '100644'): ('f53e17c1f315f49fc973b8ec949ae343e2bb99c2862a51acdaa3f37f49907770', 'ca676a72d86a701ba1daddbf53b2053b0f7708c3', 951, 'logger-only-stub'), ('ihp-sg13g2', 'IHP-GmbH/IHP-Open-PDK@5e6d592e4002946a4616f798c357f0f3c06cf3b6', 'ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/rfmos_connections.lvs', 'ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/rfmos_connections.lvs', None, '100644'): ('88d8335742119b8b88811f408defb789cc8fbde2c910c1deb33d9a4837a5b2d3', '2245c9e41ba02fa9b453adb56036669f7d6f35de', 954, 'logger-only-stub'), ('gf180mcu', 'fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr@4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c', 'rules/klayout/macros/gf180mcu_lvs.lylvs', 'rules/klayout/macros/gf180mcu_lvs.lylvs', None, '100644'): ('cf062cabd24c257733d841bbb6b667af7f03f0c6db0019d3b98d5960a7e46e1f', '27274eb5ed833e660f3e720074353bd777659155', 3033, 'lvs-macro'), ('gf180mcu', 'fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr@4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c', 'rules/klayout/macros/run_drc_main/main.drc', 'rules/klayout/macros/run_drc_main/main.drc', None, '100644'): ('211d1974056662b7b11eabdd4b7d98cf6704f973a165d10e9e7b575e7e200e23', '9c3927f582edc5f8f8eeeb9929948f0897315956', 787, 'license-only-stub'), ('gf180-fd-pv', 'efabless/globalfoundries-pdk-libs-gf180mcu_fd_pv@05e7b6adf19edf942969c1c9625f02fd87874f06', 'klayout/lvs/rule_decks/devices_connections.lvs', 'klayout/lvs/rule_decks/devices_connections.lvs', None, '100644'): ('923f7dbcab8624185f12ec4e9acd3ed84880d8a385025cd98097e5ef5e2876c0', '703c57b8f12166ca04c2b692f9c565213823067a', 1953, 'dependency-wrapper')}


def includes(text, path):
    rows = []
    for line, value in enumerate(text.splitlines(), 1):
        if not re.match(r'^\s*#\s*%', value):
            continue
        match = re.fullmatch(r'\s*#\s*%include\s+([A-Za-z0-9_./-]+)\s*', value)
        require(match is not None, 'unsupported preprocessor directive')
        target = match[1]
        require(not target.startswith('/') and '//' not in target, 'unsafe include target')
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        require(resolved not in ('.', '..') and not resolved.startswith('../'), 'include escapes source root')
        rows.append(dict(kind='klayout-preprocessor-include', name=target, line=line,
                         resolved_source_path=resolved, dependency_replayed=False, executed=False))
    return rows


def wrapper_facts(text, path, role):
    require(len(text) <= 100000 and '\0' not in text, 'source size or NUL')
    if role == 'lvs-macro':
        root = ET.fromstring(text)
        require(root.tag == 'klayout-macro' and root.findtext('interpreter') == 'dsl' and
                root.findtext('dsl-interpreter-name') == 'lvs-dsl-xml', 'unreviewed macro interpreter')
        require(not (root.findtext('prolog') or '').strip() and
                not (root.findtext('epilog') or '').strip(), 'unreviewed macro prolog/epilog')
        body = root.findtext('text') or ''
        from scripts.audit_source_dispositions import ruby_views
        rows = [dict(kind='klayout-macro', name=root.findtext('category') or '(uncategorized)',
                     interpreter='dsl', dsl_interpreter='lvs-dsl-xml', body_sha256=sha(body.encode()),
                     autorun=root.findtext('autorun'), executed=False)]
        rows += [dict(**row, line_scope='embedded-text') for row in ruby_views(body)+includes(body, path)]
        return rows
    require(role in ('dependency-wrapper', 'logger-only-stub', 'license-only-stub'), 'unreviewed source role')
    rows = includes(text, path)
    logging = []
    for line, value in enumerate(text.splitlines(), 1):
        value = value.strip()
        if not value or value.startswith('#'):
            continue
        # The exact reviewed wrappers use a single literal logging call. Do not
        # swallow appended code, interpolation or arbitrary method invocation.
        require(re.fullmatch(r"logger\.info\('[A-Za-z0-9 _-]+'\)", value) is not None,
                'unreviewed wrapper statement')
        logging.append(dict(kind='klayout-log-declaration', name='logger.info', line=line,
                            expression_sha256=sha(value.encode()), executed=False))
    require((role == 'dependency-wrapper' and rows and len(logging) == 1) or
            (role == 'logger-only-stub' and not rows and len(logging) == 1) or
            (role == 'license-only-stub' and not rows and not logging), 'wrapper role differs from content')
    return [dict(kind='reviewed-klayout-wrapper-role', name=role, text_sha256=sha(text.encode()),
                 device_rule_implementation=False, executed=False)]+rows+logging


def klayout_wrapper_views(row, raw):
    key = tuple(row.get(k) for k in ('family', 'repository', 'repository_path', 'path', 'archive', 'mode'))
    selected = REVIEWED.get(key)
    if selected is None:
        return None
    digest, blob, size, role = selected
    require(type(raw) is bytes and len(raw) == size and sha(raw) == digest, 'source bytes changed')
    require(hashlib.sha1(b'blob '+str(size).encode()+b'\0'+raw).hexdigest() == blob,
            'source Git identity changed')
    require(row.get('bytes') == size and row.get('git_blob_sha1') == blob and
            row.get('sha256', digest) == digest, 'source ledger identity changed')
    return wrapper_facts(raw.decode('utf-8'), row['path'], role)
