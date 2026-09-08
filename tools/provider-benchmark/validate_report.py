#!/usr/bin/env python3
"""Read-only structural and semantic validation of local benchmark reports."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/conformance'))
import json_schema  # noqa: E402

MAX_BYTES = 8 * 1024 * 1024
MAX_INTEGER = 2**53 - 1
RATIO_TOLERANCE = 1e-12
UNITS = {'elapsed': 'seconds', 'real_time_factor': 'ratio',
         'peak_process_tree_rss': 'bytes', 'gpu_peak_bytes': 'bytes',
         'precision': 'ratio', 'recall': 'ratio', 'f1': 'ratio',
         'tp': 'count', 'fp': 'count', 'fn': 'count'}
REASONS = {'determinism': 'determinism_violation', 'output_schema': 'schema_invalid',
           'required_outputs': 'required_output_missing',
           'failed_input_refusal': 'input_not_refused'}
RESOURCE_REASONS = {'elapsed': 'timeout', 'peak_process_tree_rss': 'memory_limit',
                    'gpu_peak_bytes': 'gpu_limit'}


class InvalidReport(ValueError):
    """A report cannot support its declared qualification."""


def require(condition, path, why, remedy):
    if not condition:
        raise InvalidReport(f'{path}: why: {why}; remedy: {remedy}')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, '#', 'duplicate JSON key', 'retain each property exactly once')
        result[key] = value
    return result


def _constant(value):
    raise InvalidReport('#: why: non-finite JSON number; remedy: supply a finite value or an explicit unavailable status')


def read_report(path):
    """Bound the read before decoding or parsing; never fetch report citations."""
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        require(len(data) <= MAX_BYTES, '#', 'report exceeds 8 MiB', 'split reports into bounded files')
        return json.loads(data.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InvalidReport):
            raise
        raise InvalidReport('#: why: cannot read bounded UTF-8 JSON (' + type(exc).__name__ +
                            '); remedy: supply an accessible, correctly encoded JSON report') from exc


def _finite_tree(value, path='#', depth=0):
    require(depth <= 128, path, 'report nesting exceeds 128 levels', 'flatten the report into the supported schema')
    if isinstance(value, float):
        require(math.isfinite(value), path, 'non-finite number', 'supply finite numeric evidence')
    elif isinstance(value, str):
        require(not any(ord(c) < 32 or ord(c) == 127 for c in value), path,
                'control character in report text', 'use printable single-line text and exact digest strings')
        require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), path,
                'unpaired Unicode surrogate', 'supply valid Unicode text')
    elif isinstance(value, dict):
        for key, child in value.items():
            _finite_tree(child, path + '/' + key, depth + 1)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _finite_tree(child, f'{path}/{i}', depth + 1)


def _safe_path(value, path):
    parts = value.split('/')
    require(not any(p in ('', '.', '..', '.cache', '__pycache__') for p in parts)
            and '\\' not in value and ':' not in value and not value.startswith('~'), path,
            'path is not a repository-relative POSIX evidence path',
            'use a relative path without traversal, drive prefixes or cache directories')


def _license(value, path):
    try:
        url = urlsplit(value['url'])
        valid = (url.scheme == 'https' and url.hostname and not url.username and not url.password
                 and not url.query and not url.fragment and not url.port
                 and not re.search(r'[\s\\]', unquote(value['url'])))
    except ValueError:
        valid = False
    require(valid, path + '/url', 'citation is not a pinned credential-free HTTPS reference',
            'use an HTTPS citation with its content digest and no credentials, query or fragment')


def _unique(rows, key, path):
    result = {}
    for i, row in enumerate(rows):
        require(row[key] not in result, f'{path}/{i}/{key}', 'duplicate ' + key,
                'retain exactly one row for each ' + key)
        result[row[key]] = row
    return result


def _numeric(value, unit, path):
    if unit in ('count', 'bytes'):
        require(type(value) is int and 0 <= value <= MAX_INTEGER, path,
                'count/bytes must be nonnegative safe integers', 'use an integer at most 2^53-1')


def _checks(case, determinism, path):
    failed = set()
    for name, check in case['checks'].items():
        p = path + '/checks/' + name
        applicable = ((case['case_kind'] == 'input_failure' and name == 'failed_input_refusal')
                      or (case['case_kind'] == 'success' and name != 'failed_input_refusal'
                          and (name != 'determinism' or determinism != 'nondeterministic')))
        require(applicable or check['status'] == 'not_applicable', p,
                'inapplicable check carries a verdict', 'mark this check not_applicable')
        if applicable:
            require(check['status'] != 'not_applicable', p, 'required check is not applicable',
                    'record pass, fail or not_run for the applicable check')
        if check['status'] in ('pass', 'fail'):
            require(bool(check['evidence']), p + '/evidence', 'verdict lacks evidence digest',
                    'retain the check evidence and supply its digest')
        else:
            require(not check['evidence'], p + '/evidence', 'unperformed check claims evidence',
                    'clear evidence for not_run or not_applicable')
        if check['status'] == 'fail':
            failed.add(REASONS[name])
        if case['status'] != 'rejected' and applicable:
            require(check['status'] == 'pass', p, 'qualification requires a passing check',
                    'complete the required check before qualification')
    d = case['checks']['determinism']
    p = path + '/checks/determinism'
    performed = d['status'] in ('pass', 'fail')
    require(len(d['output_set_sha256']) == (2 if performed else 0), p,
            'repeatability requires exactly two output sets when performed',
            'supply both output-set digests, or clear them for an unperformed check')
    for name in ('seed_sha256', 'parameters_sha256'):
        expected = 2 if performed and determinism == 'seeded' else 0
        require(len(d[name]) == expected, p + '/' + name, 'seeded comparison context is incomplete',
                'supply two identical context digests only for performed seeded comparisons')
        if expected:
            require(d[name][0] == d[name][1], p + '/' + name,
                    'seeded trials use different context', 'compare runs with identical seed and parameters')
    if performed:
        equal = d['output_set_sha256'][0] == d['output_set_sha256'][1]
        require(equal == (d['status'] == 'pass'), p,
                'repeatability verdict contradicts output digests', 'derive the verdict from digest equality')
    return failed


def _quality(metrics, path):
    names = {'tp', 'fp', 'fn', 'precision', 'recall', 'f1'}
    if not names.intersection(metrics):
        return
    require(names <= metrics.keys(), path, 'quality score lacks counts or ratios',
            'supply tp, fp, fn, precision, recall and f1 together')
    for name in ('tp', 'fp', 'fn'):
        require(metrics[name]['status'] == 'measured', path + '/' + name,
                'quality counts are unavailable', 'supply exact measured scorer counts')
    tp, fp, fn = (metrics[n]['value'] for n in ('tp', 'fp', 'fn'))
    for name, numerator, denominator in [('precision', tp, tp + fp), ('recall', tp, tp + fn),
                                         ('f1', 2 * tp, 2 * tp + fp + fn)]:
        m = metrics[name]
        valid = (m['status'] == 'not_applicable' and m['value'] is None) if denominator == 0 else (
            m['status'] == 'measured' and abs(m['value'] - numerator / denominator) <= RATIO_TOLERANCE)
        require(valid, path + '/' + name, 'ratio contradicts authoritative counts',
                'derive the ratio from tp/fp/fn; use not_applicable/null only for a zero denominator')


def validate_report(report, *, require_measured=False):
    """Raise InvalidReport on a contradiction; successful return is not authentication."""
    _finite_tree(report)
    schema = json.loads(Path(__file__).with_name('report.schema.json').read_text(encoding='utf-8'))
    errors = json_schema.validate(report, schema)
    require(not errors, '#', '\n'.join(errors), 'correct the named field using report.schema.json')
    require(not require_measured or report['evidence_kind'] == 'measured', '#/evidence_kind',
            'validator_fixture is not measured evidence', 'supply a report from an actual measured run')
    for i, lock in enumerate(report['environment']['dependency_locks']):
        _safe_path(lock['path'], f'#/environment/dependency_locks/{i}/path')
    _unique(report['environment']['dependency_locks'], 'path', '#/environment/dependency_locks')
    _license(report['identity']['candidate']['license_evidence'], '#/identity/candidate/license_evidence')
    if report['identity']['model'] is not None:
        _license(report['identity']['model']['license_evidence'], '#/identity/model/license_evidence')
    config = report['measurement_config']
    zone, sampler = config['execution_zone'], config['sampler']
    sandbox = zone == 'subprocess_sandbox'
    if not sandbox:
        require(config['kill_grace_ms'] == 'not_applicable', '#/measurement_config/kill_grace_ms',
                'only sandbox can claim process termination grace', 'use not_applicable outside sandbox')
    if zone == 'in_process_reference':
        require(config['deadline_ms'] == 'not_applicable' and sampler == 'not_applicable',
                '#/measurement_config', 'direct execution cannot enforce per-Attempt resources',
                'use not_applicable for deadline and sampler in direct mode')
    if isinstance(sampler, dict):
        require(sampler['scope'] == ('process_tree' if sandbox else 'client'), '#/measurement_config/sampler/scope',
                'sampler scope differs from execution zone', 'record the sampler for this execution zone')
        gpu = sampler['gpu_attribution'] != 'not_applicable'
        require((sampler['gpu_evidence_sha256'] is not None) == gpu, '#/measurement_config/sampler',
                'GPU attribution and evidence disagree', 'supply a digest only for attributable/exclusive GPU sampling')
        require(not gpu or (sandbox and report['environment']['accelerator'] != 'none'),
                '#/measurement_config/sampler', 'GPU attribution lacks sandbox device context',
                'record the actual sandbox accelerator or mark GPU not_applicable')
    gates = _unique(report['gates']['resources'], 'metric', '#/gates/resources')
    for name, gate in gates.items():
        require(gate['unit'] == UNITS[name], '#/gates/resources/' + name,
                'resource gate unit mismatch', 'use ' + UNITS[name])
        _numeric(gate['maximum'], gate['unit'], '#/gates/resources/' + name + '/maximum')
    cases = _unique(report['cases'], 'fixture_id', '#/cases')
    expected_rejections = set()
    for i, case in enumerate(report['cases']):
        path = f'#/cases/{i}'
        require(case['case_kind'] != 'success' or case['input']['status'] == 'present', path + '/input',
                'success case has no input identity', 'supply the actual input digest and byte length')
        failures = _checks(case, report['identity']['candidate']['determinism'], path)
        metrics = _unique(case['measurements'], 'metric', path + '/measurements')
        for j, m in enumerate(case['measurements']):
            p = f'{path}/measurements/{j}'
            name = m['metric']
            require(m['execution_zone'] == zone, p, 'measurement crosses execution zones',
                    'retain measurements under their actual parent zone')
            require(m['unit'] == UNITS[name], p + '/unit', 'metric unit mismatch', 'use ' + UNITS[name])
            require((m['value'] is not None) == (m['status'] == 'measured'), p + '/value',
                    'measurement status and value disagree', 'use a numeric value only for measured status')
            if m['status'] == 'measured':
                _numeric(m['value'], m['unit'], p + '/value')
                if name in ('precision', 'recall', 'f1'):
                    require(m['value'] <= 1, p, 'quality ratio exceeds one', 'derive the ratio from counts')
            source = ('tool_scorer' if name in ('tp', 'fp', 'fn', 'precision', 'recall', 'f1') else
                      'external_sampler' if name in ('peak_process_tree_rss', 'gpu_peak_bytes') else 'harness')
            require(m['measurement_source'] == source, p + '/measurement_source',
                    'measurement does not have its authoritative source', 'use ' + source + ' evidence')
            if name in ('peak_process_tree_rss', 'gpu_peak_bytes'):
                if not sandbox:
                    expected = 'not_enforceable' if zone == 'in_process_reference' else 'not_applicable'
                    require(m['status'] == expected, p, 'resource claim is unavailable in this zone', 'use ' + expected + '/null')
                elif m['status'] == 'measured':
                    require(isinstance(sampler, dict), p, 'resource value lacks sampler evidence', 'record the actual sampler')
                    if name == 'gpu_peak_bytes':
                        require(sampler['gpu_attribution'] != 'not_applicable', p,
                                'GPU measurement is not attributable', 'supply attributable device evidence or not_applicable/null')
        _quality(metrics, path + '/measurements')
        for name, gate in gates.items():
            m = metrics.get(name)
            available = m is not None and m['status'] == 'measured' and zone != 'in_process_reference'
            if case['status'] == 'accepted' and gate['required']:
                require(available, path + '/measurements/' + name, 'required gate evidence is unavailable',
                        'supply authoritative measurement before accepting')
            if available and m['value'] > gate['maximum']:
                failures.add(RESOURCE_REASONS[name])
        if zone != 'in_process_reference' and type(config['deadline_ms']) is int:
            elapsed = metrics.get('elapsed')
            if elapsed and elapsed['status'] == 'measured' and elapsed['value'] > config['deadline_ms'] / 1000:
                failures.add('timeout')
        if case['status'] == 'accepted':
            require(zone != 'in_process_reference', path + '/status', 'direct mode is observation_only',
                    'record observation_only for passing direct-mode checks')
            require(type(config['deadline_ms']) is int, '#/measurement_config/deadline_ms',
                    'accepted case lacks a configured deadline', 'record the actual harness/client deadline')
            require('elapsed' in metrics and metrics['elapsed']['status'] == 'measured', path,
                    'accepted case lacks elapsed evidence', 'record harness elapsed time')
            if sandbox:
                require(isinstance(sampler, dict) and type(config['kill_grace_ms']) is int,
                        '#/measurement_config', 'sandbox acceptance lacks process-tree sampler or termination configuration',
                        'record actual sampler cadence and kill grace')
                require('peak_process_tree_rss' in metrics and metrics['peak_process_tree_rss']['status'] == 'measured',
                        path, 'sandbox acceptance lacks process-tree RSS', 'record externally sampled process-tree peak RSS')
        require(set(case['rejection_reasons']) == failures, path + '/rejection_reasons',
                'rejection reasons contradict checks or resource evidence', 'record exactly the failed check and exceeded gate reasons')
        require((case['status'] == 'rejected') == bool(failures), path + '/status',
                'case status contradicts rejection evidence', 'mark rejected exactly when rejection evidence exists')
        expected_rejections.update((case['fixture_id'], reason) for reason in failures)
    actual = [(r['fixture_id'], r['reason']) for r in report['rejections']]
    require(len(set(actual)) == len(actual) and set(actual) == expected_rejections, '#/rejections',
            'rejection ledger has dangling, duplicate or contradictory rows', 'mirror every case rejection exactly once')
    supplemental = report.get('supplemental_provider_reported', [])
    seen = set()
    for i, row in enumerate(supplemental):
        path = f'#/supplemental_provider_reported/{i}'
        key = row['fixture_id'], row['metric']
        require(row['fixture_id'] in cases and key not in seen, path,
                'supplemental row is dangling or duplicated', 'reference a case and retain one row per metric')
        seen.add(key)
        value = row['value']
        require(value is None or (type(value) is bool if row['metric'] == 'server_completed'
                                 else type(value) in (int, float)), path,
                'supplemental scalar has wrong type', 'use boolean for server_completed, numeric for resources, or null')
        if value is not None and row['metric'] in UNITS:
            _numeric(value, UNITS[row['metric']], path)


def comparison_key(report):
    """Return contextual comparability only; never rank or fill missing scores."""
    validate_report(report)
    context = {'fixtures': sorted((c['fixture_id'], c['manifest_sha256'], c['input'])
                                  for c in report['cases']),
               'gates': {**report['gates'], 'resources': sorted(report['gates']['resources'], key=lambda g: g['metric'])},
               'zone': report['measurement_config']['execution_zone'],
               'capability': report['identity']['capability']}
    return json.dumps(context, sort_keys=True, separators=(',', ':'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report')
    parser.add_argument('--require-measured', action='store_true')
    args = parser.parse_args(argv)
    try:
        validate_report(read_report(args.report), require_measured=args.require_measured)
    except (InvalidReport, RecursionError, json_schema.SchemaError) as exc:
        print(str(exc) if isinstance(exc, InvalidReport) else
              '#: why: validation depth or schema is unsupported; remedy: use the supported bounded report format', file=sys.stderr)
        return 1
    print('valid report (structure and consistency only; measurement provenance is not authenticated)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
