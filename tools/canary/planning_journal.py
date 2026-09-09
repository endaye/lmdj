"""Frozen planning intents over the authenticated Journal, never effect authority.

The caller proves source/progress provenance and first-parent target ordering.
This reducer preserves that evidence, one unfinished write and a pinned active
plan. It can adopt one approved version-history baseline into an empty journal;
it cannot retire work, advance delivery progress, allocate or execute anything.
"""
from copy import deepcopy
import hashlib

from . import assessment_journal as codec, planning, records as r

SCHEMA = 'lmdj.canary-planning-journal.v1'
INTENT_SCHEMA = 'lmdj.canary-plan-intent.v1'
BASELINE_SCHEMA = 'lmdj.canary-version-baseline-receipt.v1'


def validate_baseline_approval(value):
    """Validate policy shape only; entry authenticates its frozen Git source."""
    r.require(isinstance(value, dict) and set(value) == {
        'schema', 'repository', 'revision', 'decision_ref', 'historical_changelog', 'hosts'}
        and value['schema'] == 'lmdj.canary-first-version-baseline.v1'
        and value['repository'] == 'endaye/lmdj'
        and value['decision_ref'] == 'https://github.com/endaye/lmdj/pull/1071'
        and value['historical_changelog'] == 'preserve-no-backfill',
        'first version baseline approval schema or policy differs')
    r.exact_sha(value['revision'])
    expected = [{'module': module, 'path': f'apps/{module}/module.json', 'version': '4.1.0'}
                for module in ('creator-web', 'web-runtime-host')]
    r.require(value['hosts'] == expected, 'first version baseline Host inventory differs')
    return deepcopy(value)


def _baseline_blob(text, blob):
    r.require(isinstance(text, str), 'baseline source is not complete UTF-8 text')
    r.exact_sha(blob)
    try:
        raw = text.encode('utf-8')
    except UnicodeError:
        raise r.CanaryError('why: baseline source is not valid UTF-8; remedy: restore exact Git bytes') from None
    r.require(len(raw) <= codec.MAX_EVENT_BYTES, 'baseline source exceeds small receipt budget')
    r.require(hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest() == blob,
              'baseline Git blob identity differs from exact source bytes')
    return r.decode(raw)


def validate_baseline_receipt(value):
    """Replay complete evidence, not an unauthenticated caller approval."""
    r.require(isinstance(value, dict) and set(value) == {
        'schema', 'approval', 'approval_blob', 'approval_bytes', 'manifests', 'digest'}
        and value['schema'] == BASELINE_SCHEMA, 'baseline receipt schema is not closed')
    r.verify_seal(value)
    r.require(len(r.canonical(value)) <= codec.MAX_EVENT_BYTES - 1024,
              'baseline receipt exceeds the small event budget')
    approval = validate_baseline_approval(value['approval'])
    r.require(_baseline_blob(value['approval_bytes'], value['approval_blob']) == approval,
              'baseline approval differs from retained Git bytes')
    manifests = value['manifests']
    r.require(isinstance(manifests, list) and len(manifests) == 2,
              'baseline receipt manifest inventory is incomplete')
    for source, host in zip(manifests, approval['hosts']):
        r.require(isinstance(source, dict) and set(source) == {'module', 'path', 'version', 'blob', 'bytes'}
                  and all(source[key] == host[key] for key in host),
                  'baseline receipt manifest identity differs')
        manifest = _baseline_blob(source['bytes'], source['blob'])
        r.require(isinstance(manifest, dict) and manifest.get('contract') == 'lmdj.module.v1'
                  and manifest.get('module') == host['module'] and manifest.get('version') == host['version'],
                  'baseline retained Host manifest differs from approved identity')
    return deepcopy(value)


def source_id(value):
    return r.identifier(value)


