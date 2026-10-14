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


# One verified full-SHA pin per action for every workflow that receives the
# Cloudflare deploy token. A movable tag lets whoever controls the action's
# repository run code beside that token on a shared runner. Each SHA was
# checked against `gh api repos/<action>/git/refs/tags/<tag>`.
DEPLOY_ACTION_PINS = {
    'actions/checkout': ('de0fac2e4500dabe0009e67214ff5f5447ce83dd', 'v6.0.2'),
    'actions/setup-node': ('249970729cb0ef3589644e2896645e5dc5ba9c38', 'v6.5.0'),
    'actions/setup-python': ('a309ff8b426b58ec0e2a45f0f869d46889d02405', 'v6.2.0'),
    'actions/upload-artifact': ('b7c566a772e6b6bfb58ed0dc250532a479d7789f', 'v6.0.0'),
}


def deploy_secret_workflows():
    return sorted(path for path in (ROOT / '.github/workflows').glob('*.yml')
                  if 'secrets.CLOUDFLARE_API_TOKEN' in directives(path.read_text()))


def step_items(source, key):
    """Each step whose `key:` line opens it or belongs to it, as text.

    A step runs from its `- ` item line to the next item at the same dash
    indentation or a line that leaves the step's key indentation.
    """
    lines = source.splitlines()
    items = []
    for index, line in enumerate(lines):
        match = re.match(r'^( *)(- )?' + re.escape(key) + r':', line)
        if match is None:
            continue
        key_indent = len(match.group(1)) + (2 if match.group(2) else 0)
        start = index
        if not match.group(2):
            while start > 0 and not re.match(r'^ {%d}- ' % (key_indent - 2), lines[start]):
                start -= 1
        end = start + 1
        while end < len(lines):
            depth = len(lines[end]) - len(lines[end].lstrip(' '))
            if lines[end].strip() and (depth < key_indent or lines[end].lstrip().startswith('- ') and depth <= key_indent - 2):
                break
            end += 1
        items.append('\n'.join(lines[start:end]))
    return items


class DeploySecretActionPinTest(unittest.TestCase):
    def test_the_scan_finds_every_known_deploy_workflow(self):
        names = {path.name for path in deploy_secret_workflows()}
        self.assertTrue({'deploy-cloudflare-portal.yml', 'cloudflare-preview-publish.yml',
                         'deploy-web-runtime-host.yml', 'deploy-creator-web.yml',
                         'deploy-default-assets.yml'} <= names, names)

    def test_actions_beside_the_deploy_token_use_the_verified_sha_pins(self):
        for path in deploy_secret_workflows():
            uses = re.findall(r'(?m)^\s*(?:- )?uses: (.+)$', directives(path.read_text()))
            self.assertTrue(uses, path.name)
            for value in uses:
                with self.subTest(workflow=path.name, uses=value):
                    match = re.fullmatch(r'([\w.-]+/[\w.-]+)@([0-9a-f]{40}) # (v\d+\.\d+\.\d+)', value.strip())
                    self.assertIsNotNone(match, f'why: {value} beside the Cloudflare deploy token is not a full '
                                                f'SHA pin; remedy: pin it as <sha> # <tag> from DEPLOY_ACTION_PINS')
                    self.assertEqual(DEPLOY_ACTION_PINS.get(match.group(1)), match.group(2, 3),
                                     f'why: {match.group(1)} is pinned to an unverified or divergent SHA; remedy: use '
                                     f'the shared verified pin or update DEPLOY_ACTION_PINS after verifying the tag')

    def test_checkouts_beside_the_deploy_token_do_not_persist_credentials(self):
        for path in deploy_secret_workflows():
            source = directives(path.read_text())
            checkouts = [item for item in step_items(source, 'uses') if re.search(r'uses: actions/checkout@', item)]
            self.assertTrue(checkouts, path.name)
            for checkout in checkouts:
                with self.subTest(workflow=path.name):
                    self.assertRegex(checkout, r'(?m)^ +persist-credentials: false$',
                                     'why: a checkout beside the Cloudflare deploy token leaves the job token in '
                                     '.git/config for repository scripts to read; remedy: set persist-credentials: false')


class BuildBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.raw = read_workflow('cloudflare-preview-build.yml')
        self.job = block(block(self.raw, 'jobs', 0), 'build', 2)

    def test_only_pr_events_and_activation_flag(self):
        self.assertEqual(keys(block(self.raw, 'on', 0), 2), {'pull_request'})
        self.assertIn('paths', keys(block(block(self.raw, 'on', 0), 'pull_request', 2), 4))
        condition = field(self.job, 'if', 4)
        self.assertIn("vars.CLOUDFLARE_PREVIEW_ENABLED == '1'", condition)
        self.assertIn('github.event.pull_request.head.repo.full_name == github.repository', condition)

    def test_budget_gate_is_trusted_and_first(self):
        self.assertEqual(mapping(block(self.job, 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read'})
        sequence = steps(self.job)
        self.assertEqual(optional_field(sequence[0], 'name'), 'Check out only the trusted budget gate')
        gate_checkout = block(sequence[0], 'with', 8)
        self.assertEqual(field(gate_checkout, 'ref', 10), '${{ github.event.pull_request.base.sha }}')
        self.assertEqual(field(gate_checkout, 'sparse-checkout', 10), 'scripts/ci')
        self.assertEqual(optional_field(sequence[1], 'name'), 'Admit within the approved monthly budget')
        gate_env = mapping(block(sequence[1], 'env', 8), 10)
        self.assertEqual(gate_env['GITHUB_TOKEN'], '${{ github.token }}')
        self.assertEqual(gate_env['CLOUDFLARE_PREVIEW_BUDGET_MINUTES'],
                         '${{ vars.CLOUDFLARE_PREVIEW_BUDGET_MINUTES }}')
        self.assertEqual(field(sequence[1], 'run', 8),
                         'python3 gate/scripts/ci/cloudflare_preview_budget.py --gate')

    def test_untrusted_build_cannot_reuse_privileged_runner(self):
        self.assertEqual(field(self.job, 'runs-on', 4), 'ubuntu-24.04')
        self.assertNotIn('environment', keys(self.job, 4))
        self.assertEqual(mapping(block(self.raw, 'permissions', 0), 2), {'contents': 'read'})
        self.assertNotIn('secrets.', directives(self.raw))
        self.assertNotIn('CLOUDFLARE_API_TOKEN', directives(self.raw))

    def test_no_persistent_checkout_credentials(self):
        checkouts = [s for s in steps(self.job) if optional_field(s, 'uses').startswith('actions/checkout@')]
        self.assertEqual(len(checkouts), 3)
        for checkout in checkouts:
            self.assertEqual(field(block(checkout, 'with', 8), 'persist-credentials', 10), 'false')
        self.assertEqual(field(block(checkouts[2], 'with', 8), 'ref', 10), '${{ github.event.pull_request.head.sha }}')

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
        self.assertIn("vars.CLOUDFLARE_PREVIEW_ENABLED == '1'", field(self.job, 'if', 4))

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


class BudgetMonitorBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.raw = read_workflow('cloudflare-preview-budget.yml')
        self.job = block(block(self.raw, 'jobs', 0), 'report', 2)

    def test_only_scheduled_or_manual_trusted_control(self):
        self.assertEqual(keys(block(self.raw, 'on', 0), 2), {'schedule', 'workflow_dispatch'})
        checkouts = [s for s in steps(self.job) if optional_field(s, 'uses').startswith('actions/checkout@')]
        self.assertEqual(len(checkouts), 1)
        settings = block(checkouts[0], 'with', 8)
        self.assertEqual(field(settings, 'sparse-checkout', 10), 'scripts/ci')
        self.assertEqual(field(settings, 'persist-credentials', 10), 'false')
        self.assertNotIn('ref', keys(settings, 10))

    def test_least_privilege_and_no_deployment_credential(self):
        self.assertEqual(mapping(block(self.raw, 'permissions', 0), 2), {'contents': 'read'})
        self.assertEqual(mapping(block(self.job, 'permissions', 4), 6),
                         {'contents': 'read', 'actions': 'read', 'issues': 'write'})
        self.assertNotIn('secrets.', directives(self.raw))
        self.assertNotIn('CLOUDFLARE_API_TOKEN', directives(self.raw))

    def test_activation_flag_and_cron_off_herd_marks(self):
        self.assertIn("vars.CLOUDFLARE_PREVIEW_ENABLED == '1'", field(self.job, 'if', 4))
        minute = re.search(r"- cron: '(\d+) \d+ \* \* \*'", self.raw).group(1)
        self.assertNotIn(minute, {'0', '30'})


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
                     'cloudflare-preview-build.yml', '\n  contents: read\n', '\n  contents: write\n')

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

    def test_security_contracts_need_no_ambient_site_packages(self):
        # Explicit class selection prevents recursively spawning this boundary test.
        result = subprocess.run([sys.executable, '-I', '-S', str(Path(__file__).resolve()),
                                 'BuildBoundaryTest', 'PublisherBoundaryTest', 'BudgetMonitorBoundaryTest'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         'why: workflow contracts require ambient packages; remedy: keep this test stdlib-only\n' + result.stderr)
        self.assertIn('Ran 10 tests', result.stderr)
        self.assertNotIn('skipped', result.stderr)


if __name__ == '__main__':
    unittest.main()
