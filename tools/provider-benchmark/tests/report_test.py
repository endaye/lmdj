#!/usr/bin/env python3
"""B1 boundary tests: one qualification defect per mutation."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('benchmark_report', TOOL / 'validate_report.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
VALID = TOOL / 'tests/fixtures/report-valid.json'
H = '3' * 64


def fixture(zone='subprocess_sandbox'):
    r = v.read_report(VALID)
    if zone != 'subprocess_sandbox':
        r['measurement_config'].update(execution_zone=zone, sampler='not_applicable', kill_grace_ms='not_applicable')
        r['gates']['resources'] = r['gates']['resources'][:1]
        for m in r['cases'][0]['measurements']:
            m['execution_zone'] = zone
            if m['metric'] == 'peak_process_tree_rss':
                m.update(value=None, status='not_enforceable' if zone == 'in_process_reference' else 'not_applicable')
        if zone == 'in_process_reference':
            r['measurement_config']['deadline_ms'] = 'not_applicable'
            r['cases'][0]['status'] = 'observation_only'
    return r


def set_at(report, path, value):
    keys = path.split('/')
    node = report
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    key = int(keys[-1]) if isinstance(node, list) else keys[-1]
    node[key] = value


def rejected(r, reason):
    r['cases'][0].update(status='rejected', rejection_reasons=[reason])
    r['rejections'] = [{'fixture_id': r['cases'][0]['fixture_id'], 'reason': reason}]


class ReportTests(unittest.TestCase):
    def invalid(self, r, why):
        with self.assertRaisesRegex(v.InvalidReport, why) as caught:
            v.validate_report(r)
        self.assertIn('remedy:', str(caught.exception))

    def test_sandbox_at_inclusive_limits(self):
        v.validate_report(fixture())

    def test_direct_observations(self):
        v.validate_report(fixture('in_process_reference'))

    def test_remote_client_evidence(self):
        v.validate_report(fixture('remote'))

    def test_fixture_cannot_be_measured(self):
        with self.assertRaisesRegex(v.InvalidReport, 'validator_fixture is not measured'):
            v.validate_report(fixture(), require_measured=True)

    def test_measured_marker_does_not_authenticate_provenance(self):
        r = fixture()
        r['evidence_kind'] = 'measured'
        v.validate_report(r, require_measured=True)

    def test_duplicate_case(self):
        r = fixture(); r['cases'].append(copy.deepcopy(r['cases'][0]))
        self.invalid(r, 'duplicate fixture_id')

    def test_duplicate_metric(self):
        r = fixture(); r['cases'][0]['measurements'].append(copy.deepcopy(r['cases'][0]['measurements'][0]))
        self.invalid(r, 'duplicate metric')

    def test_unknown_secret_extension(self):
        r = fixture(); r['identity']['candidate']['api_token'] = 'not-a-real-secret'
        self.invalid(r, "property 'api_token' is not allowed")

    def test_missing_candidate_revision(self):
        r = fixture(); del r['identity']['candidate']['source_revision']
        self.invalid(r, "missing required property 'source_revision'")

    def test_rss_limit_plus_one_rejects(self):
        r = fixture(); r['cases'][0]['measurements'][1]['value'] += 1
        rejected(r, 'memory_limit'); v.validate_report(r)

    def test_elapsed_limit_exceeded_rejects(self):
        r = fixture(); r['cases'][0]['measurements'][0]['value'] = 1.001
        rejected(r, 'timeout'); v.validate_report(r)

    def test_optional_gate_exceedance_is_still_a_rejection(self):
        r = fixture(); r['gates']['resources'][1]['required'] = False
        r['cases'][0]['measurements'][1]['value'] += 1
        self.invalid(r, 'rejection reasons contradict')

    def test_required_gate_absent(self):
        r = fixture(); r['gates']['resources'].append({'metric':'gpu_peak_bytes','unit':'bytes','maximum':1,'required':True})
        self.invalid(r, 'required gate evidence is unavailable')

    def test_optional_gpu_unavailable(self):
        r = fixture(); r['gates']['resources'].append({'metric':'gpu_peak_bytes','unit':'bytes','maximum':1,'required':False})
        v.validate_report(r)

    def test_rejected_partial_outputs(self):
        r = fixture(); r['cases'][0]['checks']['required_outputs']['status'] = 'fail'
        rejected(r, 'required_output_missing'); v.validate_report(r)

    def test_partial_outputs_mislabeled_accepted(self):
        self.invalid(v.read_report(TOOL / 'tests/fixtures/report-invalid.json'), 'qualification requires a passing check')

    def test_repeatability_failed_digests(self):
        r = fixture(); d = r['cases'][0]['checks']['determinism']
        d['status'] = 'fail'; d['output_set_sha256'][1] = H
        rejected(r, 'determinism_violation'); v.validate_report(r)

    def test_seeded_repeatability(self):
        r = fixture(); r['identity']['candidate']['determinism'] = 'seeded'
        d = r['cases'][0]['checks']['determinism']; d.update(seed_sha256=[H,H],parameters_sha256=[H,H])
        v.validate_report(r)

    def test_seeded_context_mismatch(self):
        r = fixture(); r['identity']['candidate']['determinism'] = 'seeded'
        d = r['cases'][0]['checks']['determinism']; d.update(seed_sha256=[H,'4'*64],parameters_sha256=[H,H])
        self.invalid(r, 'different context')

    def test_nondeterministic_explicit_na(self):
        r = fixture(); r['identity']['candidate']['determinism'] = 'nondeterministic'
        r['cases'][0]['checks']['determinism'].update(status='not_applicable',evidence=[],output_set_sha256=[])
        v.validate_report(r)

    def test_failed_input_refusal(self):
        r = fixture(); c = r['cases'][0]; c.update(case_kind='input_failure',input={'status':'absent'})
        for name, check in c['checks'].items():
            check.update(status='pass' if name == 'failed_input_refusal' else 'not_applicable',
                         evidence=[H] if name == 'failed_input_refusal' else [])
        c['checks']['determinism']['output_set_sha256'] = []
        v.validate_report(r)

    def test_failed_input_not_refused(self):
        r = fixture(); c = r['cases'][0]; c.update(case_kind='input_failure',input={'status':'absent'})
        for name, check in c['checks'].items():
            check.update(status='fail' if name == 'failed_input_refusal' else 'not_applicable',
                         evidence=[H] if name == 'failed_input_refusal' else [])
        c['checks']['determinism']['output_set_sha256'] = []
        rejected(r, 'input_not_refused'); v.validate_report(r)

    def test_provider_self_report_cannot_fill_missing_gate(self):
        r = fixture(); r['cases'][0]['measurements'][0].update(status='missing',value=None)
        r['supplemental_provider_reported']=[{'fixture_id':'synthetic-success','metric':'elapsed','measurement_source':'provider_reported','value':0}]
        self.invalid(r, 'required gate evidence is unavailable')

    def test_provider_self_report_does_not_override_measured(self):
        r = fixture(); r['supplemental_provider_reported']=[{'fixture_id':'synthetic-success','metric':'elapsed','measurement_source':'provider_reported','value':99}]
        v.validate_report(r)

    def test_gpu_with_attribution(self):
        r = fixture(); r['environment']['accelerator']={'device':'fixture','driver':'fixture'}
        r['measurement_config']['sampler'].update(gpu_attribution='exclusive',gpu_evidence_sha256=H)
        r['cases'][0]['measurements'].append({'metric':'gpu_peak_bytes','unit':'bytes','value':1,'status':'measured','execution_zone':'subprocess_sandbox','measurement_source':'external_sampler'})
        r['gates']['resources'].append({'metric':'gpu_peak_bytes','unit':'bytes','maximum':1,'required':True})
        v.validate_report(r)

    def test_gpu_without_attribution(self):
        r = fixture(); r['cases'][0]['measurements'].append({'metric':'gpu_peak_bytes','unit':'bytes','value':1,'status':'measured','execution_zone':'subprocess_sandbox','measurement_source':'external_sampler'})
        self.invalid(r, 'GPU measurement is not attributable')

    def test_dangling_rejection(self):
        r = fixture(); r['rejections']=[{'fixture_id':'missing','reason':'timeout'}]
        self.invalid(r, 'rejection ledger')

    def test_direct_cannot_fabricate_timeout(self):
        r = fixture('in_process_reference'); r['cases'][0]['measurements'][0]['value']=100
        rejected(r, 'timeout'); self.invalid(r, 'rejection reasons contradict')

    def test_direct_cannot_be_accepted(self):
        r = fixture('in_process_reference'); r['cases'][0]['status']='accepted'
        r['gates']['resources']=[]
        self.invalid(r, 'direct mode is observation_only')

    def test_remote_cannot_measure_provider_rss(self):
        r = fixture('remote'); r['cases'][0]['measurements'][1].update(status='measured',value=1)
        self.invalid(r, 'resource claim is unavailable in this zone')

    def test_remote_cannot_claim_kill_grace(self):
        r = fixture('remote'); r['measurement_config']['kill_grace_ms']=0
        self.invalid(r, 'only sandbox can claim process termination')

    def test_gpu_limit_plus_one(self):
        r = fixture(); r['environment']['accelerator']={'device':'fixture','driver':'fixture'}
        r['measurement_config']['sampler'].update(gpu_attribution='attributable',gpu_evidence_sha256=H)
        r['cases'][0]['measurements'].append({'metric':'gpu_peak_bytes','unit':'bytes','value':2,'status':'measured','execution_zone':'subprocess_sandbox','measurement_source':'external_sampler'})
        r['gates']['resources'].append({'metric':'gpu_peak_bytes','unit':'bytes','maximum':1,'required':True})
        rejected(r,'gpu_limit'); v.validate_report(r)

    def test_rtf_is_not_bounded_by_one(self):
        r = fixture(); r['cases'][0]['measurements'].append({'metric':'real_time_factor','unit':'ratio','value':10,'status':'measured','execution_zone':'subprocess_sandbox','measurement_source':'harness'})
        v.validate_report(r)

    def test_quality_undefined_ratios(self):
        r = quality_fixture(0,0,0); v.validate_report(r)

    def test_quality_defined_ratios(self):
        r = quality_fixture(2,1,3); v.validate_report(r)

    def test_quality_null_is_not_perfect(self):
        r = quality_fixture(0,0,0); r['cases'][0]['measurements'][-1].update(status='measured',value=1)
        self.invalid(r, 'ratio contradicts')

    def test_quality_display_mismatch(self):
        r = quality_fixture(2,1,3); r['cases'][0]['measurements'][-1]['value']=0.9
        self.invalid(r, 'ratio contradicts')

    def test_comparison_ignores_object_order(self):
        a = fixture(); b = copy.deepcopy(a); b['gates']['resources'].reverse()
        self.assertEqual(v.comparison_key(a),v.comparison_key(b))

    def test_comparison_separates_zone(self):
        self.assertNotEqual(v.comparison_key(fixture()),v.comparison_key(fixture('remote')))

    def test_comparison_separates_manifest(self):
        a = fixture(); b = fixture(); b['cases'][0]['manifest_sha256']=H
        self.assertNotEqual(v.comparison_key(a),v.comparison_key(b))

    def test_comparison_separates_policy(self):
        a = fixture(); b = fixture(); b['gates']['policy_version']='different'
        self.assertNotEqual(v.comparison_key(a),v.comparison_key(b))


def quality_fixture(tp,fp,fn):
    r=fixture()
    rows=[('tp',tp),('fp',fp),('fn',fn)]
    for name,num,den in [('precision',tp,tp+fp),('recall',tp,tp+fn),('f1',2*tp,2*tp+fp+fn)]:
        rows.append((name,None if den==0 else num/den))
    for name,value in rows:
        r['cases'][0]['measurements'].append({'metric':name,'unit':'count' if name in ('tp','fp','fn') else 'ratio',
          'value':value,'status':'not_applicable' if value is None else 'measured',
          'execution_zone':'subprocess_sandbox','measurement_source':'tool_scorer'})
    return r


# Each generated test changes one fact and names that defect independently.
MUTATIONS = [
 ('digest_trailing_newline','identity/capability/document_sha256','1'*64+'\n','control character'),
 ('wrong_revision','identity/bench_revision','main','does not match pattern'),
 ('uppercase_digest','identity/capability/document_sha256','A'*64,'does not match pattern'),
 ('bool_format_version','format_version',True,'expected type integer'),
 ('wrong_unit','cases/0/measurements/0/unit','bytes','metric unit mismatch'),
 ('measured_null','cases/0/measurements/0/value',None,'status and value disagree'),
 ('unmeasured_number','cases/0/measurements/0/status','missing','status and value disagree'),
 ('infinite_value','cases/0/measurements/0/value',float('inf'),'non-finite'),
 ('nan_value','cases/0/measurements/0/value',float('nan'),'non-finite'),
 ('negative_elapsed','cases/0/measurements/0/value',-1,'below minimum'),
 ('fractional_bytes','cases/0/measurements/1/value',1.5,'safe integers'),
 ('unsafe_bytes','cases/0/measurements/1/value',2**53,'safe integers'),
 ('self_report_primary','cases/0/measurements/0/measurement_source','provider_reported','allowed options'),
 ('wrong_authority','cases/0/measurements/0/measurement_source','external_sampler','authoritative source'),
 ('cross_zone','cases/0/measurements/0/execution_zone','remote','crosses execution zones'),
 ('missing_deadline','measurement_config/deadline_ms','not_applicable','lacks a configured deadline'),
 ('zero_cadence','measurement_config/sampler/cadence_ms',0,'oneOf'),
 ('wrong_sampler_scope','measurement_config/sampler/scope','client','scope differs'),
 ('missing_sampler','measurement_config/sampler','not_applicable','lacks sampler evidence'),
 ('absolute_path','environment/dependency_locks/0/path','/tmp/lock','repository-relative'),
 ('traversal_path','environment/dependency_locks/0/path','a/../lock','repository-relative'),
 ('windows_path','environment/dependency_locks/0/path','C:\\lock','repository-relative'),
 ('cache_path','environment/dependency_locks/0/path','.cache/lock','repository-relative'),
 ('citation_credentials','identity/candidate/license_evidence/url','https://user:secret@example.invalid/license','credential-free'),
 ('citation_query','identity/candidate/license_evidence/url','https://example.invalid/license?token=secret','credential-free'),
 ('citation_http','identity/candidate/license_evidence/url','http://example.invalid/license','credential-free'),
 ('surrogate','environment/cpu','\ud800','Unicode surrogate'),
 ('missing_check_evidence','cases/0/checks/output_schema/evidence',[],'lacks evidence'),
 ('skipped_required_check','cases/0/checks/output_schema/status','not_applicable','required check'),
 ('repeatability_false_pass','cases/0/checks/determinism/output_set_sha256/1',H,'contradicts output digests'),
 ('success_absent_input','cases/0/input',{'status':'absent'},'no input identity'),
]
for name,path,value,why in MUTATIONS:
    def test(self,path=path,value=value,why=why):
        r=fixture(); set_at(r,path,value); self.invalid(r,why)
    setattr(ReportTests,'test_'+name,test)


class CliTests(unittest.TestCase):
    def run_cli(self,path,*args):
        return subprocess.run([sys.executable,str(TOOL/'validate_report.py'),str(path),*args],
                              capture_output=True,text=True,timeout=10)

    def assert_failure(self,result,why):
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn(why,result.stderr)
        self.assertIn('remedy:',result.stderr)
        self.assertEqual(result.stdout,'')

    def test_valid_cli(self):
        result=self.run_cli(VALID); self.assertEqual(result.returncode,0,result.stderr)

    def test_invalid_fixture_cli(self):
        self.assert_failure(self.run_cli(TOOL/'tests/fixtures/report-invalid.json'),'qualification requires a passing check')

    def test_missing_file_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assert_failure(self.run_cli(Path(temp)/'missing.json'),'cannot read bounded UTF-8 JSON')

    def test_require_measured_cli(self):
        self.assert_failure(self.run_cli(VALID,'--require-measured'),'validator_fixture is not measured')

    def check_bytes(self,data,why):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'report.json'; path.write_bytes(data)
            self.assert_failure(self.run_cli(path),why)
            self.assertEqual(path.read_bytes(),data,'validator must not modify its input')
            self.assertEqual(list(Path(temp).iterdir()),[path],'validator must not write artifacts')

    def test_duplicate_json_key(self):
        self.check_bytes(b'{"format":1,"format":2}','duplicate JSON key')

    def test_nan_json(self):
        self.check_bytes(b'{"value":NaN}','non-finite JSON number')

    def test_overflow_json(self):
        self.check_bytes(b'{"value":1e999}','non-finite number')

    def test_bad_utf8(self):
        self.check_bytes(b'\xff','cannot read bounded UTF-8 JSON')

    def test_oversize_before_parse(self):
        self.check_bytes(b'x'*(v.MAX_BYTES+1),'report exceeds 8 MiB')

    def test_malformed_json(self):
        self.check_bytes(b'{','cannot read bounded UTF-8 JSON')

    def test_excessive_nesting(self):
        self.check_bytes(b'['*200+b']'*200,'report nesting exceeds 128 levels')


if __name__=='__main__':
    unittest.main()
