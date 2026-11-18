"""GitHub pull request operations using the authenticated GitHub CLI."""
from dataclasses import dataclass
import json
import os
import shutil
import subprocess

from .project_git import COMMIT, github_url


MERGE_METHODS = {'merge': 'Merge Commit', 'squash': 'Squash and Merge', 'rebase': 'Rebase and Merge'}
MERGE_SETTINGS = {'merge': 'allow_merge_commit', 'squash': 'allow_squash_merge', 'rebase': 'allow_rebase_merge'}
REVIEW_EVENTS = {'COMMENT': 'Comment', 'APPROVE': 'Approve', 'REQUEST_CHANGES': 'Request Changes'}
PAGE_SIZE = 30


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    author: str
    state: str
    draft: bool
    merged: bool
    mergeable: bool | None
    merge_state: str
    base: str
    base_sha: str
    head: str
    head_sha: str

    @classmethod
    def from_json(cls, row):
        return cls(row['number'], row['title'], row.get('body') or '', (row.get('user') or {}).get('login', ''),
                   row['state'], bool(row.get('draft')), bool(row.get('merged') or row.get('merged_at')), row.get('mergeable'),
                   row.get('mergeable_state') or 'unknown', row['base']['ref'], row['base']['sha'],
                   row['head']['label'], row['head']['sha'])

    @property
    def open(self):
        return self.state == 'open' and not self.merged

    @property
    def can_merge(self):
        return self.open and not self.draft and self.mergeable is True

    @property
    def reviewed_revision(self):
        return self.base, self.base_sha, self.head, self.head_sha

    @property
    def status(self):
        if self.merged:
            return 'Merged'
        if not self.open:
            return 'Closed'
        if self.draft:
            return 'Draft'
        return 'Open'


@dataclass(frozen=True)
class PullRequestDetail:
    request: PullRequest
    files: list
    reviews: list


class GitHubPullRequests:
    def __init__(self, url):
        self.repository = github_url(url).removeprefix('https://github.com/').removesuffix('.git')
        self.endpoint = 'repos/' + self.repository

    def api(self, endpoint, *, method='GET', data=None, paginate=False):
        cli = shutil.which('gh')
        if not cli:
            raise ValueError('Install GitHub CLI and sign in to use pull requests in Studio.')
        args = [cli, 'api', '--hostname', 'github.com', '--method', method,
                '--header', 'Accept: application/vnd.github+json', self.endpoint + endpoint]
        if paginate:
            args.extend(('--paginate', '--slurp'))
        packet = None
        if data is not None:
            args.extend(('--input', '-'))
            packet = json.dumps(data).encode('utf-8')
        env = {key: value for key, value in os.environ.items() if key.upper() != 'GH_DEBUG'}
        env.update(GH_PROMPT_DISABLED='1', GH_NO_UPDATE_NOTIFIER='1', GH_NO_EXTENSION_UPDATE_NOTIFIER='1')
        try:
            result = subprocess.run(args, input=packet, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=env, timeout=40, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            message = 'GitHub did not respond in time.'
            if method != 'GET':
                message += ' Refresh pull requests to check whether the action completed before retrying.'
            raise ValueError(message) from exc
        if result.returncode:
            message = result.stderr.decode('utf-8', errors='replace').strip()
            if 'gh auth login' in message or 'HTTP 401' in message:
                message = 'Sign in to github.com with GitHub CLI, then refresh pull requests.'
            raise ValueError(message or 'GitHub could not complete the pull request action.')
        try:
            response = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError('GitHub returned an unreadable pull request response.') from exc
        return [row for page in response for row in page] if paginate else response

    def repository_info(self):
        data = self.api('')
        methods = [method for method, setting in MERGE_SETTINGS.items() if data.get(setting, True)]
        return data.get('default_branch', ''), methods

    def branch_names(self):
        return [row['name'] for row in self.api('/branches?per_page=100', paginate=True)]

    def list(self, state='open', page=1):
        if state not in ('open', 'closed', 'all') or type(page) is not int or page < 1:
            raise ValueError('Choose a valid pull request filter.')
        rows = self.api(f'/pulls?state={state}&per_page={PAGE_SIZE}&page={page}')
        return [PullRequest.from_json(row) for row in rows], len(rows) == PAGE_SIZE

    def pull_path(self, number):
        if type(number) is not int or number < 1:
            raise ValueError('Choose a valid pull request.')
        return f'/pulls/{number}'

    def get(self, number):
        return PullRequest.from_json(self.api(self.pull_path(number)))

    def detail(self, number):
        path = self.pull_path(number)
        before = self.get(number)
        files = self.api(path + '/files?per_page=100', paginate=True)
        reviews = self.api(path + '/reviews?per_page=100', paginate=True)
        current = self.get(number)
        if before.reviewed_revision != current.reviewed_revision:
            raise ValueError('The branches changed while loading this pull request. Refresh to review the latest changes.')
        return PullRequestDetail(current, files, reviews)

    def create(self, title, body, base, head):
        title = title.strip()
        if not title or '\n' in title or '\r' in title or len(title) > 256:
            raise ValueError('Enter a single-line pull request title of up to 256 characters.')
        if not base or not head or base == head:
            raise ValueError('Choose different published branches for the base and head.')
        return PullRequest.from_json(self.api('/pulls', method='POST',
                                              data={'title': title, 'body': body, 'base': base, 'head': head}))

    def require_current(self, reviewed):
        current = self.get(reviewed.number)
        if (not COMMIT.fullmatch(reviewed.head_sha) or not COMMIT.fullmatch(reviewed.base_sha)
                or current.reviewed_revision != reviewed.reviewed_revision):
            raise ValueError('The base or head changed. Refresh and review this pull request again.')
        if not current.open:
            raise ValueError('This pull request is already closed.')
        return current

    def review(self, reviewed, event, body):
        if event not in REVIEW_EVENTS:
            raise ValueError('Choose a review action.')
        body = body.strip()
        if event in ('COMMENT', 'REQUEST_CHANGES') and not body:
            raise ValueError('Write a comment before submitting this review.')
        self.require_current(reviewed)
        return self.api(self.pull_path(reviewed.number) + '/reviews', method='POST',
                        data={'commit_id': reviewed.head_sha, 'event': event, 'body': body})

    def merge(self, reviewed, method):
        if method not in MERGE_METHODS:
            raise ValueError('Choose a merge method.')
        current = self.require_current(reviewed)
        if not current.can_merge:
            raise ValueError('GitHub has not marked this pull request as mergeable. Refresh its status.')
        # The SHA guard is enforced by GitHub even if the head changes after our check.
        result = self.api(self.pull_path(reviewed.number) + '/merge', method='PUT',
                          data={'sha': reviewed.head_sha, 'merge_method': method})
        if result.get('merged') is not True:
            raise ValueError(result.get('message') or 'GitHub did not merge this pull request.')
        return result
