import {createHash} from "node:crypto";
import {expect, test} from "@playwright/test";

const projectId = "00000000-0000-4000-8000-000000000001";
const patternId = "00000000-0000-4000-8000-000000000002";
const assetId = "00000000-0000-4000-8000-000000000004";
const otherId = "00000000-0000-4000-8000-000000000099";
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
function wav() {
  const bytes = Buffer.alloc(54);
  bytes.write("RIFF"); bytes.writeUInt32LE(46, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(48000, 24); bytes.writeUInt32LE(96000, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36); bytes.writeUInt32LE(10, 40);
  bytes.writeInt16LE(5000, 46); bytes.writeInt16LE(8000, 50);
  return bytes;
}
async function start(page) {
  await page.goto("/index.html");
  await page.waitForFunction(() => Boolean(window.lmdjWebRuntimeHost?.providers));
}
async function send(page, operation, payload = {}, bytes) {
  return page.evaluate(async ({operation, payload, bytes}) => {
    return window.lmdjWebRuntimeHost.transport.send({protocol_version: 1,
      request_id: crypto.randomUUID(), operation, payload},
    bytes ? {sidecar: new Uint8Array(bytes)} : undefined);
  }, {operation, payload, bytes: bytes ? [...bytes] : undefined});
}
async function provider(page, method, ...args) {
  return page.evaluate(async ({method, args}) => {
    try { return {ok: true, result: await window.lmdjWebRuntimeHost.providers[method](...args)}; }
    catch (error) { return {ok: false, error: {code: error.code, details: error.details}}; }
  }, {method, args});
}
function success(response) { expect(response, JSON.stringify(response)).toHaveProperty("ok", true); return response.result; }
// Read OPFS only for test evidence and deliberate source-byte fault injection.
// All product operations, including import, use the packaged public Host.
async function projectFiles(page, mutation) {
  return page.evaluate(async ({projectId, mutation}) => {
    const files = {};
    async function visit(directory, prefix = "") {
      for await (const [name, handle] of directory.entries()) {
        const path = `${prefix}/${name}`;
        if (handle.kind === "directory") { await visit(handle, path); continue; }
        if (!path.includes(`${projectId}.lmdj/`)) continue;
        let bytes = new Uint8Array(await (await handle.getFile()).arrayBuffer());
        if (mutation && name.endsWith(".wav")) {
          if (mutation === "missing-file") { await directory.removeEntry(name); continue; }
          if (mutation === "changed-length") bytes = new Uint8Array([...bytes, 1]);
          else bytes[bytes.length - 1] ^= 1;
          const writer = await handle.createWritable(); await writer.write(bytes); await writer.close();
        }
        files[path] = [...bytes];
      }
    }
    await visit(await navigator.storage.getDirectory());
    return files;
  }, {projectId, mutation});
}

async function outputBytes(page, attemptId, sha256) {
  return page.evaluate(async ({attemptId, sha256}) => {
    let directory = await navigator.storage.getDirectory();
    for (const part of [".lmdj-workspace", "attempts", attemptId, "artifacts"]) {
      directory = await directory.getDirectoryHandle(part);
    }
    const file = await (await directory.getFileHandle(sha256)).getFile();
    return [...new Uint8Array(await file.arrayBuffer())];
  }, {attemptId, sha256});
}

export function registerProviderOwnerJourneys(host) {
  test(`${host}: competing Project owner rejects admission without an Attempt`, async ({page, context}) => {
    await start(page);
    success(await send(page, "project.create", {project_id: projectId, bpm: 120,
      initial_pattern: {pattern_id: patternId, bars: 1, events: []}}));
    const observer = await context.newPage();
    await start(observer);
    success(await provider(observer, "selectProvider", "sample.slice.v1", "local.sample.slice"));
    const refused = await send(observer, "project.open", {project_id: projectId, pattern_id: patternId});
    expect(refused.ok).toBe(false);
    expect(refused.error.code).toBe("PROJECT_BUSY");
    expect((await provider(observer, "inspectAttempt", "never-admitted")).error.code).toBe("NOT_FOUND");
    success(await send(page, "host.close"));
    success(await send(observer, "project.open", {project_id: projectId, pattern_id: patternId}));
    expect(success(await send(observer, "project.inspect")).project_revision).toBe(0);
    success(await send(observer, "host.close"));
    await observer.close();
  });
  for (const mode of ["success", "permission", "missing-owner", "wrong-project", "wrong-asset",
    "wrong-reference", "corrupt", "changed-length", "missing-file", "malformed-owner"]) {
    test(`${host}: Provider owner ${mode} survives a real Host restart`, async ({page}) => {
      await start(page);
      expect(success(await provider(page, "listProviders")).providers).toHaveLength(3);
      success(await send(page, "project.create", {project_id: projectId, bpm: 120,
        initial_pattern: {pattern_id: patternId, bars: 1, events: []}}));
      const bytes = wav();
      const imported = success(await send(page, "asset.import", {
        command_id: "00000000-0000-4000-8000-000000000003", expected_revision: 0,
        asset_id: assetId, media_type: "audio/wav",
        sidecar: {sidecar_bytes: bytes.length, sidecar_sha256: digest(bytes)},
      }, bytes));
      expect(imported.artifact).toEqual({sha256: digest(bytes), byte_length: bytes.length, media_type: "audio/wav"});
      const truth = success(await send(page, "project.inspect"));
      const request = {attempt_id: `browser-${mode}`, capability: "sample.slice.v1",
        inputs: [{port: "source_audio", artifact: imported.artifact}],
        input_owners: [{port: "source_audio", occurrence: 0, project_id: projectId, asset_id: assetId}],
        parameters: {refractory_frames: 1}, data_classification: "public", platform: "test", region: "local",
        required_permissions: ["sample.slice.execute"]};
      if (mode !== "permission") success(await provider(page, "configureProviderPermissions", ["sample.slice.execute"]));
      success(await provider(page, "selectProvider", "sample.slice.v1", "local.sample.slice"));
      if (mode === "missing-owner") delete request.input_owners;
      if (mode === "wrong-project") request.input_owners[0].project_id = otherId;
      if (mode === "wrong-asset") request.input_owners[0].asset_id = otherId;
      if (mode === "wrong-reference") request.inputs[0].artifact = {...imported.artifact, sha256: "a".repeat(64)};
      if (mode === "malformed-owner") request.input_owners[0].project_path = "/forbidden";
      const originalFiles = await projectFiles(page);
      const damaged = ["corrupt", "changed-length", "missing-file"].includes(mode);
      const files = await projectFiles(page, damaged ? mode : undefined);
      expect(Object.keys(files).length).toBeGreaterThan(0);
      if (mode === "success") {
        // Real origin-scoped lock contention must stop publication before
        // reserving the ID. Release and retry the same ID on the same Host.
        await page.evaluate(() => new Promise((resolve) => {
          navigator.locks.request("lmdj-provider-workspace:/lmdj-workspace", async () => {
            await new Promise((release) => { window.releaseProviderProofLock = release; resolve(); });
          });
        }));
        const busy = await provider(page, "runProvider", request);
        expect(busy.error.code).toBe("IO_ERROR");
        expect((await provider(page, "inspectAttempt", request.attempt_id)).error.code).toBe("NOT_FOUND");
        await page.evaluate(async () => {
          window.releaseProviderProofLock();
          await navigator.locks.request("lmdj-provider-workspace:/lmdj-workspace", () => {});
          delete window.releaseProviderProofLock;
        });
      }
      const result = await provider(page, "runProvider", request);
      if (mode === "success") {
        const output = Buffer.from(JSON.stringify({contract: "lmdj.slice-points.v1", frame_rate: 48000,
          points: [{frame: 1}, {frame: 3}], source_sha256: imported.artifact.sha256}));
        expect(success(result).outputs).toEqual([{port: "slice_points", artifact: {
          sha256: digest(output), byte_length: output.length, media_type: "application/json"}}]);
        expect(Buffer.from(await outputBytes(page, request.attempt_id, digest(output)))).toEqual(output);
      } else {
        expect(result.ok).toBe(false);
        if (mode !== "malformed-owner") {
          expect(result.error.code).toBe(mode === "permission" ? "PERMISSION_DENIED" :
            ["corrupt", "changed-length"].includes(mode) ? "IO_ERROR" : "NOT_FOUND");
          if (mode !== "permission") expect(result.error.details.reason).toBe(
            ["corrupt", "changed-length"].includes(mode) ? "input_artifact_mismatch" : "input_artifact_unavailable");
        }
      }
      expect(await projectFiles(page)).toEqual(files);
      const afterRun = await send(page, "project.inspect");
      if (damaged) expect(afterRun.error.code).toBe("INVALID_PROJECT");
      else expect(success(afterRun)).toEqual(truth);
      const terminal = await provider(page, "inspectAttempt", request.attempt_id);
      if (mode === "malformed-owner") expect(terminal.error.code).toBe("NOT_FOUND");
      else {
        const state = success(terminal);
        expect(state.status).toBe(mode === "success" ? "succeeded" : "failed");
        expect(state.request.inputs).toEqual(request.inputs);
        if (mode === "success") expect(state.candidate_outputs).toEqual(result.result.outputs);
        else { expect(state.candidate_outputs).toEqual([]); expect(state.minted_outputs).toEqual([]); }
        expect(JSON.stringify(state)).not.toContain("project_path");
      }
      success(await send(page, "host.close"));
      await start(page);
      expect(await provider(page, "inspectAttempt", request.attempt_id)).toEqual(terminal);
      expect(await projectFiles(page)).toEqual(files);
      if (damaged) {
        // Repair only after proving the unchanged failure terminal survived
        // restart with the damaged source still present. Ordinary Project open
        // correctly requires valid source bytes, unlike Attempt inspection.
        await page.evaluate(async ({projectId, source, bytes}) => {
          let directory = await navigator.storage.getDirectory();
          for (const part of ["projects", `${projectId}.lmdj`, "assets"]) {
            directory = await directory.getDirectoryHandle(part);
          }
          const file = await directory.getFileHandle(`${source.sha256}.wav`, {create: true});
          const writer = await file.createWritable();
          await writer.write(new Uint8Array(bytes)); await writer.close();
        }, {projectId, source: imported.artifact, bytes: [...bytes]});
        expect(await projectFiles(page)).toEqual(originalFiles);
      }
      success(await send(page, "project.open", {project_id: projectId, pattern_id: patternId}));
      expect(success(await send(page, "project.inspect"))).toEqual(truth);
      if (mode === "success") {
        const published = result.result.outputs[0].artifact;
        const bytes = Buffer.from(await outputBytes(page, request.attempt_id, published.sha256));
        expect({sha256: digest(bytes), byte_length: bytes.length}).toEqual({sha256: published.sha256, byte_length: published.byte_length});
        const denied = await provider(page, "runProvider", {...request, attempt_id: "restart-no-grant"});
        expect(denied.error.code).toBe("PERMISSION_DENIED");
        expect(success(await send(page, "project.inspect"))).toEqual(truth);
      }
      success(await send(page, "host.close"));
    });
  }
}
