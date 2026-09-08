"""Credential-separated download boundary for the future Preview publisher."""
import json
from pathlib import Path
import stat
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from zipfile import ZipFile

from cloudflare_preview_artifact import MAX_ZIP_BYTES, REPOSITORY, require, validate_identity


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, path):
        require(path.startswith(f'/repos/{REPOSITORY}/'), 'foreign API path')
        return Request('https://api.github.com' + path, headers={
            'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })

    def metadata(self, path):
        with build_opener(NoRedirect).open(self.request(path), timeout=30) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        require(len(raw) <= 4 * 1024 * 1024, 'API metadata exceeds limit')
        return json.loads(raw)

    def archive_url(self, artifact_id):
        # Do not allow urllib to forward Authorization to artifact storage.
        try:
            with build_opener(NoRedirect).open(self.request(
                    f'/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip'), timeout=30):
                raise ValueError('why: artifact endpoint did not redirect; remedy: refresh the authenticated artifact receipt')
        except HTTPError as error:
            require(error.code == 302, 'artifact endpoint did not return a signed download')
            location = error.headers.get('Location', '')
        target = urlsplit(location)
        require(target.scheme == 'https' and bool(target.hostname) and
                not target.username and not target.password, 'invalid artifact download URL')
        return location


def copy_bounded(source, output, limit):
    count = 0
    while chunk := source.read(min(1024 * 1024, limit - count + 1)):
        count += len(chunk)
        require(count <= limit, 'artifact download exceeds limit')
        output.write(chunk)
    require(count > 0, 'artifact download is empty')
    return count


def download_verified(github, pr_number, run_id, artifact_id, destination, download=urlopen):
    """Use API-selected IDs, never an uploaded receipt or caller-provided URL.

    Destination must be new. The returned identity is a receipt at download
    time, not permission to publish without another current-head check.
    """
    require(all(type(value) is int and value > 0 for value in (pr_number, run_id, artifact_id)),
            'invalid GitHub object ID')
    destination = Path(destination)
    require(not destination.exists(), 'download target already exists')
    base = f'/repos/{REPOSITORY}'
    pr = github.metadata(f'{base}/pulls/{pr_number}')
    run = github.metadata(f'{base}/actions/runs/{run_id}')
    artifact = github.metadata(f'{base}/actions/artifacts/{artifact_id}')
    require(run['id'] == run_id and artifact['id'] == artifact_id and pr['number'] == pr_number,
            'API object ID mismatch')
    receipt = validate_identity(run, pr, artifact)
    signed_url = github.archive_url(artifact_id)
    with tempfile.TemporaryDirectory(prefix='preview-download-', dir=destination.parent) as temp:
        temp = Path(temp)
        transport = temp / 'transport.zip'
        # A fresh unauthenticated request is intentional: no GitHub or deploy
        # credential is forwarded to the signed artifact-storage URL.
        with download(Request(signed_url), timeout=30) as response, transport.open('xb') as output:
            copy_bounded(response, output, MAX_ZIP_BYTES)
        with ZipFile(transport) as archive:
            infos = archive.infolist()
            require(len(infos) == 1 and infos[0].filename == 'static.zip',
                    'artifact must contain exactly static.zip')
            info = infos[0]
            require(stat.S_IFMT(info.external_attr >> 16) in {0, stat.S_IFREG} and
                    not info.is_dir() and not info.flag_bits & 1, 'invalid static.zip transport member')
            require(0 < info.file_size <= MAX_ZIP_BYTES, 'inner ZIP exceeds limit')
            inner = temp / 'static.zip'
            with archive.open(info) as source, inner.open('xb') as output:
                size = copy_bounded(source, output, MAX_ZIP_BYTES)
            require(size == info.file_size, 'inner ZIP length mismatch')
        # Detect a head update during a slow download before exposing output.
        latest_pr = github.metadata(f'{base}/pulls/{pr_number}')
        validate_identity(run, latest_pr, artifact)
        created = False
        try:
            with destination.open('xb') as output, inner.open('rb') as source:
                created = True
                copy_bounded(source, output, MAX_ZIP_BYTES)
        except BaseException:
            if created:
                destination.unlink()
            raise
    return receipt
