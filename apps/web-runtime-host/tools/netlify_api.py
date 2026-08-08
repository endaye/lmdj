#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Mapping
from urllib import parse, request


@dataclass(frozen=True)
class DraftDeploy:
    id: str
    site_id: str
    deploy_ssl_url: str
    state: str


class NetlifyError(RuntimeError):
    pass


class NetlifyClient:
    _USER_AGENT = "LMDJ-Web-Runtime-Host/1"
    _POLL_INTERVAL_SECONDS = 0.1

    def __init__(self, *, token: str, api_base: str = "https://api.netlify.com/api/v1") -> None:
        if not token or "\n" in token or "\r" in token:
            raise NetlifyError("Netlify token is invalid")
        self._token = token
        self._api_base = api_base.rstrip("/")

    def create_draft(
        self,
        *,
        site_id: str,
        files: Mapping[str, bytes],
        title: str,
        deadline_seconds: float = 120.0,
    ) -> DraftDeploy:
        """Create a draft digest, upload required files, and wait for ready."""
        if not site_id or not title or deadline_seconds < 0:
            raise NetlifyError("Netlify draft deploy input is invalid")
        digests = self._file_digests(files)
        deadline = time.monotonic() + deadline_seconds
        site = self._path_segment(site_id)
        create = self._json_request(
            "POST",
            f"/sites/{site}/deploys?title={parse.quote(title, safe='')}",
            {"draft": True, "files": digests},
            deadline,
        )
        draft, required = self._parse_create_response(create, site_id)
        required_digests = set(required)
        selected: dict[str, tuple[str, bytes]] = {}
        for path in sorted(digests):
            digest = digests[path]
            if digest in required_digests and digest not in selected:
                selected[digest] = (path, files[path])
        if set(selected) != required_digests:
            raise NetlifyError("Netlify required file is unavailable")
        for digest in required:
            path, contents = selected[digest]
            self._request(
                "PUT",
                f"/deploys/{self._path_segment(draft.id)}/files/{self._upload_path(path)}",
                contents,
                "application/octet-stream",
                deadline,
            )
        return self._wait_for_ready(draft, deadline)

    def publish_deploy(self, *, site_id: str, deploy_id: str) -> dict[str, object]:
        """Restore exactly deploy_id and require the response to identify it as ready."""
        if not site_id or not deploy_id:
            raise NetlifyError("Netlify publish input is invalid")
        response = self._json_request(
            "POST",
            f"/sites/{self._path_segment(site_id)}/deploys/{self._path_segment(deploy_id)}/restore",
            {},
            None,
        )
        if not isinstance(response, dict) or not {"id", "site_id", "ssl_url", "state"}.issubset(response):
            raise NetlifyError("Netlify API response is invalid")
        if (
            response.get("id") != deploy_id
            or response.get("site_id") != site_id
            or response.get("state") != "ready"
            or not self._https_url(response.get("ssl_url"))
        ):
            raise NetlifyError("Netlify published deploy identity is invalid")
        return response

    def _file_digests(self, files: Mapping[str, bytes]) -> dict[str, str]:
        digests: dict[str, str] = {}
        for path, contents in files.items():
            self._upload_path(path)
            if not isinstance(contents, bytes):
                raise NetlifyError("Netlify draft file is invalid")
            digests[path] = hashlib.sha1(contents).hexdigest()
        if not digests:
            raise NetlifyError("Netlify draft files are invalid")
        return digests

    def _wait_for_ready(self, draft: DraftDeploy, deadline: float) -> DraftDeploy:
        current = draft
        while current.state not in {"ready", "error"}:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise NetlifyError("Netlify draft deploy timed out")
            time.sleep(min(self._POLL_INTERVAL_SECONDS, remaining))
            response = self._json_request(
                "GET", f"/deploys/{self._path_segment(current.id)}", None, deadline
            )
            current = self._parse_deploy_response(response, draft.site_id, draft.id)
        if current.state == "error":
            raise NetlifyError("Netlify draft deploy failed")
        return current

    def _parse_create_response(self, response: object, site_id: str) -> tuple[DraftDeploy, list[str]]:
        if not isinstance(response, dict) or not {
            "id", "site_id", "deploy_ssl_url", "state", "required"
        }.issubset(response):
            raise NetlifyError("Netlify API response is invalid")
        required = response.get("required")
        if not isinstance(required, list) or any(
            not isinstance(digest, str) or not self._sha1_digest(digest)
            for digest in required
        ) or len(set(required)) != len(required):
            raise NetlifyError("Netlify API response is invalid")
        deploy_response = {key: value for key, value in response.items() if key != "required"}
        return self._parse_deploy_response(deploy_response, site_id), required

    def _parse_deploy_response(
        self, response: object, site_id: str, deploy_id: str | None = None
    ) -> DraftDeploy:
        if not isinstance(response, dict) or not {
            "id", "site_id", "deploy_ssl_url", "state"
        }.issubset(response):
            raise NetlifyError("Netlify API response is invalid")
        identifier = response.get("id")
        response_site_id = response.get("site_id")
        deploy_ssl_url = response.get("deploy_ssl_url")
        state = response.get("state")
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(response_site_id, str)
            or response_site_id != site_id
            or deploy_id is not None and identifier != deploy_id
            or not self._https_url(deploy_ssl_url)
            or not isinstance(state, str)
            or not state
        ):
            raise NetlifyError("Netlify API response is invalid")
        return DraftDeploy(identifier, response_site_id, deploy_ssl_url, state)

    def _json_request(
        self,
        method: str,
        endpoint: str,
        document: object | None,
        deadline: float | None,
    ) -> object:
        data = None if document is None else json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        response = self._request(method, endpoint, data, "application/json", deadline)
        try:
            return json.loads(response)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NetlifyError("Netlify API response is invalid") from error

    def _request(
        self,
        method: str,
        endpoint: str,
        data: bytes | None,
        content_type: str,
        deadline: float | None,
    ) -> bytes:
        timeout = 120.0
        if deadline is not None:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise NetlifyError("Netlify draft deploy timed out")
        target = f"{self._api_base}{endpoint}"
        operation = request.Request(
            target,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": content_type,
                "User-Agent": self._USER_AGENT,
            },
        )
        failed = False
        try:
            with request.urlopen(operation, timeout=timeout) as response:
                return response.read()
        except OSError as error:
            try:
                error.close()
            except OSError:
                pass
            failed = True
        if failed:
            raise NetlifyError("Netlify API request failed")
        raise AssertionError("Netlify request did not return or fail")

    @staticmethod
    def _path_segment(value: str) -> str:
        if not isinstance(value, str) or not value:
            raise NetlifyError("Netlify deploy identity is invalid")
        return parse.quote(value, safe="")

    @classmethod
    def _upload_path(cls, path: str) -> str:
        if not isinstance(path, str) or not path.startswith("/"):
            raise NetlifyError("Netlify draft file path is invalid")
        segments = path[1:].split("/")
        if not segments or any(segment in {"", ".", ".."} for segment in segments):
            raise NetlifyError("Netlify draft file path is invalid")
        return "/".join(parse.quote(segment, safe="") for segment in segments)

    @staticmethod
    def _https_url(value: object) -> bool:
        if not isinstance(value, str):
            return False
        parsed = parse.urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password

    @staticmethod
    def _sha1_digest(value: str) -> bool:
        return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
