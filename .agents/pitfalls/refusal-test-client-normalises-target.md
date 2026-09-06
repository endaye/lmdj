---
id: refusal-test-client-normalises-target
area: core
status: absorbed
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/issues/722
    observed_by: claude-code/opus-5
exit: gate:tools/soundset-fixtures/tests/catalog_fixture_server_test.py
---

# A refusal test proves nothing when the client or framework between it and the code under test rewrites the very input under test.

## Why

The Sound Set Catalog fixture server must resolve exactly `{object_kind,
sha256}`, so its test sends deliberately malformed targets and expects 404.
Two layers silently repaired those targets before the assertion could mean
anything.

`http.client.HTTPConnection.request()` rewrote `//object/blob/<sha>` into
`/object/blob/<sha>` on the wire, so the refusal case never reached the
server. Switching to a raw socket exposed the second layer:
`BaseHTTPRequestHandler.parse_request` collapses a leading `//` in the target
before it assigns `self.path`, so a handler that resolves `self.path` — the
obvious thing to write — accepts `//object/blob/<sha>` and serves the object.
The test had been passing on both counts, and the server really did admit a
shape it never declared.

This is the mirror image of [[fake-tool-stub-strictness]]. There the stub was
laxer than the real tool and certified invalid invocations; here the harness
was *cleaner* than the wire and certified a refusal that never happened. Both
turn a suite into a certifier of something other than the code under test, and
both surface only on a genuine end-to-end request.

The failure is structural, not specific to HTTP: it applies to any refusal
test whose input crosses a normalising client, parser, or framework — a URL
library that percent-decodes, a JSON client that reorders keys before a
canonical-bytes check, a shell helper that word-splits an argument, a
`Path` that collapses `..` before a traversal assertion.

## How to apply

When writing a test that asserts something is **refused**:

1. Send the malformed input by the lowest-level means available — a raw
   socket, `argv` directly, literal bytes — never a convenience client that
   may canonicalise it. State in a comment why the low-level path is required,
   or the next reader will "simplify" it back.
2. Resolve the input in production code from the rawest form the framework
   preserves (`self.requestline`, not `self.path`), so the framework's own
   normalisation cannot admit a shape the code never declared.
3. Prove the gate bites: break the production code back to the convenient
   form, watch the test fail, then restore it. A refusal test that has never
   failed has not been shown to test anything.
