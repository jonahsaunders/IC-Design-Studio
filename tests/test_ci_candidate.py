"""Mutable refs and incomplete candidate identities cannot launch acceptance."""
import unittest
from scripts.ci_candidate import validate_candidate


class CandidateTests(unittest.TestCase):
    def test_manual_candidate_and_reusable_caller_event(self):
        event = {'inputs': {'candidate_sha': 'a' * 40, 'publish_release': 'false'}}
        self.assertEqual(validate_candidate('workflow_dispatch', event, 'a' * 40, 'a' * 40)['commit'], 'a' * 40)

    def test_missing_malformed_or_changed_manual_candidate_fails(self):
        for value in ('', 'experimental', 'a' * 7, 'A' * 40, 'b' * 40, None, 12, 'a' * 40 + '\n'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate('workflow_dispatch', {'inputs': {'candidate_sha': value}}, 'a' * 40, 'a' * 40)

    def test_version_tag_keeps_exact_event_checkout_without_manual_input(self):
        result = validate_candidate('push', {'ref': 'refs/tags/v0.23.0'}, 'b' * 40, 'b' * 40)
        self.assertEqual(result['commit'], 'b' * 40)

    def test_wrong_checkout_or_unselected_event_is_rejected(self):
        for event, body, expected, actual in (
            ('push', {'ref': 'refs/tags/v1'}, 'a' * 40, 'b' * 40),
            ('push', {'ref': 'refs/tags/v1'}, 'short', 'short'),
            ('push', {'ref': 'refs/heads/main'}, 'a' * 40, 'a' * 40),
            ('pull_request', {}, 'a' * 40, 'a' * 40),
            ('workflow_call', {}, 'a' * 40, 'a' * 40),
        ):
            with self.subTest(event=event, body=body), self.assertRaises(ValueError):
                validate_candidate(event, body, expected, actual)


if __name__ == '__main__':
    unittest.main()
