# Stage 8B M4 — Windows Chrome 60-second capture cap

## Result

`PASS` for the observed Windows Chrome session. The real microphone capture
started at 0 seconds, stopped automatically at 60 seconds, displayed the
capacity stop message, and remained usable for both Commit and Discard. The
committed material played back normally.

This is additional Windows evidence for the optional M4 observation. The
canonical historical row is grouped under macOS Chrome; this result does not
silently widen that platform claim.

## Session identity

| Field | Value |
| --- | --- |
| Surface | `https://creator.lmdj.workers.dev/` |
| Product Build | `1.0.42.0` |
| Creator Host | `creator-web 3.0.0` |
| Project revision shown in UI | `8` |
| OS | Windows 11 Pro 25H2 |
| Browser | Google Chrome `152.0.7977.83` (64-bit) |
| Input | Logitech C922 Pro Stream Webcam microphone |
| Output | Edifier speakers, High Definition Audio Device |
| Capture interval | `0s` → automatic stop at `60s` |
| Capacity message | `Recording stopped: reached the 60-second limit.` (observed) |
| Commit / Discard | Both successful |
| Playback | Normal by operator report |
| Screenshot | Operator-local PNG, SHA-256 `eb65d2a870e2284f9f748a47b065195e67348ca758c9236293b65afaf90fcb61` |

## Scope and limitation

The screenshot shows the exact Creator URL, Product Build/Host identity, a
selected Project and a 60-second waveform (`Start 0`, `End 60`). It is retained
as operator-local evidence at acceptance time; the hash above binds the record
to that supplied artifact. No claim is made for macOS Chrome, Safari, iPadOS,
or the optional 60-second boundary on another deployed Build.

## Version Management

Version impact: none. This file records validation evidence only.

## Documentation impact

Documentation impact: none. This update changes `docs/release-evidence/` and
the quality ledger only; no Architecture Portal page is affected.
