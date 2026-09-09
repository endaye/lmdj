import {createHash, randomUUID} from "node:crypto";
import {expect, test} from "@playwright/test";

const bundle = process.env.LMDJ_CREATOR_WEB_CANDIDATE_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_CANDIDATE_BUNDLE is required");
const sourceId = "00000000-0000-4000-8000-000000009101";
const otherSourceId = "00000000-0000-4000-8000-000000009102";
const digest = bytes => createHash("sha256").update(bytes).digest("hex");

function wav(silent = false) {
  const frames = 48_000;
  const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write("RIFF"); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(48_000, 24); bytes.writeUInt32LE(96_000, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36); bytes.writeUInt32LE(frames * 2, 40);
  if (!silent) {
    // Two bounded sustained sounds give a leading interval and a final
    // interval. Preview slice 2 contains actual nonzero PCM.
    for (let frame = 4_800; frame < 14_400; ++frame) bytes.writeInt16LE(8_000, 44 + frame * 2);
    for (let frame = 24_000; frame < 38_400; ++frame) bytes.writeInt16LE(-8_000, 44 + frame * 2);
  }
  return bytes;
}
// Passthrough evidence only: record real request/response pairs, never supply
// a mocked Facade or replace a RuntimeSession implementation.
async function observe(page) {
  await page.addInitScript(() => {
    let exposed;
    window.__candidateUiEvidence = [];
    Object.defineProperty(window, "lmdjWebRuntimeHost", {configurable: true,
      get: () => exposed,
      set(host) {
        const transport = host.transport;
        host.transport = Object.freeze({
          async send(...args) {
            const response = await transport.send(...args);
            if (args[0]?.operation?.startsWith("candidate.") || args[0]?.operation?.startsWith("provider.") || args[0]?.operation?.startsWith("snapshot.")) {
              window.__candidateUiEvidence.push({operation: args[0].operation,
                payload: args[0].payload, response: structuredClone(response)});
            }
            return response;
          },
          subscribe: (...args) => transport.subscribe(...args),
          subscribeFailure: (...args) => transport.subscribeFailure(...args),
          terminate: (...args) => transport.terminate(...args),
          get terminated() {return transport.terminated;},
          get terminalOwnerReleased() {return transport.terminalOwnerReleased;},
        });
        exposed = host;
      },
    });
  });
}
async function send(page, operation, payload = {}, bytes) {
  return page.evaluate(async ({operation, payload, bytes}) =>
    window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
      request_id: crypto.randomUUID(), operation, payload},
    bytes ? {sidecar: new Uint8Array(bytes)} : undefined),
  {operation, payload, bytes: bytes ? [...bytes] : undefined});
}
function success(response) {
  expect(response, JSON.stringify(response)).toHaveProperty("ok", true);
  return response.result;
}
async function truth(page) {return success(await send(page, "project.inspect"));}
async function evidence(page, operation) {
  return page.evaluate(operation => window.__candidateUiEvidence.filter(item => item.operation === operation), operation);
}
async function last(page, operation) {return (await evidence(page, operation)).at(-1);}
async function addSource(page, assetId, silent = false) {
  const before = await truth(page);
  const bytes = wav(silent);
  success(await send(page, "asset.import", {command_id: randomUUID(), expected_revision: before.project_revision,
    asset_id: assetId, media_type: "audio/wav", sidecar: {sidecar_bytes: bytes.length, sidecar_sha256: digest(bytes)}}, bytes));
  return {bytes, before};
}
async function start(page, silent = false) {
  await observe(page);
  await page.goto("/index.html");
  await expect(page.getByTestId("creator-phase")).toHaveText("empty");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"})).toBeVisible();
  await page.waitForFunction(() => Boolean(window.lmdjWebRuntimeHost?.candidates));
  const {bytes, before} = await addSource(page, sourceId, silent);
  expect(Object.values(before.project.patterns).some(pattern => pattern.events.length > 0)).toBe(true);
  // Preserve unrelated grants across the visible, explicit permission action.
  const existingPermission = await page.evaluate(async () => {
    const listing = await window.lmdjWebRuntimeHost.providers.listProviders();
    const permission = listing.providers.flatMap(provider => provider.capabilities)
      .filter(capability => capability.capability_id !== "sample.slice.v1")
      .flatMap(capability => capability.policy.required_permissions)[0];
    if (!permission) throw new Error("Fixture requires another registered Provider permission");
    await window.lmdjWebRuntimeHost.providers.configureProviderPermissions([permission]);
    return permission;
  });
  await page.getByRole("button", {name: "Slice", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Slice", exact: true})).toBeVisible();
  await expect(page.getByRole("combobox", {name: "Slice source"}).locator(`option[value="${sourceId}"]`)).toHaveCount(1);
  await page.getByRole("combobox", {name: "Slice source"}).selectOption(sourceId);
  await expect(page.getByRole("button", {name: "Analyze", exact: true})).toBeDisabled();
  expect(await evidence(page, "provider.select")).toHaveLength(0);
  await page.getByRole("combobox", {name: "Slice Provider"}).selectOption("local.sample.slice");
  await page.getByRole("button", {name: "Grant analysis permission"}).click();
  await expect(page.getByRole("button", {name: "Analysis permission granted"})).toBeDisabled();
  expect((await last(page, "provider.permissions.configure")).payload.granted_permissions)
    .toEqual(expect.arrayContaining([existingPermission, "sample.slice.execute"]));
  await page.getByRole("button", {name: "Refresh slices and Project"}).click();
  await expect(page.getByRole("button", {name: "Analyze", exact: true})).toBeDisabled();
  await page.getByRole("checkbox", {name: "Use this source as public audio for local analysis"}).check();
  await expect(page.getByRole("button", {name: "Analyze", exact: true})).toBeEnabled();
  const baseline = await truth(page);
  await page.getByRole("button", {name: "Analyze", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Detected slices"})).toBeVisible();
  const analyzed = await last(page, "candidate.job.run");
  const result = success(analyzed.response);
  expect(analyzed.payload.job_id).toBe(`slice-${baseline.project.project_id}-${sourceId}`);
  expect(analyzed.payload.platform).toBe("test");
  expect(analyzed.payload.data_classification).toBe("public");
  expect(JSON.stringify(result)).not.toContain("project_path");
  expect(analyzed.payload.asset_id).toBe(sourceId);
  expect(await truth(page)).toEqual(baseline);
  return {baseline, bytes, job: result, set: result.sets.find(set => set.set_id === result.active_set_id)};
}
async function target(page, index, candidateId, pad, bank = 1) {
  await page.getByRole("button", {name: "Add target"}).click();
  for (const field of ["slice", "Bank", "Pad"]) {
    await expect(page.getByRole("combobox", {name: `Target ${index} ${field}`})).toHaveValue("");
  }
  await page.getByRole("combobox", {name: `Target ${index} slice`}).selectOption(candidateId);
  await page.getByRole("combobox", {name: `Target ${index} Bank`}).selectOption(String(bank));
  await page.getByRole("combobox", {name: `Target ${index} Pad`}).selectOption({value: String(pad)});
  await expect(page.getByRole("combobox", {name: `Target ${index} Pad`})).toHaveValue(String(pad));
}
// OPFS is read only for saved-byte evidence. The deliberate missing-source
// branch is test fault injection; product operations all use the public Host.
async function files(page, projectId, removeHash = null) {
  return page.evaluate(async ({projectId, removeHash}) => {
    const result = {};
    async function visit(directory, prefix = "") {
      for await (const [name, handle] of directory.entries()) {
        const path = `${prefix}/${name}`;
        if (handle.kind === "directory") {await visit(handle, path); continue;}
        if (!path.includes(`${projectId}.lmdj/`)) continue;
        if (removeHash && name === `${removeHash}.wav`) {await directory.removeEntry(name); continue;}
        result[path] = [...new Uint8Array(await (await handle.getFile()).arrayBuffer())];
      }
    }
    await visit(await navigator.storage.getDirectory());
    return result;
  }, {projectId, removeHash});
}
async function restoreSource(page, originalFiles, sha256) {
  const entry = Object.entries(originalFiles).find(([path]) => path.endsWith(`${sha256}.wav`));
  expect(entry).toBeDefined();
  await page.evaluate(async ([path, bytes]) => {
    const parts = path.split("/").filter(Boolean);
    const name = parts.pop();
    let directory = await navigator.storage.getDirectory();
    for (const part of parts) directory = await directory.getDirectoryHandle(part);
    const file = await directory.getFileHandle(name, {create: true});
    const writer = await file.createWritable();
    await writer.write(new Uint8Array(bytes)); await writer.close();
  }, entry);
}
async function reopen(page) {
  await page.reload();
  await page.getByRole("button", {name: "Open Project 00000000"}).click();
  await expect(page.getByRole("heading", {name: "Project 00000000"})).toBeVisible();
}

test("Creator Slice UI previews, explicitly adopts repeated recipes, and reopens saved lineage and Pattern truth", async ({page}) => {
  const {baseline, bytes, set, job} = await start(page);
  expect(set.recipes.map(recipe => [recipe.start_frame, recipe.end_frame])).toEqual([[0, 4800], [4800, 24000], [24000, 48000]]);
  const projectId = baseline.project.project_id;
  const savedBefore = await files(page, projectId);
  expect(Object.keys(savedBefore).length).toBeGreaterThan(0);
  await page.getByRole("button", {name: "Preview slice 2", exact: true}).click();
  await expect(page.getByText("Preview was not played. Activate audio and try again.")).toBeVisible();
  expect(success((await last(page, "candidate.audition")).response).played).toBe(false);
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
  await page.getByRole("button", {name: "Preview slice 2", exact: true}).click();
  await expect(page.getByText("Preview started.")).toBeVisible();
  expect(success((await last(page, "candidate.audition")).response).played).toBe(true);
  await page.getByRole("button", {name: "Stop preview", exact: true}).click();
  await expect(page.getByText("Preview stopped.")).toBeVisible();
  expect(success((await last(page, "candidate.audition.stop")).response).accepted).toBe(true);
  expect(await truth(page)).toEqual(baseline);
  expect(await files(page, projectId)).toEqual(savedBefore);

  // Mode teardown sends stop; a real reload starts with suspended audio and
  // finds the durable Job again without re-analysis or hidden UI persistence.
  const stops = (await evidence(page, "candidate.audition.stop")).length;
  await page.getByRole("button", {name: "Project", exact: true}).click();
  await expect.poll(async () => (await evidence(page, "candidate.audition.stop")).length).toBeGreaterThan(stops);
  await reopen(page);
  expect(await truth(page)).toEqual(baseline);
  expect(await files(page, projectId)).toEqual(savedBefore);
  await expect(page.getByTestId("audio-state")).not.toHaveText("Audio running");
  await page.getByRole("button", {name: "Slice", exact: true}).click();
  await page.getByRole("combobox", {name: "Slice source"}).selectOption(sourceId);
  await expect(page.getByRole("button", {name: "Preview slice 2", exact: true})).toBeEnabled();
  expect(await evidence(page, "candidate.job.run")).toHaveLength(0);
  expect(success((await last(page, "candidate.job.inspect")).response).active_set_id).toBe(job.active_set_id);
  const recipe = set.recipes[1];
  await target(page, 1, recipe.candidate_id, 0);
  await target(page, 2, recipe.candidate_id, 0);
  await expect(page.getByText("Each target Pad can appear only once.")).toBeVisible();
  await expect(page.getByRole("button", {name: "Adopt selected slices"})).toBeDisabled();
  expect(await truth(page)).toEqual(baseline);
  expect(await evidence(page, "candidate.adopt")).toHaveLength(0);
  await page.getByRole("combobox", {name: "Target 2 Pad"}).selectOption({value: "1"});
  await expect(page.getByRole("combobox", {name: "Target 2 Pad"})).toHaveValue("1");
  await page.getByRole("button", {name: "Adopt selected slices"}).click();
  await expect(page.getByText(/Adopted 2 slices\./)).toBeVisible();
  expect(await evidence(page, "candidate.adopt")).toHaveLength(1);
  const adopted = await truth(page);
  expect(adopted.project_revision).toBe(baseline.project_revision + 1);
  expect(adopted.project.patterns).toEqual(baseline.project.patterns);
  expect(adopted.project.assets[sourceId]).toEqual(baseline.project.assets[sourceId]);
  const ids = [0, 1].map(pad => adopted.project.banks[1].pads[pad].asset_id);
  expect(new Set(ids).size).toBe(2);
  const saved = await files(page, projectId);
  const {candidate_id, ...interval} = recipe;
  for (const id of ids) {
    expect(baseline.project.assets[id]).toBeUndefined();
    const artifact = adopted.project.assets[id].artifact;
    const output = Buffer.from(Object.entries(saved)
      .find(([path]) => path.endsWith(`${artifact.sha256}.wav`))?.[1] ?? []);
    expect(artifact).toEqual({sha256: digest(output), byte_length: output.length, media_type: "audio/wav"});
    expect(output.length).toBe(44 + (recipe.end_frame - recipe.start_frame) * 2);
    expect(output.subarray(44)).toEqual(bytes.subarray(44 + recipe.start_frame * 2, 44 + recipe.end_frame * 2));
    expect(adopted.project.assets[id].lineage).toEqual({
      source: {kind: "asset_artifact", artifact_sha256: digest(bytes), project_revision: baseline.project_revision},
      derivation: {kind: "capability_adoption", capability: set.capability, provider: set.provider,
        model_identity: set.model_identity, parameters_sha256: set.parameters_sha256,
        attempt_id: set.attempt_id, source_asset_id: sourceId, output_artifact: set.output_artifact, recipe: interval},
    });
  }
  expect(Object.entries(saved).find(([path]) => path.endsWith(`${digest(bytes)}.wav`))?.[1]).toEqual([...bytes]);
  await reopen(page);
  expect(await truth(page)).toEqual(adopted);
  expect(await files(page, projectId)).toEqual(saved);
  await page.getByRole("button", {name: "Slice", exact: true}).click();
  await page.getByRole("combobox", {name: "Slice source"}).selectOption(sourceId);
  await page.getByRole("button", {name: "Discard slices"}).click();
  await expect(page.getByText("No active slices. Retry analysis to create a new result.")).toBeVisible();
  expect(await truth(page)).toEqual(adopted);
  expect(await files(page, projectId)).toEqual(saved);
});

test("Creator Slice UI shows successful zero-onset without a whole-source fallback", async ({page}) => {
  const {baseline, set} = await start(page, true);
  expect(set.recipes).toEqual([]);
  await expect(page.getByText("Analysis complete. No slices detected.")).toBeVisible();
  await expect(page.getByRole("button", {name: "Add target"})).toHaveCount(0);
  expect(await truth(page)).toEqual(baseline);
  await reopen(page);
  expect(await truth(page)).toEqual(baseline);
});

for (const refusal of ["stale revision", "missing source", "discarded set"]) {
  test(`Creator Slice UI ${refusal} refusal preserves every Pad and Project revision`, async ({page}) => {
    const {baseline, set, job, bytes} = await start(page);
    await target(page, 1, set.recipes[1].candidate_id, 0);
    if (refusal === "stale revision") await addSource(page, otherSourceId, true);
    const before = await truth(page);
    const originalFiles = await files(page, baseline.project.project_id);
    if (refusal === "missing source") await files(page, baseline.project.project_id, digest(bytes));
    if (refusal === "discarded set") {
      await page.evaluate(async ({jobId, setId}) => window.lmdjWebRuntimeHost.candidates.discardCandidateSet(jobId, setId),
        {jobId: job.job_id, setId: set.set_id});
    }
    const saved = await files(page, baseline.project.project_id);
    await page.getByRole("button", {name: "Adopt selected slices"}).click();
    await expect.poll(async () => (await evidence(page, "candidate.adopt")).length).toBe(1);
    await expect(page.getByText(/previous request may have committed/)).toBeVisible();
    const result = (await last(page, "candidate.adopt")).response;
    expect(result.ok).toBe(false);
    if (refusal === "stale revision") expect(result.error.code).toBe("REVISION_CONFLICT");
    if (refusal === "discarded set") {
      expect(result.error.code).toBe("NOT_FOUND");
      // Web's normalized envelope retains the code and redacts Core details.
      expect(result.error.details).toEqual({});
    }
    if (refusal === "missing source") {
      expect(result.error.code).toBe("NOT_FOUND");
      // Project inspection validates all source bytes; complete persisted-file
      // equality is the far-side Truth assertion until the fault is repaired.
      expect((await send(page, "project.inspect")).error.code).toBe("INVALID_PROJECT");
    } else expect(await truth(page)).toEqual(before);
    expect(await files(page, baseline.project.project_id)).toEqual(saved);
    expect(await evidence(page, "candidate.adopt")).toHaveLength(1);
    if (refusal === "missing source") await restoreSource(page, originalFiles, digest(bytes));
    expect(await truth(page)).toEqual(before);
    await page.getByRole("button", {name: "Refresh slices and Project"}).click();
    await expect(page.getByText(/previous request may have committed/)).toHaveCount(0);
    expect(await evidence(page, "candidate.adopt")).toHaveLength(1);
    expect(await truth(page)).toEqual(before);
    await reopen(page);
    expect(await truth(page)).toEqual(before);
    expect(await files(page, baseline.project.project_id)).toEqual(
      refusal === "missing source" ? originalFiles : saved);
  });
}

// Read the real AudioWorklet output through a standard Web Audio analyser.
// The original connection and all Runtime messages remain untouched.
async function observePadAudio(page) {
  await page.addInitScript(() => {
    const connect = AudioNode.prototype.connect;
    const attached = new WeakSet();
    window.__padAudio = {min: 0, max: 0};
    AudioNode.prototype.connect = function (...args) {
      const result = connect.apply(this, args);
      if (this instanceof AudioWorkletNode && !attached.has(this)) {
        attached.add(this);
        const analyser = this.context.createAnalyser();
        analyser.fftSize = 2048;
        const mute = this.context.createGain();
        mute.gain.value = 0;
        connect.call(this, analyser);
        connect.call(analyser, mute);
        connect.call(mute, this.context.destination);
        const samples = new Float32Array(analyser.fftSize);
        setInterval(() => {
          analyser.getFloatTimeDomainData(samples);
          for (const value of samples) {
            window.__padAudio.min = Math.min(window.__padAudio.min, value);
            window.__padAudio.max = Math.max(window.__padAudio.max, value);
          }
        }, 10);
      }
      return result;
    };
  });
}
for (const bank of [0, 1]) {
  test(`Creator adoption publishes playable audio immediately into ${bank === 0 ? "occupied A1" : "empty B1"}`, async ({page}) => {
    await observePadAudio(page);
    const {set} = await start(page);
    // Keep the recorded Pattern as preservation evidence, but select an empty
    // one for this isolated Pad-output assertion. The recorded A1 loop would
    // otherwise legitimately mix its negative PCM into the adopted B1 audio.
    const originalPatterns = (await truth(page)).project.patterns;
    await page.getByRole("button", {name: "Sequence", exact: true}).click();
    const pattern = page.getByRole("combobox", {name: "Pattern", exact: true});
    await page.getByRole("button", {name: "Create Pattern", exact: true}).click();
    await expect(pattern.locator("option")).toHaveCount(2);
    const emptyId = await pattern.locator("option").evaluateAll((options, originals) =>
      options.map(option => option.value).find(value => !Object.hasOwn(originals, value)), originalPatterns);
    await pattern.selectOption(emptyId);
    await expect(pattern).toHaveValue(emptyId);
    const patterns = (await truth(page)).project.patterns;
    expect(patterns[emptyId].events).toEqual([]);
    for (const [id, recorded] of Object.entries(originalPatterns)) expect(patterns[id]).toEqual(recorded);
    await page.getByRole("button", {name: "Slice", exact: true}).click();
    await page.getByRole("combobox", {name: "Slice source"}).selectOption(sourceId);
    // Prepare this Pattern while stopped: a live Pattern change deliberately
    // takes effect at a later musical boundary, after Bank acknowledgement.
    await page.getByRole("button", {name: "Refresh slices and Project"}).click();
    await expect.poll(async () => success((await last(page, "snapshot.reload")).response).pattern_id).toBe(emptyId);
    await page.getByRole("button", {name: "Activate audio"}).click();
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
    await target(page, 1, set.recipes[1].candidate_id, 0, bank);
    await page.getByRole("button", {name: "Adopt selected slices"}).click();
    await expect(page.getByText("Adopted 1 slices.")).toBeVisible();
    await page.getByRole("button", {name: "Project", exact: true}).click();
    const letter = bank === 0 ? "A" : "B";
    await page.getByRole("button", {name: `Bank ${letter}`, exact: true}).click();
    await page.evaluate(() => {window.__padAudio = {min: 0, max: 0};});
    await page.getByRole("button", {name: new RegExp(`^Pad ${letter}1 — assigned`)}).click();
    await expect.poll(() => page.evaluate(() => window.__padAudio.max)).toBeGreaterThan(0.01);
    // Old A1 is negative PCM; old B1 is silent. Neither can satisfy this.
    expect(await page.evaluate(() => window.__padAudio.min)).toBeGreaterThan(-0.01);
    expect(await evidence(page, "candidate.adopt")).toHaveLength(1);
    expect((await truth(page)).project.patterns).toEqual(patterns);
  });
}


test("Creator adoption prepares the selected non-current Pattern", async ({page}) => {
  const {set} = await start(page);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  const pattern = page.getByRole("combobox", {name: "Pattern", exact: true});
  const original = await pattern.inputValue();
  await page.getByRole("button", {name: "Create Pattern", exact: true}).click();
  await expect(pattern.locator("option")).toHaveCount(2);
  const selected = await pattern.locator("option").evaluateAll((options, original) =>
    options.map(option => option.value).find(value => value !== original), original);
  await pattern.selectOption(selected);
  await expect(pattern).toHaveValue(selected);
  await page.getByRole("button", {name: "Slice", exact: true}).click();
  await page.getByRole("combobox", {name: "Slice source"}).selectOption(sourceId);
  await target(page, 1, set.recipes[1].candidate_id, 0, 1);
  await page.getByRole("button", {name: "Adopt selected slices"}).click();
  await expect(page.getByText("Adopted 1 slices.")).toBeVisible();
  const publication = await last(page, "snapshot.reload");
  expect(publication.payload.pattern_id).toBe(selected);
  expect(success(publication.response).runtime_ready).toBe(true);
  await expect(page.getByRole("region", {name: "Project audio status"})).toHaveCount(0);
  expect(await evidence(page, "candidate.adopt")).toHaveLength(1);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  await expect(pattern).toHaveValue(selected);
});
