"""Canonical proposal composition; no live allocation or occupancy authority."""
import importlib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import ci_canary_assessment_test as fixtures
from tools.canary import records as r


class SourcePathTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('tools.canary.metadata_proposal')

    def test_readme_and_unrelated_contract_markdown_are_refused(self):
        for path in ('contracts/project/README.md', 'contracts/project/notes.md'):
            with self.subTest(path=path):
                self.assertFalse(self.m.source_path(path), path)

    def test_actual_assembly_markdown_profiles_are_admitted(self):
        assembly = json.loads((ROOT / self.m.PRODUCT[1]).read_text())
        profiles = [path for contract in assembly['contracts']
                    for path in (ROOT / 'contracts').glob(f"*/{contract['id']}.md")]
        self.assertTrue(profiles, 'assembly must exercise Markdown Contract profiles')
        for path in profiles:
            with self.subTest(path=path):
                self.assertTrue(self.m.source_path(path.relative_to(ROOT).as_posix()))

    def test_invalid_profile_nesting_is_refused(self):
        for path in ('contracts/lmdj.project.v1.md',
                     'contracts/project/nested/lmdj.project.v1.md'):
            with self.subTest(path=path):
                self.assertFalse(self.m.source_path(path), path)

    def test_invalid_profile_name_or_version_is_refused(self):
        for name in ('project.v1.md', 'lmdj.project.md', 'lmdj.project.v.md',
                     'lmdj.project.vx.md', 'lmdj.project.v1.0.md', 'lmdj..v1.md'):
            with self.subTest(name=name):
                self.assertFalse(self.m.source_path(f'contracts/project/{name}'), name)

    def test_schema_json_admission_is_preserved(self):
        for path in ('contracts/project/lmdj.project.v1.schema.json',
                     'contracts/example.schema.json',
                     'contracts/project/nested/example.schema.json'):
            with self.subTest(path=path):
                self.assertTrue(self.m.source_path(path), path)


class MetadataProposalTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('tools.canary.metadata_proposal')
        self.f = fixtures.AssessmentTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files'], text=True).splitlines()
        for name in tracked:
            if self.m.source_path(name) or name in self.m.GENERATORS:
                target = self.f.root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
        self.f.write('docs/frozen-manual.txt', 'Frozen bytes never change.\n')
        self.f.base = self.f.commit()
        self.f.write('apps/creator-web/src/example.ts', 'export const value = 2;\n')
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        current = json.loads((self.f.root / self.m.PRODUCT[0]).read_text())
        self.build = f"{current['milestone']}.{current['minor']}.{current['build'] + 1}.0"

    def prepare(self, *, advice=None, build=None):
        f = self.f
        return self.m.prepare_metadata(f.root, context=f.context,
            history=f.observe(output=advice or f.advice()), proposed_build=build or self.build,
            allocation_date='2026-09-09')

    def regenerate(self):
        m, root = self.m, self.f.root
        with m._generator(m.GENERATORS[0], (ROOT / m.GENERATORS[0]).read_bytes()) as version, \
                m._generator(m.GENERATORS[1], (ROOT / m.GENERATORS[1]).read_bytes()) as runtime:
            version.REPO_ROOT = root
            version.generate_lock(*(root / name for name in m.PRODUCT[:3]))
            runtime.write_or_check(root, False)
        m._pages(root, False)

    def assert_canonical(self):
        m, root = self.m, self.f.root
        with m._generator(m.GENERATORS[0], (ROOT / m.GENERATORS[0]).read_bytes()) as version, \
                m._generator(m.GENERATORS[1], (ROOT / m.GENERATORS[1]).read_bytes()) as runtime:
            version.REPO_ROOT = root
            version.verify(*(root / name for name in m.PRODUCT[:3]))
            runtime.write_or_check(root, True)
        m._pages(root, True)

    def test_actual_generators_compose_host_product_lock_runtime_and_changelog_outputs(self):
        advice = self.f.advice()
        advice['components'][1]['impact'] = 'minor'
        before = self.f.git('status', '--porcelain')
        result = self.prepare(advice=advice)
        self.assertEqual(self.f.git('status', '--porcelain'), before)
        self.assertFalse(result['admission_evidence'])
        self.assertIn('immutable-portal-snapshot', result['remaining_obligations'])
        for edit in result['edits']:
            old = self.f.root / edit['path']
            raw = old.read_bytes() if old.exists() else None
            self.assertEqual(edit['before_length'], len(raw) if raw is not None else None)
            self.assertEqual(edit['before_sha256'], hashlib.sha256(raw).hexdigest() if raw is not None else None)
            self.assertEqual(edit['after_length'], len(edit['content'].encode()))
            self.assertEqual(edit['after_sha256'], hashlib.sha256(edit['content'].encode()).hexdigest())
            self.f.write(edit['path'], edit['content'])
        self.assert_canonical()
        assembly = json.loads((self.f.root / self.m.PRODUCT[1]).read_text())
        lock = json.loads((self.f.root / self.m.PRODUCT[2]).read_text())
        identity = json.loads((self.f.root / self.m.PRODUCT[4]).read_text())
        self.assertEqual(assembly['product']['version'], self.build)
        self.assertEqual(lock['product']['version'], self.build)
        self.assertEqual(identity['product_build'], self.build)
        hosts = {host['id']: host['version'] for host in result['hosts']}
        base_versions = {host['id']: host['base_version'] for host in self.f.context['components']}
        a, b, c = map(int, base_versions['creator-web'].split('.'))
        self.assertEqual(hosts['creator-web'], f'{a}.{b}.{c + 1}')
        a, b, _ = map(int, base_versions['web-runtime-host'].split('.'))
        self.assertEqual(hosts['web-runtime-host'], f'{a}.{b + 1}.0')
        for name in self.m.PAGES:
            self.assertIn('State: **prepared**', (self.f.root / name).read_text())
        self.assertEqual((self.f.root / 'docs/frozen-manual.txt').read_text(), 'Frozen bytes never change.\n')

    def test_fixture_contains_exactly_one_source_for_each_assembly_contract(self):
        assembly = json.loads((self.f.root / self.m.PRODUCT[1]).read_text())
        for contract in assembly['contracts']:
            contract_id = contract['id']
            sources = sorted((self.f.root / 'contracts').glob(f'*/{contract_id}.schema.json'))
            sources += sorted((self.f.root / 'contracts').glob(f'*/{contract_id}.md'))
            with self.subTest(contract=contract_id):
                self.assertEqual(
                    len(sources), 1,
                    f'fixture contract inventory must resolve {contract_id} to exactly one source',
                )

    def test_product_only_proposal_preserves_host_versions_and_does_not_invent_logs(self):
        advice = self.f.advice()
        for item in advice['components']:
            item.update(impact='none', references=[], changelog=[])
        result = self.prepare(advice=advice)
        self.assertEqual(result['hosts'], [])
        self.assertEqual({edit['path'] for edit in result['edits']}, set(self.m.PRODUCT))

    def test_deterministic_replay_ignores_and_preserves_dirty_caller_bytes(self):
        expected = self.prepare()
        self.f.write(self.m.PRODUCT[0], 'caller edits must survive')
        self.f.write('apps/creator-web/CHANGELOG.md', 'caller untracked history')
        status = self.f.git('status', '--porcelain')
        self.assertEqual(self.prepare(), expected)
        self.assertEqual(self.f.git('status', '--porcelain'), status)
        self.assertEqual((self.f.root / self.m.PRODUCT[0]).read_text(), 'caller edits must survive')

    def test_prebumped_host_is_consumed_without_another_host_increment(self):
        manifest_path = self.f.root / 'apps/creator-web/module.json'
        manifest = json.loads(manifest_path.read_text())
        major, minor, patch_level = map(int, manifest['version'].split('.'))
        bumped = f'{major}.{minor}.{patch_level + 1}'
        manifest['version'] = bumped
        manifest_path.write_text(json.dumps(manifest))
        assembly_path = self.f.root / self.m.PRODUCT[1]
        assembly = json.loads(assembly_path.read_text())
        next(host for host in assembly['hosts'] if host['id'] == 'creator-web')['version'] = bumped
        assembly_path.write_text(json.dumps(assembly))
        self.regenerate()
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        result = self.prepare()
        host = next(host for host in result['hosts'] if host['id'] == 'creator-web')
        self.assertTrue(host['prebump_consumed'])
        self.assertEqual(host['version'], bumped)
        self.assertNotIn('apps/creator-web/module.json', [edit['path'] for edit in result['edits']])

    def test_invalid_product_proposals_are_not_admitted(self):
        current = json.loads((self.f.root / self.m.PRODUCT[0]).read_text())
        same = '.'.join(str(current[key]) for key in ('milestone', 'minor', 'build', 'patch'))
        for build in [same, self.build[:-1] + '1', '0.0.999.0', '1.1.999.0', 'bad', '9' * 5000 + '.0.0.0']:
            with self.subTest(build=build), self.assertRaisesRegex(r.CanaryError, 'why:.*remedy:'):
                self.prepare(build=build)

    def test_generator_source_must_match_pinned_control(self):
        self.f.write(self.m.GENERATORS[0], 'raise RuntimeError("must not execute")\n')
        self.f.base = self.f.commit()
        self.f.write('apps/creator-web/src/example.ts', 'export const value = 3;\n')
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        with self.assertRaisesRegex(r.CanaryError, 'generator differs.*remedy:'):
            self.prepare()

    def test_candidate_python_is_data_never_executed(self):
        self.f.write(self.m.GENERATORS[0], 'raise RuntimeError("candidate code executed")\n')
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        self.assertEqual(self.prepare()['state'], 'metadata-proposed')

    def test_source_head_advance_does_not_change_pinned_revision_or_proposal(self):
        expected = self.prepare()
        self.f.write('docs/newer.txt', 'A later source commit is not the candidate.\n')
        newer = self.f.commit()
        self.assertNotEqual(newer, self.f.target)
        inputs = self.m.p.a.planning.batch_controller.GitInputs(
            self.f.root, self.f.base, lambda: self.f.target)
        self.assertEqual(self.m._pinned_revision(inputs, self.f.target), self.f.target)
        self.assertEqual(self.prepare(), expected)

    def test_missing_canonical_input_fails_without_mutating_caller(self):
        self.f.git('rm', 'tools/web-runtime/runtime-identity.json')
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        before = self.f.git('status', '--porcelain')
        with self.assertRaisesRegex(r.CanaryError, 'canonical.*failed.*remedy:'):
            self.prepare()
        self.assertEqual(self.f.git('status', '--porcelain'), before)

    def test_symlinked_generator_input_is_not_followed(self):
        name = 'tools/web-runtime/runtime-identity.json'
        target = self.f.root / name
        target.unlink()
        target.symlink_to('/outside-the-fixture')
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        with self.assertRaisesRegex(r.CanaryError, 'regular Git blob'):
            self.prepare()

    def test_archive_substitution_cannot_invent_source_preimages(self):
        self.f.write('providers/archive-note.txt', '$Format:%H$\n')
        self.f.write('.gitattributes', 'providers/archive-note.txt export-subst\n')
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        with self.assertRaisesRegex(r.CanaryError, 'archived bytes differ.*remedy:'):
            self.prepare()

    def test_stale_runtime_pair_is_rejected_not_silently_repaired(self):
        self.f.write(self.m.PRODUCT[5], 'stale generated identity\n')
        self.f.target = self.f.commit()
        self.f.context = self.f.collect()
        with self.assertRaisesRegex(r.CanaryError, 'canonical.*failed.*remedy:'):
            self.prepare()

    def test_projection_failure_does_not_return_a_partial_proposal(self):
        with patch.object(self.m, '_pages', side_effect=r.CanaryError('why: fixture generator failed; remedy: restore generator')):
            with self.assertRaisesRegex(r.CanaryError, 'fixture generator failed'):
                self.prepare()
        self.assertEqual(self.f.git('status', '--porcelain'), '')

    def test_blocked_assessment_does_not_generate_metadata(self):
        advice = self.f.advice()
        advice['components'][0]['impact'] = 'major'
        with self.assertRaisesRegex(r.CanaryError, 'assessment is blocked'):
            self.prepare(advice=advice)


if __name__ == '__main__':
    unittest.main()
