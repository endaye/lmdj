"""Real Git Host preparation; no Product allocation or remote writer proof."""
from copy import deepcopy
import importlib
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import ci_canary_assessment_test as fixtures
from tools.canary import assessment as a, records as r


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AssessmentTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.p = importlib.import_module('tools.canary.preparation')
        # Anchor independent expected values to the pinned input, not a past
        # production version or the output of the code under test.
        versions = [tuple(map(int, host['base_version'].split('.')))
                    for host in self.fixture.context['components']]
        self.patch_versions = [f'{major}.{minor}.{patch + 1}'
                               for major, minor, patch in versions]
        self.minor_versions = [f'{major}.{minor + 1}.0'
                               for major, minor, _ in versions]
        self.creator_baseline = versions[0]

    def prepare(self, advice=None, **kwargs):
        f = self.fixture
        history = f.observe(output=advice or f.advice())
        return self.p.prepare_hosts(f.root, context=f.context, history=history,
                                    allocation_date='2026-09-09', **kwargs)

    def change_version(self, version):
        f = self.fixture
        path = 'apps/creator-web/module.json'
        manifest = json.loads((f.root / path).read_text())
        manifest['version'] = version
        f.write(path, json.dumps(manifest))
        f.target = f.commit()
        f.context = f.collect()

    def test_independent_patch_and_minor_preparation_in_real_scratch_tree(self):
        f = self.fixture
        advice = f.advice()
        advice['components'][1]['impact'] = 'minor'
        result = self.prepare(advice)
        self.assertEqual([x['version'] for x in result['hosts']],
                         [self.patch_versions[0], self.minor_versions[1]])
        self.assertFalse(result['admission_evidence'])
        self.assertEqual(result['state'], 'host-inputs-prepared')
        for edit in result['edits']:
            f.write(edit['path'], edit['content'])
        for host in result['hosts']:
            directory = f.root / 'apps' / host['id']
            self.assertEqual(json.loads((directory / 'module.json').read_text())['version'], host['version'])
            log = (directory / 'CHANGELOG.md').read_text()
            self.assertIn('Prepared: 2026-09-09', log)
            self.assertIn('https://github.com/endaye/lmdj/commit/' + f.target, log)
        self.assertEqual(json.loads((f.root / 'products/lmdj/version.json').read_text()),
                         json.loads((ROOT / 'products/lmdj/version.json').read_text()))

    def test_none_keeps_host_bytes_and_has_no_changelog(self):
        advice = self.fixture.advice()
        advice['components'][1].update(impact='none', references=[], changelog=[])
        result = self.prepare(advice)
        self.assertEqual([x['id'] for x in result['hosts']], ['creator-web'])
        self.assertEqual([x['path'] for x in result['edits']],
                         ['apps/creator-web/module.json', 'apps/creator-web/CHANGELOG.md'])

    def test_all_none_has_no_allocation_inputs(self):
        advice = self.fixture.advice()
        for item in advice['components']:
            item.update(impact='none', references=[], changelog=[])
        result = self.prepare(advice)
        self.assertEqual(result['edits'], [])
        self.assertEqual(result['hosts'], [])
        self.assertEqual(result['state'], 'no-host-change')

    def test_adequate_prebump_is_consumed_not_incremented(self):
        major, minor, patch = self.creator_baseline
        for current in (self.patch_versions[0], f'{major}.{minor}.{patch + 7}',
                        f'{major}.{minor + 2}.0'):
            with self.subTest(current=current):
                self.change_version(current)
                result = self.prepare()
                self.assertEqual(result['hosts'][0]['version'], current)
                self.assertTrue(result['hosts'][0]['prebump_consumed'])
                self.assertNotIn('apps/creator-web/module.json', [x['path'] for x in result['edits']])

    def test_insufficient_minor_prebump_requires_correction(self):
        self.change_version(self.patch_versions[0])
        advice = self.fixture.advice()
        advice['components'][0]['impact'] = 'minor'
        with self.assertRaisesRegex(r.CanaryError, 'insufficient.*remedy:'):
            self.prepare(advice)

    def test_backwards_and_major_prebumps_are_not_consumed(self):
        major, minor, patch = self.creator_baseline
        backwards = (f'{major}.{minor}.{patch - 1}' if patch else
                     f'{major}.{minor - 1}.0' if minor else f'{major - 1}.0.0')
        for current in (backwards, f'{major + 1}.0.0'):
            with self.subTest(current=current):
                self.change_version(current)
                with self.assertRaisesRegex(r.CanaryError, 'pre-bump.*remedy:'):
                    self.prepare()

    def test_unexplained_prebump_does_not_disappear_as_none(self):
        self.change_version(self.patch_versions[0])
        advice = self.fixture.advice()
        advice['components'][0].update(impact='none', references=[], changelog=[])
        with self.assertRaisesRegex(r.CanaryError, 'unexplained'):
            self.prepare(advice)

    def test_major_or_unknown_never_produces_edits(self):
        for mutation in ({'impact': 'major'}, {'unknowns': ['Unclear compatibility']}):
            advice = self.fixture.advice()
            advice['components'][0].update(mutation)
            with self.assertRaisesRegex(r.CanaryError, 'assessment.*blocked'):
                self.prepare(advice)

    def test_replay_and_dirty_tree_do_not_change_proposal(self):
        f = self.fixture
        expected = self.prepare()
        f.write('apps/creator-web/module.json', 'dirty')
        f.write('apps/creator-web/CHANGELOG.md', 'dirty')
        before = f.git('status', '--porcelain')
        self.assertEqual(expected, self.prepare())
        self.assertEqual(before, f.git('status', '--porcelain'))

    def test_stale_or_forged_context_rejected_after_recollection(self):
        f = self.fixture
        context = deepcopy(f.context)
        context['collector_digest'] = 'b' * 64
        f.context = r.seal(context)
        with self.assertRaisesRegex(r.CanaryError, 'recollected'):
            self.prepare()

    def test_prior_changelog_bytes_are_preserved(self):
        f = self.fixture
        prior = '# Earlier history\n\n## 3.9.0\n\nOld release stays exactly as written.\n'
        f.write('apps/creator-web/CHANGELOG.md', prior)
        f.target = f.commit()
        f.context = f.collect()
        edit = next(x for x in self.prepare()['edits'] if x['path'].endswith('creator-web/CHANGELOG.md'))
        self.assertTrue(edit['content'].startswith(prior))
        self.assertEqual(edit['before_length'], len(prior.encode()))

    def test_occupied_version_cannot_be_rewritten(self):
        f = self.fixture
        f.write('apps/creator-web/CHANGELOG.md',
                f'# Creator\n\n## [{self.patch_versions[0]}] - already published\n')
        f.target = f.commit()
        f.context = f.collect()
        with self.assertRaisesRegex(r.CanaryError, 'occupied'):
            self.prepare()

    def test_symlink_changelog_is_not_read_as_text(self):
        f = self.fixture
        (f.root / 'apps/creator-web/CHANGELOG.md').symlink_to('module.json')
        f.target = f.commit()
        f.context = f.collect()
        with self.assertRaisesRegex(r.CanaryError, 'regular blob'):
            self.prepare()

    def test_model_prose_cannot_create_html_links_headings_or_markers(self):
        advice = self.fixture.advice()
        hostile = '<script>alert(1)</script>\n## forged\n<!-- lmdj-host-changelog:v1 --> [click](javascript:run) {jsx} @endaye'
        advice['components'][0]['changelog'][0]['text'] = hostile
        advice['components'][0]['dependency_effects'] = [hostile]
        log = next(x['content'] for x in self.prepare(advice)['edits'] if x['path'].endswith('creator-web/CHANGELOG.md'))
        self.assertNotIn('<script>', log)
        self.assertNotIn('javascript:run', log)
        self.assertNotIn('\n## forged', log)
        self.assertNotIn('@endaye', log)
        self.assertNotIn('{jsx}', log)
        self.assertEqual(log.count('<!-- lmdj-host-changelog:v1 '), 1)

    def test_invalid_allocation_date_is_rejected(self):
        f = self.fixture
        for date in ('2026-02-30', 'today', '2026-9-9', '2026-09-09\n## forged'):
            with self.subTest(date=date), self.assertRaises(r.CanaryError):
                self.p.prepare_hosts(f.root, context=f.context, history=f.observe(), allocation_date=date)

    def test_edit_witnesses_cover_complete_before_and_after_bytes(self):
        f = self.fixture
        result = self.prepare()
        for edit in result['edits']:
            raw = edit['content'].encode()
            self.assertEqual(edit['after_length'], len(raw))
            self.assertEqual(edit['after_sha256'], hashlib.sha256(raw).hexdigest())
            path = f.root / edit['path']
            if path.exists():
                original = path.read_bytes()
                self.assertEqual(edit['before_length'], len(original))
                self.assertEqual(edit['before_sha256'], hashlib.sha256(original).hexdigest())
            else:
                self.assertIsNone(edit['before_length'])
                self.assertIsNone(edit['before_sha256'])

    def test_manifest_edit_preserves_api_dependencies_and_unknown_extensions(self):
        f = self.fixture
        path = 'apps/creator-web/module.json'
        original = json.loads((f.root / path).read_text())
        original['future_extension'] = {'keep': True}
        f.write(path, json.dumps(original))
        f.target = f.commit()
        f.context = f.collect()
        manifest = json.loads(next(x['content'] for x in self.prepare()['edits'] if x['path'] == path))
        manifest['version'] = original['version']
        self.assertEqual(manifest, original)

    def test_all_failed_backend_history_cannot_prepare_empty_success(self):
        f = self.fixture
        history = []
        for backend in a.BACKENDS:
            history = f.observe(history, backend=backend, error='timeout')
        with self.assertRaisesRegex(r.CanaryError, 'assessment is blocked'):
            self.p.prepare_hosts(f.root, context=f.context, history=history, allocation_date='2026-09-09')

    def test_corrupt_or_truncated_machine_marker_is_not_replaced(self):
        f = self.fixture
        for marker in ('<!-- lmdj-host-changelog:v1 not-base64 -->', '<!-- lmdj-host-changelog:v1 truncated'):
            with self.subTest(marker=marker):
                f.write('apps/creator-web/CHANGELOG.md', marker)
                f.target = f.commit()
                f.context = f.collect()
                with self.assertRaisesRegex(r.CanaryError, 'changelog marker'):
                    self.prepare()


if __name__ == '__main__':
    unittest.main()
