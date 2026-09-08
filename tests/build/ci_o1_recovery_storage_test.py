"""Fixed O1 storage identity inventory, not remote initialization evidence."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import batch_runtime


class RecoveryStorageTests(unittest.TestCase):
    def setUp(self):
        self.config = batch_runtime.strict_json((ROOT / 'scripts/ci/o1_recovery_storage.json').read_bytes())

    def test_only_three_closed_runtime_roles(self):
        self.assertEqual(set(self.config), {'scheduler', 'outbox', 'claim'},
                         'why: unexpected storage role; remedy: retain the reviewed three-role inventory')
        fields = {'repository', 'issue_number', 'issue_node_id', 'bot_node_id', 'workflow_id', 'epoch'}
        for role, item in self.config.items():
            with self.subTest(role=role):
                self.assertEqual(set(item), fields, 'why: config is not six-field Runtime input; remedy: do not add protocol or arbitrary paths')
                self.assertIs(type(item['issue_number']), int, 'why: Issue number is not an integer; remedy: use the recorded numeric identity')
                self.assertIs(type(item['workflow_id']), int, 'why: workflow ID is not an integer; remedy: use the recorded numeric identity')
                for key in fields - {'issue_number', 'workflow_id'}:
                    self.assertIsInstance(item[key], str, 'why: identity is not text; remedy: retain exact recorded strings')
                    self.assertTrue(item[key], 'why: identity is empty; remedy: retain exact recorded strings')

    def test_numbers_are_independently_distinct(self):
        self.assertEqual(len({item['issue_number'] for item in self.config.values()}), 3,
                         'why: two roles alias an Issue number; remedy: use separate reserved Issues')

    def test_node_ids_are_independently_distinct(self):
        self.assertEqual(len({item['issue_node_id'] for item in self.config.values()}), 3,
                         'why: two roles alias a GraphQL node; remedy: use separate verified Issue identities')

    def test_epochs_are_independently_distinct(self):
        self.assertEqual(len({item['epoch'] for item in self.config.values()}), 3,
                         'why: role epochs alias; remedy: retain the separately recorded epochs')

    def test_shared_existing_writer_authority(self):
        authority = {(item['repository'], item['bot_node_id'], item['workflow_id']) for item in self.config.values()}
        self.assertEqual(authority, {('endaye/lmdj', 'MDM6Qm90NDE4OTgyODI=', 352307416)},
                         'why: storage writer authority changed; remedy: review identity migration, never infer authority')

    def test_roles_match_exact_reserved_issue_inventory(self):
        expected = {
            'scheduler': (824, 'I_kwDOTK_1fs8AAAABQJ5ORQ', 'o1-recovery-scheduler-20260908-issue824'),
            'outbox': (825, 'I_kwDOTK_1fs8AAAABQJ5UMQ', 'o1-recovery-outbox-20260908-issue825'),
            'claim': (857, 'I_kwDOTK_1fs8AAAABQLLT3w', 'o1-claim-cancel-live-20260908-issue857'),
        }
        actual = {role: (item['issue_number'], item['issue_node_id'], item['epoch']) for role, item in self.config.items()}
        self.assertEqual(actual, expected, 'why: role differs from independently verified reservation; remedy: explicitly review any replacement inventory')

    def test_each_role_is_accepted_by_actual_runtime_without_api_calls(self):
        class NoApi:
            def _request(self, *args, **kwargs):
                raise AssertionError('why: config validation called remote API; remedy: keep initialization a separate operation')
        env = {'GITHUB_REPOSITORY': 'endaye/lmdj', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': 'a' * 40,
               'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '1', 'BATCH_WRITER_LOCK': 'self-test-report'}
        for item in self.config.values():
            instance = batch_runtime.Runtime(item, root=ROOT, environment=env, api=NoApi())
            self.assertEqual(instance.config, item, 'why: actual Runtime changed role config; remedy: preserve six-field compatibility')


if __name__ == '__main__':
    unittest.main()
