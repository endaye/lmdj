#!/usr/bin/env python3
"""Read-only completion relay; receipts convey ancestry, never execution authority."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import batch_runtime
import incremental_batch as batch
import self_test
from api_observation import observe

WORKFLOW = '.github/workflows/incremental-completion.yml'
SCRIPT = 'scripts/ci/incremental_completion.py'
JOB = 'Relay authenticated completion'
SAVE = 'Save authenticated parent receipt'
UPLOAD = 'Retain authenticated completion receipt'
SCHEMA = 'lmdj.ci-incremental-completion.v1'
FIELDS = ('id', 'run_attempt', 'workflow_id', 'path', 'head_sha', 'head_branch', 'event', 'status', 'conclusion')


def require(ok, why):
    batch.require(ok, why, 'restore the exact authenticated completion receipt; use the independent health tick for durable recovery')


def identity(run):
    return {key: run[key] for key in FIELDS}


def same(left, right):
    return self_test.canonical_json(left) == self_test.canonical_json(right)


def repo_identity(runtime):
    repo = runtime.call('GET', runtime.repo(''))
    require(isinstance(repo, dict) and type(repo.get('id')) is int and repo['id'] > 0
            and repo.get('full_name') == runtime.config['repository'], 'repository identity is unavailable')
    return {'id': repo['id'], 'full_name': repo['full_name']}


def in_main(runtime, revision):
    batch.exact_sha(revision)
    main = runtime.inputs.main
    require(revision in runtime.git('rev-list', '--first-parent', main).decode().splitlines(),
            'completion source is outside actual main first-parent history')


def parent(runtime, hint, repository):
    require(isinstance(hint, dict) and type(hint.get('id')) is int and hint['id'] > 0
            and type(hint.get('run_attempt')) is int and hint['run_attempt'] == 1,
            'parent run/attempt is invalid')
    run = runtime.get_run(hint['id'], hint['run_attempt'])
    require(run.get('status') == 'completed' and isinstance(run.get('conclusion'), str),
            'parent is not a terminal controller run')
    require(runtime.run_state({'run_id': run['id'], 'attempt': 1}) == 'terminal'
            and same(runtime.get_run(run['id'], 1), run), 'parent terminal identity changed or conclusion is unknown')
    require(all(key in hint and key in run and same(hint[key], run[key]) for key in FIELDS),
            'parent event identity differs from the actual exact attempt')
    require(all(isinstance(run.get(key), dict) and run[key].get('id') == repository['id']
                and type(run[key].get('id')) is int and run[key].get('full_name') == repository['full_name']
                for key in ('repository', 'head_repository')), 'parent repository identity differs')
    in_main(runtime, run['head_sha'])
    return run


def relay(runtime, hint, repository, *, completed):
    require(isinstance(hint, dict) and type(hint.get('id')) is int and hint['id'] > 0
            and type(hint.get('run_attempt')) is int and hint['run_attempt'] == 1,
            'relay run/attempt is invalid')
    run = runtime.call('GET', runtime.repo(f"/actions/runs/{hint['id']}/attempts/1"))
    require(isinstance(run, dict) and all(key in run and key in hint and same(run[key], hint[key]) for key in FIELDS),
            'relay hint differs from the actual exact attempt')
    workflow = runtime.call('GET', runtime.repo('/actions/workflows/incremental-completion.yml'))
    require(isinstance(workflow, dict) and type(workflow.get('id')) is int and workflow['id'] > 0
            and type(run.get('workflow_id')) is int and run['workflow_id'] == workflow['id']
            and workflow.get('path') == run.get('path') == WORKFLOW,
            'relay workflow identity differs')
    require(run.get('event') == 'workflow_run' and run.get('head_branch') == 'main', 'relay is not a main callback')
    require(all(isinstance(run.get(key), dict) and type(run[key].get('id')) is int
                and run[key]['id'] == repository['id'] and run[key].get('full_name') == repository['full_name']
                for key in ('repository', 'head_repository')), 'relay repository identity differs')
    require(run.get('status') == ('completed' if completed else 'in_progress')
            and (run.get('conclusion') == 'success' if completed else run.get('conclusion') is None),
            'relay has not reached the required execution state')
    in_main(runtime, run['head_sha'])
    for path in (WORKFLOW, SCRIPT):
        # Helpers imported by this reviewed module remain trusted main code,
        # as in the existing controller. This is not a hermetic import closure.
        require(runtime.git('show', f"{run['head_sha']}:{path}") == runtime.git('show', f'{runtime.control}:{path}'),
                'relay source differs from reviewed current control')
    jobs = runtime.pages(f"/actions/runs/{run['id']}/attempts/1/jobs", 'jobs')
    require(len(jobs) == 1, 'relay job inventory is not closed')
    job = jobs[0]
    require(job.get('name') == JOB and type(job.get('run_id')) is int and job['run_id'] == run['id']
            and type(job.get('run_attempt')) is int and job['run_attempt'] == 1
            and job.get('head_sha') == run['head_sha'], 'relay job identity differs')
    require(job.get('status') == ('completed' if completed else 'in_progress')
            and (job.get('conclusion') == 'success' if completed else job.get('conclusion') is None),
            'relay job did not execute successfully')
    steps = job.get('steps')
    require(isinstance(steps, list), 'relay step inventory unavailable')
    for name in ((SAVE, UPLOAD) if completed else (SAVE,)):
        matches = [step for step in steps if step.get('name') == name]
        require(len(matches) == 1 and matches[0].get('status') == ('completed' if completed else 'in_progress')
                and (matches[0].get('conclusion') == 'success' if completed else matches[0].get('conclusion') is None),
                'relay save/upload step is not proven')
    return run


def receipt(repository, relay_run, parent_run):
    return {'schema': SCHEMA, 'repository': repository,
            'relay': {'run_id': relay_run['id'], 'attempt': 1, 'control': relay_run['head_sha']},
            'parent': identity(parent_run)}


def produce(runtime, payload):
    """Authenticate a real main relay while its save step runs; no journal APIs."""
    require(runtime.env.get('GITHUB_EVENT_NAME') == 'workflow_run'
            and runtime.env.get('GITHUB_WORKFLOW_REF') == f"{runtime.config['repository']}/{WORKFLOW}@refs/heads/main",
            'producer context is not the fixed relay workflow')
    require(runtime.git('rev-parse', 'HEAD').decode().strip() == runtime.control, 'relay checkout differs from control')
    runtime.inputs.refresh()
    in_main(runtime, runtime.control)
    repository = repo_identity(runtime)
    require(isinstance(payload, dict) and payload.get('action') == 'completed'
            and isinstance(payload.get('repository'), dict)
            and payload['repository'].get('id') == repository['id']
            and type(payload['repository'].get('id')) is int
            and payload['repository'].get('full_name') == repository['full_name'], 'relay event repository or action differs')
    actual = runtime.call('GET', runtime.repo(f"/actions/runs/{runtime.current['run_id']}/attempts/1"))
    own = relay(runtime, actual, repository, completed=False)
    require(own['id'] == runtime.current['run_id'] and own['head_sha'] == runtime.control,
            'relay API run/control differs')
    source = parent(runtime, payload.get('workflow_run'), repository)
    require(source['id'] != own['id'], 'relay cannot identify itself as its parent')
    return receipt(repository, own, source)


def resolve(runtime, hint):
    """Return (authenticated controller parent, immediate relay witness)."""
    repository = repo_identity(runtime)
    own = relay(runtime, hint, repository, completed=True)
    name = f"incremental-completion-{own['id']}-1"
    artifacts = runtime.pages(f"/actions/runs/{own['id']}/artifacts", 'artifacts')
    matches = [item for item in artifacts if item.get('name') == name]
    require(len(matches) == 1, 'exact relay receipt is missing or ambiguous')
    artifact = matches[0]
    binding = artifact.get('workflow_run')
    require(artifact.get('expired') is False and isinstance(binding, dict)
            and type(binding.get('id')) is int and binding['id'] == own['id']
            and type(binding.get('repository_id')) is int and binding['repository_id'] == repository['id']
            and type(binding.get('head_repository_id')) is int and binding['head_repository_id'] == repository['id']
            and binding.get('head_sha') == own['head_sha'] and binding.get('head_branch') == 'main',
            'relay artifact expired or its actual run binding differs')
    raw = runtime.call('GET', runtime.repo(f"/actions/artifacts/{artifact['id']}/zip"), raw=True)
    bundle = batch_runtime.parse_bundle(raw, {'receipt.json'})
    document = bundle['receipt.json']
    require(isinstance(document, dict) and set(document) == {'schema', 'repository', 'relay', 'parent'},
            'relay receipt fields are not closed')
    source = parent(runtime, document['parent'], repository)
    require(source['id'] != own['id'] and same(document, receipt(repository, own, source)),
            'receipt does not bind the exact relay and parent')
    return source, document['relay']


@observe('relay')
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    runtime = None
    try:
        require(not args.output.exists(), 'receipt output already exists')
        from incremental_entry import load_storage
        root = Path.cwd()
        runtime = batch_runtime.Runtime(load_storage(root, os.environ)['scheduler'], root=root)
        document = produce(runtime, batch_runtime.strict_json(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes()))
        with args.output.open('x') as stream:
            stream.write(self_test.canonical_json(document) + '\n')
        print(self_test.canonical_json(document), flush=True)
        return 0
    except Exception as error:
        from incremental_entry import emit_diagnostic
        stage = getattr(runtime, 'diagnostic_stage', None)
        emit_diagnostic('relay', stage if type(stage) is str else 'authenticate', error)
        print('why: completion relay could not authenticate its source; remedy: inspect exact source and let the independent health tick reconcile durable state')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
