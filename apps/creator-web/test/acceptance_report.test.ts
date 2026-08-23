import {expect, test} from "vitest";

import {createAcceptanceReport} from "../src/report/acceptance_report";

const TEST_PRODUCT_BUILD = "9.8.7.6";

test("emits only deterministic privacy-safe acceptance facts", () => {
  const report = createAcceptanceReport({
    identity: {
      productBuild: TEST_PRODUCT_BUILD,
      hostId: "creator-web",
      hostVersion: "1.3.6",
      platformVersion: "0.3.4",
      protocolVersion: 1,
    },
    capabilities: {
      secureContext: true,
      crossOriginIsolated: true,
      sharedArrayBuffer: true,
      webAssembly: true,
      audioWorklet: true,
      opfs: true,
      opfsSyncAccessHandle: true,
      opfsWritableReplace: true,
      webMidi: false,
    },
    diagnostics: {
      state: "running",
      error_code: null,
      trigger_admitted_count: 32,
      trigger_outcome_count: 31,
      trigger_rejected_count: 1,
      project_id: "11111111-1111-4111-8111-111111111111",
      absolute_path: "/Users/private/Music/beat.wav",
      midi_device_name: "Private Controller",
      project: {contract: "lmdj.project.v2", banks: [], assets: {}},
      waveform_buckets: [16_384, 32_768],
      audio_bytes: [82, 73, 70, 70],
    },
    sampleEvidence: {
      projectRevision: 9,
      runtimeRevision: 8,
      operationOutcomes: [
        {operation: "replace", outcome: "committed", errorCode: null},
        {operation: "prepare", outcome: "failed", errorCode: "COOK_FAILED"},
      ],
      triggerModeCoverage: ["one_shot", "gate", "loop_gate", "loop_toggle"],
      sourceFileName: "private-source.wav",
      opfsPath: "/private/opfs/sample.wav",
      projectJson: {contract: "lmdj.project.v2"},
      waveformBuckets: [16_384, 32_768],
      audioBytes: new Uint8Array([82, 73, 70, 70]),
    },
    bankCount: 4,
    padCount: 64,
  });

  expect(report).toEqual({
    contract: "lmdj.creator-web.acceptance.v1",
    product_build: TEST_PRODUCT_BUILD,
    host_id: "creator-web",
    host_version: "1.3.6",
    platform_version: "0.3.4",
    protocol_version: 1,
    capabilities: {
      secure_context: true,
      cross_origin_isolated: true,
      shared_array_buffer: true,
      web_assembly: true,
      audio_worklet: true,
      opfs: true,
      opfs_sync_access_handle: true,
      opfs_writable_replace: true,
      web_midi: false,
    },
    state: "running",
    bank_count: 4,
    pad_count: 64,
    trigger_admitted_count: 32,
    trigger_outcome_count: 31,
    trigger_rejected_count: 1,
    error_code: null,
    sample: {
      project_revision: 9,
      runtime_revision: 8,
      operation_outcomes: [
        {operation: "replace", outcome: "committed", error_code: null},
        {operation: "prepare", outcome: "failed", error_code: "COOK_FAILED"},
      ],
      trigger_mode_coverage: ["one_shot", "gate", "loop_gate", "loop_toggle"],
    },
    physical: {
      macos_safari_pointer: "deferred / unverified",
      macos_chrome_pointer: "deferred / unverified",
      macos_chrome_physical_midi: "deferred / unverified",
      ipados_safari_touch: "deferred / unverified",
      ipados_safari_lifecycle: "deferred / unverified",
    },
  });
  const serialized = JSON.stringify(report);
  expect(serialized).not.toContain("11111111");
  expect(serialized).not.toContain("/Users/private");
  expect(serialized).not.toContain("Private Controller");
  expect(serialized).not.toContain("private-source.wav");
  expect(serialized).not.toContain("/private/opfs");
  expect(serialized).not.toContain("lmdj.project.v2");
  expect(serialized).not.toContain("16384");
  expect(serialized).not.toContain("82,73,70,70");
});
