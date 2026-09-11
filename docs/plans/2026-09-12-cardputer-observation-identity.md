# Cardputer measured-content identity

Relates to #1104, #1107 and #1111. Internal prerequisite for observation
transport; no wire opcode or Contract decision is made here.

## Declared files

- `apps/cardputer-host/main/runtime_host.hpp`
- `apps/cardputer-host/main/runtime_host.cpp`
- `tests/platform/cardputer/audio_lifecycle_test.cpp`
- `tests/platform/cardputer/CMakeLists.txt`
- `apps/docs-site/docs/hosts/cardputer-host.mdx`
- This plan.

## Behavior

Capture complete content digest/length when Core admits a start, before the
audio task begins. Keep a boot-local monotonic observation generation, never a
RuntimeEpoch; refuse generation exhaustion instead of wrapping. New admitted
starts replace the previous record. Failed Core starts do not create a record.
While audio owns callback state, return unavailable and clear the caller's
output. Once joined, capture available audio diagnostics and explicit
start/quiescent/silent outcomes. Failed joins remain unavailable until retry
confirms quiescence. Keep the measured identity after stop/unload/load of new
content; never label an old observation with current Host content.

AudioSession's optional diagnostic query defaults to unavailable; that is not
zero samples. EspAudioSession supplies its existing finished-only implementation.
All observation operations belong to the serialized control owner. No new
render/ISR access or synchronization protocol is introduced.

The record currently binds content only. Full firmware/profile identity and a
cross-reset boot identity must be supplied by the later generated-identity and
wire integration; this local generation alone is not globally unique.

## Verification

Use real RuntimeHost/Facade content loading with a fake AudioSession. Assert
A start → stop → unload → B load retains A's full identity and diagnostic
values; starting B hides the old record, stopping B replaces it with B and a
new generation. Assert failed start plus failed join does not query diagnostics
or expose a record, then successful cleanup preserves the failed start outcome
and original identity. Native and ASan lifecycle/stress, EIM compile/link,
staged ownership and portal verification are required. Synthetic content and
fake audio are not music-capacity, physical silence or timing evidence.

Native and ASan/UBSan each pass 34/34 (33 component and existing audio stress),
exit 0: `/tmp/cardputer-observation-final-tests.log` and
`/tmp/cardputer-observation-final-asan-tests.log`. Unavailable diagnostics are
also tested with a backend that writes a value before returning false; the
Host must not publish it. The first native invocation selected five unbuilt
diagnostic tests (Not Run, exit 8, `/tmp/cardputer-observation-tests.log`);
the complete selected set was then built and rerun, without dropping tests.
Final EIM compile/link exits 0 (`/tmp/cardputer-observation-final-eim.log`).

## Version Management

Version impact: none — internal Host observation binding; no public wire,
Assembly or Build identity changes. Final candidate allocation remains pending.

## Documentation Impact

Documentation impact: required — `/hosts/cardputer-host/` explains measured
content binding and its remaining firmware/profile integration boundary.
