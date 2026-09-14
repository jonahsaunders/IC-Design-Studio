"""Private unsent composer text, scoped to a session and checkpoint.

Loading a draft never submits a request. The submitted-action outbox remains
the sole authority for network retry IDs and exactly-once replay.
"""
import json
from pathlib import Path
from .model import atomic_write, clone

MAX_BYTES = 1024 * 1024
MAX_DRAFTS = 100


class ReviewDrafts:
    def __init__(self, path, server, workspace, actor):
        self.path = Path(path)
        self.identity = dict(server=server, workspace=workspace, actor=actor)
        self.rows = {}
        if self.path.is_file():
            if self.path.stat().st_size > MAX_BYTES: raise ValueError('Review drafts exceed the storage limit.')
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('schema') != 1 or data.get('identity') != self.identity:
                raise ValueError('Saved review drafts belong to a different session.')
            rows = data.get('drafts')
            if not isinstance(rows, dict) or len(rows) > MAX_DRAFTS: raise ValueError('Invalid review drafts.')
            for checkpoint, row in rows.items():
                if (not isinstance(checkpoint, str) or not isinstance(row, dict) or
                    not isinstance(row.get('text'), str) or not isinstance(row.get('reply'), str)):
                    raise ValueError('Invalid review draft.')
            self.rows = rows

    def get(self, checkpoint):
        return clone(self.rows.get(checkpoint, dict(text='', reply='')))

    def save(self, checkpoint, text, reply=''):
        if not checkpoint: return
        rows = dict(self.rows)
        if text: rows[checkpoint] = dict(text=text, reply=reply or '')
        else: rows.pop(checkpoint, None)
        if rows == self.rows: return
        if len(rows) > MAX_DRAFTS: raise ValueError('Review draft limit reached. Finish or discard an older draft first.')
        data = json.dumps(dict(schema=1, identity=self.identity, drafts=rows), ensure_ascii=False)
        if len(data.encode('utf-8')) > MAX_BYTES: raise ValueError('Review drafts exceed the 1 MiB storage limit.')
        self.path.parent.mkdir(parents=True, exist_ok=True); self.path.parent.chmod(0o700)
        atomic_write(self.path, data); self.path.chmod(0o600)
        self.rows = rows

    def acknowledge(self, request):
        checkpoint = request.get('checkpoint')
        if request.get('action') not in ('comment', 'reply', 'decide') or checkpoint not in self.rows: return
        row = self.rows[checkpoint]
        if row == dict(text=request.get('text', ''), reply=request.get('parent', '')):
            self.save(checkpoint, '')
