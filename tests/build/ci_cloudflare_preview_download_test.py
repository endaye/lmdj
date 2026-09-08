import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import cloudflare_preview_download as download
from cloudflare_preview_artifact import WORKFLOW


class FakeGitHub:
    def __init__(self):
        head = 'a' * 40
        repo = {'full_name': 'endaye/lmdj'}
        self.pr = {'number': 1, 'state': 'open', 'base': {'ref': 'main', 'repo': repo},
                   'head': {'sha': head, 'repo': repo}}
        self.run = {'id': 2, 'run_attempt': 1, 'repository': repo, 'head_repository': repo,
                    'path': WORKFLOW, 'event': 'pull_request', 'status': 'completed',
                    'conclusion': 'success', 'head_sha': head,
                    'pull_requests': [{'number': 1, 'head': {'sha': head}}]}
        self.artifact = {'id': 3, 'workflow_run': {'id': 2, 'head_sha': head},
                         'name': f'portal-preview-{head}-1', 'expired': False, 'size_in_bytes': 200}
        self.pr_reads = 0
        self.move_head = False
        self.url_reads = 0

    def metadata(self, path):
        if path.endswith('/pulls/1'):
            self.pr_reads += 1
            result = copy.deepcopy(self.pr)
            if self.move_head and self.pr_reads > 1:
                result['head']['sha'] = 'b' * 40
            return result
        return self.run if path.endswith('/runs/2') else self.artifact

    def archive_url(self, artifact_id):
        self.url_reads += 1
        return 'https://artifact.example/static?signature=private'


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'static.zip'
        self.github = FakeGitHub()
        self.name = 'static.zip'
        self.payload = b'inner archive bytes'
        self.requests = []

    def transport(self, request, timeout):
        self.requests.append(request)
        content = io.BytesIO()
        with ZipFile(content, 'w') as zipped:
            zipped.writestr(self.name, self.payload)
        content.seek(0)
        return content

    def run_download(self):
        return download.download_verified(self.github, 1, 2, 3, self.target, self.transport)

    def test_authenticated_selection_and_credential_free_storage_request(self):
        receipt = self.run_download()
        self.assertEqual(receipt['artifact_id'], 3)
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertEqual(self.requests[0].header_items(), [])
        self.assertEqual(self.github.pr_reads, 2)

    def test_head_update_during_download_does_not_expose_output(self):
        self.github.move_head = True
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.run_download()
        self.assertFalse(self.target.exists())

    def test_foreign_run_never_requests_download_url(self):
        self.github.artifact['workflow_run']['id'] = 4
        with self.assertRaisesRegex(ValueError, 'another run'):
            self.run_download()
        self.assertEqual(self.github.url_reads, 0)

    def test_transport_path_is_not_extracted(self):
        self.name = '../static.zip'
        with self.assertRaisesRegex(ValueError, 'exactly static.zip'):
            self.run_download()
        self.assertFalse(self.target.exists())

    def test_stream_limit_rejects_before_writing_excess(self):
        output = io.BytesIO()
        with self.assertRaisesRegex(ValueError, 'exceeds limit'):
            download.copy_bounded(io.BytesIO(b'12345'), output, 4)
        self.assertLessEqual(len(output.getvalue()), 4)

    def test_existing_output_is_preserved(self):
        self.target.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_download()
        self.assertEqual(self.target.read_bytes(), b'keep')


class GitHubBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.client = download.GitHub('test-token')

    def test_authenticated_api_request_and_foreign_path_guard(self):
        request = self.client.request('/repos/endaye/lmdj/actions/artifacts/3/zip')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
        with self.assertRaisesRegex(ValueError, 'foreign API path'):
            self.client.request('/repos/foreign/lmdj/actions/artifacts/3/zip')

    def test_redirect_handler_never_creates_forwarded_request(self):
        self.assertIsNone(download.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://storage.example'))

    def redirect(self, location, status=302):
        return HTTPError('https://api.github.com/example', status, 'redirect', {'Location': location}, io.BytesIO())

    def test_valid_signed_redirect_uses_no_redirect_opener(self):
        with patch.object(download, 'build_opener') as builder:
            builder.return_value.open.side_effect = self.redirect('https://storage.example/archive?signature=opaque')
            self.assertEqual(self.client.archive_url(3), 'https://storage.example/archive?signature=opaque')
            self.assertIs(builder.call_args.args[0], download.NoRedirect)
            request = builder.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')

    def test_success_without_signed_redirect_fails(self):
        with patch.object(download, 'build_opener') as builder:
            builder.return_value.open.return_value = io.BytesIO(b'not a redirect')
            with self.assertRaisesRegex(ValueError, 'did not redirect'):
                self.client.archive_url(3)

    def test_unsafe_signed_locations_fail(self):
        for location in ['http://storage.example/archive', 'https://user:secret@storage.example/archive', '']:
            with self.subTest(location=location), patch.object(download, 'build_opener') as builder:
                builder.return_value.open.side_effect = self.redirect(location)
                with self.assertRaisesRegex(ValueError, 'invalid artifact download URL'):
                    self.client.archive_url(3)

    def test_non_302_response_fails(self):
        with patch.object(download, 'build_opener') as builder:
            builder.return_value.open.side_effect = self.redirect('https://storage.example', 403)
            with self.assertRaisesRegex(ValueError, 'signed download'):
                self.client.archive_url(3)

    def test_metadata_limit_and_redirect_policy(self):
        with patch.object(download, 'build_opener') as builder:
            builder.return_value.open.return_value = io.BytesIO(b' ' * (4 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, 'metadata exceeds limit'):
                self.client.metadata('/repos/endaye/lmdj/pulls/1')
            self.assertIs(builder.call_args.args[0], download.NoRedirect)

    def test_metadata_redirect_is_not_followed(self):
        with patch.object(download, 'build_opener') as builder:
            builder.return_value.open.side_effect = self.redirect('https://storage.example')
            with self.assertRaises(HTTPError):
                self.client.metadata('/repos/endaye/lmdj/pulls/1')
            self.assertEqual(builder.return_value.open.call_count, 1)

    def test_missing_destination_parent_fails_before_api_calls(self):
        github = FakeGitHub()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'parent directory is missing.*remedy:'):
                download.download_verified(github, 1, 2, 3, Path(directory) / 'missing/static.zip')
        self.assertEqual(github.pr_reads, 0)


if __name__ == '__main__':
    unittest.main()