def validate_intent(value):
    r.require(isinstance(value, dict) and set(value) == {
        'schema', 'source_request_id', 'main_sha', 'control_sha', 'target_sha',
        'progress', 'scheduler_storage', 'source_digest', 'decision_digest', 'target_rank',
        'decision_action', 'digest'} and value['schema'] == INTENT_SCHEMA,
        'planning intent schema is not closed')
    source_id(value['source_request_id'])
    for key in ('main_sha', 'control_sha', 'target_sha'):
        r.exact_sha(value[key])
    for key in ('source_digest', 'decision_digest'):
        r.exact_digest(value[key])
    r.validate_progress(value['progress'], repository='endaye/lmdj')
    storage = value['scheduler_storage']
    r.require(isinstance(storage, dict) and set(storage) == {
        'repository', 'issue_number', 'issue_node_id', 'bot_node_id', 'workflow_id', 'epoch'}
        and storage['repository'] == 'endaye/lmdj'
        and type(storage['issue_number']) is int and storage['issue_number'] == 807
        and type(storage['workflow_id']) is int and storage['workflow_id'] > 0
        and all(isinstance(storage[k], str) and storage[k] for k in ('issue_node_id', 'bot_node_id', 'epoch')),
        'planning intent scheduler storage identity differs')
    r.require(type(value['target_rank']) is int and value['target_rank'] > 0,
              'planning target rank is not a positive first-parent position')
    r.require(value['decision_action'] in ('plan', 'ignore'), 'unknown planning decision action')
    r.verify_seal(value)
    r.require(len(r.canonical(value)) <= codec.MAX_EVENT_BYTES - 1024,
              'planning intent exceeds the small pre-chunk record budget')
    return deepcopy(value)


def validate_decision(intent, value):
    """Check retained decision identity; Git/verdict provenance belongs to entry."""
    intent = validate_intent(intent)
    r.require(isinstance(value, dict) and set(value) == {'action', 'source_role', 'source', 'plan'}
              and value['action'] == intent['decision_action'] and value['source_role'] == 'wakeup-only',
              'planning decision is not a closed wakeup-only result')
    source = value['source']
    r.require(isinstance(source, dict) and set(source) == {
        'request_id', 'request_kind', 'base_sha', 'target_sha', 'control_sha',
        'policy_digest', 'run_id', 'run_attempt', 'status', 'evidence_digest'},
        'planning decision source identity is not closed')
    r.require(source['request_id'] == intent['source_request_id']
              and source['target_sha'] == intent['target_sha'], 'planning decision names another source or target')
    for key in ('target_sha', 'control_sha'):
        r.exact_sha(source[key])
    if source['base_sha'] is not None:
        r.exact_sha(source['base_sha'])
    r.exact_digest(source['policy_digest'])
    r.require(source['request_kind'] in ('auto', 'bootstrap', 'node', 'candidate')
              and (source['request_kind'] != 'auto' or source['base_sha'] is not None)
              and type(source['run_id']) is int and source['run_id'] > 0
              and type(source['run_attempt']) is int and source['run_attempt'] == 1,
              'planning source request or run identity is invalid')
    r.require(source['status'] in ('passed', 'failed', 'missing', 'not-required'),
              'planning source status is unknown')
    if source['status'] == 'missing':
        r.require(source['evidence_digest'] is None, 'absent verdict claims an evidence digest')
    elif source['status'] != 'not-required' or source['evidence_digest'] is not None:
        # not-required can be a special receipt (None) or an authenticated
        # retained verdict with zero selected suites (its real digest).
        r.exact_digest(source['evidence_digest'])
    eligible = source['status'] == 'passed' and source['request_kind'] in ('auto', 'bootstrap')
    r.require((value['action'] == 'plan') == eligible, 'planning action contradicts source eligibility')
    if eligible:
        plan = value['plan']
        r.require(isinstance(plan, dict) and set(plan) == {
            'schema', 'purpose', 'admission_evidence', 'request_id', 'repository', 'channel',
            'target_sha', 'control_sha', 'progress_digest', 'policy_digest', 'kind',
            'requested_sites', 'force', 'input_digest', 'version_interval', 'formal_interval',
            'site_intervals', 'site_test_floors', 'test_floor', 'affected_sites', 'deploy_sites',
            'build_hosts', 'digest', 'test_source'} and plan.get('schema') == planning.SCHEMA
                  and plan.get('purpose') == 'read-only-preview' and plan.get('admission_evidence') is False
                  and plan.get('kind') == 'result' and plan.get('repository') == 'endaye/lmdj'
                  and plan.get('channel') == 'canary' and plan.get('test_source') == source
                  and plan.get('target_sha') == intent['target_sha']
                  and plan.get('control_sha') == intent['control_sha']
                  and plan.get('progress_digest') == intent['progress']['digest']
                  and plan.get('request_id') == 'canary-result:' + r.digest(source),
                  'retained plan differs from frozen input or claims admission')
        r.verify_seal(plan)
    else:
        r.require(value['plan'] is None, 'ignored source contains a plan')
    r.require(r.digest(source) == intent['source_digest'] and r.digest(value) == intent['decision_digest'],
              'planning source or complete decision differs from frozen intent')
    return deepcopy(value)


