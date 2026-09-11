# Live desktop layout collaboration

This experimental feature shares a layout through a self-hosted server. Open
**Layout → Live collaboration → Share layout** to create a workspace, choose
**Can view** or **Can edit**, and copy an expiring invitation. A collaborator
opens the link in their browser and chooses **Open IC Design Studio**, or pastes
the complete link into **Join with invitation** in the desktop app.

This repository supplies the server and desktop client. It does not supply a
running public service. A host must run the server at an address collaborators
can reach. Browser links launch the installed desktop app; there is no browser
layout editor. The earlier shared-folder collaboration remains available under
**Layout → Concurrent editing**.

## Start a server

Use Python 3.12 with the application's `requirements.txt` installed:

```sh
python -m icstudio.live_server --data ./private-live-data
```

The server listens on `http://127.0.0.1:8765`. This address is useful for testing
two desktop windows on the same computer. The server creates
`private-live-data/creation-key.txt`; enter its contents in the **Workspace
creation key** field when sharing a project. Keep this key with the host. Invitees
receive invitation links, not the workspace creation key.

For other computers, configure a trusted HTTPS reverse proxy for a dedicated
origin, forwarding to the loopback listener, or supply a valid TLS certificate:

```sh
python -m icstudio.live_server --data ./private-live-data --listen 0.0.0.0 --port 8765 --certfile fullchain.pem --keyfile privkey.pem
```

Use the reachable HTTPS origin in **Share layout**, for example
`https://layout.example.org`. A reverse proxy must allow 16 MiB JSON requests and
forward the `Authorization` header. Do not cache API responses. Direct HTTP is
accepted by the desktop client only on loopback addresses; non-loopback server
listeners require TLS. Certificate verification is never disabled. Firewall,
DNS, certificate renewal and server availability are managed by the host.

The application entry point also accepts `python main.py --collaboration-server
--data ./private-live-data`. The packaged application includes these modules,
though running a source Python server gives the host a visible console.

## Share and join

1. Open a project and choose **Share layout**. Enter the server origin, creation
   key and your name. Sharing copies the current project into a new workspace.
2. The live panel lists participants and recent accepted edits. Choose an
   invitation permission and expiry (1–30 days), then **Create and copy invitation**.
3. Send the link to your collaborator. Anyone holding that link can join with its
   permission until it expires or is revoked. Names are display names, not
   independently verified identities.
4. Invitees choose their name and join. Layout edits and presence update
   automatically. Colored cursors and selection outlines identify participants
   viewing the same cell. The schematic and PDK can be inspected but cannot be
   changed within this layout session.
5. Select an invitation and choose **Revoke selected invitation** to prevent new
   joins and invalidate existing sessions created through it. Revocation cannot
   erase project copies already downloaded by a recipient.

The Windows installer registers the `icstudio://` invitation handler and removes
it on uninstall. Source checkouts, portable packages, Linux and macOS can always
use the in-app **Join with invitation** command. They can also launch directly:

```sh
python main.py --join "FULL_INVITATION_LINK"
```

The browser landing page keeps the invitation credential in the URL fragment;
the server does not receive it in the landing-page request. The landing page
does not load third-party scripts or send invitation data to another service.
Opening a link starts a separate desktop window and asks for the participant's
name before joining.

## Editing, reservations and undo

Editors can change different objects in the same cell and on the same layer.
Selections reserve existing objects for 12 seconds, renewed while selected;
deselecting or leaving releases them. A disconnected editor's reservations
expire automatically. Generated geometry, instance/port changes and other
structured layout collections reserve the whole affected cell. Objects with the
same explicit net name also share a reservation and conflict boundary. This is
deliberately conservative for connected edits and generated footprints.

Every edit is one validated server transaction. If another editor changes an
affected object or connected group after the client's base revision, the server
rejects the edit. Reservations are checked again when committing; a race while
acquiring a selection never grants permission to overwrite another edit.
Connected moves and generated edits commit their complete change sets together.

**Undo and Redo apply to your accepted edits only.** They preserve disjoint edits
by other participants and reject overlapping intervening edits, even when another
person moves geometry away and then back. Each session retains up to 100 personal
undo operations. Rejoining through a link creates a new identity; use **Resume
saved live session** to retain your existing personal history.

Layout transactions still require ordinary DRC/LVS and connectivity review.
Object conflict detection does not prove geometric spacing, manufactured device
correctness or foundry signoff. Schematic changes, technology changes, new cell
creation and existing-object reordering require leaving the session. Existing
layout text collections are treated as one atomic collection because they do
not yet have stable individual IDs.

## Connection loss and recovery

The client sends asynchronous HTTP updates every 500 ms while connected, backing
off to eight seconds during an outage. Unchanged polls omit project data. This
is polling-based live collaboration, not WebSocket/CRDT replication. Network
I/O never blocks the Qt event loop. Incoming geometry is deferred while a drawing
gesture or inspector edit is in progress.

One local edit may await acknowledgement at a time. The client saves its request
ID and proposed change before sending it. If the acknowledgement is lost, retrying
that request returns the already committed result without applying the edit
again. New edits pause until the pending transaction is settled. This version
does not support accumulating independent offline edits.

The private `live-sessions` folder under the app's user data directory retains
session credentials, pending edits and conflict snapshots. **Resume saved live
session** recovers one after restarting the app. Treat these files as credentials;
do not commit, email or upload them. They are separate from normal `.icproj`
documents. Active sessions renew their seven-day inactivity expiry, but invitation
expiry and revocation still apply.

When a conflict occurs, the proposed project remains in the private recovery
journal. Use **Save retained conflicting edit** to write an independent `.icproj`
copy for review, or **Discard retained conflicting edit** to resume from the
server's accepted state. **Leave and keep local copy** preserves the currently
displayed project for ordinary saving and independent editing.

## Server persistence and limits

SQLite stores accepted projects, edit history, request IDs, invitations and
session identities in atomic transactions with full synchronization. Server
restarts preserve accepted edits and personal history. Credentials are hashed
in the server database; the creation key is a separate host-only file. Presence
is transient. Claims expire after a crash. Keep the private data directory on
storage with reliable local filesystem semantics; use a SQLite-consistent backup
or stop the server before copying its database and WAL files.

This prototype bounds each project to 8 MiB and 20,000 stored layout objects,
each edit to 2,000 changed objects, and requests/responses to 16 MiB. Hierarchical
arrays retain their compact stored representation. Each workspace permits up to
100 sessions and 100 active invitation links; the server permits 100 workspaces
and 16 concurrent HTTP requests. These are safety bounds, not measured service
capacity guarantees. History storage grows with accepted transactions; the host
must monitor disk capacity and retain backups. A disk failure cannot publish
half an edit, but it prevents further durable changes.

The service has no hosted account management, tenant billing, SSO, schematic
collaboration, internet discovery, NAT traversal, automatic deployment, binary
asset transfer or browser editor. Participants must resolve simulation PDK assets
locally. This is an engineering preview for small trusted teams.

## Verification

```sh
python -m unittest discover -s tests -p test_live_collaboration.py -v
python tests/gui_live_collaboration.py --out build/live-collaboration-evidence
```

For headless runs, set `QT_QPA_PLATFORM=offscreen`. The tests use real HTTP requests,
simultaneous clients, three Qt editor windows, view/edit links, revocation,
reservations, conditional personal undo, server restart, lost acknowledgements
and local-session recovery. The desktop workflow runs these checks on Windows
and Linux. Only screenshots and the non-secret report are uploaded as artifacts;
the generated server database and session journals stay out of release artifacts.
