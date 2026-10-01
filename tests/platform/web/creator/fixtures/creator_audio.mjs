import {clickCreatorSystemAction} from "./creator_navigation.mjs";
import {expect} from "@playwright/test";

// A real accepted Pad gesture owns activation. Require its far-side admission
// before a caller starts counting its own subsequent musical journey.
export async function wakeAudioWithPad(page, {padAddress} = {}) {
  const selected = page.locator(".pad-grid button[aria-pressed='true']").first();
  const selectedLabel = await selected.count() ? await selected.getAttribute("aria-label") : null;
  const assigned = page.getByRole("button", {name: padAddress === undefined
    ? /Pad [A-D]\d+ — assigned — Key/ : new RegExp(`^Pad ${padAddress} — assigned — Key`)});
  let pad = null;
  let mode = null;
  for (const candidate of await assigned.all()) {
    const address = /Pad ([A-D])(\d+)/.exec(await candidate.getAttribute("aria-label"));
    const slot = {bank: address[1].charCodeAt(0) - 65, pad: Number(address[2]) - 1};
    const inspect = await page.evaluate(async slot => window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1, request_id: crypto.randomUUID(), operation: "sample.inspect", payload: {slot},
    }), slot);
    expect(inspect, JSON.stringify(inspect)).toHaveProperty("ok", true);
    if (!inspect.result.playback.muted && (pad === null || inspect.result.playback.trigger_mode === "one_shot")) {
      pad = candidate;
      mode = inspect.result.playback.trigger_mode;
      if (mode === "one_shot") break;
    }
  }
  if (pad !== null) {
    await page.evaluate(() => {
      const host = window.lmdjWebRuntimeHost;
      const transport = host.transport;
      const responses = [];
      window.__firstMusicalGestureResponses = responses;
      window.__firstMusicalVoiceEvents = [];
      const unsubscribe = transport.subscribe(message => {
        if (message.event === "runtime.voice_state") window.__firstMusicalVoiceEvents.push(...message.payload.events);
      });
      window.__restoreMusicalGestureTransport = () => {unsubscribe(); host.transport = transport;};
      host.transport = new Proxy({}, {get(_target, key) {
        const target = transport;
        if (key !== "send") return Reflect.get(target, key);
        return async (...args) => {
          const result = await target.send(...args);
          if (args[0]?.operation === "trigger" && args[0]?.payload?.velocity > 0) responses.push(result);
          return result;
        };
      }});
    });
    try {
      await pad.focus();
      if (mode !== "one_shot") await page.keyboard.down("Enter");
      else await page.keyboard.press("Enter");
      await expect.poll(() => page.evaluate(() => window.__firstMusicalGestureResponses.length),
        {timeout: 30_000}).toBe(1);
      const response = await page.evaluate(() => window.__firstMusicalGestureResponses[0]);
      expect(response, JSON.stringify(response)).toHaveProperty("ok", true);
      expect(response.result.sequence).toBeGreaterThan(0);
      await expect.poll(() => page.evaluate(sequence => window.__firstMusicalVoiceEvents
        .some(event => event.sequence === sequence && event.state === "started"), response.result.sequence),
        {timeout: 30_000}).toBe(true);
      if (mode !== "one_shot") await page.keyboard.up("Enter");
      const stopped = await page.evaluate(async () => window.lmdjWebRuntimeHost.transport.send({
        protocol_version: 1, request_id: crypto.randomUUID(), operation: "sample.stop", payload: {},
      }));
      expect(stopped, JSON.stringify(stopped)).toHaveProperty("ok", true);
      expect(stopped.result.scope).toBe("all");
      await expect.poll(() => page.evaluate(sequence => window.__firstMusicalVoiceEvents
        .some(event => event.sequence === sequence && ["stopped", "completed"].includes(event.state)), response.result.sequence),
        {timeout: 30_000}).toBe(true);
    } finally {
      // Preserve the original assertion failure if its browser context closed.
      await page.evaluate(() => window.__restoreMusicalGestureTransport()).catch(() => {});
    }
    if (selectedLabel !== null) {
      const original = page.getByRole("button", {name: selectedLabel, exact: true});
      if (await original.count()) await original.dispatchEvent("click", {detail: 1});
    }
    await page.evaluate(() => {window.__wakeAudioAdmissionCount = (window.__wakeAudioAdmissionCount ?? 0) + 1;});
  } else {
    // An unassigned Project has no sound to play; its explicit MIDI permission
    // click is still a genuine UI activation gesture, independent of Note data.
    await clickCreatorSystemAction(page, "Enable MIDI");
  }
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {timeout: 30_000});
}
