"""Typed, secret-safe GitHub REST projections used by release tooling."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


class GitHubApiError(RuntimeError):
    """A GitHub release projection or request is unavailable or malformed."""


@dataclass(frozen=True)
class BranchProjection:
    name: str
    protected: bool
    commit_sha: str


@dataclass(frozen=True)
class RunProjection:
    id: int
    event: str
    head_sha: str
    head_branch: str
    workflow_name: str
    status: str
    conclusion: str | None


@dataclass(frozen=True)
class GitHubAsset:
    id: int
    name: str
    size: int
    api_url: str
    browser_download_url: str


@dataclass(frozen=True)
class GitHubRelease:
    id: int
    tag_name: str
    name: str
    body: str
    draft: bool
    prerelease: bool
    make_latest: bool | None
    html_url: str
    upload_url: str
    assets: tuple[GitHubAsset, ...]


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str], object]
HttpTransport = Callable[[str, str, Mapping[str, str], bytes | None], HttpResponse]


class GitHubClient:
    """Small typed REST client with exact mutation and complete pagination APIs."""

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        http_transport: HttpTransport | None = None,
        token: str | None = None,
        page_cap: int = 100,
    ) -> None:
        self._transport = transport or _get_json
        self._http_transport = http_transport or _http_request
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        if type(page_cap) is not int or page_cap <= 0:
            raise GitHubApiError("GitHub pagination page cap is invalid")
        self._page_cap = page_cap

    def get_branch(self, repository: str, branch: str) -> BranchProjection:
        document = self._get(f"/repos/{repository}/branches/{branch}")
        if not isinstance(document, dict):
            raise GitHubApiError("GitHub branch projection is invalid")
        commit = document.get("commit")
        name, protected = document.get("name"), document.get("protected")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        if not isinstance(name, str) or not isinstance(protected, bool) or not _sha(sha):
            raise GitHubApiError("GitHub branch projection is invalid")
        return BranchProjection(name, protected, sha)

    def list_runs_for_sha(self, repository: str, sha: str) -> list[RunProjection]:
        if not _sha(sha):
            raise GitHubApiError("GitHub run target is invalid")
        document = self._get(f"/repos/{repository}/actions/runs?{urlencode({'head_sha': sha, 'per_page': 100})}")
        runs = document.get("workflow_runs") if isinstance(document, dict) else None
        if not isinstance(runs, list):
            raise GitHubApiError("GitHub run projection is invalid")
        parsed: list[RunProjection] = []
        for run in runs:
            if not isinstance(run, dict):
                raise GitHubApiError("GitHub run projection is invalid")
            identifier, event, head_sha, head_branch, workflow_name, status, conclusion = (
                run.get("id"), run.get("event"), run.get("head_sha"), run.get("head_branch"),
                run.get("name"), run.get("status"), run.get("conclusion"),
            )
            if (
                not _positive_id(identifier) or not isinstance(event, str)
                or not _sha(head_sha) or not isinstance(head_branch, str)
                or not isinstance(workflow_name, str) or not isinstance(status, str)
                or (conclusion is not None and not isinstance(conclusion, str))
            ):
                raise GitHubApiError("GitHub run projection is invalid")
            parsed.append(RunProjection(
                identifier, event, head_sha, head_branch, workflow_name, status, conclusion,
            ))
        return parsed

    def get_release_by_tag(self, repository: str, tag: str) -> GitHubRelease | None:
        if not isinstance(tag, str) or not tag:
            raise GitHubApiError("GitHub release tag is invalid")
        response = self._request("GET", f"/repos/{repository}/releases/tags/{quote(tag, safe='')}")
        if response.status == 404:
            return None
        return _parse_release(_json_response(response, {200}))

    def get_release(self, repository: str, release_id: int) -> GitHubRelease | None:
        _require_id(release_id, "release")
        response = self._request("GET", f"/repos/{repository}/releases/{release_id}")
        if response.status == 404:
            return None
        return _parse_release(_json_response(response, {200}))

    def create_draft_release(
        self,
        repository: str,
        *,
        tag: str,
        name: str,
        body: str,
        prerelease: bool,
        make_latest: bool,
    ) -> GitHubRelease:
        if not all(isinstance(item, str) and item for item in (tag, name, body)):
            raise GitHubApiError("GitHub Draft metadata is invalid")
        if not isinstance(prerelease, bool) or not isinstance(make_latest, bool):
            raise GitHubApiError("GitHub Draft metadata is invalid")
        payload = json.dumps({
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": True,
            "prerelease": prerelease,
            "make_latest": "true" if make_latest else "false",
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        response = self._request(
            "POST", f"/repos/{repository}/releases", payload,
            content_type="application/json",
        )
        return _parse_release(_json_response(response, {201}))

    def list_release_assets(self, repository: str, release_id: int) -> list[GitHubAsset]:
        _require_id(release_id, "release")
        next_path: str | None = f"/repos/{repository}/releases/{release_id}/assets?per_page=100"
        visited: set[str] = set()
        assets: list[GitHubAsset] = []
        while next_path is not None:
            if next_path in visited or len(visited) >= self._page_cap:
                raise GitHubApiError("GitHub asset pagination is invalid")
            visited.add(next_path)
            response = self._request("GET", next_path)
            document = _json_response(response, {200})
            if not isinstance(document, list):
                raise GitHubApiError("GitHub asset projection is invalid")
            assets.extend(_parse_asset(item) for item in document)
            next_path = _next_link(response.headers, repository)
        identifiers = [asset.id for asset in assets]
        if len(identifiers) != len(set(identifiers)):
            raise GitHubApiError("GitHub asset pagination returned duplicate IDs")
        return assets

    def upload_release_asset(
        self, repository: str, upload_url: str, name: str, payload: bytes,
    ) -> GitHubAsset:
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise GitHubApiError("GitHub asset name is invalid")
        if not isinstance(payload, bytes):
            raise GitHubApiError("GitHub asset payload is invalid")
        base = upload_url.split("{", 1)[0]
        parsed = urlparse(base)
        expected = re.fullmatch(
            rf"/repos/{re.escape(repository)}/releases/[1-9][0-9]*/assets", parsed.path,
        )
        if parsed.scheme != "https" or parsed.netloc != "uploads.github.com" or expected is None or parsed.query:
            raise GitHubApiError("GitHub asset upload URL is invalid")
        url = f"{base}?name={quote(name, safe='')}"
        response = self._request("POST", url, payload, content_type="application/octet-stream")
        return _parse_asset(_json_response(response, {201}))

    def download_asset(self, asset: GitHubAsset) -> bytes:
        _require_id(asset.id, "asset")
        if not _api_url(asset.api_url):
            raise GitHubApiError("GitHub asset API URL is invalid")
        response = self._request(
            "GET", asset.api_url, accept="application/octet-stream",
        )
        if response.status != 200:
            raise GitHubApiError("GitHub asset download is unavailable")
        return response.body

    def delete_release(self, repository: str, release_id: int) -> None:
        _require_id(release_id, "release")
        response = self._request("DELETE", f"/repos/{repository}/releases/{release_id}")
        if response.status != 204:
            raise GitHubApiError("GitHub Draft deletion is unavailable")

    def _get(self, path: str) -> object:
        try:
            return self._transport(path)
        except GitHubApiError:
            raise
        except Exception:
            raise GitHubApiError("GitHub release preflight is unavailable") from None

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        *,
        accept: str = "application/vnd.github+json",
        content_type: str | None = None,
    ) -> HttpResponse:
        headers = {"Accept": accept, "User-Agent": "lmdj-release-pipeline"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if content_type is not None:
            headers["Content-Type"] = content_type
        try:
            response = self._http_transport(method, url, headers, body)
        except GitHubApiError:
            raise
        except Exception:
            raise GitHubApiError("GitHub release request is unavailable") from None
        if not isinstance(response, HttpResponse):
            raise GitHubApiError("GitHub release response is invalid")
        return response


def _get_json(path: str) -> object:
    response = _http_request(
        "GET", path,
        {"Accept": "application/vnd.github+json", "User-Agent": "lmdj-release-pipeline"},
        None,
    )
    return _json_response(response, {200})


def _http_request(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> HttpResponse:
    selected_url = f"https://api.github.com{url}" if url.startswith("/") else url
    request = Request(selected_url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return HttpResponse(response.status, dict(response.headers.items()), response.read())
    except HTTPError as error:
        try:
            payload = error.read()
        except OSError:
            payload = b""
        return HttpResponse(error.code, dict(error.headers.items()) if error.headers else {}, payload)
    except Exception:
        raise GitHubApiError("GitHub release request is unavailable") from None


def _json_response(response: HttpResponse, allowed: set[int]) -> object:
    if response.status not in allowed:
        raise GitHubApiError("GitHub release request was rejected")
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GitHubApiError("GitHub release response is invalid") from None


def _parse_release(document: object) -> GitHubRelease:
    if not isinstance(document, dict):
        raise GitHubApiError("GitHub Release projection is invalid")
    identifier = document.get("id")
    tag, name, body = document.get("tag_name"), document.get("name"), document.get("body")
    draft, prerelease = document.get("draft"), document.get("prerelease")
    html_url, upload_url, assets = document.get("html_url"), document.get("upload_url"), document.get("assets")
    if name is None:
        name = ""
    if body is None:
        body = ""
    if (
        not _positive_id(identifier) or not isinstance(tag, str) or not tag
        or not isinstance(name, str) or not isinstance(body, str)
        or not isinstance(draft, bool) or not isinstance(prerelease, bool)
        or not _github_url(html_url) or not _upload_url(upload_url) or not isinstance(assets, list)
    ):
        raise GitHubApiError("GitHub Release projection is invalid")
    latest_value = document.get("make_latest")
    if latest_value in (True, "true"):
        make_latest: bool | None = True
    elif latest_value in (False, "false"):
        make_latest = False
    elif latest_value is None:
        make_latest = None
    else:
        raise GitHubApiError("GitHub Release projection is invalid")
    return GitHubRelease(
        identifier, tag, name, body, draft, prerelease, make_latest, html_url, upload_url,
        tuple(_parse_asset(item) for item in assets),
    )


def _parse_asset(document: object) -> GitHubAsset:
    if not isinstance(document, dict):
        raise GitHubApiError("GitHub asset projection is invalid")
    identifier, name, size = document.get("id"), document.get("name"), document.get("size")
    api_url, download_url = document.get("url"), document.get("browser_download_url")
    if (
        not _positive_id(identifier) or not isinstance(name, str) or not name
        or "/" in name or "\\" in name or type(size) is not int or size < 0
        or not _api_url(api_url) or not _github_url(download_url)
    ):
        raise GitHubApiError("GitHub asset projection is invalid")
    return GitHubAsset(identifier, name, size, api_url, download_url)


def _next_link(headers: Mapping[str, str], repository: str) -> str | None:
    value = next((item for key, item in headers.items() if key.lower() == "link"), None)
    if value is None:
        return None
    next_urls: list[str] = []
    for item in value.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*', item)
        if match is None:
            raise GitHubApiError("GitHub asset pagination is invalid")
        if match.group(2) == "next":
            next_urls.append(match.group(1))
    if len(next_urls) > 1:
        raise GitHubApiError("GitHub asset pagination is invalid")
    if not next_urls:
        return None
    parsed = urlparse(next_urls[0])
    prefix = f"/repos/{repository}/releases/"
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or not parsed.path.startswith(prefix):
        raise GitHubApiError("GitHub asset pagination is invalid")
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _require_id(value: object, subject: str) -> None:
    if not _positive_id(value):
        raise GitHubApiError(f"GitHub {subject} ID must be numeric")


def _positive_id(value: object) -> bool:
    return type(value) is int and value > 0


def _api_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://api.github.com/")


def _github_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://github.com/")


def _upload_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://uploads.github.com/")


def _sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)