def _slot(state, intent):
    # Rank equality is meaningful only with equal target bytes. Check all
    # observations, including superseded pending and ignored sources.
    for row in state['observations'].values():
        old = row['intent']
        r.require(old['target_rank'] != intent['target_rank'] or old['target_sha'] == intent['target_sha'],
                  'equal first-parent ranks name different targets')
        r.require(old['target_sha'] != intent['target_sha'] or old['target_rank'] == intent['target_rank'],
                  'one target has inconsistent first-parent ranks')
    if intent['decision_action'] == 'ignore':
        return 'ignored'
    if state['active'] is None:
        return 'active'
    newest = max(state['observations'][key]['intent']['target_rank']
                 for key in (state['active'], state['pending']) if key is not None)
    return 'pending' if intent['target_rank'] > newest else 'historical'


def reduce(state, event):
    r.require(isinstance(event, dict) and set(event) == {'id', 'epoch', 'generation', 'type', 'data'}
              and event['epoch'] == state['epoch'], 'planning event schema or epoch differs')
    r.identifier(event['id'])
    fingerprint = r.digest(event)
    if event['id'] in state['events']:
        r.require(state['events'][event['id']] == fingerprint, 'planning event ID reused with changed bytes')
        return deepcopy(state)
    r.require(type(event['generation']) is int and event['generation'] == state['generation']
              and len(r.canonical(event)) <= codec.MAX_EVENT_BYTES, 'planning event sequence or size differs')
    data = event['data']
    r.require(isinstance(data, dict), 'planning event data is not an object')
    answer = deepcopy(state)
    if event['type'] == 'bootstrap':
        r.require(set(data) == {'repository'} and data['repository'] == 'endaye/lmdj'
                  and state['generation'] == 0 and state['progress'] is None,
                  'planning progress bootstrap is not an explicit first event')
        answer['progress'] = r.initial_progress(data['repository'])
    elif event['type'] == 'adopt-version-baseline':
        r.require(set(data) == {'receipt'} and state['baseline_receipt'] is None
                  and state['progress'] == r.initial_progress('endaye/lmdj')
                  and not state['observations']
                  and all(state[key] is None for key in ('active', 'pending', 'unfinished')),
                  'version baseline adoption requires an empty explicitly bootstrapped journal')
        receipt = validate_baseline_receipt(data['receipt'])
        answer['baseline_receipt'] = receipt
        answer['progress'] = r.seal({**state['progress'], 'version_accounted': {
            'revision': receipt['approval']['revision'], 'receipt_digest': receipt['digest']}})
        r.validate_progress(answer['progress'], repository='endaye/lmdj')
    elif event['type'] == 'intent':
        r.require(set(data) == {'intent', 'slot'} and state['progress'] is not None
                  and state['unfinished'] is None, 'planning intent lacks bootstrap or overtakes unfinished work')
        intent = validate_intent(data['intent'])
        key = intent['source_request_id']
        r.require(key not in state['observations'] and intent['progress'] == state['progress'],
                  'planning intent replaces an observation or changes independent progress')
        r.require(data['slot'] == _slot(state, intent), 'planning intent slot contradicts pinned target ordering')
        answer['observations'][key] = {'intent': intent, 'slot': data['slot'], 'blob': None, 'decision': None}
        answer['unfinished'] = key
    elif event['type'] == 'blob':
        key = state['unfinished']
        r.require(key is not None, 'planning chunk has no preceding frozen intent')
        row = answer['observations'][key]
        reference = r.exact_digest(data.get('blob'))
        r.require(row['blob'] in (None, reference)
                  and (reference not in state['blobs'] or row['blob'] == reference),
                  'planning chunks changed their original payload')
        # Reuse the established bounded chunk reducer and pack/unpack codec.
        # Its blob branch does not access assessment-specific state. Do not
        # borrow assessment claim/complete semantics or any storage authority.
        answer['blobs'] = codec.reduce(state, event)['blobs']
        row['blob'] = reference
    elif event['type'] == 'complete':
        r.require(set(data) == {'source_request_id', 'decision'}, 'planning completion schema differs')
        key = source_id(data['source_request_id'])
        r.require(key == state['unfinished'] and key in state['observations'],
                  'planning completion has no original unfinished intent')
        row = answer['observations'][key]
        r.require(row['blob'] == data['decision'], 'planning completion changed its stored payload')
        decision = codec._blob(state, data['decision'])
        validate_decision(row['intent'], decision)
        row['decision'] = data['decision']
        if row['slot'] in ('active', 'pending'):
            answer[row['slot']] = key
        answer['unfinished'] = None
    else:
        r.require(False, 'unknown planning event type')
    answer['generation'] += 1
    answer['events'][event['id']] = fingerprint
    return answer


