import {createHash} from "node:crypto";
import {expect, test} from "@playwright/test";

const projectId = "00000000-0000-4000-8000-000000000001";
const patternId = "00000000-0000-4000-8000-000000000002";
const assetId = "00000000-0000-4000-8000-000000000004";
const commandId = "00000000-0000-4000-8000-000000000003";
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
function wav(silent = false) {
  const frames = 144000;
  const bytes = Buffer.alloc(44 + frames * 2);
  bytes.write("RIFF"); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(48000, 24); bytes.writeUInt32LE(96000, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36); bytes.writeUInt32LE(frames * 2, 40);
  if (!silent) for (let frame = 1; frame < frames; frame++) bytes.writeInt16LE(5000, 44 + frame * 2);
  return bytes;
}
async function start(page) {
  await page.goto("/index.html");
  await page.waitForFunction(() => Boolean(window.lmdjWebRuntimeHost?.candidates));
}
async function send(page, operation, payload = {}, bytes) {
  return page.evaluate(async ({operation, payload, bytes}) =>
    window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
      request_id: crypto.randomUUID(), operation, payload},
    bytes ? {sidecar: new Uint8Array(bytes)} : undefined),
  {operation, payload, bytes: bytes ? [...bytes] : undefined});
}
async function call(page, group, method, ...args) {
  return page.evaluate(async ({group, method, args}) => {
    try { return {ok: true, result: await window.lmdjWebRuntimeHost[group][method](...args)}; }
    catch (error) { return {ok: false, error: {code: error.code, details: error.details}}; }
  }, {group, method, args});
}
const candidate = (page, method, ...args) => call(page, "candidates", method, ...args);
const provider = (page, method, ...args) => call(page, "providers", method, ...args);
function success(response) {
  expect(response, JSON.stringify(response)).toHaveProperty("ok", true);
  return response.result;
}
// Bundle reads and mutation are test evidence/fault injection only.
// Every authoring operation goes through the packaged public Host transport.
async function files(page, corrupt = false) {
  return page.evaluate(async ({projectId, corrupt}) => {
    const result = {};
    async function visit(directory, prefix = "") {
      for await (const [name, handle] of directory.entries()) {
        const path = `${prefix}/${name}`;
        if (handle.kind === "directory") { await visit(handle, path); continue; }
        if (!path.includes(`${projectId}.lmdj/`)) continue;
        const bytes = new Uint8Array(await (await handle.getFile()).arrayBuffer());
        if (corrupt && name.endsWith(".wav")) {
          bytes[bytes.length - 1] ^= 1;
          const writer = await handle.createWritable(); await writer.write(bytes); await writer.close();
        }
        result[path] = [...bytes];
      }
    }
    await visit(await navigator.storage.getDirectory());
    return result;
  }, {projectId, corrupt});
}
async function setup(page, silent = false, host) {
  await start(page);
  if (host === "Web Runtime Host") {
    expect(await page.evaluate(() => window.lmdjWebRuntimeController.loadDiagnosticProject())).toBe(true);
    await expect(page.locator("#diagnostic-project-state")).toHaveText("ready");
  }
  success(await send(page, "project.create", {project_id: projectId, bpm: 120,
    initial_pattern: {pattern_id: patternId, bars: 1, events: [
      {onset_tick: 0, duration_tick: 240, slot: {bank: 0, pad: 0}, velocity: 100}]}}));
  const bytes = wav(silent);
  const imported = success(await send(page, "asset.import", {
    command_id: commandId, expected_revision: 0, asset_id: assetId, media_type: "audio/wav",
    sidecar: {sidecar_bytes: bytes.length, sidecar_sha256: digest(bytes)},
  }, bytes));
  expect(imported.artifact).toEqual({sha256: digest(bytes), byte_length: bytes.length, media_type: "audio/wav"});
  success(await send(page, "pad.assign", {command_id: "00000000-0000-4000-8000-000000000019",
    expected_revision: 1, slot: {bank: 0, pad: 0}, asset_id: assetId}));
  if (host === "Creator Web") {
    success(await send(page, "host.close"));
    await start(page);
    await page.getByRole("button", {name: "Open local", exact: true}).click();
    await page.getByRole("button", {name: "Open Project 00000000", exact: true}).click();
    try {
      await expect(page.getByRole("heading", {name: "Project 00000000", exact: true})).toBeVisible();
    } catch (error) {
      const download = page.waitForEvent("download");
      await page.getByRole("button", {name: "Export report", exact: true}).click();
      const report = await download;
      await report.saveAs(test.info().outputPath("creator-open-report.json"));
      throw error;
    }
  }
  success(await provider(page, "configureProviderPermissions", ["sample.slice.execute"]));
  expect(success(await provider(page, "listProviders")).granted_permissions).toEqual(["sample.slice.execute"]);
  success(await provider(page, "selectProvider", "sample.slice.v1", "local.sample.slice"));
  return {bytes, imported, truth: success(await send(page, "project.inspect"))};
}
const runRequest = (attemptId = "slice-first") => ({job_id: "browser-slice", attempt_id: attemptId,
  project_id: projectId, asset_id: assetId, expected_revision: 2,
  parameters: {refractory_frames: 1}, data_classification: "public", platform: "test", region: "local",
  required_permissions: ["sample.slice.execute"]});
