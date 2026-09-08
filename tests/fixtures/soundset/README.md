# Sound Set Catalog fixture corpus

A local, offline `lmdj.soundset-catalog.v1` Catalog for Stage 11. It exists so
[Task 4](../../../docs/plans/2026-09-06-lmdj-stage11-sound-set.md),
Task 5 and Task 7 can drive inspect, preview and install against real bytes —
canonical manifests, real PCM16 WAV blobs, a real hash mismatch — without a
network and without a Marketplace.

Authority is
[`2026-09-06-lmdj-stage11-sound-set.md`](../../../docs/plans/2026-09-06-lmdj-stage11-sound-set.md)
(Locked Constants, Locked Error Reasons) and
[`2026-08-31-lmdj-stage11-sound-set-design.md`](../../../docs/design/2026-08-31-lmdj-stage11-sound-set-design.md)
(S11-D1, S11-D2, S11-D6, S11-D7, S8-D6). This directory invents no manifest
semantics of its own; a disagreement with those documents is a bug here, or a
design conflict to raise on the Issue — never a local reinterpretation.

## Layout

```text
catalog/index.json   the lmdj.soundset-catalog.v1 index (the Catalog endpoint)
manifest/<sha256>    canonical lmdj.soundset.v1 manifest objects
blob/<sha256>        PCM16 WAV Artifact blobs
```

`{object_kind, sha256}` names exactly one basename under exactly one
directory, which is the whole of the S11-D6 transport surface: one canonical
manifest read and one content-addressed blob read. There is no archive, and
nothing here needs unpacking.

Every manifest object is byte-for-byte
`foundation::canonical_json(parsed_manifest)` as UTF-8 with **no trailing
newline** (S11-D1), so its SHA-256 is its filename. `catalog/index.json` is
written the same way. Do not reformat these files and do not add a final
newline — that changes the identity of the Set.

## Regenerating

```bash
python3 tools/soundset-fixtures/generate.py          # rewrite the corpus
python3 tools/soundset-fixtures/generate.py --check  # verify it byte-for-byte
```

All audio is integer-only synthesis (a decaying LCG noise burst), so the bytes
are identical on every platform and Python version. Never hand-edit a blob or
a manifest; change `tools/soundset-fixtures/soundset_fixtures.py` and
regenerate.

## Serving the corpus

```bash
python3 tools/soundset-fixtures/catalog_fixture_server.py \
    --root tests/fixtures/soundset --port 8099
```

The server admits exactly three request shapes — `GET|HEAD
/catalog/index.json`, `/object/manifest/<sha256>`, `/object/blob/<sha256>` —
and answers 404 for everything else, including a directory listing, an archive
path, a query string, a percent-encoded traversal, a leading `//`, a
non-lowercase digest, and a manifest hash requested under `blob`. It never
emits a redirect and never follows a symlinked basename.
`tools/soundset-fixtures/tests/catalog_fixture_server_test.py` pins that.

Add `--cross-origin` when a browser page must read the corpus. A Creator page
is served cross-origin isolated (`Cross-Origin-Embedder-Policy: require-corp`),
so a Catalog on another origin is unreachable from it unless the response
carries both `Access-Control-Allow-Origin` and
`Cross-Origin-Resource-Policy: cross-origin`; without them the browser blocks
the fetch before the Host transport sees a status and the refusal arrives as
`catalog_unavailable`. The flag is off by default so the same-origin surface
stays exactly the S11-D6 one.

## The Sets

| Set | `set_id` | `manifest_sha256` | License | Occupied slots | What it exercises |
| --- | --- | --- | --- | --- | --- |
| Fixture Foundry CC0 | `11111111-…-111111111111` | `33175f66…18dd9111` | `CC0-1.0`, empty attribution | 0–9, 12 | The happy path. Both S8-D6 sample rates, mono and stereo, five empty slots, slot 12 reusing slot 0's Artifact, and a set-level `demo` no slot references. |
| Fixture Attribution Kit | `22222222-…-222222222222` | `ae578e4f…7a313bb4` | `CC-BY-4.0`, non-empty attribution | 0–3 | An eligible `CC-BY-4.0` Set whose attribution string must reach listing and inspect. Its set-level `demo` declares slot 0's Artifact hash, so the Set holds four unique blobs and `total_bytes` counts that one once. |
| Fixture Unsupported Audio Kit | `33333333-…-333333333333` | `57ab3bf8…0df2e64c` | `CC0-1.0` | 0–2 | Slot 0 is 22.05 kHz, slot 1 is 8-bit, slot 2 is legal 48 kHz. Manifest and hashes are valid, so the only fault is the audio. |
| Fixture Tampered Kit | `44444444-…-444444444444` | `00a4700e…9892df8e` | `CC0-1.0` | 0–1 | Slot 0's stored bytes contradict its declared `sha256` **and** `byte_length`; slot 1 is honest. |
| Fixture Mismatched Summary Kit | `55555555-…-555555555555` | `68500bf2…a2cf8ce6` | `CC-BY-4.0` | 0–1 | The manifest is eligible; the catalog entry names `Impostor Records` as `rights_holder`. |
| Fixture Unallowlisted License Kit | `66666666-…-666666666666` | `9bdf3163…e3ba9592` | `MIT` | 0 | A Schema-valid `license` block whose `spdx_id` is outside the v1 allowlist. |
| Fixture Unattributed BY Kit | `77777777-…-777777777777` | `3038f32d…fac8e7c0` | `CC-BY-4.0`, empty attribution | 0 | `CC-BY-4.0` with no attribution: Schema-valid, ineligible. |

