"""Authenticated manual result planning; no execution or delivery authority.

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

OPERATIONS = ('init', 'bootstrap', 'observe-result', 'recover')
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


def control(operation, config, request, *, root, environment, api=None):
    config, request = planning_storage(config), request_for(operation, request)
    runtime = PlanningRuntime(config, root=root, environment=environment, api=api)
    # Only a manual first-attempt main workflow may initialize/write this store.
    runtime.authenticate_current()
    r.require(runtime.get_run(runtime.current['run_id'], 1).get('event') == 'workflow_dispatch',
              'planning writer is not an explicit manual invocation')
    if operation == 'init':
        runtime.initialize()
        return {'action': 'initialized', 'admission_evidence': False}
    plans = storage.Plans(runtime.journal(), runtime.lock_held, config['epoch'])
    if operation == 'bootstrap':
        return {'action': 'bootstrapped', 'admission_evidence': False,
                'progress': plans.bootstrap(config['repository'])}
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
    current = plans.load()
    r.require(current['progress'] is not None, 'planning progress has not been explicitly bootstrapped')
    r.require(current['unfinished'] is None, 'another planning intent is unfinished',
              'recover the original unfinished source before observing another result')
    source_config = incremental_entry.load_storage(runtime.root, runtime.env)['scheduler']
    r.require(source_config['bot_node_id'] == config['bot_node_id']
              and source_config['issue_node_id'] != config['issue_node_id']
              and source_config['workflow_id'] != config['workflow_id'],
              'planning and scheduler storage authorities alias or differ')
    state = scheduler_state(runtime, source_config)
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
