"""Actual HTTP-boundary counts, not predictions from journal fixture sizes."""
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPMessage
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import self_test_report as reporting
import api_observation as observation


def response(status=200, headers=None, payload=b'{}'):
    answer = mock.MagicMock()
    answer.status = status
    answer.headers = HTTPMessage() if headers is None else headers
    answer.read.return_value = payload
    answer.__enter__.return_value = answer
    return answer


class ObservationTests(unittest.TestCase):
    def exercise(self, function, responses):
        output, opener = io.StringIO(), mock.Mock()
        opener.open.side_effect = responses
        with redirect_stdout(output), mock.patch.object(reporting.urllib.request, 'build_opener', return_value=opener):
            answer = observation.observe('report')(function)()
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        return answer, rows, opener

    def test_real_client_records_one_rest_and_graphql_without_private_inputs(self):
        import api_observation as observation
        output = io.StringIO()
        response = mock.MagicMock()
        response.status = 200
        response.headers = HTTPMessage()
        response.read.return_value = b'{}'
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret-token')
        with redirect_stdout(output), mock.patch.object(reporting.urllib.request, 'build_opener', return_value=opener):
            @observation.observe('entry')
            def run():
                api._request('GET', '/private?secret=hidden')
                api._request('POST', '/graphql', body={'secret': 'hidden'})
            run()
        result = json.loads(output.getvalue())
        self.assertEqual(result['requests'], {'rest': 1, 'graphql': 1, 'artifact': 0})
        self.assertEqual(result['responses']['2xx'], 2)
        self.assertEqual(result['phase'], 'final')
        for private in ('secret', 'hidden', '/private', 'Authorization'):
            self.assertNotIn(private, output.getvalue())
        self.assertEqual(opener.open.call_count, 2)

    def test_http_failure_and_transport_loss_keep_single_post_and_original_failure(self):
        for failure, group, transport in ((HTTPError('https://private', 403, 'secret', HTTPMessage(), None), '4xx', 0),
                                           (URLError('secret'), 'unavailable', 1)):
            with self.subTest(group=group):
                api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret')
                def call():
                    with self.assertRaises(reporting.GitHubApiError):
                        api.create_issue(title='private', body='private', labels=[], assignees=[])
                _, rows, opener = self.exercise(call, [failure])
                self.assertEqual(opener.open.call_count, 1, 'why: observation retried a POST; remedy: preserve single-attempt transport')
                self.assertEqual(rows[-1]['requests']['rest'], 1)
                self.assertEqual(rows[-1]['responses'][group], 1)
                self.assertEqual(rows[-1]['transport_errors'], transport)
                self.assertNotIn('secret', json.dumps(rows))

    def test_existing_retry_is_counted_per_real_attempt_without_new_retries(self):
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret')
        sleeps = []
        result, rows, opener = self.exercise(lambda: reporting.with_retry(
            lambda: api.get_run(1), sleep=sleeps.append, delays=(1, 2)),
            [HTTPError('https://private', 503, 'secret', HTTPMessage(), None), response()])
        self.assertEqual(result, {})
        self.assertEqual(sleeps, [1])
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(rows[-1]['responses']['5xx'], 1)
        self.assertEqual(rows[-1]['responses']['2xx'], 1)

    def test_artifact_redirect_is_counted_separately_and_keeps_token_off_download(self):
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret-token')
        headers = HTTPMessage()
        headers['Location'] = 'https://storage.invalid/private?signature=secret'
        headers['x-ratelimit-resource'] = 'core'
        headers['x-ratelimit-remaining'] = '99'
        third_party = HTTPMessage()
        third_party['x-ratelimit-resource'] = 'core'
        third_party['x-ratelimit-remaining'] = '0'
        result, rows, opener = self.exercise(lambda: api.download_artifact(1), [
            HTTPError('https://api.github.com/private', 302, 'Found', headers, None),
            response(headers=third_party, payload=b'archive')])
        self.assertEqual(result, b'archive')
        self.assertEqual(rows[-1]['requests'], {'rest': 1, 'graphql': 0, 'artifact': 1})
        self.assertEqual(rows[-1]['minimum_remaining'], {'core': 99})
        requests = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual(requests[0].get_header('Authorization'), 'Bearer secret-token')
        self.assertIsNone(requests[1].get_header('Authorization'))
        self.assertNotIn('signature', json.dumps(rows))

    def test_quota_headers_require_single_bounded_ascii_integer_and_known_resource(self):
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret')
        fixtures = []
        for resource, values in [('core', ['200']), ('core', ['150']), ('graphql', ['12']),
                                 ('search', ['7']), ('private', ['0']), ('core', ['1', '2']),
                                 ('core', [' 0']), ('core', ['-1']), ('core', ['１２']),
                                 ('core', ['9' * 13]), ('core', ['secret'])]:
            headers = HTTPMessage()
            headers['x-ratelimit-resource'] = resource
            for value in values:
                headers['x-ratelimit-remaining'] = value
            fixtures.append(response(headers=headers))
        count = len(fixtures)
        _, rows, _ = self.exercise(lambda: [api.get_run(1) for _ in range(count)], fixtures)
        self.assertEqual(rows[-1]['minimum_remaining'], {'core': 150, 'graphql': 12, 'search': 7})
        self.assertNotIn('private', json.dumps(rows))

    def test_parallel_clients_share_exact_counts_and_bounded_cumulative_checkpoints(self):
        def call():
            def worker(_):
                return reporting.UrllibGitHubApi('endaye/lmdj', 'secret').get_run(1)
            with ThreadPoolExecutor(max_workers=4) as pool:
                return list(pool.map(worker, range(205)))
        result, rows, _ = self.exercise(call, [response() for _ in range(205)])
        self.assertEqual(len(result), 205)
        self.assertEqual([row['completed'] for row in rows], [100, 200, 205])
        self.assertEqual([row['phase'] for row in rows], ['checkpoint', 'checkpoint', 'final'])
        self.assertEqual(rows[-1]['requests']['rest'], 205)
        self.assertEqual(rows[-1]['responses']['2xx'], 205)

    def test_logging_failure_does_not_change_successful_post_or_trigger_replay(self):
        class BrokenOutput:
            def write(self, _):
                raise OSError('private sink failure')
            def flush(self):
                raise OSError('private sink failure')
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret')
        opener = mock.Mock()
        opener.open.return_value = response(payload=b'{"number": 17}')
        with redirect_stdout(BrokenOutput()), mock.patch.object(reporting.urllib.request, 'build_opener', return_value=opener):
            result = observation.observe('report')(lambda: api.create_issue(title='t', body='b', labels=[], assignees=[]))()
        self.assertEqual(result, {'number': 17})
        self.assertEqual(opener.open.call_count, 1)
        self.assertIsNone(observation._active)

    def test_checkpoint_logging_failure_preserves_all_one_hundred_posts(self):
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret')
        opener = mock.Mock()
        opener.open.return_value = response(payload=b'{"number": 17}')
        with mock.patch.object(reporting.urllib.request, 'build_opener', return_value=opener), \
                mock.patch('builtins.print', side_effect=OSError('sink unavailable')) as emit:
            result = observation.observe('report')(lambda: [api.create_issue(
                title='t', body='b', labels=[], assignees=[]) for _ in range(100)])()
        self.assertEqual(result, [{'number': 17}] * 100)
        self.assertEqual(opener.open.call_count, 100)
        self.assertEqual(emit.call_count, 2)  # checkpoint and final, neither retried.
        self.assertIsNone(observation._active)

    def test_body_read_transport_failure_keeps_original_error_and_response_accounting(self):
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret')
        for error in (OSError('private read failure'), TimeoutError('private timeout')):
            with self.subTest(kind=type(error).__name__):
                answer = response()
                answer.read.side_effect = error
                def call():
                    with self.assertRaises(reporting.GitHubApiError) as caught:
                        api.get_run(1)
                    self.assertIs(caught.exception.__cause__, error)
                _, rows, opener = self.exercise(call, [answer])
                self.assertEqual(opener.open.call_count, 1)
                self.assertEqual(rows[-1]['responses']['2xx'], 1)
                self.assertEqual(rows[-1]['transport_errors'], 0)
                self.assertEqual(rows[-1]['completed'], 1)

    def test_application_failure_emits_final_without_changing_exception_or_next_invocation(self):
        output, opener = io.StringIO(), mock.Mock()
        opener.open.return_value = response(payload=b'not JSON')
        api = reporting.UrllibGitHubApi('endaye/lmdj', 'secret')
        run = observation.observe('report')(lambda: api.get_run(1))
        with redirect_stdout(output), mock.patch.object(reporting.urllib.request, 'build_opener', return_value=opener):
            for _ in range(2):
                with self.assertRaises(json.JSONDecodeError):
                    run()
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([row['requests']['rest'] for row in rows], [1, 1])
        self.assertEqual([row['responses']['2xx'] for row in rows], [1, 1])
        self.assertIsNone(observation._active)

    def test_zero_request_or_uninstrumented_client_has_no_observation(self):
        result, rows, _ = self.exercise(lambda: 42, [])
        self.assertEqual((result, rows), (42, []))
        output, opener = io.StringIO(), mock.Mock()
        opener.open.return_value = response()
        with redirect_stdout(output), mock.patch.object(reporting.urllib.request, 'build_opener', return_value=opener):
            reporting.UrllibGitHubApi('endaye/lmdj', 'secret').get_run(1)
        self.assertEqual(output.getvalue(), '')

    def test_actual_cli_error_paths_emit_bound_role_and_keep_failure_exit(self):
        import incremental_entry as entry
        import incremental_completion as relay
        import report_runtime as report
        import review_discovery_runtime as discovery
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.json'
            config.write_text('{}')
            cases = [
                ('entry', entry, 'Entry', ['control', '--root', directory, '--output', str(root / 'result.json')]),
                ('report', report, 'ReportRuntime', ['--config', str(config), '--root', directory, '--summary', str(root / 'report.md'), 'drain']),
                ('discovery', discovery, 'DiscoveryRuntime', ['--root', directory, '--summary', str(root / 'discovery.md')]),
                ('relay', relay.batch_runtime, 'Runtime', ['--output', str(root / 'receipt.json')]),
            ]
            for role, module, attribute, argv in cases:
                with self.subTest(role=role):
                    output, opener = io.StringIO(), mock.Mock()
                    opener.open.return_value = response()
                    def unavailable(*args, **kwargs):
                        reporting.UrllibGitHubApi('endaye/lmdj', 'secret').get_run(1)
                        raise OSError('fixture source unavailable')
                    cli = relay if role == 'relay' else module
                    with redirect_stdout(output), mock.patch.object(module, attribute, side_effect=unavailable), \
                            mock.patch.object(reporting.urllib.request, 'build_opener', return_value=opener), \
                            mock.patch.object(entry, 'load_storage', return_value={'scheduler': {}}):
                        self.assertEqual(cli.main(argv), 1)
                    rows = [json.loads(line) for line in output.getvalue().splitlines()
                            if line.startswith('{') and 'lmdj.ci-api-observation.v1' in line]
                    self.assertEqual(len(rows), 1, 'why: actual CLI is not observed; remedy: wrap the production main entry')
                    self.assertEqual(rows[0]['role'], role)
                    self.assertEqual(rows[0]['requests']['rest'], 1)
                    self.assertEqual(rows[0]['phase'], 'final')


if __name__ == '__main__':
    unittest.main()
