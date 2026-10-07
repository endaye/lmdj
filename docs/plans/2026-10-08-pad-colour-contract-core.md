# Pad 颜色：Contract／Core 前置计划（Desktop Final T7 前置，#1207）

## Outcome and authority

Persist each Pad's colour as the two decisions define it, through Contract, Domain, Project I/O, Facade and the Web Runtime Platform, so that Desktop Final T7 can draw one effective colour on the Pad matrix, the Sequence upper-screen rows and the touch grid notes.

**Authority:**

- [`2026-10-07-pad-colour-source.md`](../prd/decisions/2026-10-07-pad-colour-source.md), which defines:
  - the category default and the user override;
  - the five-colour palette;
  - storage in Truth as a stable index;
  - retention across re-separation and restore-default;
  - one effective colour on all three surfaces;
  - the white-border-plus-lime-dot selected state.
- [`2026-10-08-pad-colour-defaults-and-retention.md`](../prd/decisions/2026-10-08-pad-colour-defaults-and-retention.md), which records the owner's choices for the items the first decision left to this plan:
  - unclassified and empty Pads are neutral;
  - labels map by meaning, and `other` stays unclassified;
  - the override follows the Pad across asset changes and is cleared when the Pad is deleted;
  - no backfill for existing Projects.
- [Desktop Final plan](2026-10-06-creator-desktop-final-ui.md), T7 addendum. It requires this prerequisite before any Creator colour work.

**Process.** Each Task below is one Conventional Commit on its own short-lived branch, with verified commit, push, current-head review and squash merge. P1 is a Contract cut and so also carries the Product Build allocation and portal snapshot that a cut requires. No other Task releases or allocates a Product Build.

## Facts this plan relies on

Checked on `486beb8c1`.

