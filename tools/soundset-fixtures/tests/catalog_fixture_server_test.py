#!/usr/bin/env python3
"""The Catalog fixture server resolves `{object_kind, sha256}` and nothing else.

S11-D6 gives a Catalog transport exactly two logical reads. This test pins the
fixture server to that surface so a Host-side network `CatalogTransport` built
against it cannot quietly acquire an archive route, a directory listing, a
redirect, or a path-normalising open.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile

tool_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(tool_root))

from catalog_fixture_server import CatalogFixtureServer  # noqa: E402

repository_root = tool_root.parents[1]
corpus_root = repository_root / "tests" / "fixtures" / "soundset"

index_bytes = (corpus_root / "catalog" / "index.json").read_bytes()
index = json.loads(index_bytes)
manifest_sha256 = index["entries"][0]["manifest_sha256"]
manifest_bytes = (corpus_root / "manifest" / manifest_sha256).read_bytes()
blob_sha256 = json.loads(manifest_bytes)["slots"][0]["artifact"]["sha256"]
blob_bytes = (corpus_root / "blob" / blob_sha256).read_bytes()

absent_sha256 = "0" * 64


def fetch(server, target, method="GET"):
    """Send `target` byte-for-byte over a raw socket.

    `http.client` rewrites some targets (a leading `//` loses a slash), which
    would silently weaken the refusal cases below. A raw request line is the
    only way to prove the server itself refuses a shape.
    """
    host, port = server.address
    request = (
        f"{method} {target} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    with socket.create_connection((host, port), timeout=10) as connection:
        connection.sendall(request)
        received = b""
        while True:
            chunk = connection.recv(65_536)
            if not chunk:
                break
            received += chunk
    head, _, body = received.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split(" ", 2)[1])
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip()] = value.strip()
    return status, body, headers


refused_targets = [
    # No index page, no directory listing, no listing fallback.
    "/",
    "/index.html",
    "/catalog",
    "/catalog/",
    "/manifest/",
    "/blob/",
    "/object",
    "/object/",
    "/object/blob",
    "/object/blob/",
    "/object/manifest/",
    # The Catalog endpoint is one exact path, not a prefix.
    "/catalog/index.json/",
    "/catalog/index.json/extra",
    "/CATALOG/index.json",
    "/catalog/INDEX.JSON",
    # A digest must be exactly 64 lowercase hex characters.
    f"/object/blob/{blob_sha256.upper()}",
    f"/object/blob/{blob_sha256[:63]}",
    f"/object/blob/{blob_sha256}a",
    f"/object/blob/{absent_sha256}",
    "/object/blob/not-a-digest",
    # There is no third object kind, and in particular no archive.
    f"/object/archive/{blob_sha256}",
    f"/object/set/{manifest_sha256}",
    f"/object/blobs/{blob_sha256}",
    "/object/archive.tar",
    f"/object/blob/{blob_sha256}.zip",
    f"/soundset/{manifest_sha256}.zip",
    # An object kind never falls back or redirects to another kind.
    f"/object/blob/{manifest_sha256}",
    f"/object/manifest/{blob_sha256}",
    # No prefix-free shortcut to the store.
    f"/blob/{blob_sha256}",
    f"/manifest/{manifest_sha256}",
    f"/{blob_sha256}",
    # No suffix, query string or fragment is admitted.
    f"/object/blob/{blob_sha256}/",
    f"/object/blob/{blob_sha256}/extra",
    f"/object/blob/{blob_sha256}?download=1",
    f"/object/blob/{blob_sha256}#fragment",
    f"/object/blob/{blob_sha256};name=kick.wav",
    # No path traversal, encoded or raw. The target is matched literally.
    "/../catalog/index.json",
    "/object/blob/../../catalog/index.json",
    "/object/blob/..%2f..%2fcatalog%2findex.json",
    "/object/blob/%2e%2e%2fcatalog%2findex.json",
    "/object/../object/blob/" + blob_sha256,
    "//object/blob/" + blob_sha256,
    "/object//blob/" + blob_sha256,
    "/object/blob//" + blob_sha256,
]

refused_methods = ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"]

with CatalogFixtureServer(corpus_root) as server:
    # The three admitted shapes serve exact bytes.
    status, body, headers = fetch(server, "/catalog/index.json")
    assert status == 200, status
    assert body == index_bytes
    assert headers["Content-Type"] == "application/json", headers
    assert headers["Content-Length"] == str(len(index_bytes)), headers

    status, body, headers = fetch(server, f"/object/manifest/{manifest_sha256}")
    assert status == 200, status
    assert body == manifest_bytes
    assert hashlib.sha256(body).hexdigest() == manifest_sha256
    assert headers["Content-Type"] == "application/json", headers

    status, body, headers = fetch(server, f"/object/blob/{blob_sha256}")
    assert status == 200, status
    assert body == blob_bytes
    assert hashlib.sha256(body).hexdigest() == blob_sha256
    assert headers["Content-Type"] == "application/octet-stream", headers

    # HEAD reports the same length and no body.
    status, body, headers = fetch(
        server, f"/object/blob/{blob_sha256}", method="HEAD"
    )
    assert status == 200, status
    assert body == b""
    assert headers["Content-Length"] == str(len(blob_bytes)), headers

    # Every other request shape is a miss, never a redirect.
    for target in refused_targets:
        status, body, headers = fetch(server, target)
        assert status == 404, (
            f"why: the Catalog transport surface is exactly "
            f"/catalog/index.json plus /object/(manifest|blob)/<64 lowercase "
            f"hex> (S11-D6), and {target!r} answered {status} instead of 404, "
            f"so a Host transport built against this server could depend on a "
            f"shape Core never promised. remedy: keep resolution in "
            f"tools/soundset-fixtures/catalog_fixture_server.py matched "
            f"literally against OBJECT_REQUEST and CATALOG_INDEX_PATH over "
            f"the raw request line; do not widen the surface to admit "
            f"{target!r}."
        )
        assert body == b"", (
            f"why: {target!r} is a refused shape and must carry no body, but "
            f"it served {len(body)} bytes. remedy: answer refusals through "
            f"_send(404, b\"\", ...) in catalog_fixture_server.py."
        )
        assert "Location" not in headers, (
            f"why: {target!r} was answered with a redirect ({headers}), and "
            f"S11-D6 forbids a Catalog adapter redirecting one object kind to "
            f"another. remedy: remove the redirect from "
            f"catalog_fixture_server.py and answer 404."
        )

    # A Catalog object store is read-only.
    for method in refused_methods:
        status, body, headers = fetch(
            server, f"/object/blob/{blob_sha256}", method=method
        )
        assert status == 405, (
            f"why: a Catalog object store is read-only, so {method} must be "
            f"refused with 405, not answered {status}. remedy: keep {method} "
            f"bound to _reject_method in catalog_fixture_server.py."
        )
        assert body == b"", (
            f"why: refused method {method} served {len(body)} bytes. "
            f"remedy: answer it through _send(405, b\"\", ...)."
        )
        assert "Location" not in headers, (
            f"why: refused method {method} was redirected ({headers}). "
            f"remedy: answer 405 without a Location header."
        )

    # A well-formed digest whose basename is not a regular file is a miss.
    staging = Path(tempfile.mkdtemp(prefix="lmdj-soundset-fixture-"))
    try:
        (staging / "catalog").mkdir()
        (staging / "manifest").mkdir()
        (staging / "blob").mkdir()
        shutil.copyfile(
            corpus_root / "catalog" / "index.json",
            staging / "catalog" / "index.json",
        )
        shutil.copyfile(
            corpus_root / "manifest" / manifest_sha256,
            staging / "manifest" / manifest_sha256,
        )
        symlink_digest = "1" * 64
        directory_digest = "2" * 64
        fifo_digest = "3" * 64
        os.symlink(
            staging / "manifest" / manifest_sha256,
            staging / "blob" / symlink_digest,
        )
        (staging / "blob" / directory_digest).mkdir()
        os.mkfifo(staging / "blob" / fifo_digest)

        with CatalogFixtureServer(staging) as guarded:
            # Sanity: the copied manifest is reachable in the staging root.
            status, body, _ = fetch(
                guarded, f"/object/manifest/{manifest_sha256}"
            )
            assert status == 200 and body == manifest_bytes, status
            for digest, shape in (
                (symlink_digest, "symlink"),
                (directory_digest, "directory"),
                (fifo_digest, "fifo"),
            ):
                status, body, headers = fetch(guarded, f"/object/blob/{digest}")
                assert status == 404, (
                    f"why: S11-D6 requires a Catalog adapter to refuse a "
                    f"basename that is not a regular file, and this {shape} "
                    f"answered {status}. remedy: keep read_regular_file in "
                    f"catalog_fixture_server.py opening with O_NOFOLLOW plus "
                    f"O_NONBLOCK and rejecting anything fstat does not report "
                    f"as S_ISREG."
                )
                assert body == b"", (
                    f"why: the {shape} case served {len(body)} bytes. "
                    f"remedy: return None from read_regular_file for every "
                    f"non-regular basename."
                )
                assert "Location" not in headers, (
                    f"why: the {shape} case was redirected ({headers}). "
                    f"remedy: answer 404 without a Location header."
                )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

print("soundset catalog fixture server tests: PASS")
