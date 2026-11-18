"""Git branches for one Studio document, with an explicit GitHub remote."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .model import clone, now, validate
from .project_merge import merge_design
from .project_versions import Version, same_design


PROJECT_FILE = 'project.icproj'
GITHUB = re.compile(r'https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})/?')
COMMIT = re.compile(r'[0-9a-f]{40}')


def github_url(text):
    match = GITHUB.fullmatch(text.strip())
    if match:
        owner, repository = match.groups()
        repository = repository.removesuffix('.git')
        if repository and repository not in ('.', '..'):
            return f'https://github.com/{owner}/{repository}.git'
    raise ValueError('Enter a GitHub repository URL, such as https://github.com/owner/repository.')


@dataclass(frozen=True)
class Branch:
    name: str
    head: str
    remote: bool = False

    @property
    def ref(self):
        return ('refs/remotes/github/' if self.remote else 'refs/heads/') + self.name


@dataclass(frozen=True)
class MergeReview:
    target: Branch
    source: Branch
    base: str
    ancestor: dict
    current: dict
    incoming: dict

    def resolve(self, choices=None):
        return merge_design(self.ancestor, self.current, self.incoming, choices)


class ProjectGit:
    def __init__(self, project_path, project_id):
        path = Path(project_path).resolve()
        self.path = path.with_name(path.name + '.branches.git')
        self.project_id = project_id

    def _run(self, *args, cwd, data=None, check=True, timeout=25):
        git = shutil.which('git')
        if not git:
            raise ValueError('Install Git to use project branches and GitHub.')
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
        env.update(GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1', GIT_LFS_SKIP_SMUDGE='1')
        try:
            result = subprocess.run([git, '--no-pager', '-c', 'core.hooksPath=/dev/null',
                                     '-c', 'protocol.allow=never', '-c', 'protocol.https.allow=always',
                                     '-c', 'http.followRedirects=false', '-c', 'http.sslVerify=true',
                                     '-c', 'user.name=IC Design Studio',
                                     '-c', 'user.email=studio-project@users.noreply.github.com', *args],
                                    cwd=cwd, env=env, input=data, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=timeout,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Git did not finish in time. Fetch branches before retrying a publish.') from exc
        if check and result.returncode:
            feedback = result.stderr.decode('utf-8', errors='replace').strip()
            raise ValueError(feedback or 'Git could not complete this action.')
        return result

    def git(self, *args, **kwargs):
        return self._run('--git-dir=' + str(self.path), *args, cwd=self.path.parent, **kwargs)

    def text(self, *args):
        return self.git(*args).stdout.decode('utf-8', errors='replace').strip()

    def initialize(self):
        if not self.path.exists():
            with tempfile.TemporaryDirectory(prefix='.studio-branches-', dir=self.path.parent) as folder:
                staging = Path(folder) / 'repository'
                self._run('init', '--bare', '--template=', '--initial-branch=main',
                          '--object-format=sha1', str(staging), cwd=self.path.parent)
                self._run('--git-dir=' + str(staging), 'config', '--local', 'studio.projectid',
                          self.project_id, cwd=self.path.parent)
                try:
                    staging.rename(self.path)
                except OSError:
                    if not self.path.is_dir():
                        raise
        self.verify()

    def verify(self):
        if (self.path.is_symlink() or self.path.is_junction()
                or self.text('rev-parse', '--is-bare-repository') != 'true'
                or self.text('config', '--local', '--get', 'studio.projectid') != self.project_id):
            raise ValueError('The branch repository belongs to a different project.')

    def entries(self):
        if not self.path.exists():
            return []
        self.verify()
        refs = self.text('for-each-ref', '--format=%(refname) %(objectname)',
                         'refs/heads/', 'refs/remotes/github/')
        branches = []
        for row in refs.splitlines():
            ref, commit = row.split(' ', 1)
            remote = ref.startswith('refs/remotes/github/')
            name = ref.removeprefix('refs/remotes/github/' if remote else 'refs/heads/')
            branches.append(Branch(name, commit, remote))
        return branches

    def active(self):
        ref = self.text('symbolic-ref', 'HEAD')
        if not ref.startswith('refs/heads/'):
            raise ValueError('The project has no active branch.')
        name = ref.removeprefix('refs/heads/')
        return Branch(name, self.tip(ref))

    def tip(self, ref):
        result = self.git('rev-parse', '--verify', '--quiet', ref, check=False)
        return result.stdout.decode('ascii').strip() if result.returncode == 0 else ''

    def branch_name(self, name):
        name = name.strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,79}', name):
            raise ValueError('Use a branch name such as filter-tuning or review/rev-b.')
        self.git('check-ref-format', 'refs/heads/' + name)
        return name

    def create(self, name, head):
        name = self.branch_name(name)
        self.load(head)
        result = Branch(name, head)
        self.git('update-ref', result.ref, head, '')
        return result

    def switch(self, source):
        if self.tip(source.ref) != source.head:
            raise ValueError('That branch changed. Refresh the branch list and try again.')
        project = self.load(source.head)
        if source.remote:
            source = self.create(source.name, source.head)
        self.git('symbolic-ref', 'HEAD', source.ref)
        return project

    def load(self, version_id):
        if not COMMIT.fullmatch(version_id):
            raise ValueError('Choose a valid saved version.')
        files = self.git('ls-tree', '-z', '--name-only', version_id).stdout
        if files != PROJECT_FILE.encode('ascii') + b'\x00':
            raise ValueError('Use a GitHub branch dedicated to this Studio project. Its root must contain only project.icproj.')
        location = version_id + ':' + PROJECT_FILE
        if int(self.text('cat-file', '-s', location)) > 512 * 1024 * 1024:
            raise ValueError('This branch version exceeds the Studio project limit.')
        project = json.loads(self.git('show', location).stdout)
        if not isinstance(project, dict) or project.get('id') != self.project_id:
            raise ValueError('That branch contains a different project.')
        return validate(project)

    def version(self, commit, date, message):
        body, _, trailer = message.rstrip().rpartition('\nStudio-Revision: ')
        title, _, note = (body if trailer.isdecimal() else message).strip().partition('\n')
        return Version(commit, title or 'Untitled version', note.strip(), date,
                       int(trailer) if trailer.isdecimal() else None)

    def list(self):
        branch = self.active()
        if not branch.head:
            return []
        raw = self.git('log', '-z', '--first-parent', '--format=%H%x00%cI%x00%B', branch.head, '--')
        parts = raw.stdout.decode('utf-8', errors='replace').removesuffix('\x00').split('\x00')
        return [self.version(*parts[i:i+3]) for i in range(0, len(parts), 3)]

    def commit(self, project, branch, name, note='', merge_parent=None):
        name, note = name.strip(), note.strip()
        if not name or len(name) > 100 or len(note) > 4000 or '\x00' in name + note or '\n' in name or '\r' in name:
            raise ValueError('Enter a single-line version name of 1–100 characters and a note of up to 4,000 characters.')
        if project['id'] != self.project_id:
            raise ValueError('Save versions within their original project.')
        document = validate(clone(project))
        data = (json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        blob = self.git('hash-object', '-w', '--stdin', data=data).stdout.strip()
        tree_data = b'100644 blob ' + blob + b'\t' + PROJECT_FILE.encode('ascii') + b'\n'
        tree = self.git('mktree', data=tree_data).stdout.decode('ascii').strip()
        parents = [flag for parent in (branch.head, merge_parent) if parent for flag in ('-p', parent)]
        message = f'{name}\n\n{note}\n\nStudio-Revision: {document["revision"]}\n'.encode('utf-8')
        sha = self.git('commit-tree', tree, *parents, '-F', '-', data=message).stdout.decode('ascii').strip()
        self.git('update-ref', branch.ref, sha, branch.head)
        return self.version(sha, self.text('show', '-s', '--format=%cI', sha), message.decode('utf-8'))

    def save(self, project, name, note=''):
        self.verify()
        branch = self.active()
        if not branch.head and any(b.remote for b in self.entries()):
            raise ValueError('Switch to a fetched GitHub branch before saving your first branch version.')
        if branch.head:
            self.load(branch.head)
        return self.commit(project, branch, name, note)

    def review(self, source):
        target = self.active()
        if not target.head:
            raise ValueError('Save a version or switch to a GitHub branch to start.')
        if self.tip(source.ref) != source.head:
            raise ValueError('That branch changed. Refresh the branch list and try again.')
        if source.head == target.head:
            raise ValueError('These branches already have the same version.')
        bases = self.git('merge-base', '--all', target.head, source.head, check=False).stdout.decode('ascii').split()
        if not bases:
            raise ValueError('These branches do not share a saved ancestor.')
        if len(bases) != 1:
            raise ValueError('These branches have multiple merge bases. Reconcile that history in Git before merging in Studio.')
        base = bases[0]
        if base == source.head:
            raise ValueError('All versions from that branch are already in the active branch.')
        return MergeReview(target, source, base, self.load(base), self.load(target.head), self.load(source.head))

    def merge(self, review, choices, revision):
        if self.active() != review.target or self.tip(review.source.ref) != review.source.head:
            raise ValueError('A branch changed during review. Reopen the merge preview.')
        candidate, _, error = review.resolve(choices)
        if candidate is None:
            raise ValueError(error or 'Resolve every conflict before merging.')
        if review.base == review.target.head and same_design(candidate, review.incoming):
            self.git('update-ref', review.target.ref, review.source.head, review.target.head)
        else:
            candidate['revision'] = revision
            candidate['modified'] = now()
            self.commit(candidate, review.target, f'Merge {review.source.name}'[:100],
                        f'Merge into {review.target.name}.', review.source.head)
        return candidate

    def remote_url(self):
        result = self.git('config', '--local', '--get', 'studio.github', check=False)
        value = result.stdout.decode('utf-8').strip()
        return github_url(value) if value else ''

    def connect(self, url):
        url = github_url(url)
        previous = self.remote_url()
        if previous and previous != url:
            raise ValueError('This history is already connected to another GitHub repository.')
        self._transport('ls-remote', url, 'HEAD')
        self.git('config', '--local', 'studio.github', url)
        return url

    def disconnect(self):
        tracking = [b for b in self.entries() if b.remote]
        if tracking:
            changes = ''.join(f'delete {b.ref} {b.head}\n' for b in tracking)
            self.git('update-ref', '--stdin', data=changes.encode('utf-8'))
        self.git('config', '--local', '--unset', 'studio.github')

    def _transport(self, command, *args):
        return self.git(command, *args, timeout=120)

    def fetch(self):
        url = self.remote_url()
        if not url:
            raise ValueError('Connect to a GitHub repository before fetching.')
        self._transport('fetch', '--atomic', '--prune', '--no-tags', '--no-auto-maintenance', url,
                        '+refs/heads/*:refs/remotes/github/*')

    def publish(self, branch):
        url = self.remote_url()
        if not url or branch.remote or not branch.head or self.tip(branch.ref) != branch.head:
            raise ValueError('Choose an up-to-date local branch and connect to GitHub before publishing.')
        self.load(branch.head)
        self._transport('push', '--porcelain', url, branch.head + ':refs/heads/' + branch.name)
