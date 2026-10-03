import unittest

from scripts.release_intent import public_release_requested


class ReleaseIntentTests(unittest.TestCase):
    def test_ordinary_source_push_keeps_release_private(self):
        self.assertFalse(public_release_requested('0.23.0', 'push', 'refs/heads/main',
                                                 {'head_commit': {'message': 'Fix a dialog'}}))

    def test_exact_version_commit_requests_publication_on_main(self):
        for message in ('Release 0.23.0', 'Release 0.23.0\n\nWindows and Linux downloads'):
            with self.subTest(message=message):
                self.assertTrue(public_release_requested('0.23.0', 'push', 'refs/heads/main',
                                                        {'head_commit': {'message': message}}))

    def test_other_version_or_similar_message_does_not_publish(self):
        for message in ('Release 0.22.0', 'Release 0.23.0 documentation', 'release 0.23.0', ''):
            with self.subTest(message=message):
                self.assertFalse(public_release_requested('0.23.0', 'push', 'refs/heads/main',
                                                         {'head_commit': {'message': message}}))

    def test_manual_publication_is_explicit(self):
        for value in (True, 'true'):
            self.assertTrue(public_release_requested('0.23.0', 'workflow_dispatch', 'refs/heads/main',
                                                    {'inputs': {'publish_release': value}}))
        for value in (False, 'false', None):
            self.assertFalse(public_release_requested('0.23.0', 'workflow_dispatch', 'refs/heads/main',
                                                     {'inputs': {'publish_release': value}}))

    def test_experimental_and_feature_branches_cannot_publish(self):
        for ref in ('refs/heads/experimental', 'refs/heads/fix/public-usability-review', 'refs/tags/v0.23.0'):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'main'):
                public_release_requested('0.23.0', 'workflow_dispatch', ref,
                                         {'inputs': {'publish_release': True}})

    def test_development_version_cannot_be_published_as_a_regular_release(self):
        with self.assertRaisesRegex(ValueError, 'X.Y.Z'):
            public_release_requested('0.22.0.dev25', 'workflow_dispatch', 'refs/heads/main',
                                     {'inputs': {'publish_release': True}})

    def test_versions_with_leading_zeroes_cannot_request_publication(self):
        for version in ('00.23.0', '0.023.0', '0.23.00'):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'X.Y.Z'):
                public_release_requested(version, 'workflow_dispatch', 'refs/heads/main',
                                         {'inputs': {'publish_release': True}})
            self.assertFalse(public_release_requested(version, 'push', 'refs/heads/main',
                                                     {'head_commit': {'message': 'Release ' + version}}))

    def test_development_and_experimental_release_commits_keep_draft_behavior(self):
        for version, ref in (('0.22.0.dev25', 'refs/heads/main'),
                             ('0.23.0', 'refs/heads/experimental')):
            with self.subTest(version=version, ref=ref):
                self.assertFalse(public_release_requested(version, 'push', ref,
                                                         {'head_commit': {'message': 'Release ' + version}}))

    def test_pull_request_commit_message_does_not_publish(self):
        self.assertFalse(public_release_requested('0.23.0', 'pull_request', 'refs/pull/60/merge',
                                                 {'head_commit': {'message': 'Release 0.23.0'}}))


if __name__ == '__main__':
    unittest.main()
