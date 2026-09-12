"""Restart-durable review requests, isolated from the full design journal."""
import json
from pathlib import Path
from .model import atomic_write, clone
from .live_protocol import ID, MAX_BYTES

ACTIONS = {'comment', 'reply', 'resolve_comment', 'decide', 'create_checkpoint', 'share_report'}


class ReviewOutbox:
    def __init__(self, path, server, workspace, actor):
        self.path = Path(path)
        self.identity = dict(server=server, workspace=workspace, actor=actor)
        self.pending = None
        self.error = ''
        if self.path.is_file():
            if self.path.stat().st_size > MAX_BYTES:
                raise ValueError('Saved review action exceeds the recovery limit.')
            state = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(state, dict) or state.get('schema') != 1 or state.get('identity') != self.identity:
                raise ValueError('Saved review action belongs to a different session.')
            request = state.get('pending')
            if request is not None:
                self.validate(request)
            self.pending = request
            self.error = state.get('error', '')
            if not isinstance(self.error, str): raise ValueError('Invalid saved review error.')

    @staticmethod
    def validate(request):
        if not isinstance(request, dict) or request.get('action') not in ACTIONS:
            raise ValueError('Invalid saved review action.')
        if not isinstance(request.get('id'), str) or not ID.fullmatch(request['id']):
            raise ValueError('Invalid saved review request identity.')

    def _write(self, pending, error=''):
        data = json.dumps(dict(schema=1, identity=self.identity, pending=pending, error=error), allow_nan=False)
        if len(data.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Review action exceeds the recovery limit.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        atomic_write(self.path, data)
        self.path.chmod(0o600)
        self.pending, self.error = clone(pending), error

    def stage(self, request):
        self.validate(request)
        if self.pending is not None:
            if self.pending != request:
                raise ValueError('Retry or discard the saved review action before submitting another one.')
            return
        self._write(request)

    def failed(self, request_id, error):
        if self.pending and self.pending['id'] == request_id:
            self._write(self.pending, str(error)[:2000])

    def acknowledge(self, request_id):
        if self.pending and self.pending['id'] == request_id:
            # An atomic empty record prevents an old pending request reappearing
            # after a failed deletion. Replays still use the server's retry ID.
            self._write(None)

    def discard(self):
        self._write(None)