class Plans:
    def __init__(self, journal, lock_held, epoch):
        r.identifier(epoch)
        self.journal, self.lock_held, self.epoch = journal, lock_held, epoch

    def load(self):
        r.require(self.lock_held() is True, 'planning storage lacks its shared writer lock')
        state = {'schema': SCHEMA, 'epoch': self.epoch, 'generation': 0, 'events': {}, 'blobs': {},
                 'progress': None, 'baseline_receipt': None, 'observations': {},
                 'active': None, 'pending': None, 'unfinished': None}
        try:
            for event in self.journal.load():
                state = reduce(state, event)
            return state
        except Exception:
            raise r.CanaryError('why: planning journal cannot be authenticated or replayed; remedy: reconcile original checkpoint and complete history') from None

    def _persist(self, state, kind, data):
        r.require(self.lock_held() is True, 'planning append lost its shared writer lock')
        event = {'id': f"plan:{state['generation']}", 'epoch': self.epoch,
                 'generation': state['generation'], 'type': kind, 'data': data}
        expected = reduce(state, event)
        try:
            self.journal.append(event)
            r.require(self.load() == expected, 'planning append lacks confirmed persisted state')
            return expected
        except Exception:
            raise r.CanaryError('why: planning append outcome is unresolved; remedy: reconcile original intent and bytes, never repeat an uncertain POST') from None

    def bootstrap(self, repository='endaye/lmdj'):
        r.require(repository == 'endaye/lmdj', 'planning bootstrap repository differs')
        state = self.load()
        if state['progress'] is None:
            state = self._persist(state, 'bootstrap', {'repository': repository})
        return deepcopy(state['progress'])

    def adopt_version_baseline(self, receipt):
        receipt = validate_baseline_receipt(receipt)
        state = self.load()
        if state['baseline_receipt'] is None:
            state = self._persist(state, 'adopt-version-baseline', {'receipt': receipt})
        else:
            r.require(state['baseline_receipt'] == receipt, 'adopted version baseline receipt cannot be replaced')
        return deepcopy(state['progress'])

    @staticmethod
    def _view(state, key):
        row = state['observations'][key]
        return deepcopy({'intent': row['intent'], 'slot': row['slot'],
                         'decision': codec._blob(state, row['decision']) if row['decision'] else None})

    def lookup(self, source_request_id):
        key = source_id(source_request_id)
        state = self.load()
        return self._view(state, key) if key in state['observations'] else None

    def begin(self, intent):
        intent = validate_intent(intent)
        state = self.load()
        key = intent['source_request_id']
        if key in state['observations']:
            r.require(state['observations'][key]['intent'] == intent, 'existing planning intent cannot be replaced')
        else:
            state = self._persist(state, 'intent', {'intent': intent, 'slot': _slot(state, intent)})
        return self._view(state, key)

    def finish(self, source_request_id, decision):
        key = source_id(source_request_id)
        state = self.load()
        r.require(key in state['observations'], 'planning result has no frozen intent')
        row = state['observations'][key]
        decision = validate_decision(row['intent'], decision)
        if row['decision'] is None:
            r.require(state['unfinished'] == key, 'planning completion cannot overtake another source')
            # The codec's existing resumable chunk writer calls this class's
            # guarded _persist; no codec-specific assessment event is emitted.
            state, reference = codec.Assessments._store(self, state, decision)
            state = self._persist(state, 'complete', {'source_request_id': key, 'decision': reference})
        else:
            r.require(codec._blob(state, row['decision']) == decision, 'completed planning decision cannot be replaced')
        return self._view(state, key)
