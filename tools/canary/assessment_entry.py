"""Manual-only authenticated control / credential-isolated execution boundary.

Run as a module from frozen main. No auto-init, model replay, metadata admission,
release or deployment. Runner isolation/provisioning is an operator prerequisite,
not something a label, environment variable or private directory can prove.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from . import assessment as a, assessment_handoff as h, assessment_runtime, records as r
import report_outbox

POLICY_PATH = 'tools/canary/executor_policy.json'
CLAIM_SCHEMA = 'lmdj.canary-assessment-claim.v1'
OPERATIONS = ('init-assessment', 'init-outbox', 'claim', 'settle', 'report')
MAX_BINARY_BYTES = 256 * 1024 * 1024


class AssessmentRuntime(h.runtime_api.Runtime):
    workflow = '.github/workflows/canary-assessment.yml'
    controller_job = 'Canary assessment controller'

    def lock_held(self):
        return self.env.get('BATCH_WRITER_LOCK') == 'canary-assessment'


def storage_pair(config):
    r.require(isinstance(config, dict) and set(config) == {'assessment', 'outbox'},
              'assessment storage pair fields are not closed')
    for role, prefix in (('assessment', 'canary-assessment-inputs-'),
                         ('outbox', 'canary-assessment-outbox-')):
        item = config[role]
        r.require(isinstance(item, dict) and set(item) == {
            'repository', 'issue_number', 'issue_node_id', 'bot_node_id', 'workflow_id', 'epoch'},
            'assessment storage identity fields are not closed')
        r.require(item['repository'] == 'endaye/lmdj'
                  and type(item['issue_number']) is int and item['issue_number'] > 0
                  and item['issue_number'] not in (807, 817, 849)
                  and type(item['workflow_id']) is int and item['workflow_id'] > 0
                  and all(isinstance(item[k], str) and item[k] for k in ('issue_node_id', 'bot_node_id', 'epoch'))
                  and item['epoch'].startswith(prefix) and len(item['epoch']) > len(prefix),
                  'storage is reserved, invalid or lacks its dedicated assessment role')
    left, right = config['assessment'], config['outbox']
    r.require(all(left[k] == right[k] for k in ('repository', 'workflow_id', 'bot_node_id'))
              and all(left[k] != right[k] for k in ('issue_number', 'issue_node_id', 'epoch')),
              'assessment/outbox storage aliases or authorities differ')
    return deepcopy(config)


def request_for(operation, request):
    r.require(operation in OPERATIONS, 'unknown assessment control operation')
    keys = {'base_sha', 'target_sha'} if operation == 'claim' else (
        {'input_digest'} if operation in ('settle', 'report') else set())
    r.require(isinstance(request, dict) and set(request) == keys,
              'assessment request mixes operations or omits exact identity')
    for key, value in request.items():
        (r.exact_digest if key == 'input_digest' else r.exact_sha)(value)
    return deepcopy(request)


def claim_document(claim):
    r.require(claim.get('action') == 'execute' and claim.get('result') is None,
              'only a fresh durable claim can grant execution')
    context = a._context(claim['context'])
    return r.seal({'schema': CLAIM_SCHEMA, 'context': context,
                   'executor': h.storage._executor(claim['executor'], context)})


def input_artifact(document):
    return 'canary-assessment-input-' + document['digest']


def control(operation, config, request, *, root, environment, api=None):
    config, request = storage_pair(config), request_for(operation, request)
    # Fail before any claim/write, not only by skipping the downstream job.
    if operation == 'claim':
        r.require(environment.get('CANARY_ASSESSMENT_EXECUTION_READY') == 'true',
                  'assessment execution readiness has not been accepted',
                  'accept isolated disposable runner, protected Environment and pinned tools before enabling new claims')
    role = 'outbox' if operation == 'init-outbox' else 'assessment'
    runtime = AssessmentRuntime(config[role], root=root, environment=environment, api=api)
    if operation.startswith('init-'):
        runtime.initialize()
        return {'action': 'initialized', 'role': role}
    handoff = h.Handoff(runtime)
    if operation == 'claim':
        answer = handoff.claim(**request)
        return {'action': answer['action'], 'input_digest': answer['context']['digest'],
                'claim': claim_document(answer) if answer['action'] == 'execute' else None}
    if operation == 'settle':
        answer = handoff.settle(request['input_digest'])
        return {'action': answer['action'], 'input_digest': request['input_digest'],
                'state': answer['result']['state'] if answer['result'] else 'pending'}
    reporter = AssessmentRuntime(config['outbox'], root=root, environment=environment, api=api)
    reporter.authenticate_current()
    outbox = report_outbox.Outbox(reporter.journal(), reporter.lock_held, reporter.config['epoch'])
    answer = handoff.report(request['input_digest'], outbox, runtime.api)
    return {'action': 'reported', 'input_digest': request['input_digest'], 'report': answer}


def authenticated_input(document, *, root, environment):
    """Same-run artifact wiring is trusted; independently recheck all Git bytes.

