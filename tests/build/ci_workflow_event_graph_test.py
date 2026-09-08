#!/usr/bin/env python3
"""Catch GitHub's observed self-subscription rejection, not hypothetical cycles.

This scans the repository's explicit YAML layout using the existing workflow
contract helpers. It does not claim to replace GitHub's server validation.
"""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/build'))
from ci_self_test_report_workflow_test import block, field, scalars
from workflow_inventory import jobs_in


def unsupported():
    raise AssertionError('why: workflow name is outside the explicit YAML string subset; remedy: use a plain or quoted string name without nested values')


def scalar(value):
    """Explicit names only; not a general YAML scalar resolver."""
    value = value.strip()
    if value.startswith('"'):
        try:
            value = json.loads(value)  # JSON escapes are a YAML string subset.
        except ValueError:
            unsupported()
    elif value.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')*'", value):
            unsupported()
        value = value[1:-1].replace("''", "'")
    elif (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9 _./()'-]*", value)
          or value.lower() in {'null', 'true', 'false', 'yes', 'no', 'on', 'off'}):
        unsupported()
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        unsupported()
    return value


def flow_names(value):
    """Parse only single-line flow lists of supported string names."""
    if not value.endswith(']'):
        unsupported()
    remainder, names = value[1:-1].strip(), []
    while remainder:
        match = re.match(r'''"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^,\[\]{}]+''', remainder)
        if match is None:
            unsupported()
        names.append(scalar(match.group()))
        remainder = remainder[match.end():].strip()
        if remainder:
            if not remainder.startswith(',') or not remainder[1:].strip():
                unsupported()
            remainder = remainder[1:].strip()
    return names


def subscriptions(source):
    if not re.search(r'(?m)^  workflow_run:', source):
        return []
    callbacks = block(block(source, 'on', 0), 'workflow_run', 2)
    value = block(callbacks, 'workflows', 4)
    first, _, rest = value.partition('\n')
    if first.startswith('['):
        names = flow_names(first)
    elif first:
        names = [scalar(first)]
    else:
        names = [scalar(line.strip()[2:]) for line in rest.splitlines()
                 if line.strip().startswith('- ')]
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
        raise AssertionError('why: workflow subscription is not explicit; remedy: keep named workflow_run inputs readable')
    return names


def assert_no_self_subscription(source):
    names = subscriptions(source)
    if names:
        own_name = scalar(field(source, 'name', 0))
        if own_name in names:
            raise AssertionError('why: GitHub rejects a workflow listening to itself; remedy: use the authenticated completion relay')


