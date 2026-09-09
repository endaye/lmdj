"""Authenticated bounded result discovery; no execution or delivery authority.

Only the dedicated planning Journal is writable. Scheduler evidence is read
through the existing complete read-only replay, not caller JSON or an Actions
conclusion. Finished plans survive artifact expiry and moving control/main.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import os
from pathlib import Path

from . import planning, planning_journal as storage, records as r
import batch_runtime
import incremental_entry
import report_runtime
import test_scope

OPERATIONS = ('init', 'bootstrap', 'observe-result', 'recover', 'reconcile-next', 'adopt-version-baseline')
BASELINE_PATH = 'tools/canary/first_version_baseline.json'
MAX_BASELINE_FILE_BYTES = 16384
STORAGE_KEYS = {'repository', 'issue_number', 'issue_node_id', 'bot_node_id', 'workflow_id', 'epoch'}


class PlanningRuntime(batch_runtime.Runtime):
    workflow = '.github/workflows/canary-planning.yml'
    controller_job = 'Canary planning controller'

    def lock_held(self):
        return self.env.get('BATCH_WRITER_LOCK') == 'canary-planning'


class SchedulerReader(batch_runtime.Runtime):
    # This lock serializes planning writers, NOT scheduler writers. The reader
    # verifies a complete checkpoint and refuses an in-flight scheduler append.
    # Historical writer trust remains the scheduler workflow, never planning.
    def lock_held(self):
        return self.env.get('BATCH_WRITER_LOCK') == 'canary-planning'


def planning_storage(config):
    r.require(isinstance(config, dict) and set(config) == STORAGE_KEYS,
              'planning storage fields are not closed')
    r.require(config['repository'] == 'endaye/lmdj'
              and type(config['issue_number']) is int and config['issue_number'] > 0
              and config['issue_number'] not in (807, 817, 849)
              and type(config['workflow_id']) is int and config['workflow_id'] > 0
              and all(isinstance(config[k], str) and config[k] for k in ('issue_node_id', 'bot_node_id', 'epoch'))
              and config['epoch'].startswith('canary-planning-')
              and len(config['epoch']) > len('canary-planning-'),
              'planning storage is reserved, invalid or lacks its dedicated role')
    r.identifier(config['epoch'])
    return deepcopy(config)


def request_for(operation, request):
    r.require(operation in OPERATIONS, 'unknown planning operation')
    keys = {'source_request_id'} if operation in ('observe-result', 'recover') else set()
    r.require(isinstance(request, dict) and set(request) == keys,
              'planning request mixes operations or accepts caller evidence')
    if keys:
        r.identifier(request['source_request_id'])
    return deepcopy(request)


def scheduler_state(runtime, config):
    reader = SchedulerReader(config, root=runtime.root, environment=runtime.env, api=runtime.api)
    # Current planning writer was authenticated separately. Share its exact
    # authenticated main observation; do not authenticate it as scheduler writer.
    reader.inputs.main = runtime.inputs.main
    return report_runtime.scheduler_state(reader)


def decision_for(runtime, intent, scheduler):
    decision = planning.plan_after_result(runtime.root, scheduler=scheduler,
        source_request_id=intent['source_request_id'], main_sha=intent['main_sha'],
        control_sha=intent['control_sha'], progress=intent['progress'], wakeup='recovery')
    r.require(r.digest(decision['source']) == intent['source_digest']
              and r.digest(decision) == intent['decision_digest'],
              'original planning source or complete decision changed',
              'restore the frozen source/control/progress; never replace an unfinished intent')
    return decision


def rank(runtime, target, main):
    test_scope.collect_interval(runtime.root, target, main)
    value = runtime.git('rev-list', '--first-parent', '--count', target).decode().strip()
    r.require(value.isascii() and value.isdecimal() and int(value) > 0,
              'complete first-parent target rank is unavailable')
    return int(value)


def answer(row):
    r.require(row['decision'] is not None, 'planning observation is not completely persisted')
    return {'action': 'ignored' if row['decision']['action'] == 'ignore' else 'planned',
            'admission_evidence': False, **deepcopy(row)}


def source_storage(runtime):
    config = incremental_entry.load_storage(runtime.root, runtime.env)['scheduler']
    r.require(config['bot_node_id'] == runtime.config['bot_node_id']
              and config['issue_node_id'] != runtime.config['issue_node_id']
              and config['workflow_id'] != runtime.config['workflow_id'],
              'planning and scheduler storage authorities alias or differ')
    return config


def baseline_blob(runtime, revision, path):
    """Read only an exact regular nonexecutable Git blob, never worktree bytes."""
    rows = runtime.git('ls-tree', '-z', revision, '--', path).split(b'\0')
    r.require(len(rows) == 2 and rows[1] == b'' and b'\t' in rows[0],
              'baseline evidence is not one exact Git entry')
    metadata, actual_path = rows[0].split(b'\t', 1)
    fields = metadata.split(b' ')
    r.require(len(fields) == 3 and fields[:2] == [b'100644', b'blob']
              and actual_path == path.encode('utf-8'),
              'baseline evidence must be a regular nonexecutable Git blob')
    oid = r.exact_sha(fields[2].decode('ascii'))
    # Check before reading the object, not only after allocating its bytes.
    size = runtime.git('cat-file', '-s', oid).decode('ascii').strip()
    r.require(size.isascii() and size.isdecimal() and 0 < int(size) <= MAX_BASELINE_FILE_BYTES,
              'baseline evidence exceeds the bounded file budget')
    raw = runtime.git('cat-file', 'blob', oid)
    r.require(len(raw) == int(size), 'baseline Git blob size differs')
    return oid, raw.decode('utf-8')


def baseline_receipt(runtime):
    approval_blob, approval_bytes = baseline_blob(runtime, runtime.control, BASELINE_PATH)
    approval = storage.validate_baseline_approval(batch_runtime.strict_json(approval_bytes))
    test_scope.collect_interval(runtime.root, approval['revision'], runtime.inputs.main)
    manifests = []
    for host in approval['hosts']:
        oid, raw = baseline_blob(runtime, approval['revision'], host['path'])
        manifests.append({**host, 'blob': oid, 'bytes': raw})
    # Run/control authenticate this writer but are deliberately not receipt
    # identity: unchanged approved Git bytes survive later manual recovery.
    return storage.validate_baseline_receipt(r.seal({
        'schema': 'lmdj.canary-version-baseline-receipt.v1', 'approval': approval,
        'approval_blob': approval_blob, 'approval_bytes': approval_bytes, 'manifests': manifests}))


def authenticate_wakeup(runtime, operation):
    kind = runtime.env.get('GITHUB_EVENT_NAME')
    r.require(runtime.get_run(runtime.current['run_id'], 1).get('event') == kind,
              'planning API event differs from workflow context')
    if kind == 'workflow_dispatch':
        return
    r.require(kind == 'workflow_run' and operation == 'reconcile-next',
              'planning writer is not an explicit manual invocation or accepted completion')
    payload = batch_runtime.strict_json(Path(runtime.env['GITHUB_EVENT_PATH']).read_bytes())
    r.require(isinstance(payload, dict) and payload.get('action') == 'completed'
              and isinstance(payload.get('workflow_run'), dict), 'planning callback is not a completed run')
    hint = payload['workflow_run']
    r.require(type(hint.get('id')) is int and hint['id'] > 0
              and type(hint.get('run_attempt')) is int and hint['run_attempt'] == 1,
              'planning callback is not an exact first attempt')
    config = source_storage(runtime)
    reader = SchedulerReader(config, root=runtime.root, environment=runtime.env, api=runtime.api)
    run = reader.get_run(hint['id'], hint['run_attempt'])
    r.require(run.get('status') == 'completed' and reader.run_state({'run_id': hint['id'], 'attempt': 1}) == 'terminal',
              'planning callback source is not actually terminal')
    for key in ('id', 'run_attempt', 'workflow_id', 'head_sha', 'head_branch', 'path', 'event', 'status', 'conclusion'):
        r.require(key in hint and type(hint[key]) is type(run.get(key)) and hint[key] == run.get(key),
                  'planning callback metadata differs from exact source attempt')
    repository = runtime.call('GET', runtime.repo(''))
    workflow = runtime.call('GET', runtime.repo(f"/actions/workflows/{config['workflow_id']}"))
    r.require(isinstance(repository, dict) and type(repository.get('id')) is int and repository['id'] > 0
              and repository.get('full_name') == config['repository'], 'planning callback repository is unavailable')
    for source in (payload.get('repository'), hint.get('repository'), hint.get('head_repository'),
                   run.get('repository'), run.get('head_repository')):
        r.require(isinstance(source, dict) and type(source.get('id')) is int
                  and source['id'] == repository['id'] and source.get('full_name') == config['repository'],
                  'planning callback repository identity differs')
    r.require(isinstance(workflow, dict) and type(workflow.get('id')) is int
              and workflow['id'] == config['workflow_id'] and workflow.get('path') == reader.workflow,
              'planning callback workflow identity differs')
    test_scope.collect_interval(runtime.root, run['head_sha'], runtime.inputs.main)
    # Neither callback conclusion nor producer artifacts become test evidence.


def control(operation, config, request, *, root, environment, api=None):
    config, request = planning_storage(config), request_for(operation, request)
    if environment.get('GITHUB_EVENT_NAME') == 'workflow_run':
        r.require(operation == 'reconcile-next' and environment.get('CANARY_PLANNING_AUTOMATIC_READY') == 'true',
                  'automatic planning discovery readiness or operation has not been accepted')
    runtime = PlanningRuntime(config, root=root, environment=environment, api=api)
    runtime.authenticate_current()
    authenticate_wakeup(runtime, operation)
    if operation == 'init':
        runtime.initialize()
        return {'action': 'initialized', 'admission_evidence': False}
    plans = storage.Plans(runtime.journal(), runtime.lock_held, config['epoch'])
    if operation == 'bootstrap':
        return {'action': 'bootstrapped', 'admission_evidence': False,
                'progress': plans.bootstrap(config['repository'])}
    if operation == 'adopt-version-baseline':
        progress = plans.adopt_version_baseline(baseline_receipt(runtime))
        return {'action': 'baseline-adopted', 'admission_evidence': False,
                'progress': progress, 'receipt': plans.load()['baseline_receipt']}
    state = source_config = current = None
    if operation == 'reconcile-next':
        current = plans.load()
        r.require(current['progress'] is not None, 'planning progress has not been explicitly bootstrapped')
        source_id = current['unfinished']
        if source_id is None:
            source_config = source_storage(runtime)
            state = scheduler_state(runtime, source_config)
            # Admission insertion order comes from complete journal replay,
            # never lexicographic IDs, callback completion order or main tip.
            source_id = next((key for key in state['requests']
                              if key in state['results'] and key not in current['observations']), None)
            if source_id is None:
                return {'action': 'idle', 'admission_evidence': False}
    else:
        source_id = request['source_request_id']
    row = plans.lookup(source_id)
    if row is not None:
        if row['decision'] is None:
            intent = row['intent']
            state = scheduler_state(runtime, intent['scheduler_storage'])
            row = plans.finish(source_id, decision_for(runtime, intent, state))
        return answer(row)
    r.require(operation != 'recover', 'recovery has no original persisted intent',
              'observe the exact retained result once; recovery cannot invent a new plan')
    current = current if current is not None else plans.load()
    r.require(current['progress'] is not None, 'planning progress has not been explicitly bootstrapped')
    r.require(current['unfinished'] is None, 'another planning intent is unfinished',
              'recover the original unfinished source before observing another result')
    source_config = source_config if source_config is not None else source_storage(runtime)
    state = state if state is not None else scheduler_state(runtime, source_config)
    decision = planning.plan_after_result(runtime.root, scheduler=state, source_request_id=source_id,
        main_sha=runtime.inputs.main, control_sha=runtime.control, progress=current['progress'])
    target = decision['source']['target_sha']
    target_rank = rank(runtime, target, runtime.inputs.main)
    # Counts alone are not ancestry. Every retained slot must still lie on the
    # observed main first-parent chain, with its original rank and exact target.
    for key in (current['active'], current['pending']):
        if key is not None:
            frozen = plans.lookup(key)['intent']
            r.require(rank(runtime, frozen['target_sha'], runtime.inputs.main) == frozen['target_rank'],
                      'retained planning target rank or protected history changed')
    intent = r.seal({'schema': 'lmdj.canary-plan-intent.v1', 'source_request_id': source_id,
        'main_sha': runtime.inputs.main, 'control_sha': runtime.control, 'target_sha': target,
        'scheduler_storage': source_config, 'progress': current['progress'],
        'source_digest': r.digest(decision['source']), 'decision_digest': r.digest(decision),
        'target_rank': target_rank, 'decision_action': decision['action']})
    # Check complete storage bounds before reserving the sole unfinished slot.
    # This is pure encoding, not a chunk write or a second model assessment.
    storage.validate_decision(intent, decision)
    storage.codec.pack(decision)
    plans.begin(intent)
    return answer(plans.finish(source_id, decision))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    env = dict(os.environ)
    result = control(env.get('PLANNING_OPERATION'), batch_runtime.strict_json(env.get('PLANNING_STORAGE', '')),
        batch_runtime.strict_json(env.get('PLANNING_REQUEST') or '{}'), root=args.root, environment=env)
    args.directory.mkdir(parents=True, exist_ok=True)
    with (args.directory / 'planning.json').open('xb') as output:
        output.write(r.canonical(result))
    with open(env['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('Canary planning: ' + result['action'] + '\n')
        if 'intent' in result:
            summary.write('Frozen input: `' + result['intent']['digest'] + '`; original slot: ' + result['slot'] + '\n')
        summary.write('Planning only; no test, version allocation, publication, deployment or promotion.\n')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('why: planning operation is unresolved; remedy: restore authenticated storage/source and recover the exact original intent; never reset progress or replay an uncertain append') from None