- **Contract.**
  - `contracts/project/lmdj.project.v5.schema.json` is `lmdj.project.v5` at Contract 5.2.0.
  - `$defs/pad` is exactly `{pad, asset_id, playback}`, and `$defs/asset` is `{asset_id, artifact, lineage}`. Neither has a category or colour field.
  - The last two additive changes (5.0→5.1.0 #1697, 5.1→5.2.0 #1756) were Contract MINORs under the same ID. Each cut also touched `products/lmdj/assembly.lock.json` (schema digest), `assembly.json`, `version.json`, the generated Runtime identity, `src/compiled_assembly.cpp`, `tests/conformance/schema_contract_test.py`, the `tests/fixtures/contracts/project-v5-*-valid.json` fixtures and `/contracts/project/`. Each allocated a Product Build and froze a portal snapshot in the same PR (`.agents/pitfalls/portal-snapshot-not-deferrable.md`). Reading and writing the new keys followed in a separate Core PR.
- **Domain** (`packages/authoring-domain/include/lmdj/domain/project.hpp`).
  - `PadSlot` is `{id, asset_id, playback}` and `Asset` is `{id, artifact, lineage}`.
  - Every asset change rebuilds the Pad: `pad.playback = PadPlayback{}` in `command_handler.cpp` for `AssignPad` (asset change only), `ImportAssignSample`, `AdoptCandidates` and `InstallSoundSet`. A new Pad field must be kept or cleared explicitly at each site.
  - `DeletePad` lowers to `AssignPad` with a null asset.
- **Undo.** `AuthoringDelta.pads` stores whole `PadSlot` values. A new field reaches Undo/Redo once equality and the history serialiser cover it. History serialises Pads with exact keys `{slot, asset_id, playback}` (`project_store.cpp:1564, 1658`).
- **Labels.**
  - Sound Set slots carry one of 13 roles (`contracts/soundset/lmdj.soundset.v1.schema.json`, `foundation/soundset_manifest.hpp:48`). They are used only as preview metadata (`commands.hpp:111-112`) and are not persisted, but `map_soundset` sees the manifest at install time.
  - `stem.split.v1` declares `bass`, `drums`, `other` and `vocals`, but stem separation is not wired into Core or Creator. No separation result can reach a Pad today.
- **Reading.**
  - `project_store.cpp` `parse_project` reads v1–v5, checks Pad keys as exact sets, and admits optional keys per Contract level (`PlaybackKeys`). That is the pattern to copy.
  - Opening a Project rewrites nothing; saving promotes it to v5.
  - Writers: `project_store.cpp:551` and the Facade's `application.cpp:805` `project_json`.
- **Creator.** Pad colour today rotates by slot: `pad_surface.tsx:59` `data-identity = slot % 5`, with colours in `styles.css` that are not the decision's palette. The overview rows and the grid notes have no Pad colour.

## Locked interfaces

### Palette

The palette index is stable and persisted; this order never changes.

| Index | Category | Colour |
|---|---|---|
| 0 | DRUMS | `#F3B580` |
| 1 | BASS | `#DFF779` |
| 2 | MELODIC | `#B49DE8` |
| 3 | VOCAL | `#94D2DC` |
| 4 | TEXTURE | `#E6ED98` |

### Project Truth (Contract `lmdj.project.v5` 5.3.0, additive)

- `$defs/asset` gains an optional `category`, one of `"drums" | "bass" | "melodic" | "vocal" | "texture"`.
  - An absent key means unclassified. There is no `"none"` value.
  - Category describes the sound, so it lives on the Asset.
- `$defs/pad` gains an optional `colour`, an integer from 0 to 4: the user's override as a palette index.
  - An absent key means no override.
  - The override describes the Pad, so it lives on the Pad.
  - It is allowed only while `asset_id` is non-null. An empty Pad carrying `colour` is invalid.
- A reader of 5.2.0 rejects the new keys, as with earlier MINORs. Core reads them only from a 5.3.0-or-later checkpoint, using the same per-level admission as `PlaybackKeys`.

### Effective colour

Core owns one resolver:

```
effective(pad) = pad.colour            if present
               = index(asset.category) if the Pad has an asset with a category
               = null                  otherwise (neutral)
```

The Facade inspection projects, for each Pad, `category` (from its asset, or null), `colour_override` (or null) and `colour` (the effective index, or null). Hosts never recompute the rule.

### Category from labels

Sound Set roles map as follows:

| Roles | Category |
|---|---|
| `kick`, `snare`, `clap`, `hat_closed`, `hat_open`, `perc`, `cymbal` | `drums` |
| `bass` | `bass` |
| `melody`, `chord` | `melodic` |
| `vocal` | `vocal` |
| `fx` | `texture` |
| `other` | unclassified |

Stem labels, for when separation is wired in later: `drums`→`drums`, `bass`→`bass`, `vocals`→`vocal`, `other`→unclassified.

Imported files, recordings, resamples and Slice adoptions are unclassified. No backfill applies to Assets that already exist.

### Command and retention

- **New Domain command** `SetPadColour {meta, slot, colour: optional<0..4>}`.
  - `nullopt` restores the category default by removing the override.
  - It is refused on an empty Pad (`pad_empty`) and on an out-of-range index.
  - Setting the current value is a no-op with no history entry.
  - History label: "Set Pad colour".
  - It follows `apply_checked`: `expected_revision` / `command_id` replay.
- **New Facade / Host operation** `pad.colour.set {slot, colour | null, expected_revision, command_id}`.
  - Admitted while playing, because it changes no audio.
  - Refused while recording, with the same guard as other non-Sequence authoring.
  - It changes no Runtime publication.
- **Retention at the existing sites:**

| Command | `colour` | Asset `category` |
|---|---|---|
| `AssignPad` to another asset | kept | the target asset's |
| `AssignPad` to null / `DeletePad` | **cleared** | — |
| `ImportAssignSample` | kept | unclassified |
| `InstallSoundSet` (each written Pad) | kept | from the slot role |
| `AdoptCandidates` (Slice) | kept | unclassified |
| Future stem adoption | kept | from the stem label |

  A Sound Set `keep` leaves the occupied Pad untouched, colour included.

## Tasks

### P1 — Contract cut: Project 5.3.0

- **Change.** Add the two optional keys and their constraints to `lmdj.project.v5.schema.json` (Contract 5.3.0). Add `project-v5-*-valid.json` fixtures with a category, an override, and both. Add invalid fixtures for:
  - an override on an empty Pad;
  - an out-of-range index;
  - an unknown category.
- **Cut obligations.** Update the assembly lock digest, `assembly.json`, `version.json`, the generated Runtime identity and `compiled_assembly.cpp`, as the 5.2.0 cut did. Allocate the Product Build, freeze its portal snapshot in the same PR, and update `/contracts/project/`.
- **Lowest-tier tests.** `tests/conformance/schema_contract_test.py` covers the valid and invalid fixtures; existing 5.2.0 fixtures still validate.
- **Gate defect caught.** A Project carrying a colour or category the schema does not describe, or an override on an empty Pad.

### P2 — Domain: types, resolver, command and retention

- **Change.**
  - `Asset.category` and `PadSlot.colour` (both optional, both in `operator==`).
  - The palette and the label mapping.
  - `effective_pad_colour`.
  - `SetPadColour` in `commands.hpp` / `command_handler.cpp`.
  - Retention as tabled at each site that rebuilds playback.
  - `map_soundset` / `InstallSoundSet` record the slot role's category on the new Asset.
- **Lowest-tier tests** (`tests/core/domain/command_handler_test.cpp`):
  - set, change and restore;
  - refused on an empty Pad and on a bad index;
  - the no-op;
  - each retention row, including that Delete clears and that a Sound Set `keep` preserves;
  - the role→category table, with `other` unclassified;
  - the resolver: override first, then category, then neutral.
- **Gate defect caught.** An asset change silently dropping or keeping the override against the table, or a role mapped to the wrong category.

### P3 — Project I/O: read, write, history

- **Change.**
  - Read and write `category` / `colour` from 5.3.0 checkpoints with per-level admission. Keys in a 5.2.0-or-earlier checkpoint are refused.
  - Serialise both in the authoring history.
  - Add the "Set Pad colour" history label.
  - Opening an older Project writes nothing, and the first save emits the new keys only where they are set.
- **Lowest-tier tests** (`tests/core/project_io/`):
  - round trip of each combination;
  - an older checkpoint with the keys is refused;
  - a legacy Project opens with no category and no override;
  - Undo/Redo of set, restore and Delete-clears, each restoring the exact Pad;
  - save and reopen keep the override;
  - re-install of a Sound Set over an overridden Pad (`replace`) keeps the override and updates the category.
- **Gate defect caught.** Loss of the user's choice across save, reopen, Undo or Redo.

### P4 — Facade and Web Runtime Platform

- **Change.**
  - `pad.colour.set` in the operation table, dispatch and failure contract.
  - The inspection projection fields `category`, `colour_override` and `colour`.
  - The Web Runtime bridge, `protocol.mjs` validation, `runtime_session.mjs` `setPadColour` and `runtime_types.d.ts`.
- **Lowest-tier tests.**
  - A dedicated `tests/core/facade/pad_colour_test.cpp`: admitted while playing, refused while recording, stale revision, replay, no publication.
  - The protocol and session payload tests.
  - The operation-inventory tests.
- **Gate defect caught.** A Host recomputing or diverging from the Core resolver, or a colour change disturbing playback.

### P5 — Creator (Desktop Final T7)

This Task belongs to the Desktop Final plan and gets its own implementation addendum there once P4 lands. It consumes `colour` from the inspection only:

- **Display.** The Pad matrix border, the Sequence overview rows and the touch grid notes all use the effective colour. A null colour is the neutral EMPTY style.
- **Selected state.** White border plus a lime dot, with the existing accessible state.
- **Controls.** Five-colour selection and "Restore category default". Their placement is proposed in that addendum.
- **Journey.** Category default → manual override → re-install `replace` (the stand-in for re-separation until stems reach Pads) → save and reopen → restore default. Each transition checks the Truth and all three surfaces, and Undo/Redo is checked at each step.

## Verification

- Each Task runs its lowest-tier tests first, then the affected Core and JS suites (`scripts/core.sh test dev`, `scripts/creator-web.sh test`).
- P1 also runs the schema conformance suite and `scripts/docs-site.sh check`.
- Each batch-only lane a change selects records its `pass key=` in the Pull Request.
- Revert proofs run against rebuilt artefacts.
- No timeout, coverage floor, owned lane or journey leg is relaxed.
- **Not covered by automation.** Stem separation reaching Pads does not exist yet. Its retention row is fixed here as a rule, and its tests belong to the Task that wires stems into Pad adoption.

## Version Management

Version impact: none for this plan Pull Request (documentation only).

The implementation owes:

- **P1:** Contract `lmdj.project.v5` 5.2.0 → 5.3.0 (MINOR, additive optional keys), plus the Product Build and Assembly updates the cut requires.
- **P2–P4:** MINOR bumps for `authoring-domain`, `project-io`, `application-facade` and `web-runtime-platform` at the next coordinated version settlement. No numbers are pre-filled.
- **P5:** `creator-web` MINOR, owed through the Desktop Final plan.

## Documentation Impact

Documentation impact: none

Reason: this Pull Request adds a plan and a product decision under `docs/`, and no portal page describes them as implemented.

Each implementation Task is `required`:

- P1 updates `/contracts/project/`;
- P2–P4 update the Authoring Domain, Project I/O, Application Facade and Web Runtime Platform module pages and `/platform/web-runtime/`;
- P5 updates `/hosts/creator-web/`.

## Pitfall Impact

Pitfall impact: none expected. P1 applies `portal-snapshot-not-deferrable`. Each Task re-checks open `area:core`, `area:creator` and `area:web-host` entries before shipping.
