from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/build'))
from ci_self_test_report_workflow_test import block, field, scalars


def read_workflow(name):
    return (ROOT / '.github/workflows' / name).read_text()


def keys(source, indent):
    """Direct keys in the repository's explicit mapping layout, not YAML parsing."""
    names = []
    for line in source.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        depth = len(line) - len(line.lstrip(' '))
        if depth > indent:
            continue
        match = re.fullmatch(r'([\w-]+):(?: .*|)', line[indent:]) if depth == indent else None
        if match is None:
            raise AssertionError('why: unsupported workflow mapping syntax; remedy: retain explicit unquoted direct keys')
        names.append(match.group(1))
    if len(names) != len(set(names)):
        raise AssertionError('why: duplicate workflow key is ambiguous; remedy: retain one explicit declaration per key')
    return set(names)


def mapping(source, indent):
    values = scalars(source, indent)
    if keys(source, indent) != set(values):
        raise AssertionError('why: security mapping is not explicit scalars; remedy: retain auditable key/value declarations')
    return values


def steps(job):
    # Reuse exact-indentation block/field helpers for each real sequence item.
    # Shell bodies and nested `with`/`env` mappings cannot start another step.
    source = block(job, 'steps', 4)
    parts = re.split(r'(?m)^      - ', source)
    if parts[0].strip() or len(parts) == 1:
        raise AssertionError('why: workflow steps are not an explicit list; remedy: keep one six-space step item per entry')
    return ['        ' + part for part in parts[1:]]


def optional_field(source, name):
    return field(source, name, 8) if name in keys(source, 8) else ''


def directives(source):
    return '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('#'))


class BuildBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.raw = read_workflow('cloudflare-preview-build.yml')
        self.job = block(block(self.raw, 'jobs', 0), 'build', 2)

    def test_only_pr_events_and_exact_opt_in_branch(self):
        self.assertEqual(keys(block(self.raw, 'on', 0), 2), {'pull_request'})
        condition = field(self.job, 'if', 4)
        self.assertIn("vars.CLOUDFLARE_PREVIEW_PILOT_BRANCH != ''", condition)
        self.assertIn('github.head_ref == vars.CLOUDFLARE_PREVIEW_PILOT_BRANCH', condition)
        self.assertIn('github.event.pull_request.head.repo.full_name == github.repository', condition)

    def test_untrusted_build_cannot_reuse_privileged_runner(self):
        self.assertEqual(field(self.job, 'runs-on', 4), 'ubuntu-24.04')
        self.assertNotIn('environment', keys(self.job, 4))
        self.assertEqual(mapping(block(self.raw, 'permissions', 0), 2), {'contents': 'read'})
        self.assertNotIn('secrets.', directives(self.raw))
        self.assertNotIn('CLOUDFLARE_API_TOKEN', directives(self.raw))

    def test_no_persistent_checkout_credentials(self):
        checkouts = [s for s in steps(self.job) if optional_field(s, 'uses').startswith('actions/checkout@')]
        self.assertEqual(len(checkouts), 2)
        for checkout in checkouts:
            self.assertEqual(field(block(checkout, 'with', 8), 'persist-credentials', 10), 'false')
        self.assertEqual(field(block(checkouts[1], 'with', 8), 'ref', 10), '${{ github.event.pull_request.head.sha }}')

    def test_artifact_identity_matches_consumer_contract(self):
        uploads = [s for s in steps(self.job) if optional_field(s, 'uses').startswith('actions/upload-artifact@')]
        self.assertEqual(len(uploads), 1)
        settings = block(uploads[0], 'with', 8)
        self.assertEqual(field(settings, 'name', 10), 'portal-preview-${{ github.event.pull_request.head.sha }}-${{ github.run_attempt }}')
        self.assertTrue(field(settings, 'path', 10).endswith('/static.zip'))
        self.assertEqual(field(settings, 'if-no-files-found', 10), 'error')


class PublisherBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.raw = read_workflow('cloudflare-preview-publish.yml')
        self.job = block(block(self.raw, 'jobs', 0), 'publish', 2)

    def test_only_default_branch_workflow_run_control(self):
        self.assertEqual(keys(block(self.raw, 'on', 0), 2), {'workflow_run'})
        checkouts = [s for s in steps(self.job) if optional_field(s, 'uses').startswith('actions/checkout@')]
        self.assertEqual(len(checkouts), 1)
        settings = block(checkouts[0], 'with', 8)
        self.assertEqual(field(settings, 'ref', 10), '${{ github.workflow_sha }}')
        self.assertEqual(field(settings, 'persist-credentials', 10), 'false')
        self.assertIn("vars.CLOUDFLARE_PREVIEW_PILOT_BRANCH != ''", field(self.job, 'if', 4))

    def test_deploy_secret_only_enters_trusted_publish_step(self):
        holders = [s for s in steps(self.job) if 'env' in keys(s, 8)
                   and 'CLOUDFLARE_API_TOKEN' in mapping(block(s, 'env', 8), 10)]
        self.assertEqual(len(holders), 1)
        self.assertEqual(field(holders[0], 'run', 8), 'python3 scripts/ci/cloudflare_preview_publish.py')
        self.assertEqual(field(self.job, 'environment', 4), 'portal-cloudflare-preview')
        installs = [s for s in steps(self.job) if optional_field(s, 'name').startswith('Install trusted')]
        self.assertEqual(len(installs), 1)
        self.assertNotIn('env', keys(installs[0], 8))
        self.assertEqual(field(block(self.raw, 'concurrency', 0), 'cancel-in-progress', 2), 'false')


class ContractRegressionTest(unittest.TestCase):
    def rejects(self, case_type, method, filename, old, new):
        source = read_workflow(filename)
        self.assertEqual(source.count(old), 1)
        with mock.patch(__name__ + '.read_workflow', return_value=source.replace(old, new)):
            result = unittest.TestResult()
            case_type(method).run(result)
        self.assertEqual(len(result.errors), 0, result.errors)
        self.assertEqual(len(result.failures), 1,
                         'why: unsafe workflow mutation escaped its contract; remedy: restore the exact security assertion')

    def test_wrong_build_permission_is_rejected(self):
        self.rejects(BuildBoundaryTest, 'test_untrusted_build_cannot_reuse_privileged_runner',
                     'cloudflare-preview-build.yml', '  contents: read', '  contents: write')

    def test_wrong_exact_source_checkout_is_rejected(self):
        self.rejects(BuildBoundaryTest, 'test_no_persistent_checkout_credentials',
                     'cloudflare-preview-build.yml',
                     '          ref: ${{ github.event.pull_request.head.sha }}',
                     '          ref: ${{ github.event.pull_request.base.sha }}')

    def test_quoted_job_environment_is_rejected(self):
        self.rejects(BuildBoundaryTest, 'test_untrusted_build_cannot_reuse_privileged_runner',
                     'cloudflare-preview-build.yml', '    runs-on: ubuntu-24.04\n',
                     '    runs-on: ubuntu-24.04\n    "environment": protected\n')

    def test_inline_secret_on_another_step_is_rejected(self):
        self.rejects(PublisherBoundaryTest, 'test_deploy_secret_only_enters_trusted_publish_step',
                     'cloudflare-preview-publish.yml',
                     '      - name: Retain sanitized publication observations\n',
                     '      - name: Retain sanitized publication observations\n'
                     '        env: {CLOUDFLARE_API_TOKEN: "${{ secrets.CLOUDFLARE_API_TOKEN }}"}\n')

    def test_secret_in_install_step_is_rejected(self):
        self.rejects(PublisherBoundaryTest, 'test_deploy_secret_only_enters_trusted_publish_step',
                     'cloudflare-preview-publish.yml',
                     '      - name: Install trusted tools without deployment credentials\n',
                     '      - name: Install trusted tools without deployment credentials\n'
                     '        env:\n          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}\n')

    def test_six_security_contracts_need_no_ambient_site_packages(self):
        # Explicit class selection prevents recursively spawning this boundary test.
        result = subprocess.run([sys.executable, '-I', '-S', str(Path(__file__).resolve()),
                                 'BuildBoundaryTest', 'PublisherBoundaryTest'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         'why: workflow contracts require ambient packages; remedy: keep this test stdlib-only\n' + result.stderr)
        self.assertIn('Ran 6 tests', result.stderr)
        self.assertNotIn('skipped', result.stderr)


if __name__ == '__main__':
    unittest.main()
