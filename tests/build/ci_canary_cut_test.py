"""Real pre/post-squash histories, not GitHub authority or allocation proof."""
import importlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import ci_canary_planning_test as fixtures
from tools.canary import records as r


class CutTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PlanningTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.c = importlib.import_module('tools.canary.cut')
        self.assessed = self.f.base
        self.path = 'apps/creator-web/module.json'
        self.f.git('checkout', '-b', 'docs/version')
        manifest = json.loads((self.f.root / self.path).read_text())
        parts = list(map(int, manifest['version'].split('.')))
        parts[2] += 1
        manifest['version'] = '.'.join(map(str, parts))
        self.proposed = json.dumps(manifest, indent=2) + '\n'
        self.head = self.f.change(self.path, self.proposed)
        self.f.git('checkout', 'main')

    def check(self, merged=None, **kwargs):
        arguments = dict(assessed_target=self.assessed, reviewed_base=self.assessed,
                         reviewed_head=self.head, observed_main=self.f.git('rev-parse', 'main'),
                         control_sha=self.assessed, declared_outputs=[self.path], merged_sha=merged)
        arguments.update(kwargs)
        return self.c.check_coverage(self.f.root, **arguments)

    def squash(self, extra=False, text=None):
        self.f.write(self.path, self.proposed if text is None else text)
        if extra:
            self.f.write('apps/creator-web/src/unreviewed.ts', 'unreviewed')
        return self.f.commit('squash version PR')

    def test_premerge_unchanged_base_is_covered_not_admitted(self):
        result = self.check()
        self.assertEqual(result['status'], 'covered')
        self.assertEqual(result['intervening']['commits'], [])
        self.assertFalse(result['admission_evidence'])
        self.assertEqual(result['stage'], 'pre-merge')

    def test_explanatory_docs_allow_no_reassessment(self):
        self.f.change('docs/design/harmless.md', 'explanation')
        result = self.check()
        self.assertEqual(result['status'], 'covered')
        self.assertEqual(len(result['intervening']['commits']), 1)
        self.assertEqual(result['intervening_scope']['kind'], 'none')

    def test_routed_docs_require_reassessment(self):
        self.f.change('apps/docs-site/docs/overview/index.mdx', 'new source fact')
        self.assertEqual(self.check()['status'], 'needs-assessment')

    def test_foundational_changes_require_reassessment(self):
        self.f.change('packages/foundation/src/unassessed.cpp', 'change')
        result = self.check()
        self.assertEqual(result['status'], 'needs-assessment')
        self.assertEqual(result['intervening_scope']['kind'], 'full')

    def test_intermediate_edit_and_revert_do_not_disappear(self):
        self.f.change('apps/creator-web/src/unassessed.ts', 'change')
        self.f.git('revert', '--no-edit', 'HEAD')
        self.assertEqual(self.f.git('diff', '--name-only', self.assessed, 'main'), '')
        result = self.check()
        self.assertEqual(result['status'], 'needs-assessment')
        self.assertEqual(len(result['intervening']['commits']), 2)

    def test_changed_output_preimage_requires_refresh(self):
        self.f.change(self.path, self.proposed + ' ')
        result = self.check()
        self.assertIn('reviewed-output-preimage-moved', result['reasons'])
        self.assertEqual(result['status'], 'needs-assessment')

    def test_exact_squash_with_intervening_docs_is_covered(self):
        self.f.change('docs/design/harmless.md', 'note')
        merged = self.squash()
        result = self.check(merged)
        self.assertEqual(result['status'], 'covered')
        self.assertEqual(result['candidate_sha'], merged)
        self.assertEqual(result['stage'], 'post-squash')

    def test_extra_or_changed_squash_outputs_require_refresh(self):
        result = self.check(self.squash(extra=True))
        self.assertEqual(result['status'], 'needs-assessment')
        self.assertIn('squash-differs-from-reviewed-delta', result['reasons'])

    def test_tampered_squash_bytes_cannot_keep_coverage(self):
        result = self.check(self.squash(text=self.proposed + ' '))
        self.assertIn('squash-differs-from-reviewed-delta', result['reasons'])

    def test_deleted_squash_output_cannot_keep_coverage(self):
        self.f.git('rm', self.path)
        merged = self.f.commit('delete instead of allocation')
        self.assertEqual(self.check(merged)['status'], 'needs-assessment')

    def test_mode_only_tampering_is_detected(self):
        self.f.write(self.path, self.proposed)
        self.f.git('add', self.path)
        self.f.git('update-index', '--chmod=+x', self.path)
        self.f.git('commit', '-m', 'wrong mode')
        self.assertEqual(self.check(self.f.git('rev-parse', 'HEAD'))['status'], 'needs-assessment')

    def test_later_main_does_not_retarget_covered_candidate(self):
        merged = self.squash()
        before = self.check(merged)
        self.f.change('packages/foundation/src/later.cpp', 'next batch')
        after = self.check(merged)
        self.assertEqual(before, after)

    def test_multiple_parent_merge_is_not_squash(self):
        self.f.git('merge', '--no-ff', 'docs/version', '-m', 'wrong merge method')
        with self.assertRaisesRegex(r.CanaryError, 'single-parent'):
            self.check(self.f.git('rev-parse', 'HEAD'))

    def test_undeclared_or_ambiguous_inventory_is_refused(self):
        for paths in ([], [self.path, self.path], ['../escape'], [self.path, 'extra']):
            with self.subTest(paths=paths), self.assertRaises(r.CanaryError):
                self.check(declared_outputs=paths)

    def test_missing_objects_or_side_branch_candidate_are_refused(self):
        for args in ({'reviewed_head': 'f' * 40}, {'merged_sha': self.head},
                     {'assessed_target': self.head}, {'control_sha': 'f' * 40}):
            with self.subTest(args=args), self.assertRaises(r.CanaryError):
                self.check(**args)

    def test_dirty_files_and_replay_do_not_change_proof(self):
        before = self.check()
        self.f.write(self.path, 'dirty')
        self.f.write('scripts/ci/test_scope.py', 'raise RuntimeError("untrusted")')
        state = self.f.git('status', '--porcelain'), self.f.git('show-ref')
        self.assertEqual(before, self.check())
        self.assertEqual(state, (self.f.git('status', '--porcelain'), self.f.git('show-ref')))

    def test_intervening_policy_change_cannot_exempt_itself(self):
        self.f.change('scripts/ci/test_scope_policy.json', '{}')
        result = self.check()
        self.assertEqual(result['status'], 'needs-assessment')
        self.assertEqual(result['intervening_scope']['kind'], 'full')

    def test_rename_is_complete_delete_and_add_not_one_omitted_path(self):
        self.f.git('checkout', 'docs/version')
        self.f.git('mv', self.path, 'apps/creator-web/moved.json')
        self.f.git('commit', '--amend', '--no-edit')
        renamed = self.f.git('rev-parse', 'HEAD')
        self.f.git('checkout', 'main')
        result = self.check(reviewed_head=renamed,
                            declared_outputs=[self.path, 'apps/creator-web/moved.json'])
        self.assertEqual(result['status'], 'covered')
        rows = {row['path']: row for row in result['reviewed_delta']}
        self.assertEqual(rows[self.path]['after_oid'], self.c.ZERO)
        self.assertEqual(rows['apps/creator-web/moved.json']['before_oid'], self.c.ZERO)

    def test_reviewed_multiple_commits_are_not_one_atomic_cut(self):
        self.f.git('checkout', 'docs/version')
        head = self.f.change('docs/design/extra.md', 'another task')
        self.f.git('checkout', 'main')
        with self.assertRaisesRegex(r.CanaryError, 'one single-parent commit'):
            self.check(reviewed_head=head, declared_outputs=[self.path, 'docs/design/extra.md'])

    def test_post_squash_exact_outputs_do_not_cover_unassessed_business_change(self):
        self.f.change('packages/foundation/src/unassessed.cpp', 'change')
        result = self.check(self.squash())
        self.assertEqual(result['reviewed_delta'], result['merged_delta'])
        self.assertEqual(result['status'], 'needs-assessment')
        self.assertIn('unassessed-intervening-changes', result['reasons'])

    def test_invalid_current_policy_is_unavailable_not_covered(self):
        control = self.f.change('scripts/ci/test_scope_policy.json', 'invalid json')
        with self.assertRaisesRegex(r.CanaryError, 'why:.*remedy:'):
            self.check(control_sha=control)


if __name__ == '__main__':
    unittest.main()
