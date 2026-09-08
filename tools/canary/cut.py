"""Read-only moving-main coverage checks, not canonical allocation admission.

The caller authenticates GitHub review/head/main and verifies the declared files
are canonical allocation outputs. Exact Git deltas prove byte coverage only;
they cannot prove assessment truth, occupancy, a lease, tests or release health.
"""
from __future__ import annotations

from . import planning as p, records as r

SCHEMA = 'lmdj.canary-cut-coverage.v1'
ZERO = '0' * 40


def _parents(inputs, revision):
    return inputs._git('show', '-s', '--format=%P', revision).decode('ascii').strip().split()


def _delta(inputs, base, head):
    """Complete tree delta with modes and full object IDs; renames are D + A."""
    raw = inputs._git('diff', '--no-ext-diff', '--no-textconv', '--raw', '--no-abbrev',
                      '--no-renames', '-z', base, head, '--')
    fields = raw.split(b'\0')
    r.require(fields[-1] == b'' and (len(fields) - 1) % 2 == 0, 'Git raw delta is incomplete')
    rows = []
    for position in range(0, len(fields) - 1, 2):
        metadata = fields[position].decode('ascii').split()
        r.require(len(metadata) == 5 and metadata[0].startswith(':')
                  and metadata[4] in {'A', 'D', 'M', 'T'}, 'Git raw delta has unsupported fields')
        path = fields[position + 1].decode('utf-8')
        p.test_scope._paths([path])
        rows.append({'path': path, 'before_mode': metadata[0][1:], 'after_mode': metadata[1],
                     'before_oid': r.exact_sha(metadata[2]), 'after_oid': r.exact_sha(metadata[3])})
    r.require(len({row['path'] for row in rows}) == len(rows), 'Git delta duplicates a path')
    return sorted(rows, key=lambda row: row['path'])


def _tree_entry(inputs, revision, path):
    raw = inputs._git('ls-tree', '-z', revision, '--', path)
    if not raw:
        return '000000', ZERO
    rows = raw.split(b'\0')
    r.require(len(rows) == 2 and rows[-1] == b'', 'Git tree entry is ambiguous')
    metadata, observed = rows[0].split(b'\t', 1)
    fields = metadata.decode('ascii').split()
    r.require(len(fields) == 3 and observed.decode('utf-8') == path, 'Git tree path identity differs')
    return fields[0], r.exact_sha(fields[2])


def _scope(inputs, control, interval):
    current = inputs.policy_at(control)
    if not interval['commits']:
        return p.test_scope._selection(current, [], ['verified empty intervening interval'])
    policies = [current]
    for revision in dict.fromkeys([interval['base_sha']] + [item['sha'] for item in interval['commits']]):
        try:
            policies.append(inputs.policy_at(revision))
        except (p.incremental_batch.BatchError, p.test_scope.ScopeError, ValueError, TypeError, KeyError):
            policies.append(None)
    return p.test_scope.select_across_policies(interval['paths'], policies, complete=True)


def check_coverage(root, *, assessed_target, reviewed_base, reviewed_head,
                   observed_main, control_sha, declared_outputs, merged_sha=None):
    """Check before merge or after an exact squash, without moving any ref.

The declaration is an inventory, not proof of metadata-only allocation. This
function must never be the sole predicate for merging, signing or deployment.
Later main changes do not alter a fixed post-squash candidate's coverage record.
"""
    for revision in (assessed_target, reviewed_base, reviewed_head, observed_main, control_sha):
        r.exact_sha(revision)
    if merged_sha is not None:
        r.exact_sha(merged_sha)
    try:
        declared = p.test_scope._paths(declared_outputs)
        r.require(declared and len(declared) == len(declared_outputs), 'declared output inventory is empty or duplicated')
        inputs = p.batch_controller.GitInputs(root, control_sha, lambda: observed_main)
        inputs.refresh()
        collect = p.test_scope.collect_interval
        collect(root, control_sha, observed_main)
        collect(root, assessed_target, reviewed_base)
        reviewed = collect(root, reviewed_base, reviewed_head)
        r.require(len(reviewed['commits']) == 1 and _parents(inputs, reviewed_head) == [reviewed_base],
                  'reviewed allocation must be one single-parent commit')
        expected = _delta(inputs, reviewed_base, reviewed_head)
        r.require([row['path'] for row in expected] == declared,
                  'reviewed delta differs from declared output inventory')
        if merged_sha is None:
            stage, merge_base, actual = 'pre-merge', observed_main, None
        else:
            collect(root, merged_sha, observed_main)
            parents = _parents(inputs, merged_sha)
            r.require(len(parents) == 1, 'candidate must be a single-parent squash')
            stage, merge_base = 'post-squash', parents[0]
            actual = _delta(inputs, merge_base, merged_sha)
        collect(root, reviewed_base, merge_base)
        interval = collect(root, assessed_target, merge_base)
        scope = _scope(inputs, control_sha, interval)
        reasons = []
        if scope['kind'] != 'none':
            reasons.append('unassessed-intervening-changes')
        if any(_tree_entry(inputs, merge_base, row['path']) != (row['before_mode'], row['before_oid'])
               for row in expected):
            reasons.append('reviewed-output-preimage-moved')
        if actual is not None and actual != expected:
            reasons.append('squash-differs-from-reviewed-delta')
        return r.seal({'schema': SCHEMA, 'admission_evidence': False, 'purpose': 'coverage-only',
                       'stage': stage, 'status': 'needs-assessment' if reasons else 'covered',
                       'assessed_target': assessed_target, 'reviewed_base': reviewed_base,
                       'reviewed_head': reviewed_head, 'control_sha': control_sha,
                       'candidate_sha': merged_sha, 'merge_base': merge_base,
                       'declared_outputs': declared, 'reviewed_delta': expected, 'merged_delta': actual,
                       'intervening': interval, 'intervening_scope': scope, 'reasons': reasons,
                       'remaining_obligations': ['authenticated-review-and-main', 'canonical-allocation-output-proof',
                           'fenced-occupancy-and-three-attempt-cut', 'post-squash-snapshot-witness',
                           'exact-candidate-test-and-artifact-acceptance']})
    except (p.incremental_batch.BatchError, p.test_scope.ScopeError, OSError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, r.CanaryError):
            raise
        raise r.CanaryError('why: complete cut history or policy is unavailable; remedy: restore exact Git/control inputs and reassess; never admit from missing evidence') from None
