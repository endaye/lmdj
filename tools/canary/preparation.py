"""Propose pinned Host edits; never allocate a Product or write any repository.

The caller owns authenticated assessment receipts and main observations. This
module recollects Git bytes and validates advice, not semantic AI truth or live
authority. A proposal is incomplete until canonical Product/Assembly/identity/
snapshot generation, occupancy and post-squash coverage checks have succeeded.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import date
import hashlib
import json
import re

from . import assessment as a, records as r

SCHEMA = 'lmdj.canary-host-preparation.v1'
ENTRY_SCHEMA = 'lmdj.host-changelog-entry.v1'
MARKER = '<!-- lmdj-host-changelog:v1 '


def _bytes_digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _version(value):
    r.require(isinstance(value, str) and re.fullmatch(
        r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', value),
        'Host version is not stable SemVer')
    try:
        return tuple(int(part) for part in value.split('.'))
    except ValueError:
        raise r.CanaryError('why: Host version exceeds numeric parser limits; remedy: reconcile manifest identity') from None


def _select_version(base, current, impact):
    baseline, committed = _version(base), _version(current)
    r.require(committed >= baseline and committed[0] == baseline[0],
              'backwards or major pre-bump needs compatibility review')
    if impact == 'none':
        r.require(committed == baseline, 'unexplained pre-bump conflicts with none advice')
        return current, False
    r.require(impact in {'patch', 'minor'}, 'Host impact requires compatibility review')
    needed = (baseline[0], baseline[1] + 1, 0) if impact == 'minor' else (
        baseline[0], baseline[1], baseline[2] + 1)
    if committed != baseline:
        r.require(committed >= needed, 'insufficient pre-bump requires an explicit correction')
        return current, True
    return '.'.join(map(str, needed)), False


def _blob(inputs, revision, path, *, optional=False):
    rows = inputs._git('ls-tree', '-z', revision, '--', path).split(b'\0')
    rows = [row for row in rows if row]
    if not rows and optional:
        return None
    r.require(len(rows) == 1, 'pinned preparation source is missing or ambiguous')
    metadata, observed_path = rows[0].split(b'\t', 1)
    fields = metadata.split()
    r.require(observed_path.decode('utf-8') == path and len(fields) == 3
              and fields[0] in {b'100644', b'100755'} and fields[1] == b'blob',
              'preparation source must be a regular blob, not a symlink or submodule')
    raw = inputs._git('show', f'{revision}:{path}')
    r.require(len(raw) <= r.MAX_BYTES, 'preparation source exceeds byte limit')
    raw.decode('utf-8', errors='strict')
    return raw


def _prose(text):
    """Entity-escape all markup punctuation before Markdown/MDX interprets it."""
    a._text(text)
    return ''.join(char if char.isalnum() or char == ' ' else f'&#{ord(char)};'
                   for char in ' '.join(text.split()))


def _links(references):
    # Validated exact commits only; no provider-supplied URL or PR number.
    return ', '.join(f'[{sha[:12]}](https://github.com/endaye/lmdj/commit/{sha})' for sha in references)


def _entry(host, version, advice, context, assessment_result, allocation_date):
    return r.seal({'schema': ENTRY_SCHEMA, 'host': host, 'version': version,
                   'prepared_date': allocation_date, 'base_sha': context['base_sha'],
                   'target_sha': context['target_sha'], 'input_digest': context['digest'],
                   'assessment_digest': assessment_result['digest'],
                   'impact': advice['impact'], 'rationale': advice['rationale'],
                   'references': deepcopy(advice['references']),
                   'dependency_effects': deepcopy(advice['dependency_effects']),
                   'changes': deepcopy(advice['changelog'])})


def _changelog(previous, entry):
    prior = previous.decode('utf-8') if previous is not None else f"# {entry['host']} changelog\n"
    # Existing Markdown may predate this generator; preserve it verbatim but
    # refuse any occupied version. No historical entry is rewritten/upserted.
    headings = re.findall(r'^##[ \t]+\[?([0-9]+\.[0-9]+\.[0-9]+)(?=\]|[ \t\r\n]|$)', prior, re.MULTILINE)
    r.require(all(_version(version) < _version(entry['version']) for version in headings),
              'changelog version is occupied or newer than the proposed entry',
              'reconcile the existing allocation; published corrections require an attributed addendum')
    for encoded in re.findall(re.escape(MARKER) + r'([^\n]*?) -->', prior):
        try:
            historical = r.decode(base64.b64decode(encoded, validate=True))
            r.verify_seal(historical)
            r.require(historical['schema'] == ENTRY_SCHEMA and historical['host'] == entry['host']
                      and _version(historical['version']) < _version(entry['version']),
                      'changelog machine identity is occupied or inconsistent')
        except (ValueError, KeyError, TypeError):
            raise r.CanaryError('why: existing changelog marker is occupied or invalid; remedy: reconcile immutable source history') from None
    r.require(prior.count(MARKER) == len(re.findall(re.escape(MARKER) + r'([^\n]*?) -->', prior)),
              'existing changelog marker is truncated')
    marker = MARKER + base64.b64encode(r.canonical(entry)).decode('ascii') + ' -->'
    lines = [f"## {entry['version']}", '', marker, '',
             f"Prepared: {entry['prepared_date']}. Publication, deployment and promotion are separate evidence.", '',
             _prose(entry['rationale']), '', 'Changes:', '']
    for change in entry['changes']:
        lines.append(f"- {change['kind']}: {_prose(change['text'])} ({_links(change['references'])})")
    if entry['dependency_effects']:
        lines += ['', 'Dependency effects:', '']
        lines += ['- ' + _prose(effect) for effect in entry['dependency_effects']]
    lines += ['', 'Assessed commits: ' + _links(entry['references']), '']
    return prior + ('\n' if prior.endswith('\n') else '\n\n') + '\n'.join(lines)


def prepare_hosts(root, *, context, history, allocation_date):
    """Return bytes with exact before/after witnesses; do not apply or allocate.

