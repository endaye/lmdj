import {readFile} from "node:fs/promises";

import {expect} from "@playwright/test";

// Shared Perform-surface helpers: the recording lifecycle, the deterministic
// witness PCM and the WAV parse the Perform and metronome journeys both assert
// on. A bounded recording or audio transition shares the same budget
// everywhere, so the timeouts live here too.
export const AUDIO_TRANSITION_TIMEOUT_MS = 35_000;
export const PROJECT_TRANSITION_TIMEOUT_MS = 125_000;

export async function openPerform(page) {
  const perform = page.getByRole("button", {name: "Perform"});
  await expect(perform).toBeEnabled({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await perform.click();
  await expect(page.getByRole("main", {name: "Perform"})).toBeVisible();
  await expect(page.getByRole("button", {name: /^Launch Pattern /}))
    .toHaveCount(16);
}

export async function beginRecording(page) {
  await page.getByRole("button", {name: "Record Performance"}).click();
  const status = page.getByRole("status", {name: "Performance recording status"});
  await expect(status).toContainText("recording", {
    timeout: PROJECT_TRANSITION_TIMEOUT_MS,
  });
  return status;
}

export async function stopRecording(page) {
  await page.getByRole("button", {name: "Stop Performance"}).click();
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("sealed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
}

function deterministicPcm16Sample(frame, channel) {
  return Math.round((((frame + channel * 17) % 97) / 96 * 2 - 1) * 24_000);
}

export function pcm16Wav({frames = 4_800, sampleRate = 48_000, channels = 1} = {}) {
  const bytes = Buffer.alloc(44 + frames * channels * 2);
  bytes.write("RIFF", 0, "ascii");
  bytes.writeUInt32LE(bytes.length - 8, 4);
  bytes.write("WAVE", 8, "ascii");
  bytes.write("fmt ", 12, "ascii");
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20);
  bytes.writeUInt16LE(channels, 22);
  bytes.writeUInt32LE(sampleRate, 24);
  bytes.writeUInt32LE(sampleRate * channels * 2, 28);
  bytes.writeUInt16LE(channels * 2, 32);
  bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36, "ascii");
  bytes.writeUInt32LE(frames * channels * 2, 40);
  for (let frame = 0; frame < frames; frame += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      const value = deterministicPcm16Sample(frame, channel);
      bytes.writeInt16LE(value, 44 + (frame * channels + channel) * 2);
    }
  }
  return bytes;
}

export function parsePcm16StereoWav(bytes) {
  expect(bytes.subarray(0, 4).toString("ascii")).toBe("RIFF");
  expect(bytes.readUInt32LE(4)).toBe(bytes.byteLength - 8);
  expect(bytes.subarray(8, 12).toString("ascii")).toBe("WAVE");
  expect(bytes.subarray(12, 16).toString("ascii")).toBe("fmt ");
  expect(bytes.readUInt32LE(16)).toBe(16);
  expect(bytes.readUInt16LE(20)).toBe(1);
  expect(bytes.readUInt16LE(22)).toBe(2);
  expect(bytes.readUInt32LE(24)).toBe(48_000);
  expect(bytes.readUInt32LE(28)).toBe(192_000);
  expect(bytes.readUInt16LE(32)).toBe(4);
  expect(bytes.readUInt16LE(34)).toBe(16);
  expect(bytes.subarray(36, 40).toString("ascii")).toBe("data");
  expect(bytes.readUInt32LE(40)).toBe(bytes.byteLength - 44);
  expect((bytes.byteLength - 44) % 4).toBe(0);
  return {
    frames: (bytes.byteLength - 44) / 4,
    left: Array.from({length: (bytes.byteLength - 44) / 4}, (_, frame) =>
      bytes.readInt16LE(44 + frame * 4)),
    right: Array.from({length: (bytes.byteLength - 44) / 4}, (_, frame) =>
      bytes.readInt16LE(46 + frame * 4)),
  };
}

export function firstSignalFrame(channel, from = 0) {
  const frame = channel.findIndex((sample, index) =>
    index >= from && Math.abs(sample) > 256);
  if (frame < 0) throw new Error(`No master-output signal after frame ${from}`);
  return frame;
}

export async function exportPerformanceWav(page) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export Performance WAV"}).click();
  return readFile(await (await pending).path());
}

export async function installPerformWitnessSample(page) {
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await page.getByTestId("physical-controls").getByRole("button", {name: "Bank A", exact: true}).click();
  const pad = page.getByRole("button", {name: /^Pad A01 — assigned — Key Q$/});
  await expect(pad).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await pad.evaluate((element) => element.click());
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Replace Sample"}).click();
  await (await chooser).setFiles({
    name: "perform-master-witness-stereo.wav",
    mimeType: "audio/wav",
    buffer: pcm16Wav({channels: 2}),
  });
  await expect(page.getByRole("dialog", {name: "Replace Pad A01?"})).toBeVisible();
  await page.getByRole("button", {name: "Confirm replace"}).click();
  await expect(page.getByRole("button", {name: "Replace Sample"}))
    .toBeEnabled({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await expect(page.locator(".selected-sample"))
    .toContainText("48 kHz · Mono · 4,800 frames");
  await openPerform(page);
}
