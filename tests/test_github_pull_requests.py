"""GitHub pull requests pin reviewed revisions and use authenticated CLI transport."""
import json
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

from icstudio.github_pull_requests import GitHubPullRequests, PullRequest


def pull_json(number=42, *, head='a' * 40, base='b' * 40, state='open', draft=False,
              mergeable=True, merged=False, title='Tune RC filter'):
    return {
        'number': number, 'title': title, 'body': 'Compare the two resistor values.',
        'user': {'login': 'designer'}, 'state': state, 'draft': draft,
        'mergeable': mergeable, 'mergeable_state': 'clean', 'merged': merged,
        'base': {'ref': 'main', 'sha': base}, 'head': {'label': 'designer:tuning', 'sha': head},
    }


class PullRequestTests(unittest.TestCase):
    def setUp(self):
        self.client = GitHubPullRequests('https://github.com/designer/filter.git')
        self.request = PullRequest.from_json(pull_json())

    def test_uses_one_explicit_repository_and_json_stdin(self):
        response = CompletedProcess([], 0, json.dumps(pull_json()).encode(), b'')
        with patch('icstudio.github_pull_requests.shutil.which', return_value='gh'), patch(
            'icstudio.github_pull_requests.subprocess.run', return_value=response
        ) as execute:
            result = self.client.create('Tune RC filter', 'Unicode Δ and newlines\n', 'main', 'tuning')
        args = execute.call_args
        self.assertIn('repos/designer/filter/pulls', args.args[0])
        self.assertIn('github.com', args.args[0])
        self.assertNotIn('Unicode Δ and newlines\n', args.args[0])
        self.assertEqual(json.loads(args.kwargs['input']), {
            'title': 'Tune RC filter', 'body': 'Unicode Δ and newlines\n', 'base': 'main', 'head': 'tuning',
        })
        self.assertEqual(result, self.request)

    def test_paginated_files_and_reviews_are_bound_to_both_revisions(self):
        file = {'filename': 'project.icproj', 'patch': '-10k\n+20k'}
        review = {'state': 'APPROVED'}
        responses = [pull_json(), [file], [review], pull_json()]
        with patch.object(self.client, 'api', side_effect=responses) as call:
            detail = self.client.detail(self.request.number)
        self.assertEqual((detail.request, detail.files, detail.reviews), (self.request, [file], [review]))
        self.assertTrue(call.call_args_list[1].kwargs['paginate'])
        self.assertTrue(call.call_args_list[2].kwargs['paginate'])
        responses[-1] = pull_json(base='c' * 40)
        with patch.object(self.client, 'api', side_effect=responses), self.assertRaisesRegex(ValueError, 'changed while loading'):
            self.client.detail(self.request.number)

    def test_read_and_write_operations_honor_sign_in_and_server_denials(self):
        response = CompletedProcess([], 1, b'', b'Run gh auth login before continuing')
        with patch('icstudio.github_pull_requests.shutil.which', return_value='gh'), patch(
            'icstudio.github_pull_requests.subprocess.run', return_value=response
        ):
            with self.assertRaisesRegex(ValueError, 'Sign in to github.com'):
                self.client.list()
        with patch.object(self.client, 'api', side_effect=[pull_json(), {'merged': False, 'message': 'Review required'}]):
            with self.assertRaisesRegex(ValueError, 'Review required'):
                self.client.merge(self.request, 'merge')

    def test_submit_review_and_merge_send_the_reviewed_head(self):
        with patch.object(self.client, 'api', side_effect=[pull_json(), {'state': 'APPROVED'}]) as call:
            self.client.review(self.request, 'APPROVE', 'Checked the simulation output.')
        call.assert_called_with('/pulls/42/reviews', method='POST', data={
            'event': 'APPROVE', 'commit_id': self.request.head_sha, 'body': 'Checked the simulation output.',
        })
        with patch.object(self.client, 'api', side_effect=[pull_json(), {'merged': True}]) as call:
            self.client.merge(self.request, 'squash')
        call.assert_called_with('/pulls/42/merge', method='PUT', data={
            'sha': self.request.head_sha, 'merge_method': 'squash',
        })

    def test_rejects_stale_head_moved_base_draft_and_unmergeable(self):
        cases = ((pull_json(head='c' * 40), 'changed'), (pull_json(base='c' * 40), 'changed'),
                 (pull_json(draft=True), 'mergeable'), (pull_json(mergeable=None), 'mergeable'),
                 (pull_json(mergeable=False), 'mergeable'), (pull_json(state='closed'), 'closed'))
        for remote, message in cases:
            with self.subTest(remote=remote), patch.object(self.client, 'api', return_value=remote) as call:
                with self.assertRaisesRegex(ValueError, message):
                    self.client.merge(self.request, 'merge')
                call.assert_called_once_with('/pulls/42')
        with patch.object(self.client, 'api', return_value=pull_json(head='c' * 40)) as call:
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.client.review(self.request, 'COMMENT', 'Reviewed.')
            call.assert_called_once_with('/pulls/42')

    def test_repository_settings_select_only_enabled_merge_methods(self):
        data = {'default_branch': 'stable', 'allow_merge_commit': False,
                'allow_squash_merge': True, 'allow_rebase_merge': False}
        with patch.object(self.client, 'api', return_value=data):
            self.assertEqual(self.client.repository_info(), ('stable', ['squash']))
