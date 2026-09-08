"""Authenticate claimed Actions output before durable assessment/metadata handoff.

Use an independent configured assessment Issue through the existing short-lock
Runtime. No caller result, digest or artifact name grants completion authority.
Workflow activation, producer isolation and allocation admission are separate.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from . import assessment as a, assessment_journal as storage, metadata_proposal, records as r

runtime_api = a.planning.batch_runtime
PRODUCER_JOB = 'Canary assessment executor'
EXECUTE_STEP = 'Execute bounded Host assessment'
UPLOAD_STEP = 'Retain Host assessment result'
ARTIFACT_SCHEMA = 'lmdj.canary-assessment-artifact.v1'


def artifact_name(context, executor):
    return f"canary-assessment-{context['digest']}-{executor['run_id']}-{executor['attempt']}"


def artifact_document(context, executor, result):
    """Producer serialization only; the consumer independently authenticates it."""
    context = a._context(context)
    return r.seal({'schema': ARTIFACT_SCHEMA, 'input_digest': context['digest'],
                   'executor': storage._executor(executor, context),
                   'result': storage._result(context, result)})


def _uploaded(producer):
    steps = producer.get('steps')
    if (producer.get('conclusion') != 'success' or not isinstance(steps, list)
            or not all(isinstance(step, dict) for step in steps)):
        return False
    for name in (EXECUTE_STEP, UPLOAD_STEP):
        matches = [step for step in steps if isinstance(step, dict) and step.get('name') == name]
        if len(matches) != 1 or matches[0].get('status') != 'completed' or matches[0].get('conclusion') != 'success':
            return False
    return True


def _retention_elapsed(producer):
    step = next(step for step in producer['steps'] if step.get('name') == UPLOAD_STEP)
    timestamp = step.get('completed_at')
    if not isinstance(timestamp, str):
        return False
    try:
        ended = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        return False
    return ended.tzinfo is not None and datetime.now(timezone.utc) >= ended + runtime_api.ARTIFACT_RETENTION


class Handoff:
    def __init__(self, runtime):
        r.require(isinstance(runtime, runtime_api.Runtime), 'assessment handoff requires the authenticated Actions Runtime')
        r.require(runtime.config['repository'] == 'endaye/lmdj', 'assessment repository is not the configured product repository')
        r.require(runtime.config['issue_number'] not in (807, 817),
                  'assessment storage aliases production scheduler/outbox')
        r.require(runtime.config['epoch'].startswith('canary-assessment-'),
                  'assessment storage epoch does not identify an assessment journal')
        self.runtime = runtime

    def _storage(self):
        self.runtime.authenticate_current()
        return storage.Assessments(self.runtime.journal(), self.runtime.lock_held, self.runtime.config['epoch'])

    def _context(self, context):
        runtime = self.runtime
        context = a._context(context)
        for revision in (context['base_sha'], context['target_sha'], context['control_sha']):
            runtime.inputs.verify_target(revision)
            a.planning.test_scope.collect_interval(runtime.root, revision, runtime.inputs.main)
        r.require(runtime.inputs.policy_at(context['control_sha']).digest == context['policy_digest'],
                  'assessment policy differs from pinned trusted policy')
        recollected = a.collect(runtime.root, **{key: context[key] for key in
            ('base_sha', 'target_sha', 'control_sha', 'policy_digest')})
        r.require(recollected == context, 'assessment input differs from complete pinned Git data')
        return context

    def claim(self, *, base_sha, target_sha):
        """Explicit interval only; this does not choose version-accounted progress."""
        journal = self._storage()
        context = self._context(a.collect(self.runtime.root, base_sha=base_sha,
            target_sha=target_sha, control_sha=self.runtime.control,
            policy_digest=self.runtime.inputs.policy_at(self.runtime.control).digest))
        executor = {**self.runtime.current, 'control_sha': self.runtime.control}
        return journal.claim(context, executor)

    def _row(self, journal, input_digest):
        key = r.exact_digest(input_digest)
        state = journal.load()
        r.require(key in state['assessments'], 'assessment handoff has no original persisted claim')
        row = storage._row(state, key)
        self._context(row['context'])
        return row

    @staticmethod
    def _answer(row, action, reason):
        answer = {'action': action, 'reason': reason, 'admission_evidence': False, **deepcopy(row)}
        if action == 'needs-reconciliation':
            answer.update(why=reason, remedy='restore and reconcile the original exact producer output; preserve the claim and never repeat its model execution')
        return answer

    def settle(self, input_digest):
        """Reconcile exact remote producer, never invoke a model or reset a claim."""
        journal = self._storage()
        row = self._row(journal, input_digest)
        if row['result'] is not None:
            return self._answer(row, 'terminal', 'complete result already retained in authenticated journal')
        owner = row['executor']
        runtime = self.runtime
        run = runtime.get_run(owner['run_id'], owner['attempt'])
        r.require(run['head_sha'] == owner['control_sha'], 'assessment producer control differs from persisted claim')
        if run.get('status') in runtime_api.storage.WAITING_RUN_STATUSES + ('in_progress',):
            return self._answer(row, 'pending', 'exact claimed producer is still active')
        r.require(run.get('status') == 'completed' and run.get('conclusion') in {
            'success', 'failure', 'cancelled', 'skipped', 'timed_out', 'neutral', 'action_required', 'startup_failure', 'stale'},
            'assessment producer has no recognized terminal state')
        jobs = runtime.pages(f"/actions/runs/{owner['run_id']}/attempts/{owner['attempt']}/jobs", 'jobs')
        r.require(all(type(job.get('run_id')) is int and job['run_id'] == owner['run_id']
                      and type(job.get('run_attempt')) is int and job['run_attempt'] == owner['attempt']
                      and job.get('status') == 'completed' for job in jobs),
                  'assessment producer job inventory differs from terminal exact attempt')
        producers = [job for job in jobs if job.get('name') == PRODUCER_JOB]
        r.require(len(producers) <= 1, 'assessment producer job is ambiguous')
        if not producers or not _uploaded(producers[0]):
            return self._answer(row, 'needs-reconciliation', 'terminal producer has no successful assessment and upload; preserve claim')
        try:
            bundle = runtime.artifact_bundle(run, artifact_name(row['context'], owner), ('assessment.json',))
        except runtime_api.EvidenceExpired:
            return self._answer(row, 'needs-reconciliation', 'exact assessment artifact expired before persistence; preserve claim')
        except runtime_api.InvalidEvidence:
            return self._answer(row, 'needs-reconciliation', 'exact assessment artifact is invalid; preserve claim')
        if bundle is None:
            return self._answer(row, 'needs-reconciliation' if _retention_elapsed(producers[0]) else 'pending',
                                'successful upload is not visible; reconcile original output without re-execution')
        try:
            document = bundle['assessment.json']
            r.require(isinstance(document, dict) and set(document) == {
                'schema', 'input_digest', 'executor', 'result', 'digest'}, 'assessment artifact schema is not closed')
            r.verify_seal(document)
            r.require(document == artifact_document(row['context'], owner, document['result']),
                      'assessment artifact differs from original claim or validated result')
        except (r.CanaryError, KeyError, TypeError):
            return self._answer(row, 'needs-reconciliation', 'assessment output contradicts original claim or protocol; preserve claim')
        # The API identity and exact artifact have now been verified. A lost
        # append response is recovered from this same claim, never model replay.
        return journal.complete(input_digest, owner, document['result'])

    def report(self, input_digest, outbox, api):
        """Reuse the independent durable outbox; never repair or close an Issue."""
        r.require(outbox.journal.issue_id != self.runtime.config['issue_number'],
                  'report outbox aliases assessment storage')
        row = self.settle(input_digest)
        if row['action'] == 'pending':
            return {'status': 'pending'}
        if row['action'] == 'terminal':
            return self._storage().report(input_digest, outbox, api)
        context, owner = row['context'], row['executor']
        identity = {'input_digest': input_digest, 'executor': owner, 'reason': row['reason']}
        report = storage.reporting.Report(key='canary-assessment-execution',
            title='canary assessment: execution evidence needs reconciliation',
            observation='assessment-execution/' + r.digest(identity), severity='medium',
            labels=(storage.reporting.REPORT_LABEL, 'area:ci-release'),
            summary='\n'.join([
                '- Input: `' + input_digest + '`; original claim is retained, not completed or reset.',
                f"- Base: `{context['base_sha']}`; target: `{context['target_sha']}`; control: `{owner['control_sha']}`",
                f"- Producer: https://github.com/endaye/lmdj/actions/runs/{owner['run_id']}/attempts/{owner['attempt']}",
                '- Why: ' + row['why'], '- Remedy: ' + row['remedy']]),
            detail='No model retry, automatic repair, Issue closure, metadata admission or deployment is authorized by this report.')
        return outbox.deliver(api, report)

    def prepare_metadata(self, input_digest, *, proposed_build, allocation_date):
        journal = self._storage()
        row = self._row(journal, input_digest)
        r.require(row['result'] is not None and row['result']['state'] == 'advised',
                  'metadata requires an authenticated advised terminal assessment',
                  'settle the original producer or resolve blocked advice externally; never infer success')
        return metadata_proposal.prepare_metadata(self.runtime.root, context=row['context'],
            history=row['result']['attempts'], proposed_build=proposed_build, allocation_date=allocation_date)
