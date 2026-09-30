---
id: crashed-profile-relaunch-restores-tabs
area: creator
status: open
recurrences:
  - date: 2026-09-30
    occurrence: https://github.com/endaye/lmdj/issues/1691
    observed_by: claude-opus-5-5
exit: none
---

# A harness that SIGKILLs Chromium and relaunches it on the same profile gets the crashed tabs back, so the journey's "successor" page is really a second page.

## Why

`creator_web_perform.spec.mjs` models owner loss by killing the owner
Chromium's process group and relaunching the browser with the same
`--user-data-dir`. Chromium treats that as a crash and restores the previous
session. In 6 of 7 relaunches during #1691, the successor browser held
`["about:blank", ".../index.html", ".../index.html"]`: the restored pre-crash
tab, plus the page the journey opened with `newPage()`.

Before #1660 a restored Creator tab did not open a Project at boot, so the
extra page only interfered occasionally; #1699 met it independently and
closes restored pages before the successor opens its Project. Once boot
reopened the remembered Project, the restored tab took the Project's single
writer lease on most relaunches, and the journey's own page was correctly
refused `PROJECT_BUSY`.

#1691 was first filed as a per-pthread writer-lease defect in
`library_opfs_storage.js`. Lease events tagged with a per-realm id disproved
that: two realms, one holding the lease and one failing 117 times. Nothing in
the product was wrong.

## How to apply

- Before relaunching Chromium on a profile it was killed with, remove the
  session-restore state: `Default/Sessions`, plus the legacy
  `Current Session`, `Current Tabs`, `Last Session` and `Last Tabs` files.
  `discardRestorableSession` in `creator_web_perform.spec.mjs` does this, and
  it is the only harness that relaunches on a profile today. A new one must
  do the same. Closing restored pages after launch, as `openProjectSuccessor`
  also does since #1699, is not enough on its own once boot reopens the
  Project: a restored page can take the writer before it is closed, and the
  successor then waits on that lease's release.
- When a relaunched browser refuses ownership (`PROJECT_BUSY`, a busy lease,
  or a second capture owner), list its pages (`context.pages()`) before
  suspecting the product. A second page with the same origin is the first
  thing to rule out.

No mechanism exits this entry. The discard lives inside the one harness that
needs it, and nothing detects a future harness that relaunches without it.
