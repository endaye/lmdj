---
id: playwright-byte-transfer-overhead
area: web-host
status: open
recurrences:
  - date: 2026-10-09
    occurrence: https://github.com/endaye/lmdj/pull/1936
    observed_by: Codex GPT-6
exit: none
---

# Expanding complete byte evidence into numeric arrays before Playwright transport spends the journey budget on serialization.

## Why

The complete Creator Slice journey failed at its original total deadline while
reopening the saved Project. A retained trace showed complete saved-file reads
spending 0.86–2.62 seconds across Playwright. Paired execution on the exact
fixture/distribution established the cost outside OPFS: all 10 file paths and
232,344 bytes were equal, with browser reads taking 18–48 ms, numeric-array
transport 834–922 ms, and typed-byte transport plus Node expansion 31–76 ms.
An input probe preserved the same 96,044-byte WAV digest and length while
reducing numeric-array transfer from 832–1,149 ms to typed transfer in 5–12 ms.

Playwright 1.62.1 has a direct typed-array serializer. Expanding bytes before
crossing that boundary instead represents every byte as a separate value. This
is distinct from per-sample matcher starvation: the original byte comparisons
were fast, and optimizing transport alone still left a total-budget failure
and an unrelated initial-import timeout. The measured cost is real; complete
journey acceptance and the remaining timing causes are separate evidence.

## How to apply

Profile the unchanged failure and separate file-read time, wire time and matcher
cost. Where byte serialization is material, retain Uint8Array across the locked
Playwright boundary and expand it after transport only when the existing
assertion shape requires it. Copy a Buffer's visible bytes explicitly instead
of passing its possibly larger backing allocation. Verify every original path
and byte, digest and length; retain deletion/restoration faults and all saved
Truth/reopen legs. Run the complete existing journey with its original limits.

No universal timing gate exists: costs depend on payload and environment.
Preserve paired identity/cost evidence, and keep later timeouts as unresolved
rather than increasing a deadline or replacing complete bytes with a weaker
summary to obtain a pass.