Only the fixed workflow downloads this claim from its controller in the same
first attempt. This function is not a public API accepting arbitrary uploads.
"""
    r.require(isinstance(document, dict) and set(document) == {'schema', 'context', 'executor', 'digest'}
              and document['schema'] == CLAIM_SCHEMA, 'claim artifact fields are not closed')
    r.verify_seal(document)
    context = a._context(document['context'])
    owner = h.storage._executor(document['executor'], context)
    r.require(environment.get('GITHUB_REPOSITORY') == 'endaye/lmdj'
              and environment.get('GITHUB_REF') == 'refs/heads/main'
              and environment.get('GITHUB_RUN_ATTEMPT') == '1'
              and str(owner['run_id']) == environment.get('GITHUB_RUN_ID')
              and owner['attempt'] == 1 and owner['control_sha'] == environment.get('GITHUB_SHA'),
              'claim differs from exact main executor run/attempt/control')
    inputs = a.planning.batch_controller.GitInputs(root, context['control_sha'], lambda: context['control_sha'])
    r.require(inputs._git('rev-parse', 'HEAD').decode().strip() == context['control_sha'],
              'executor checkout differs from frozen control')
    inputs.refresh()  # Exact dispatched main control, not an untrusted candidate tip.
    for sha in (context['base_sha'], context['target_sha']):
        a.planning.test_scope.collect_interval(root, sha, context['control_sha'])
    r.require(inputs.policy_at(context['control_sha']).digest == context['policy_digest'],
              'executor policy differs from claimed policy')
    recollected = a.collect(root, **{key: context[key] for key in
        ('base_sha', 'target_sha', 'control_sha', 'policy_digest')})
    r.require(recollected == context, 'claim differs from complete pinned Git input')
    return context, owner, inputs


def executor_policy(inputs):
    raw = inputs._git('show', f'{inputs.control_sha}:{POLICY_PATH}')
    policy = h.runtime_api.strict_json(raw)
    r.require(isinstance(policy, dict) and set(policy) == {'schema', 'binaries', 'models'}
              and policy['schema'] == 'lmdj.canary-executor-policy.v1'
              and isinstance(policy['binaries'], dict) and set(policy['binaries']) == {'claude', 'grok'}
              and isinstance(policy['models'], dict) and set(policy['models']) == set(a.BACKENDS),
              'executor binary/model policy is not closed')
    for name, pin in policy['binaries'].items():
        r.require(isinstance(pin, dict) and set(pin) == {'path', 'sha256'}
                  and isinstance(pin['path'], str) and pin['path'].startswith('/opt/lmdj/assessment/')
                  and '..' not in Path(pin['path']).parts and Path(pin['path']).name.startswith(name + '-'),
                  'binary path is outside reviewed pre-provisioned storage')
        r.exact_digest(pin['sha256'])
    for model in policy['models'].values():
        r.require(isinstance(model, str) and model and len(model) <= 100
                  and all(c.isalnum() or c in '._-' for c in model), 'model identifier is invalid')
    return policy


def _root_owned(metadata, *, directory):
    r.require((stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode))
              and metadata.st_uid == 0 and not metadata.st_mode & 0o022,
              'provisioned binary or parent is not immutable root-owned storage',
              'provision the pinned native binary outside writable CI storage; never execute an unverified substitute')


def copy_verified_binary(pin, destination):
    """Read bounded pinned bytes from immutable ancestry; execute only our copy."""
    path = Path(pin['path'])
    for parent in reversed(path.parents):
        _root_owned(parent.lstat(), directory=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        _root_owned(metadata, directory=False)
        r.require(0 < metadata.st_size <= MAX_BINARY_BYTES and metadata.st_mode & 0o111,
                  'provisioned binary size or executable mode is invalid')
        digest, total = hashlib.sha256(), 0
        with open(destination, 'xb') as output:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                r.require(total <= MAX_BINARY_BYTES, 'provisioned binary exceeds byte budget')
                digest.update(chunk)
                output.write(chunk)
        r.require(total == metadata.st_size and digest.hexdigest() == pin['sha256'],
                  'provisioned binary differs from exact reviewed SHA-256')
    destination.chmod(0o500)


def execute(document, *, root, environment):
    r.require(environment.get('CANARY_ASSESSMENT_EXECUTION_READY') == 'true',
              'assessment execution readiness has not been accepted')
    context, owner, inputs = authenticated_input(document, root=root, environment=environment)
    policy = executor_policy(inputs)
    credentials = {key: environment[key] for key in assessment_runtime._SECRETS.values() if environment.get(key)}
    with tempfile.TemporaryDirectory(prefix='canary-pinned-tools-') as directory:
        copied = {}
        for name, pin in policy['binaries'].items():
            target = Path(directory) / name
            try:
                copy_verified_binary(pin, target)
                copied[name] = str(target)
            except (OSError, r.CanaryError):
                # A missing Grok must not prevent a valid GLM/Kimi assessment.
                # Never execute a partial copy or fall back to PATH discovery.
                copied[name] = str(Path(directory) / ('unavailable-' + name))
        config = {backend: {'executable': copied['grok' if backend == 'grok' else 'claude'],
                            'model': policy['models'][backend]} for backend in a.BACKENDS}
        result = assessment_runtime.execute(context, config=config, credentials=credentials)
    return h.artifact_document(context, owner, result)


def _write(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as output:
        output.write(r.canonical(document))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('control', 'execute'))
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    env = dict(os.environ)
    if args.mode == 'control':
        answer = control(env.get('ASSESSMENT_OPERATION'), h.runtime_api.strict_json(env.get('ASSESSMENT_STORAGE', '')),
                         h.runtime_api.strict_json(env.get('ASSESSMENT_REQUEST') or '{}'), root=args.root, environment=env)
        outputs = {'action': answer['action']}
        if answer.get('claim'):
            _write(args.directory / 'input' / 'claim.json', answer['claim'])
            outputs['input_artifact'] = input_artifact(answer['claim'])
        if answer.get('input_digest'):
            outputs['input_digest'] = answer['input_digest']
    else:
        document = h.runtime_api.strict_json((args.directory / 'input' / 'claim.json').read_bytes())
        answer = execute(document, root=args.root, environment=env)
        _write(args.directory / 'result' / 'assessment.json', answer)
        outputs = {'state': answer['result']['state'],
                   'result_artifact': h.artifact_name(document['context'], document['executor'])}
    _write(args.directory / (args.mode + '.json'), answer)
    with open(env['GITHUB_OUTPUT'], 'a') as output:
        for key, value in outputs.items():
            r.require(isinstance(value, str) and '\n' not in value and '\r' not in value,
                      'unsafe workflow output')
            output.write(f'{key}={value}\n')
    with open(env['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('Manual assessment: ' + outputs.get('action', outputs.get('state')) + '\n')
        if outputs.get('input_digest'):
            summary.write('Input: `' + outputs['input_digest'] + '`\n')
        summary.write('No allocation, publication, deployment or promotion authority.\n')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Raw input, HTTP/provider errors and credentials never enter logs.
        raise SystemExit('why: manual assessment operation failed; remedy: reconcile the exact claim/storage/run and provisioning; never rerun a claimed model or unknown Issue POST') from None