Every Set has 16 slots numbered 0–15 with at least one empty slot, so S11-D12
(an empty Set slot is not a wipe instruction) always has something to assert.

Two Sets carry the optional set-level `demo` Artifact of S11-D5, and they carry
it the two ways that differ under S11-D7's unique-blob accounting. Foundry CC0's
demo is a blob no slot references, so it adds its own length to `total_bytes`.
The Attribution Kit's demo declares the *same* `sha256` as its slot 0, so it is
one stored object: it is downloaded once, counted once, and the Set's
`total_bytes` is 34788 — canonical manifest bytes plus four unique blob lengths
— rather than the 40592 a second charge would produce.

## Which plan checkbox each case serves

| Fixture case | Plan checkbox |
| --- | --- |
| Canonical manifest objects, no trailing newline, hash over exactly those bytes | Task 1 — "RED: `soundset_manifest_test.cpp` — canonical byte equality" |
| `blob/`, `manifest/` as single-basename, lowercase-sha256 stores | Task 2 — "RED: local adapter rejects `/`, `..`, non-lowercase sha256 basename, symlink, and non-regular file" |
| Foundry CC0 slot 12 reusing slot 0's Artifact; every `total_bytes` in the index | Task 2 — "RED: unique blob hash is fetched once; declared `total_bytes` must equal canonical manifest bytes plus unique blob lengths" |
| Attribution Kit's `demo` reusing its slot 0 Artifact hash | Task 2 / #740 — the same rule across the demo and the slots: one hash is one download and one charge |
| Foundry CC0's standalone `demo` blob | Task 4 — S11-D5 set-level audition; Task 5 — the preview surface |
| Fixture Tampered Kit | Task 2 — "Tampered blob → `soundset_content_mismatch`" (staging must stay invisible) |
| Small, exactly known object and Set sizes | Task 2 — "RED: four Host limits, each exact allowed and +1 fail-closed" |
| Foundry CC0 empty slots 10, 11, 13–15 | Task 3 — "empty Set slots never clear occupied pads"; Task 4 — S11-D12 |
| Foundry CC0 slot 0 / slot 12 sharing one Artifact | Task 4 — "RED: Bank and generation quota rehearsals count decoded float PCM per Pad (duplicate Artifact on two Pads counts twice)" |
| Fixture Unsupported Audio Kit | Task 4 — "RED: S8-D6 — a published Set whose blob is not PCM16 44.1/48 kHz mono/stereo WAV → `UNSUPPORTED_AUDIO` + `soundset_audio_unsupported` on inspect, slot preview, and install" |
| Fixture Mismatched Summary Kit | Task 4 — "a catalog `license_summary` that differs from the published manifest → `soundset_license_ineligible` at inspect" |
| Fixture Unallowlisted License Kit, Fixture Unattributed BY Kit | Task 4 — the same `soundset_license_ineligible` gate for a non-allowlisted SPDX and for an empty `CC-BY-4.0` attribution |
| Fixture Attribution Kit | Task 5 — "the `CC-BY-4.0` `attribution` string is shown on listing and inspect" |
| The fixture server's three-shape surface | Task 5 — "a web-runtime-platform test that the fetch transport refuses non-`{object_kind, sha256}` requests" |
| The fixture server, stopped mid-journey | Task 4 — "catalog list of a cached Set succeeds when the injected `CatalogTransport` fails with `catalog_unavailable`"; Task 7 — "Catalog unreachable: cached Set still inspectable and installable" |
| Foundry CC0 as the install target Set | Task 7 — "list → inspect → map.preview → install keep → install replace" |

## Consuming this corpus

- **A native Host or a Core test** points the local directory adapter at
  `tests/fixtures/soundset/manifest` and `tests/fixtures/soundset/blob`.
- **The Web Host** points its fetch `CatalogTransport` at the fixture server's
  base URL. Core keeps hash and length verification either way; the transport
  only moves bytes.
- **Nothing** may treat this directory as Project Truth or copy it into a
  Project bundle. It models a Workspace-side Catalog cache and Set Store.

Adding a case means adding it to `tools/soundset-fixtures/soundset_fixtures.py`,
regenerating, and adding the row above — otherwise
`tools/soundset-fixtures/tests/fixture_corpus_test.py` will not know the case
exists and the next reader will not know what it is for.
