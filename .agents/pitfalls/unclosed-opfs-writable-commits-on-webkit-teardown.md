---
id: unclosed-opfs-writable-commits-on-webkit-teardown
area: web-host
status: open
recurrences:
  - date: 2026-09-20
    occurrence: https://github.com/endaye/lmdj/issues/1570
    observed_by: Claude Code (Fable 5.1)
exit: none
---

# An OPFS writable stream that is never closed is discarded by Chromium but committed by WebKit when its page is torn down, so "unclosed means invisible" is not a fact a cross-engine test may assert.

## Why

The File System Access specification gives `createWritable()` swap-file
semantics: bytes reach the target only on `close()`, and a stream that is
dropped without closing changes nothing. Chromium implements exactly that. In
WebKit, `FileSystemWritableFileStreamSink::~FileSystemWritableFileStreamSink`
calls `closeWritable(identifier, FileSystemWriteCloseReason::Completed)` when
script never closed the stream, and the network process then copies the
temporary file onto the target. Only a dropped IPC connection (the whole web
process going away) aborts. Closing one page while another same-origin page
keeps the process alive therefore commits every unclosed stream once its sink
is garbage-collected — at a time nothing in the test controls.

`project_io_web_conformance.spec.mjs` asserted that a publication interrupted
at `before_commit_close` — committed record written, stream not yet closed —
left the destination hidden from enumeration on both engines. On WebKit the
inspector page sometimes ran after the collection and saw a committed record
and a visible destination (#1570, batch run 35460937963). The product handles
both outcomes: a torn record reads as `pending` and recovery re-publishes, a
complete committed record is simply a finished publication. Only the test had
turned one engine's teardown behaviour into a protocol invariant, and nothing
in the product code says which engine does what.

## How to apply

When a browser test interrupts a write by closing the page, do not assert what
an unclosed `createWritable()` stream left behind; assert the relation the
protocol guarantees whatever the engine did — here, that enumeration agrees
with the intent record actually on disk and that recovery converges from
either state. Read the record through OPFS and derive the expected visibility
from it; keep the engine-independent points strict (`pending` before the
commit was buffered, `committed` after the close was observed) and widen only
the one boundary point. If the product ever needs an unclosed stream to stay
invisible until `close()`, it cannot rely on WebKit for that; use a sync
access handle plus an explicit marker, or `abort()` the stream on the
teardown path. A navigation that hangs in the same test is a different
defect; see
[`webkit-page-cycle-wedge-hangs-later-navigations`](webkit-page-cycle-wedge-hangs-later-navigations.md).
No deterministic gate fits: the behaviour lives in the browser engine, so
this stays open with `exit: none`.
