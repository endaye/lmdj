#!/usr/bin/env python3
"""Build the S1 candidate, double-execute S3 inputs, retain and validate evidence."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import generate_sample_slice_evaluation as generator
import validate_report as validator

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
CANDIDATE = '07044d2950c3ee6ff382468a536d6be87e5cd5d8'
ZONE = 'in_process_reference'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def file_identity(path):
    data = path.read_bytes()
    return dict(sha256=digest(data), byte_length=len(data))


def output(command, cwd=None):
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def run_logged(command, directory, name, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, capture_output=True)
    (directory / (name + '.stdout')).write_bytes(result.stdout)
    (directory / (name + '.stderr')).write_bytes(result.stderr)
    (directory / (name + '.command.json')).write_bytes(encoded(dict(
        argv=[str(a) for a in command], cwd=str(cwd), exit_code=result.returncode)))
    if result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}; retained logs in {directory}')
    return result.stdout


def predictions(manifest, manifest_sha, raw):
    """Consume retained bytes, never substitute expected onset labels."""
    if raw['manifest_sha256'] != manifest_sha or raw['parameters'] != {}:
        raise ValueError('manifest or parameter identity mismatch')
    scenarios = {s['id']: s for s in manifest['scenarios']}
    if [r['fixture_id'] for r in raw['cases']] != list(scenarios):
        raise ValueError('raw case inventory differs')
    cases = []
    for row in raw['cases']:
        if len(row['runs']) != 2:
            raise ValueError('two real executions required')
        scenario = scenarios[row['fixture_id']]
        for run in row['runs']:
            if not isinstance(run['elapsed_seconds'], (int, float)) or run['elapsed_seconds'] < 0:
                raise ValueError('invalid elapsed observation')
            if scenario['class'] == 'success':
                data = run['output_bytes'].encode()
                if digest(data) != run['output_sha256'] or len(data) != run['output_byte_length']:
                    raise ValueError('output byte identity mismatch')
                value = json.loads(data)
                if value['source_sha256'] != scenario['sha256'] or value['frame_rate'] != scenario['sample_rate']:
                    raise ValueError('output source identity mismatch')
                if run['frame_count'] != scenario['generation']['frame_count'] or run['sample_rate'] != scenario['sample_rate']:
                    raise ValueError('duration differs from source')
                run['real_time_factor'] = run['elapsed_seconds'] / (run['frame_count'] / run['sample_rate'])
        if scenario['class'] == 'success':
            value = json.loads(row['runs'][0]['output_bytes'])
            cases.append(dict(fixture_id=row['fixture_id'], source_sha256=scenario['sha256'],
                              frames=[p['frame'] for p in value['points']]))
    return dict(format='slice-frame-predictions', format_version=1, manifest_sha256=manifest_sha, cases=cases)


def measurement(metric, unit, value, source='harness', status=None):
    return dict(metric=metric, unit=unit, value=value, execution_zone=ZONE,
                measurement_source=source, status=status or ('not_applicable' if value is None else 'measured'))


def make_cases(manifest, manifest_sha, raw, scores):
    result = []
    by_id = {s['fixture_id']: s for s in scores['cases']}
    for scenario, row in zip(manifest['scenarios'], raw['cases'], strict=True):
        success = scenario['class'] == 'success'
        runs = row['runs']
        proof = digest(encoded(row))
        def check(verdict):
            return dict(status=verdict, evidence=[proof] if verdict in ('pass', 'fail') else [])
        checks = {key: check('pass' if success else 'not_applicable')
                  for key in ('output_schema', 'required_outputs')}
        equal = success and runs[0]['output_bytes'] == runs[1]['output_bytes']
        checks['determinism'] = dict(**check(('pass' if equal else 'fail') if success else 'not_applicable'),
                                    output_set_sha256=[r['output_sha256'] for r in runs] if success else [],
                                    parameters_sha256=[], seed_sha256=[])
        refused = not success and all(r.get('error_reason') == scenario['expected']['reason']
                                      and r['persisted_status'] == 'failed' for r in runs)
        checks['failed_input_refusal'] = check('not_applicable' if success else ('pass' if refused else 'fail'))
        reasons = (['determinism_violation'] if success and not equal else []) + (
            ['input_not_refused'] if not success and not refused else [])
        metrics = [measurement('elapsed', 'seconds', runs[0]['elapsed_seconds']),
                   measurement('real_time_factor', 'ratio', runs[0].get('real_time_factor'))]
        metrics += [measurement(name, 'bytes', None, 'external_sampler', 'not_enforceable')
                    for name in ('peak_process_tree_rss', 'gpu_peak_bytes')]
        if success:
            score = by_id[scenario['id']]
            metrics += [measurement(key, 'count' if key in ('tp', 'fp', 'fn') else 'ratio',
                                    score[key], 'tool_scorer')
                        for key in ('tp', 'fp', 'fn', 'precision', 'recall', 'f1')]
        result.append(dict(fixture_id=scenario['id'], manifest_sha256=manifest_sha,
                           input=dict(status='present', sha256=scenario['sha256'], byte_length=scenario['byte_length'])
                           if 'path' in scenario else dict(status='absent'),
                           case_kind=scenario['class'], status='rejected' if reasons else 'observation_only',
                           measurements=metrics, checks=checks, rejection_reasons=reasons))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source, destination = args.candidate_source.resolve(), args.output_dir.resolve()
    if output(['git', 'rev-parse', 'HEAD'], source) != CANDIDATE:
        raise ValueError('use the S1 fixed candidate checkout')
    if output(['git', 'status', '--porcelain', '--untracked-files=no'], source):
        raise ValueError('candidate tracked source is dirty')
    generator.generate(ROOT / generator.PREFIX, check=True)
    destination.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    base = output(['git', 'rev-parse', 'HEAD'], ROOT)
    harness_paths = [TOOL / name for name in ('CMakeLists.txt', 'run_sample_slice_evaluation.cpp',
        'run_sample_slice_evaluation.py', 'generate_sample_slice_evaluation.py', 'score_slice.py',
        'validate_report.py', 'report.schema.json')]
    harness_paths.append(ROOT / 'tests/conformance/json_schema.py')
    inputs = {str(p.relative_to(ROOT)): file_identity(p) for p in harness_paths}
    # Freeze both manifests and all materialized bytes BEFORE the first execute.
    manifests = [ROOT / 'tests/fixtures/provider-benchmark' / corpus / 'manifest.json'
                 for corpus in ('sample-slice', 'sample-slice-evaluation')]
    smoke_relative = manifests[0].relative_to(ROOT)
    if manifests[0].read_bytes() != (source / smoke_relative).read_bytes():
        raise ValueError('smoke manifest differs from S1 candidate')
    for path in manifests:
        inputs[str(path.relative_to(ROOT))] = file_identity(path)
        inputs[str((path.parent / 'LICENSE.md').relative_to(ROOT))] = file_identity(path.parent / 'LICENSE.md')
        for scenario in json.loads(path.read_bytes())['scenarios']:
            if 'path' in scenario:
                identity = file_identity(ROOT / scenario['path'])
                if identity != {key: scenario[key] for key in ('sha256', 'byte_length')}:
                    raise ValueError('fixture bytes differ from frozen manifest')
                inputs[scenario['path']] = identity
    (destination / 'frozen-inputs.json').write_bytes(encoded(inputs))
    build = destination / 'build'
    run_logged(['cmake', '-S', str(TOOL), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
                f'-DLMDJ_CANDIDATE_SOURCE={source}'], destination, 'configure')
    run_logged(['cmake', '--build', str(build), '--parallel', '4'], destination, 'build')
    executable = build / 'slice-evaluation'
    package_path = build / 'local-sample-slice/local.sample.slice.source-package.json'
    package = json.loads(package_path.read_bytes())
    for item in package['files']:
        if file_identity(source / item['path'])['sha256'] != item['sha256']:
            raise ValueError('candidate package differs from source')
    cpu = output(['sysctl', '-n', 'machdep.cpu.brand_string']) if sys.platform == 'darwin' else platform.processor() or platform.machine()
    memory = int(output(['sysctl', '-n', 'hw.memsize'])) if sys.platform == 'darwin' else os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    cache = (build / 'CMakeCache.txt').read_text()
    compiler = next(line.split('=', 1)[1] for line in cache.splitlines() if line.startswith('CMAKE_CXX_COMPILER:FILEPATH='))
    environment = dict(os=platform.system(), kernel=platform.release(), architecture=platform.machine(),
                       cpu=cpu, memory_bytes=memory, accelerator='none',
                       toolchain=[dict(name='Python', version=platform.python_version()),
                                  dict(name='CMake', version=output(['cmake', '--version']).splitlines()[0]),
                                  dict(name='C++', version=output([compiler, '--version']).splitlines()[0])],
                       dependency_locks=[dict(path='products/lmdj/assembly.lock.json',
                           sha256=file_identity(source / 'products/lmdj/assembly.lock.json')['sha256'])])
    contract_path = source / 'contracts/capability/sample.slice.v1.json'
    contract = json.loads(contract_path.read_bytes())
    identity = dict(bench_revision=base, harness_revision=base,
                    capability=dict(id=contract['capability_id'], contract_version=contract['contract_version'],
                                    document_sha256=file_identity(contract_path)['sha256']),
                    candidate=dict(publisher='endaye/lmdj', provider_id=package['provider_id'],
                                   version=package['provider_version'], source_revision=CANDIDATE,
                                   artifact_sha256=file_identity(package_path)['sha256'], determinism='deterministic',
                                   license_evidence=dict(url=f'https://github.com/endaye/lmdj/blob/{CANDIDATE}/LICENSE',
                                                         sha256=file_identity(source / 'LICENSE')['sha256'])), model=None)
    evidence = dict(started_utc=started, candidate_source_revision=CANDIDATE,
                    harness_base_revision=base, harness_identity_rule='base revision plus frozen source byte inventory',
                    frozen_inputs=inputs, executable=file_identity(executable), source_package=package,
                    parameters={}, effective_defaults=dict(threshold_pcm16=4096, refractory_frames=240),
                    timing_scope='steady_clock around AttemptStore.execute including verification and persistence; first run in report; both runs retained; no warmup',
                    groups=[])
    evidence['candidate_identities'] = {p: dict(**file_identity(source / p), value=json.loads((source / p).read_bytes()))
        for p in ('products/lmdj/version.json', 'products/lmdj/assembly.lock.json',
                  'packages/provider-sdk/module.json', 'providers/local-sample-slice/module.json',
                  'contracts/capability/sample.slice.v1.json')}
    for manifest_path in manifests:
        name = manifest_path.parent.name
        manifest = json.loads(manifest_path.read_bytes())
        manifest_sha = file_identity(manifest_path)['sha256']
        raw_bytes = run_logged([str(executable), str(ROOT), str(manifest_path), str(destination / (name + '-workspace')),
                                started], destination, name)
        raw = json.loads(raw_bytes)
        if any(raw[key] != identity['candidate'][key] for key in ('provider_id', 'version', 'artifact_sha256')):
            raise ValueError('executed provider differs from source package')
        predicted = predictions(manifest, manifest_sha, raw)
        prediction_file = destination / (name + '-predictions.json')
        prediction_file.write_bytes(encoded(predicted))
        score_bytes = run_logged([sys.executable, str(TOOL / 'score_slice.py'), '--manifest', str(manifest_path),
                                  '--predictions', str(prediction_file)], destination, name + '-score')
        scored = json.loads(score_bytes)
        cases = make_cases(manifest, manifest_sha, raw, scored)
        report = dict(format='provider-benchmark-report', format_version=1, evidence_kind='measured',
                      environment=environment, identity=identity,
                      measurement_config=dict(execution_zone=ZONE, sampler='not_applicable',
                                              deadline_ms='not_applicable', kill_grace_ms='not_applicable'),
                      gates=dict(policy_version='S1-observation-only-no-production-threshold', resources=[]),
                      cases=cases, rejections=[dict(fixture_id=c['fixture_id'], reason=reason)
                                              for c in cases for reason in c['rejection_reasons']])
        validator.validate_report(report, require_measured=True)
        report_file = destination / (name + '-report.json')
        report_file.write_bytes(encoded(report))
        run_logged([sys.executable, str(TOOL / 'validate_report.py'), str(report_file), '--require-measured'],
                   destination, name + '-validate')
        evidence['groups'].append(dict(manifest_path=str(manifest_path.relative_to(ROOT)), raw=raw,
                                      raw_stdout_sha256=digest(raw_bytes), predictions=predicted, scores=scored, report=report))
    if any(file_identity(ROOT / p) != identity for p, identity in inputs.items()):
        raise ValueError('frozen inputs changed during execution')
    if (output(['git', 'rev-parse', 'HEAD'], source) != CANDIDATE or
            output(['git', 'status', '--porcelain', '--untracked-files=no'], source)):
        raise ValueError('candidate changed during execution')
    evidence['commands'] = {p.name: json.loads(p.read_bytes()) for p in sorted(destination.glob('*.command.json'))}
    evidence['logs'] = {p.name: dict(**file_identity(p), text=p.read_text())
                        for suffix in ('*.stdout', '*.stderr') for p in sorted(destination.glob(suffix))}
    (destination / 'measured.json').write_bytes(encoded(evidence))
    print(json.dumps({g['manifest_path']: g['scores']['micro'] for g in evidence['groups']}, indent=2))
    return 1 if any(g['report']['rejections'] for g in evidence['groups']) else 0


if __name__ == '__main__':
    sys.exit(main())
