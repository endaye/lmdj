"""Real Journal and canonical planner composition; not live GitHub authority."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests/build'))
from tools.canary import planning_journal as storage, records as r
import ci_canary_planning_test as planning_fixture
from ci_batch_controller_test import Memory


class PlanningJournalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = planning_fixture.PlanningTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.memory = Memory()
        self.progress = r.initial_progress('endaye/lmdj')

    def fresh(self):
        return storage.Plans(self.memory.journal(), lambda: self.memory.lock, 'canary-planning-fixture')

    def baseline_receipt(self):
        approval = {'schema': 'lmdj.canary-first-version-baseline.v1', 'repository': 'endaye/lmdj',
            'revision': self.fixture.base, 'decision_ref': 'https://github.com/endaye/lmdj/pull/1071',
            'historical_changelog': 'preserve-no-backfill', 'hosts': [
                {'module': module, 'path': f'apps/{module}/module.json', 'version': '4.1.0'}
                for module in ('creator-web', 'web-runtime-host')]}
        def blob(text):
            raw = text.encode('utf-8')
            return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        approval_bytes = json.dumps(approval, indent=2) + '\n'
        manifests = []
        for host in approval['hosts']:
            text = json.dumps({'contract': 'lmdj.module.v1', 'module': host['module'],
                               'version': host['version'], 'api_version': 2}, indent=2) + '\n'
            manifests.append({**host, 'blob': blob(text), 'bytes': text})
        return r.seal({'schema': 'lmdj.canary-version-baseline-receipt.v1', 'approval': approval,
            'approval_blob': blob(approval_bytes), 'approval_bytes': approval_bytes, 'manifests': manifests})

    def test_adoption_changes_only_version_pointer_and_is_idempotent_after_observations(self):
        self.fresh().bootstrap()
        receipt = self.baseline_receipt()
        expected = r.seal({**self.progress, 'version_accounted': {
            'revision': receipt['approval']['revision'], 'receipt_digest': receipt['digest']}})
        self.assertEqual(self.fresh().adopt_version_baseline(receipt), expected)
        self.progress = expected
        intent, decision = self.decision()
        self.complete(intent, decision)
        before = deepcopy(self.memory.comments)
        self.assertEqual(self.fresh().adopt_version_baseline(receipt), expected)
        self.assertEqual(self.memory.comments, before)
        state = self.fresh().load()
        self.assertEqual(state['baseline_receipt'], receipt)
        self.assertEqual(state['active'], intent['source_request_id'])
        self.assertIsNone(state['progress']['formal'])
        self.assertEqual(state['progress']['deployments'], dict.fromkeys(r.SITES))

    def test_adoption_requires_empty_explicit_bootstrap_and_lock(self):
        receipt = self.baseline_receipt()
        with self.assertRaises(r.CanaryError):
            self.fresh().adopt_version_baseline(receipt)
        self.assertEqual(self.memory.comments, [])
        self.fresh().bootstrap()
        self.memory.lock = False
        with self.assertRaises(r.CanaryError):
            self.fresh().adopt_version_baseline(receipt)
        self.memory.lock = True
        intent, decision = self.decision(ignored=True)
        self.fresh().begin(intent)
        for complete in (False, True):
            if complete:
                self.fresh().finish(intent['source_request_id'], decision)
            before = deepcopy(self.memory.comments)
            with self.assertRaises(r.CanaryError):
                self.fresh().adopt_version_baseline(receipt)
            self.assertEqual(self.memory.comments, before)

    def test_adoption_rejects_changed_receipt_and_resealed_tampering(self):
        receipt = self.baseline_receipt()
        mutations = []
        for key, value in (('unknown', True), ('approval_blob', 'f' * 40),
                           ('approval_bytes', receipt['approval_bytes'] + ' ')):
            mutations.append(r.seal({**receipt, key: value}))
        for key, value in (('blob', 'f' * 40), ('bytes', '{}'), ('version', '4.2.0'),
                           ('path', 'apps/other/module.json'), ('unknown', True)):
            changed = deepcopy(receipt)
            changed['manifests'][0][key] = value
            mutations.append(r.seal(changed))
        mutations.append(r.seal({**receipt, 'manifests': receipt['manifests'][::-1]}))
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaises(r.CanaryError):
                storage.validate_baseline_receipt(changed)
        self.fresh().bootstrap()
        self.fresh().adopt_version_baseline(receipt)
        changed = deepcopy(receipt)
        changed['approval_bytes'] += ' '
        raw = changed['approval_bytes'].encode()
        changed['approval_blob'] = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        changed = r.seal(changed)
        storage.validate_baseline_receipt(changed)
        before = deepcopy(self.memory.comments)
        with self.assertRaises(r.CanaryError):
            self.fresh().adopt_version_baseline(changed)
        self.assertEqual(self.memory.comments, before)

    def test_adoption_lost_post_or_checkpoint_ack_never_blindly_reposts(self):
        receipt = self.baseline_receipt()
        for failure in ('before', 'after', 'checkpoint'):
            with self.subTest(failure=failure):
                self.memory = Memory()
                self.fresh().bootstrap()
                original = self.memory.replace
                def replace(previous, replacement):
                    original(previous, replacement)
                    if previous['pending'] is not None and replacement['pending'] is None:
                        raise RuntimeError('lost checkpoint acknowledgement')
                if failure == 'checkpoint':
                    with patch.object(self.memory, 'replace', side_effect=replace), self.assertRaises(r.CanaryError):
                        self.fresh().adopt_version_baseline(receipt)
                else:
                    self.memory.fail = ('adopt-version-baseline', failure)
                    with self.assertRaises(r.CanaryError):
                        self.fresh().adopt_version_baseline(receipt)
                if failure == 'before':
                    pending = deepcopy(self.memory.checkpoint['pending'])
                    before = deepcopy(self.memory.comments)
                    with self.assertRaises(r.CanaryError):
                        self.fresh().adopt_version_baseline(receipt)
                    self.assertEqual(self.memory.comments, before)
                    self.memory.comments.append({'id': 2, 'edited': False, 'envelope': pending, 'provenance': {}})
                self.fresh().adopt_version_baseline(receipt)
                self.assertEqual(len(self.memory.comments), 2)
                self.assertEqual(self.fresh().load()['baseline_receipt'], receipt)

    def test_adoption_fresh_process_replays_exact_receipt_without_new_writes(self):
        self.fresh().bootstrap()
        receipt = self.baseline_receipt()
        self.fresh().adopt_version_baseline(receipt)
        script = '''
import json, os, sys
sys.path.insert(0, 'tests/build')
from ci_batch_controller_test import Memory
from tools.canary.planning_journal import Plans
value = json.load(sys.stdin)
memory = Memory()
memory.checkpoint, memory.comments = value['checkpoint'], value['comments']
def forbidden(*args, **kwargs):
    raise AssertionError('replay must not append')
memory.append = forbidden
plans = Plans(memory.journal(), lambda: True, 'canary-planning-fixture')
state = plans.load()
plans.adopt_version_baseline(state['baseline_receipt'])
print(json.dumps({'pid': os.getpid(), 'state': state, 'comments': memory.comments}))
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, input=json.dumps({
            'checkpoint': self.memory.checkpoint, 'comments': self.memory.comments}),
            text=True, capture_output=True, timeout=30, check=True)
        value = json.loads(result.stdout)
        self.assertNotEqual(value['pid'], os.getpid())
        self.assertEqual(r.canonical(value['state']['baseline_receipt']), r.canonical(receipt))
        self.assertEqual(value['state'], self.fresh().load())
        self.assertEqual(value['comments'], self.memory.comments)

    def test_baseline_approval_and_receipt_reject_unapproved_shape_and_oversize(self):
        receipt = self.baseline_receipt()
        approval = receipt['approval']
        for changes in ({'extra': True}, {'revision': 'main'}, {'repository': 'other/lmdj'},
                        {'decision_ref': 'https://github.com/endaye/lmdj/pull/1'},
                        {'historical_changelog': 'backfill'}, {'hosts': approval['hosts'][:1]}):
            with self.subTest(changes=changes), self.assertRaises(r.CanaryError):
                storage.validate_baseline_approval({**approval, **changes})
        for changes in ({'digest': 'a' * 64}, {'schema': 'other'}):
            with self.subTest(changes=changes), self.assertRaises(r.CanaryError):
                storage.validate_baseline_receipt({**receipt, **changes})
        oversized = r.seal({**receipt, 'approval_bytes': ' ' * storage.codec.MAX_EVENT_BYTES})
        with self.assertRaisesRegex(r.CanaryError, 'small event budget'):
            storage.validate_baseline_receipt(oversized)
        # Even recomputed blob/seal cannot disguise duplicate JSON fields or
        # changed Host identity inside the retained complete manifest bytes.
        for text in ('{"module":"creator-web","module":"creator-web"}',
                     '{"contract":"lmdj.module.v1","module":"creator-web","version":"4.2.0"}'):
            changed = deepcopy(receipt)
            raw = text.encode()
            changed['manifests'][0].update(bytes=text,
                blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())
            with self.assertRaises(r.CanaryError):
                storage.validate_baseline_receipt(r.seal(changed))

    def test_baseline_initial_checkpoint_ack_loss_blocks_without_posting(self):
        self.fresh().bootstrap()
        receipt = self.baseline_receipt()
        original = self.memory.replace
        def replace(previous, replacement):
            original(previous, replacement)
            if previous['pending'] is None and replacement['pending'] is not None:
                raise RuntimeError('initial checkpoint acknowledgement lost')
        before = deepcopy(self.memory.comments)
        with patch.object(self.memory, 'replace', side_effect=replace), self.assertRaises(r.CanaryError):
            self.fresh().adopt_version_baseline(receipt)
        self.assertIsNotNone(self.memory.checkpoint['pending'])
        with self.assertRaises(r.CanaryError):
            self.fresh().adopt_version_baseline(receipt)
        self.assertEqual(self.memory.comments, before)

    def test_baseline_reducer_refuses_noninitial_progress_or_duplicate_transition(self):
        self.fresh().bootstrap()
        receipt = self.baseline_receipt()
        initial = self.fresh().load()
        event = {'id': 'plan:1', 'epoch': initial['epoch'], 'generation': 1,
                 'type': 'adopt-version-baseline', 'data': {'receipt': receipt}}
        for key in ('version_accounted', 'formal', 'docs'):
            changed = deepcopy(initial)
            pointer = {'revision': self.fixture.base, 'receipt_digest': 'a' * 64}
            if key == 'docs':
                changed['progress']['deployments'][key] = pointer
            else:
                changed['progress'][key] = pointer
            changed['progress'] = r.seal(changed['progress'])
            with self.subTest(key=key), self.assertRaises(r.CanaryError):
                storage.reduce(changed, event)
        adopted = storage.reduce(initial, event)
        with self.assertRaises(r.CanaryError):
            storage.reduce(adopted, {**event, 'id': 'plan:2', 'generation': 2})

    def decision(self, number=1, *, ignored=False, large=False):
        f = self.fixture
        f.change(f'apps/creator-web/src/fixture-{number}.ts')
        state = f.result_state(conclusion='failure' if ignored else 'success')
        old = 'batch:fixture:1'
        key = f'batch:fixture:{number}'
        request = state['requests'].pop(old)
        terminal = state['results'].pop(old)
        request['id'], terminal['request_id'] = key, key
        verdict = planning_fixture.batch_runtime.decode_reference(terminal['reference'])
        verdict['identity']['request_id'] = key
        verdict = planning_fixture.batch_verdict.build(
            planning_fixture.test_scope.load_policy(f.root), verdict['identity'], request['selection'], verdict['observations'])
        terminal['reference'] = planning_fixture.batch_runtime.encode_reference(verdict)
        state['requests'][key], state['results'][key] = request, terminal
        value = planning_fixture.p.plan_after_result(f.root, scheduler=state, source_request_id=key,
            main_sha=f.git('rev-parse', 'HEAD'), control_sha=f.base, progress=self.progress)
        if large:
            # Codec-boundary fixture: complete incompressible explanatory data,
            # not a claim that Git collected a 180 KB filename or real report.
            value['plan']['test_floor']['reasons'].append(random.Random(12).randbytes(90000).hex())
            value['plan'] = r.seal(value['plan'])
        intent = r.seal({'schema': storage.INTENT_SCHEMA, 'source_request_id': key,
            'main_sha': f.git('rev-parse', 'HEAD'), 'control_sha': f.base,
            'target_sha': value['source']['target_sha'], 'progress': self.progress,
            'scheduler_storage': {'repository': 'endaye/lmdj', 'issue_number': 807,
                'issue_node_id': 'I_scheduler', 'bot_node_id': 'BOT_fixture', 'workflow_id': 17, 'epoch': 'fixture'},
            'source_digest': r.digest(value['source']), 'decision_digest': r.digest(value),
            'target_rank': int(f.git('rev-list', '--first-parent', '--count', value['source']['target_sha'])),
            'decision_action': value['action']})
        return intent, value

    def complete(self, intent, value):
        self.fresh().begin(intent)
        return self.fresh().finish(intent['source_request_id'], value)

    def restart_process(self, source_request_id, decision=None):
        # Only serialized remote transport state crosses this boundary. The
        # child gets no parent Plans/Journal instances, codec cache or fixture
        # repository. A partial write also receives the entry's recomputed
        # decision; a complete replay receives no external decision at all.
        request = {'checkpoint': self.memory.checkpoint, 'comments': self.memory.comments,
                   'source_request_id': source_request_id}
        if decision is not None:
            request['decision'] = decision
        script = '''
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests/build'))
from tools.canary import planning_journal as storage, records as r
from ci_batch_controller_test import Memory
request = json.load(sys.stdin)
memory = Memory()
memory.checkpoint, memory.comments = request['checkpoint'], request['comments']
plans = storage.Plans(memory.journal(), lambda: memory.lock, 'canary-planning-fixture')
initial = plans.load()
if 'decision' in request:
    plans.finish(request['source_request_id'], request['decision'])
else:
    def forbidden(*args, **kwargs):
        raise AssertionError('complete recovery cannot append or reconstruct a decision')
    memory.append = forbidden
row = plans.lookup(request['source_request_id'])
state = plans.load()
json.dump({'pid': os.getpid(), 'row': row, 'decision_digest': r.digest(row['decision']),
           'initial_active': initial['active'], 'initial_unfinished': initial['unfinished'],
           'active': state['active'], 'pending': state['pending'], 'unfinished': state['unfinished'],
           'checkpoint': memory.checkpoint, 'comments': memory.comments}, sys.stdout)
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                input=r.canonical(request), capture_output=True, timeout=30, check=True)
        return json.loads(result.stdout)

    def test_bootstrap_is_explicit_and_idempotent_not_missing_storage_fallback(self):
        self.assertIsNone(self.fresh().load()['progress'])
        intent, _ = self.decision()
        with self.assertRaises(r.CanaryError):
            self.fresh().begin(intent)
        self.assertFalse(self.memory.comments)
        self.assertEqual(self.fresh().bootstrap(), self.progress)
        self.assertEqual(self.fresh().bootstrap(), self.progress)
        self.assertEqual(len(self.memory.comments), 1)

    def test_intent_precedes_chunks_and_completion_alone_sets_active(self):
        self.fresh().bootstrap()
        intent, value = self.decision()
        begun = self.fresh().begin(intent)
        self.assertEqual(begun, {'intent': intent, 'decision': None, 'slot': 'active'})
        self.assertIsNone(self.fresh().load()['active'])
        self.assertEqual(self.fresh().load()['unfinished'], intent['source_request_id'])
        finished = self.fresh().finish(intent['source_request_id'], value)
        self.assertEqual(finished['decision'], value)
        self.assertEqual(self.fresh().load()['active'], intent['source_request_id'])
        self.assertIsNone(self.fresh().load()['unfinished'])
        self.assertEqual([e['type'] for e in self.memory.journal().load()], ['bootstrap', 'intent', 'blob', 'complete'])

    def test_reopened_complete_bytes_are_idempotent_and_independent_copies(self):
        self.fresh().bootstrap()
        intent, value = self.decision()
        answer = self.complete(intent, value)
        count = len(self.memory.comments)
        self.assertEqual(self.complete(intent, value), answer)
        self.assertEqual(len(self.memory.comments), count)
        answer['intent']['main_sha'] = 'f' * 40
        self.assertEqual(self.fresh().lookup(intent['source_request_id'])['intent'], intent)

    def test_different_source_cannot_overtake_unfinished_intent(self):
        self.fresh().bootstrap()
        first, _ = self.decision()
        second, _ = self.decision(2)
        self.fresh().begin(first)
        with self.assertRaises(r.CanaryError):
            self.fresh().begin(second)
        self.assertEqual(list(self.fresh().load()['observations']), [first['source_request_id']])

    def test_newer_pending_coalesces_but_active_and_old_pending_history_remain(self):
        self.fresh().bootstrap()
        pairs = [self.decision(n) for n in (1, 2, 3, 4)]
        for n in (0, 2, 3, 1):
            self.complete(*pairs[n])
        state = self.fresh().load()
        self.assertEqual(state['active'], pairs[0][0]['source_request_id'])
        self.assertEqual(state['pending'], pairs[3][0]['source_request_id'])
        self.assertEqual(state['observations'][pairs[1][0]['source_request_id']]['slot'], 'historical')
        self.assertEqual(self.fresh().lookup(pairs[2][0]['source_request_id'])['decision'], pairs[2][1])
        self.assertEqual(state['progress'], self.progress)

    def test_ignored_failure_never_occupies_active_or_pending(self):
        self.fresh().bootstrap()
        intent, value = self.decision(ignored=True)
        self.assertEqual(self.complete(intent, value)['slot'], 'ignored')
        self.assertIsNone(self.fresh().load()['active'])
        self.assertIsNone(self.fresh().load()['pending'])

    def test_not_required_preserves_both_retained_verdict_and_special_receipt(self):
        intent, value = self.decision(ignored=True)
        for digest in (None, 'a' * 64):
            with self.subTest(digest=digest):
                self.memory = Memory()
                self.fresh().bootstrap()
                changed = deepcopy(value)
                changed['source'].update(status='not-required', evidence_digest=digest)
                bound = r.seal({**intent, 'source_digest': r.digest(changed['source']),
                                'decision_digest': r.digest(changed)})
                self.assertEqual(self.complete(bound, changed)['decision'], changed)

    def test_equal_rank_different_target_and_equal_target_different_rank_reject(self):
        self.fresh().bootstrap()
        first, decision = self.decision()
        self.complete(first, decision)
        other, _ = self.decision(2)
        for changes in ({'target_rank': first['target_rank']}, {'target_sha': first['target_sha']}):
            with self.subTest(changes=changes), self.assertRaises(r.CanaryError):
                self.fresh().begin(r.seal({**other, **changes}))

    def test_changed_intent_and_result_cannot_replace_frozen_input(self):
        self.fresh().bootstrap()
        intent, value = self.decision()
        self.fresh().begin(intent)
        for key, changed in (('main_sha', 'f' * 40), ('control_sha', 'e' * 40),
                             ('source_digest', 'a' * 64), ('decision_digest', 'b' * 64)):
            with self.subTest(key=key), self.assertRaises(r.CanaryError):
                self.fresh().begin(r.seal({**intent, key: changed}))
        altered = deepcopy(value)
        altered['plan']['admission_evidence'] = True
        altered['plan'] = r.seal(altered['plan'])
        with self.assertRaises(r.CanaryError):
            self.fresh().finish(intent['source_request_id'], altered)
        self.assertEqual(self.fresh().finish(intent['source_request_id'], value)['decision'], value)

    def test_intent_rejects_closed_schema_boolean_rank_and_storage_alias(self):
        intent, _ = self.decision()
        mutations = ({'unknown': True}, {'target_rank': True}, {'source_request_id': 'x' * 129},
                     {'scheduler_storage': {**intent['scheduler_storage'], 'issue_number': 817}},
                     {'scheduler_storage': {**intent['scheduler_storage'], 'workflow_id': True}},
                     {'scheduler_storage': {**intent['scheduler_storage'], 'epoch': ''}})
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaises(r.CanaryError):
                storage.validate_intent(r.seal({**intent, **changed}))

    def test_nonempty_progress_cannot_be_imported_without_receipts(self):
        self.fresh().bootstrap()
        intent, _ = self.decision()
        progress = deepcopy(intent['progress'])
        progress['version_accounted'] = {'revision': intent['target_sha'], 'receipt_digest': 'a' * 64}
        changed = r.seal({**intent, 'progress': r.seal(progress)})
        with self.assertRaises(r.CanaryError):
            self.fresh().begin(changed)
        self.assertEqual(len(self.memory.comments), 1)

    def test_resealed_plan_cannot_change_frozen_control_or_add_authority(self):
        intent, value = self.decision()
        for change in ({'control_sha': 'f' * 40}, {'admission_evidence': True},
                       {'deploy_authorized': True}, {'progress_digest': 'a' * 64}):
            with self.subTest(change=change):
                changed = deepcopy(value)
                changed['plan'] = r.seal({**changed['plan'], **change})
                bound = r.seal({**intent, 'decision_digest': r.digest(changed)})
                with self.assertRaises(r.CanaryError):
                    storage.validate_decision(bound, changed)

    def test_decision_identity_is_checked_even_with_recomputed_expected_digest(self):
        intent, value = self.decision()
        for key, bad in (('run_attempt', True), ('target_sha', 'f' * 40), ('request_id', 'batch:other:1')):
            mutated = deepcopy(value)
            mutated['source'][key] = bad
            changed = r.seal({**intent, 'source_digest': r.digest(mutated['source']), 'decision_digest': r.digest(mutated)})
            with self.subTest(key=key), self.assertRaises(r.CanaryError):
                storage.validate_decision(changed, mutated)

    def test_lock_epoch_and_edited_journal_reject_without_reset(self):
        self.fresh().bootstrap()
        self.memory.lock = False
        with self.assertRaises(r.CanaryError):
            self.fresh().load()
        self.memory.lock = True
        with self.assertRaises(r.CanaryError):
            storage.Plans(self.memory.journal(), lambda: True, 'other').load()
        self.memory.comments[0]['edited'] = True
        with self.assertRaises(r.CanaryError):
            self.fresh().bootstrap()
        self.assertEqual(len(self.memory.comments), 1)

    def test_every_append_response_loss_preserves_exact_intent_and_complete_bytes(self):
        intent, value = self.decision(large=True)
        self.fresh().bootstrap()
        self.complete(intent, value)
        expected_events = self.memory.journal().load()
        self.assertGreater(sum(e['type'] == 'blob' for e in expected_events), 2)
        for position in range(len(expected_events)):
            for timing in ('before', 'after'):
                with self.subTest(position=position, timing=timing):
                    self.memory = Memory()
                    original = self.memory.append
                    count = 0
                    def append(issue, envelope):
                        nonlocal count
                        if count == position:
                            self.memory.fail = (envelope['event']['type'], timing)
                        count += 1
                        return original(issue, envelope)
                    with patch.object(self.memory, 'append', side_effect=append):
                        with self.assertRaises(r.CanaryError):
                            self.fresh().bootstrap()
                            self.complete(intent, value)
                    if timing == 'before':
                        checkpoint = deepcopy(self.memory.checkpoint)
                        saved = deepcopy(self.memory.comments)
                        with self.assertRaises(r.CanaryError):
                            self.fresh().load()
                        self.assertEqual(self.memory.comments, saved, 'unknown POST must not be reissued')
                        # The ORIGINAL request becomes visible; this is not a
                        # replacement write authorized by the coordinator.
                        self.memory.comments.append({'id': len(saved) + 1, 'edited': False,
                            'envelope': checkpoint['pending'], 'provenance': {}})
                    self.fresh().bootstrap()
                    self.assertEqual(self.complete(intent, value)['decision'], value)
                    self.assertEqual(self.memory.journal().load(), expected_events)
                    self.assertEqual(self.fresh().load()['active'], intent['source_request_id'])

    def test_fresh_process_resumes_partial_chunks_without_replacing_active(self):
        self.fresh().bootstrap()
        active, active_decision = self.decision()
        self.complete(active, active_decision)
        intent, value = self.decision(2, large=True)
        self.fresh().begin(intent)
        self.memory.fail = ('blob', 'after')
        with self.assertRaises(r.CanaryError):
            self.fresh().finish(intent['source_request_id'], value)
        before = deepcopy(self.memory.comments)
        self.assertIsNotNone(self.memory.checkpoint['pending'], 'fixture must lose the real chunk POST response')
        result = self.restart_process(intent['source_request_id'], value)
        self.assertNotEqual(result['pid'], os.getpid())
        self.assertEqual(result['initial_unfinished'], intent['source_request_id'])
        self.assertEqual(result['initial_active'], active['source_request_id'])
        self.assertEqual(result['active'], active['source_request_id'])
        self.assertEqual(result['pending'], intent['source_request_id'])
        self.assertIsNone(result['unfinished'])
        self.assertEqual(result['row']['intent'], intent)
        self.assertEqual(r.canonical(result['row']['decision']), r.canonical(value))
        self.assertEqual(result['decision_digest'], intent['decision_digest'])
        self.assertEqual(result['comments'][:len(before)], before, 'restart must retain the already persisted prefix')
        events = [row['envelope']['event'] for row in result['comments']]
        self.assertEqual(len({event['id'] for event in events}), len(events))
        self.assertEqual(sum(event['type'] == 'intent' for event in events), 2)
        self.assertEqual(sum(event['type'] == 'complete' for event in events), 2)

    def test_fresh_process_replays_complete_decision_from_transport_only(self):
        self.fresh().bootstrap()
        intent, value = self.decision(large=True)
        self.fresh().begin(intent)
        self.memory.fail = ('complete', 'after')
        with self.assertRaises(r.CanaryError):
            self.fresh().finish(intent['source_request_id'], value)
        before = deepcopy(self.memory.comments)
        # No decision or fixture Git path is supplied to the child. It must
        # recover the terminal checkpoint and complete bytes from storage.
        result = self.restart_process(intent['source_request_id'])
        self.assertNotEqual(result['pid'], os.getpid())
        self.assertEqual(r.canonical(result['row']['decision']), r.canonical(value))
        self.assertEqual(result['decision_digest'], intent['decision_digest'])
        self.assertEqual(result['row']['intent'], intent)
        self.assertEqual(result['active'], intent['source_request_id'])
        self.assertIsNone(result['unfinished'])
        self.assertIsNone(result['checkpoint']['pending'])
        self.assertEqual(result['comments'], before, 'complete recovery must not append even a duplicate event')

    def test_replay_rejects_chunk_without_intent_and_mutated_terminal(self):
        self.fresh().bootstrap()
        intent, value = self.decision()
        self.complete(intent, value)
        events = self.memory.journal().load()
        empty = storage.Plans(Memory().journal(), lambda: True, 'canary-planning-fixture').load()
        state = storage.reduce(empty, events[0])
        chunk = deepcopy(events[2])
        chunk.update(id='plan:1', generation=1)
        with self.assertRaises(r.CanaryError):
            storage.reduce(state, chunk)
        for event in events[1:-1]:
            state = storage.reduce(state, event)
        changed = deepcopy(events[-1])
        changed['data']['decision'] = 'a' * 64
        with self.assertRaises(r.CanaryError):
            storage.reduce(state, changed)

    def test_replay_rejects_wrong_slot_sequence_unknown_type_and_corrupt_chunk(self):
        self.fresh().bootstrap()
        intent, value = self.decision()
        self.complete(intent, value)
        events = self.memory.journal().load()
        empty = storage.Plans(Memory().journal(), lambda: True, 'canary-planning-fixture').load()
        bootstrapped = storage.reduce(empty, events[0])
        changed = deepcopy(events[1])
        changed['data']['slot'] = 'pending'
        with self.assertRaises(r.CanaryError):
            storage.reduce(bootstrapped, changed)
        for changes in ({'generation': True}, {'generation': 9}, {'type': 'advance-progress'}):
            with self.subTest(changes=changes), self.assertRaises(r.CanaryError):
                storage.reduce(bootstrapped, {**events[1], **changes})
        begun = storage.reduce(bootstrapped, events[1])
        for changes in ({'index': 1}, {'total': True}, {'text': '{}'}, {'blob': 'a' * 64}):
            changed = deepcopy(events[2])
            changed['data'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(r.CanaryError):
                storage.reduce(begun, changed)


if __name__ == '__main__':
    unittest.main()