class EventGraphTests(unittest.TestCase):
    def test_flow_lists_support_explicit_quoted_and_plain_names(self):
        for declaration, expected in (
            ('[Cloudflare Preview Build]', ['Cloudflare Preview Build']),
            ('["A", B, \'C\']', ['A', 'B', 'C']),
            ('["A, B", \'Author\'\'s build\']', ['A, B', "Author's build"]),
            ('["A\\\" B"]', ['A" B']),
        ):
            with self.subTest(declaration=declaration):
                self.assertEqual(subscriptions(f'on:\n  workflow_run:\n    workflows: {declaration}\n'), expected)

    def test_own_name_and_subscription_share_yaml_string_decoding(self):
        for name, subscription in (("'Author''s build'", '"Author\'s build"'),
                                   ('"A, B"', "'A, B'"),
                                   ('Cloudflare Preview Build', 'Cloudflare Preview Build')):
            with self.subTest(name=name):
                with self.assertRaisesRegex(AssertionError, 'GitHub rejects'):
                    assert_no_self_subscription(f'name: {name}\non:\n  workflow_run:\n    workflows: [{subscription}]\n')

    def test_unsupported_flow_and_nonstring_subscription_values_fail_closed(self):
        for declaration in ('[]', '[ ]', '[A,]', '[,A]', '[A,,B]', '[A', '[A] junk',
                            '[[A]]', '[{name: A}]', '[1]', '[null]', '[true]',
                            '["A" "B"]', "['A' 'B']", '["A\\x41"]',
                            '1', 'null', 'false', '{name: A}', '*alias', '!!str A',
                            '[""]', "['']"):
            with self.subTest(declaration=declaration):
                with self.assertRaisesRegex(AssertionError, 'why:.*remedy:'):
                    subscriptions(f'on:\n  workflow_run:\n    workflows: {declaration}\n')

    def test_nonstring_own_name_cannot_hide_self_subscription(self):
        for name in ('null', 'true', '123', '[A]', '{name: A}'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(AssertionError, 'why:.*remedy:'):
                    assert_no_self_subscription(f'name: {name}\non:\n  workflow_run:\n    workflows: [A]\n')

    def test_actual_workflows_never_subscribe_to_their_own_exact_name(self):
        for path in sorted((ROOT / '.github/workflows').glob('*.y*ml')):
            with self.subTest(workflow=path.name):
                assert_no_self_subscription(path.read_text())

    def test_observed_self_report_subscription_is_rejected(self):
        original = 'name: Self-test Report\non:\n  workflow_run:\n    workflows: ["Self-test Report", "Core CI", "PR Review"]\n    types: [completed]\n'
        with self.assertRaisesRegex(AssertionError, 'GitHub rejects'):
            assert_no_self_subscription(original)

    def test_quoted_name_and_block_subscription_still_reject_self(self):
        with self.assertRaisesRegex(AssertionError, 'GitHub rejects'):
            assert_no_self_subscription('name: "Self-test Report"\non:\n  workflow_run:\n    workflows:\n      - "Core CI"\n      - \'Self-test Report\'\n')

    def test_scalar_self_subscription_still_rejects_self(self):
        with self.assertRaisesRegex(AssertionError, 'GitHub rejects'):
            assert_no_self_subscription('name: A\non:\n  workflow_run:\n    workflows: A\n')

    def test_different_workflow_cross_subscription_is_not_speculatively_banned(self):
        for own, source in [('A', 'B'), ('B', 'A')]:
            assert_no_self_subscription(f'name: {own}\non:\n  workflow_run:\n    workflows: ["{source}"]\n')

    def test_non_event_text_and_similar_names_are_not_self_subscriptions(self):
        assert_no_self_subscription('name: A\non:\n  push:\njobs:\n  job:\n    name: A\n')
        assert_no_self_subscription('name: A\non:\n  workflow_run:\n    workflows: ["A completion"]\n')

    def test_relay_is_one_readonly_hosted_job_without_product_or_dispatch_authority(self):
        path = ROOT / '.github/workflows/incremental-completion.yml'
        source = path.read_text()
        self.assertEqual(scalar(field(source, 'name', 0)), 'Incremental Completion')
        self.assertEqual(subscriptions(source), ['Self-test Report'])
        events = block(source, 'on', 0)
        self.assertEqual(set(re.findall(r'(?m)^  ([a-z_]+):', events)), {'workflow_run'})
        self.assertEqual(field(block(events, 'workflow_run', 2), 'types', 4), '[completed]')
        self.assertEqual(field(source, 'permissions', 0), '{}')
        jobs = jobs_in(path)
        self.assertEqual(len(jobs), 1)
        job = block(source, jobs[0].job_id, 2)
        self.assertEqual(scalars(block(job, 'permissions', 4), 6), {'contents': 'read', 'actions': 'read'})
        self.assertIsNotNone(jobs[0].runs_on)
        self.assertNotIn('self-hosted', jobs[0].runs_on)
        self.assertNotIn('concurrency:', source)
        for forbidden in ('issues: write', 'contents: write', 'actions: write', 'pull-requests:',
                          'id-token:', 'scripts/core.sh', 'scripts/release.sh',
                          'batch_runtime.py', 'report_runtime.py', 'gh workflow run',
                          '/dispatches', 'repository_dispatch', 'secrets: inherit',
                          'uses: ./.github/workflows/ci.yml'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
