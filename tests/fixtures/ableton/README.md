# Ableton Live 12 baseline capture (#1676, T0)

No native `.adg` / `.als` template is checked in yet. T0 remains **NOT RUN**:
the implementation environment has no usable Ableton Live installation and no
captured native pair. The inspector's synthetic unit inputs are parser tests,
not native templates, a format specification, or proof that Live can open them.

## Capture the native pair

Use one fixed, usable Live 12 version and edition. Record its exact version,
OS, operator, capture date, and the original files' SHA-256 and byte length.
Use self-authored or explicitly redistributable samples; record their origins,
license and hashes before adding any native template or audio to the repository.
Do not copy Koala templates or third-party preset content.

1. Save a minimal Drum Rack `.adg`, with occupied and empty Pads and native
   Simpler devices. Use a self-authored test WAV and keep an unmodified original.
2. Save a minimal `.als` with that Rack and Session MIDI Clips, including note
   velocity, note length, loop length, and a deliberately empty Scene.
3. Collect the audio into the project. Move the entire captured folder to a
   new location; open the Set and separately load the Rack without missing media.
4. Play both, edit a Clip, save, close and reopen. Retain recordings/observations
   and PASS/FAIL for each transition, with file identities after saving.
5. Compare Creator and Live for trim, gain, mute, velocity, `one_shot`, `gate`,
   `loop_gate`, and `loop_toggle`. Preserve each observed difference. Only a
   demonstrated equivalent mapping can enable that parameter in a writer.

Live 12 Standard/Suite is the default baseline edition, pending actual testing.
The Set design preserves 16 Pattern slots and any unassigned Patterns, so
Lite/Intro must receive separate edition-limit testing before compatibility
is claimed. No edition/version matrix has run.

## Inspect supplied identities

```bash
shasum -a 256 /absolute/capture/Rack.adg /absolute/capture/Set.als
python3 tools/project-bundle/ableton_baseline.py \
  --rack /absolute/capture/Rack.adg --rack-sha256 ORIGINAL_RACK_SHA256 \
  --set /absolute/capture/Set.als --set-sha256 ORIGINAL_SET_SHA256
python3 tools/project-bundle/tests/ableton_baseline_test.py
```

The expected digests come from the original capture record. Inspection checks
complete encoded identity, gzip integrity, bounded UTF-8 XML, the `Ableton`
root and matching declared Live 12 creator versions, and inventories element
names without inventing device schemas. A `Creator` attribute can be forged:
it is not native provenance. Exit 0 means **bytes/XML inspection only**; the
report deliberately says `manual_acceptance: not-assessed`. The tool does not
validate device IDs, sample closure, audio equivalence, or certify T0.

After human evidence is retained, use the verified native pair to establish
the Rack/Set writer templates. Do not start the corresponding writer while
that baseline's open/play/edit/save/reopen evidence or sample rights is missing.

## Evidence to retain

Keep the raw `.adg`/`.als`, every referenced sample, original and post-save
file identities, bytes/XML inspection output, and the human observations
together. Record the exact Creator source/candidate used for comparison,
input Project/Artifact identities, actual output/audio device, test steps,
and each supported/refused parameter. Never manufacture PASS rows from the
inspection result or from the synthetic tests.

Sources: [Live file types](https://help.ableton.com/hc/en-us/articles/209769625-Live-specific-file-types),
[Collect All and Save](https://help.ableton.com/hc/en-us/articles/209775645-Collect-All-and-Save),
[Live Set Export documentation](https://ableton.github.io/export/).

## Version Management

Version impact: none
Reason: this preparatory fixture inspector and capture procedure do not change
product code, a Module/Host API, Project Contract, Assembly or Product Build.
T1–T4 need their own versioned product changes. No tag/release/deployment is
initiated by this preparation.

## Documentation Impact

Documentation impact: none
Reason: this is a fixture capture procedure for an unimplemented feature. It
adds no portal product capability or evidence claim; current product pages
remain unchanged until the corresponding implementation Task.
