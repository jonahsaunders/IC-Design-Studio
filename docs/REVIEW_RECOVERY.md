# Recovery of submitted review actions

Dev19 saves a review mutation before sending it to the team server. Comments, replies, resolve/reopen actions, decisions, checkpoint creation and shared report submissions retain their original request ID in a private local outbox beside the session journal.

If the connection or acknowledgement is lost, the collaboration dashboard shows the saved action and **Retry last action**. Reopening the app and resuming the same session restores it. Retry reuses the original ID, so a request already accepted by the server is not submitted twice. Refreshing the discussion list does not clear a pending mutation.

A single submitted action is retained at a time. Retry or explicitly discard it before posting another action. **Discard saved review action…** clears the local retry record after confirmation; an action already accepted by the server remains on the server. Text merely typed into the editor has not been submitted and is not persisted by this feature.

The `.review-outbox` sidecar contains the action and session identity, not access tokens. It is bound to server, workspace and participant. An atomic empty record acknowledges completion; failed storage leaves the original request available. The separate suffix keeps it out of the recent-session journal scan. The server database/document protocols are unchanged.

Tests cover lost responses, panel reconstruction, client/server restart, refresh before retry, cross-session rejection, storage failure and exactly one server comment after retry. This is a submitted-review recovery feature. A general offline design-edit queue, unsent draft recovery and notifications remain roadmap work.

See [live collaboration](LIVE_COLLABORATION.md) and [workflow review](WORKFLOW_REVIEW_0.22.md).
