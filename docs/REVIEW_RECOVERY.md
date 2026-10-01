# Recovery of submitted review actions

The desktop saves a review mutation before sending it to the team server. Introduced in dev19, this outbox retains the original request ID for comments, replies, resolve/reopen actions, decisions, checkpoint creation and shared report submissions beside the private session journal.

If the connection or acknowledgement is lost, the collaboration dashboard shows the saved action and **Retry last action**. Reopening the app and resuming the same session restores it. Retry reuses the original ID, so a request already accepted by the server is not submitted twice. Refreshing the discussion list does not clear a pending mutation.

A single submitted action is retained at a time. Retry or explicitly discard it before posting another action. **Discard saved review action…** clears the local retry record after confirmation; an action already accepted by the server remains on the server. Text merely typed into the editor is handled separately by the dev21 unsent-draft store; see [draft recovery](UPDATE_0.22_DEV21.md#durable-unsent-review-drafts). Restoring it does not submit an action.

The `.review-outbox` sidecar contains the action and session identity, not access tokens. It is bound to server, workspace and participant. An atomic empty record acknowledges completion; failed storage leaves the original request available. The separate suffix keeps it out of the recent-session journal scan. The server database/document protocols are unchanged.

Tests cover lost responses, panel reconstruction, client/server restart, refresh before retry, cross-session rejection, storage failure and exactly one server comment after retry. This is a submitted-review recovery feature. A general offline design-edit queue and notifications remain roadmap work.

## Unsent drafts

Review text typed before submission saves locally after a short pause and is
flushed when switching checkpoints, hiding the panel or closing the application.
Resuming the same session restores its checkpoint text and reply context;
attachments must be reviewed again. Restoring text never sends a request.
Draft-save failures keep the text visible and block closing until the text is
preserved or explicitly cleared. A successful submitted-action acknowledgement
clears only the matching draft, preserving newer text entered during the request.

The separate `.review-drafts` sidecar is bound to server, workspace and participant,
contains no access tokens, and is bounded to 100 checkpoints and 1 MiB total.
See the [dev21 implementation and evidence](UPDATE_0.22_DEV21.md#durable-unsent-review-drafts).

See [live collaboration](LIVE_COLLABORATION.md) and [workflow review](WORKFLOW_REVIEW_0.22.md).
