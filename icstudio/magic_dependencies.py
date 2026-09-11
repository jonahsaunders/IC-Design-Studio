"""Bounded dependency audit before converting a native Magic cell tree."""
import shlex
from pathlib import Path
from .model import file_digest


def closure(source):
    source=Path(source).resolve();pending=[source];seen={};total=0
    while pending:
        path=pending.pop()
        if path in seen:continue
        if len(seen)>=1000:raise ValueError('Magic import exceeds 1,000 source cells.')
        total+=path.stat().st_size
        if total>64*1024*1024:raise ValueError('Magic source hierarchy exceeds 64 MB.')
        seen[path]=file_digest(path)
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.startswith('use '):continue
            fields=shlex.split(line)
            if len(fields)<3:raise ValueError('Malformed Magic cell use in '+path.name)
            name=fields[1]+('.mag' if not fields[1].endswith('.mag') else '')
            candidates=[path.parent/name,source.parent/name]
            if len(fields)>3:candidates.append(Path(fields[3])/name)
            child=next((p.resolve() for p in candidates if p.is_file()),None)
            if child is None:raise ValueError('Missing Magic child '+name+' referenced by '+path.name+'. Supply the complete source tree.')
            pending.append(child)
    return {str(p.relative_to(source.parent)) if p.is_relative_to(source.parent) else str(p):h for p,h in sorted(seen.items())}