No command supplied by the model is evaluated. Host edits intentionally cannot
be committed as a Product allocation by themselves: the cut coordinator must
complete canonical generators and all recorded obligations under its own lease.
"""
    context = a._context(context)
    r.require(isinstance(allocation_date, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', allocation_date),
              'allocation date must be an exact ISO date')
    try:
        date.fromisoformat(allocation_date)
    except ValueError:
        raise r.CanaryError('why: allocation date is invalid; remedy: supply a valid allocation date, not a release date') from None
    result = a.finish(context, history)
    r.require(result['state'] == 'advised', 'assessment is blocked; Host preparation cannot continue')
    recollected = a.collect(root, base_sha=context['base_sha'], target_sha=context['target_sha'],
                            control_sha=context['control_sha'], policy_digest=context['policy_digest'])
    r.require(recollected == context, 'assessment context differs from recollected pinned Git inputs')
    inputs = a.planning.batch_controller.GitInputs(root, context['control_sha'], lambda: context['target_sha'])
    hosts, edits = [], []

    def edit(path, before, text):
        after = text.encode('utf-8')
        if before == after:
            return
        r.require(len(after) <= r.MAX_BYTES, 'prepared file exceeds byte limit')
        edits.append({'path': path, 'before_sha256': _bytes_digest(before) if before is not None else None,
                      'before_length': len(before) if before is not None else None,
                      'after_sha256': _bytes_digest(after), 'after_length': len(after), 'content': text})

    try:
        for component, advice in zip(context['components'], history[-1]['advice']['components']):
            version, consumed = _select_version(component['base_version'], component['target_version'], advice['impact'])
            if advice['impact'] == 'none':
                continue
            host = component['id']
            manifest_path, log_path = f'apps/{host}/module.json', f'apps/{host}/CHANGELOG.md'
            original = _blob(inputs, context['target_sha'], manifest_path)
            manifest = r.decode(original)
            r.require(manifest['module'] == host and manifest['version'] == component['target_version'],
                      'pinned Host identity differs from the assessment')
            if version != component['target_version']:
                manifest['version'] = version
                edit(manifest_path, original, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            previous = _blob(inputs, context['target_sha'], log_path, optional=True)
            entry = _entry(host, version, advice, context, result, allocation_date)
            edit(log_path, previous, _changelog(previous, entry))
            hosts.append({'id': host, 'previous_version': component['target_version'], 'version': version,
                          'prebump_consumed': consumed, 'entry_digest': entry['digest']})
    except (a.planning.incremental_batch.BatchError, UnicodeError, KeyError):
        raise r.CanaryError('why: pinned preparation source is unavailable; remedy: restore exact Git and manifest inputs') from None
    return r.seal({'schema': SCHEMA, 'admission_evidence': False,
                   'state': 'host-inputs-prepared' if hosts else 'no-host-change',
                   'target_sha': context['target_sha'], 'input_digest': context['digest'],
                   'assessment_digest': result['digest'], 'allocation_date': allocation_date,
                   'hosts': hosts, 'edits': edits,
                   'remaining_obligations': ['authenticated-assessment-and-main', 'occupancy-and-fenced-cut',
                       'canonical-product-assembly-lock-identity-snapshot', 'reviewed-version-pr',
                       'post-squash-coverage-and-witness', 'exact-candidate-test-and-artifact-acceptance']})