const selection = set => ({project_id: projectId, expected_revision: 2,
  job_id: "browser-slice", set_id: set.set_id, candidate_id: set.recipes[1].candidate_id});
const adoption = set => { const {candidate_id, ...request} = selection(set); return {...request,
  command_id: "00000000-0000-4000-8000-000000000005",
  selections: [{candidate_id, bank: 0, pad: 1}, {candidate_id, bank: 2, pad: 3}]}; };

// The full journey ran 32.8 s on the trusted pool's Web Runtime Host lane
// (run 35419357786) against Playwright's 30 s default, which no measurement
// had ever set; Creator finishes the same legs in 20.7 s. 60 s is that
// measurement with headroom, not a target: the journey keeps every leg.
const CANDIDATE_JOURNEY_TIMEOUT_MS = 60_000;

export function registerCandidateJourneys(host) {
  test(`${host}: real Candidate preview, explicit adoption and restart preserve source and Pattern`, async ({page}) => {
    test.setTimeout(CANDIDATE_JOURNEY_TIMEOUT_MS);
    const {bytes, imported, truth} = await setup(page, false, host);
    const before = await files(page);
    const job = success(await candidate(page, "runCandidateJob", runRequest()));
    expect(success(await candidate(page, "inspectCandidateJob", "browser-slice"))).toEqual(job);
    const set = job.sets.find(value => value.set_id === job.active_set_id);
    expect(set.status).toBe("active");
    expect(JSON.stringify(job)).not.toContain("project_path");
    expect(set.recipes.map(({start_frame, end_frame}) => [start_frame, end_frame])).toEqual([[0, 1], [1, 144000]]);
    expect(await files(page)).toEqual(before);
    expect(success(await send(page, "project.inspect"))).toEqual(truth);
    success(await send(page, "project.open", {project_id: projectId, pattern_id: patternId}));
    expect(success(await candidate(page, "auditionCandidate", selection(set))).played).toBe(false);
    if (host === "Creator Web") {
      await page.getByRole("button", {name: "Activate audio"}).click();
      await expect(page.getByTestId("audio-state")).toHaveText("Audio running");
    } else {
      await page.locator("#audio-activate").click();
      await expect(page.locator("#host-state")).toHaveText("running");
    }
    const preview = success(await candidate(page, "auditionCandidate", selection(set)));
    expect(preview).toMatchObject({played: true, sample_rate: 48000, channels: 1, source_frames: 143999, project_revision: 2});
    expect(success(await candidate(page, "stopCandidateAudition"))).toMatchObject({accepted: true});
    expect(await files(page)).toEqual(before);
    expect(success(await send(page, "project.inspect"))).toEqual(truth);
    const adopted = success(await candidate(page, "adoptCandidates", adoption(set)));
    expect(adopted.project_revision).toBe(3);
    expect(adopted.adopted).toHaveLength(2);
    expect(new Set(adopted.adopted.map(value => value.asset_id)).size).toBe(2);
    const after = success(await send(page, "project.inspect"));
    expect(after.project.patterns).toEqual(truth.project.patterns);
    expect(after.project.assets[assetId]).toEqual(truth.project.assets[assetId]);
    expect(Object.keys(after.project.assets)).toHaveLength(3);
    const committed = await files(page);
    const source = Object.entries(committed).find(([path]) => path.endsWith(`/${imported.artifact.sha256}.wav`));
    expect(Buffer.from(source[1])).toEqual(bytes);
    for (const target of adopted.adopted) {
      expect(after.project.banks[target.bank].pads[target.pad].asset_id).toBe(target.asset_id);
      const asset = after.project.assets[target.asset_id];
      const blob = Buffer.from(Object.entries(committed).find(([path]) => path.endsWith(`/${asset.artifact.sha256}.wav`))[1]);
      expect(asset.artifact).toEqual({sha256: digest(blob), byte_length: blob.length, media_type: "audio/wav"});
      expect(blob.length).toBe(44 + 143999 * 2);
      expect(blob.subarray(44)).toEqual(bytes.subarray(46));
      expect(asset.lineage.source).toEqual({kind: "asset_artifact", artifact_sha256: imported.artifact.sha256, project_revision: 2});
      const {candidate_id, ...recipe} = set.recipes[1];
      expect(asset.lineage.derivation).toEqual({kind: "capability_adoption", capability: set.capability,
        provider: set.provider, model_identity: null, parameters_sha256: set.parameters_sha256,
        attempt_id: set.attempt_id, source_asset_id: assetId, output_artifact: set.output_artifact, recipe});
    }
    const stale = await candidate(page, "adoptCandidates", adoption(set));
    expect(stale.error.code).toBe("REVISION_CONFLICT");
    expect(await files(page)).toEqual(committed);
    expect(success(await send(page, "project.inspect"))).toEqual(after);
    success(await candidate(page, "discardCandidateSet", "browser-slice", set.set_id));
    expect(await files(page)).toEqual(committed);
    // Suspend through the owning session so its AudioContext and control lane
    // complete quiescence before the explicit Host close/reopen boundary.
    await page.getByRole("button", {name: "Suspend audio", exact: true}).click();
    if (host === "Creator Web") await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended");
    else await expect(page.locator("#host-state")).toHaveText("audio-suspended");
    success(await send(page, "host.close"));
    await start(page);
    const restored = success(await candidate(page, "inspectCandidateJob", "browser-slice"));
    expect(restored.sets.find(value => value.set_id === set.set_id).status).toBe("discarded");
    success(await send(page, "project.open", {project_id: projectId, pattern_id: patternId}));
    expect(success(await send(page, "project.inspect"))).toEqual(after);
    expect(await files(page)).toEqual(committed);
    success(await send(page, "host.close"));
  });
  test(`${host}: no-onset success has zero recipes and leaves authoring unchanged`, async ({page}) => {
    const {truth} = await setup(page, true, host);
    const before = await files(page);
    const job = success(await candidate(page, "runCandidateJob", runRequest()));
    expect(job.sets.find(value => value.set_id === job.active_set_id).recipes).toEqual([]);
    expect(await files(page)).toEqual(before);
    expect(success(await send(page, "project.inspect"))).toEqual(truth);
    success(await send(page, "host.close"));
    await start(page);
    expect(success(await candidate(page, "inspectCandidateJob", "browser-slice"))).toEqual(job);
    success(await send(page, "project.open", {project_id: projectId, pattern_id: patternId}));
    expect(success(await send(page, "project.inspect"))).toEqual(truth);
    success(await send(page, "host.close"));
  });
  for (const refusal of ["stale", "discarded", "superseded", "corrupt"]) {
    test(`${host}: Candidate ${refusal} refuses preview/adoption without authoring changes`, async ({page}) => {
      await setup(page, false, host);
      const job = success(await candidate(page, "runCandidateJob", runRequest()));
      const set = job.sets.find(value => value.set_id === job.active_set_id);
      if (refusal === "discarded") success(await candidate(page, "discardCandidateSet", "browser-slice", set.set_id));
      if (refusal === "superseded") success(await candidate(page, "runCandidateJob", runRequest("slice-second")));
      const before = await files(page, refusal === "corrupt");
      const truth = await send(page, "project.inspect");
      const preview = selection(set), adopt = adoption(set);
      if (refusal === "stale") {preview.expected_revision = 0; adopt.expected_revision = 0;}
      for (const [method, request] of [["auditionCandidate", preview], ["adoptCandidates", adopt]]) {
        const response = await candidate(page, method, request);
        expect(response.ok).toBe(false);
        expect(response.error.code).toBe(refusal === "stale" ? "REVISION_CONFLICT" : refusal === "corrupt" ? "COOK_FAILED" : "NOT_FOUND");
        expect(await files(page)).toEqual(before);
        const current = await send(page, "project.inspect");
        expect({ok: current.ok, result: current.result, error: current.error}).toEqual({ok: truth.ok, result: truth.result, error: truth.error});
      }
      success(await send(page, "host.close"));
      await start(page);
      expect(await files(page)).toEqual(before);
      expect(success(await candidate(page, "inspectCandidateJob", "browser-slice")).sets).toHaveLength(refusal === "superseded" ? 2 : 1);
      success(await send(page, "host.close"));
    });
  }
}
