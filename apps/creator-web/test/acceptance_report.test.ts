import {expect, test} from "vitest";

import {createAcceptanceReport} from "../src/report/acceptance_report";

test("emits only deterministic privacy-safe acceptance facts", () => {
  const report = createAcceptanceReport({
    identity: {
      productBuild: "1.0.16.5",
      hostId: "creator-web",
      hostVersion: "1.0.2",
      platformVersion: "0.1.2",
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
    },
    bankCount: 4,
    padCount: 64,
  });

  expect(report).toEqual({
    contract: "lmdj.creator-web.acceptance.v1",
    product_build: "1.0.16.5",
    host_id: "creator-web",
    host_version: "1.0.2",
    platform_version: "0.1.2",
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
});
