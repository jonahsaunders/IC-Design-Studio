"""Run the real Git graph and transport with two Studio project copies."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from icstudio.model import clone, example
from icstudio.project_git import ProjectGit, github_url
from icstudio.project_merge import merge_design


class ProjectMergeTests(unittest.TestCase):
    def test_disjoint_component_and_simulation_edits_merge(self):
        base = example('rc')
        current, incoming = clone(base), clone(base)
        current['analysis']['stop'] = '300u'
        incoming['cells'][0]['devices'][1]['value'] = '47k'
        result, conflicts, error = merge_design(base, current, incoming)
        self.assertEqual((conflicts, error), ([], ''))
        self.assertEqual(result['analysis']['stop'], '300u')
        self.assertEqual(result['cells'][0]['devices'][1]['value'], '47k')

    def test_deletion_and_edit_require_a_choice(self):
        base = example('rc')
        current, incoming = clone(base), clone(base)
        current['cells'][0]['devices'].pop(1)
        incoming['cells'][0]['devices'][1]['value'] = '47k'
        result, conflicts, _ = merge_design(base, current, incoming)
        self.assertIsNone(result)
        self.assertEqual(len(conflicts), 1)
        self.assertIn('R1', conflicts[0].label)
        kept, _, _ = merge_design(base, current, incoming, {conflicts[0].path: 'incoming'})
        self.assertEqual(next(d for d in kept['cells'][0]['devices'] if d['name'] == 'R1')['value'], '47k')

    def test_github_url_accepts_only_repository_urls(self):
        self.assertEqual(github_url('https://github.com/owner/filter/'), 'https://github.com/owner/filter.git')
        for url in ('https://github.com.evil.com/org/repo', 'https://token@github.com/org/repo',
                    'https://github.com/org/repo/issues', 'https://github.com/org/..'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                github_url(url)


@unittest.skipUnless(shutil.which('git'), 'Git is required for the project branch tests')
class ProjectGitTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.project = example('rc')
        self.repo = ProjectGit(self.root / 'Filter with spaces.icproj', self.project['id'])
        self.repo.initialize()
        self.base = self.repo.save(self.project, 'RC baseline', 'Before tuning').id

    def save_value(self, repo, value):
        project = repo.load(repo.active().head)
        project['cells'][0]['devices'][1]['value'] = value
        project['revision'] += 1
        return repo.save(project, 'Tune R1', f'Set it to {value}').id

    def test_diverged_branches_review_choices_and_keep_both_parents(self):
        topic = self.repo.create('test/tuning', self.base)
        self.repo.switch(topic)
        incoming = self.save_value(self.repo, '47k')
        main = next(b for b in self.repo.entries() if b.name == 'main')
        self.repo.switch(main)
        current = self.save_value(self.repo, '20k')
        topic = next(b for b in self.repo.entries() if b.name == 'test/tuning')
        review = self.repo.review(topic)
        candidate, conflicts, _ = review.resolve()
        self.assertIsNone(candidate)
        self.assertEqual((conflicts[0].base, conflicts[0].current, conflicts[0].incoming), ('10k', '20k', '47k'))
        with self.assertRaisesRegex(ValueError, 'Resolve every conflict'):
            self.repo.merge(review, {}, 4)
        self.assertEqual(self.repo.active().head, current)
        choice = {conflicts[0].path: 'incoming'}
        result = self.repo.merge(review, choice, 4)
        merged = self.repo.active().head
        self.assertEqual(self.repo.text('show', '-s', '--format=%P', merged).split(), [current, incoming])
        self.assertEqual(result['cells'][0]['devices'][1]['value'], '47k')
        versions = self.repo.list()
        self.assertEqual([v.id for v in versions], [merged, current, self.base])
        self.assertEqual((versions[0].revision, versions[-1].note), (4, 'Before tuning'))

    def test_stale_preview_and_fast_forward(self):
        topic = self.repo.create('tuning', self.base)
        self.repo.switch(topic)
        self.save_value(self.repo, '47k')
        main, topic = self.repo.entries()
        self.repo.switch(main)
        review = self.repo.review(topic)
        self.repo.switch(topic)
        incoming = self.save_value(self.repo, '38k')
        self.repo.switch(main)
        with self.assertRaisesRegex(ValueError, 'changed during review'):
            self.repo.merge(review, {}, 6)
        self.assertEqual(self.repo.active().head, self.base)
        updated = next(b for b in self.repo.entries() if b.name == 'tuning')
        self.repo.merge(self.repo.review(updated), {}, 6)
        self.assertEqual(self.repo.active().head, incoming)

    def test_fetch_publish_and_reject_non_fast_forward(self):
        remote = self.root / 'Remote with spaces.git'
        subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(remote)],
                       check=True, capture_output=True)
        url = 'https://github.com/owner/filter.git'

        class LocalTransport(ProjectGit):
            def _transport(self, command, *args):
                forwarded = [str(remote) if arg == url else arg for arg in args]
                self.git('-c', 'protocol.file.allow=always', command, *forwarded)

        first = LocalTransport(self.root / 'Filter with spaces.icproj', self.project['id'])
        first.connect(url)
        first.publish(first.active())
        other = LocalTransport(self.root / 'Collaborator.icproj', self.project['id'])
        other.initialize()
        other.connect(url)
        other.fetch()
        remote_main = next(b for b in other.entries() if b.remote and b.name == 'main')
        self.assertEqual(remote_main.head, self.base)
        other.switch(remote_main)
        upstream = self.save_value(other, '47k')
        other.publish(other.active())
        self.save_value(first, '20k')
        with self.assertRaises(ValueError):
            first.publish(first.active())
        first.fetch()
        fetched = next(b for b in first.entries() if b.remote and b.name == 'main')
        self.assertEqual(fetched.head, upstream)
        self.assertIsNone(first.review(fetched).resolve()[0])
        working = first.active()
        first.disconnect()
        self.assertEqual(first.remote_url(), '')
        self.assertTrue(all(not branch.remote for branch in first.entries()))
        self.assertEqual(first.active(), working)
