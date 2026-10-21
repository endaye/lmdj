import {createHash} from "node:crypto";
import {spawn} from "node:child_process";
import {mkdtemp, mkdir, rm, writeFile} from "node:fs/promises";
import {createServer} from "node:http";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {expect, test} from "@playwright/test";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {openProjectPageAfterBoot} from "./fixtures/creator_boot.mjs";
import {clickCreatorSystemAction, createSequencePattern, showSamplePage,
  showSequenceLayer, showPerformPage} from "./fixtures/creator_navigation.mjs";
import {AUDIO_TRANSITION_TIMEOUT_MS, PROJECT_TRANSITION_TIMEOUT_MS,
  beginRecording, openPerform, pcm16Wav, stopRecording} from "./fixtures/perform_helpers.mjs";

const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");
const repoRoot = resolve(import.meta.dirname, "../../../..");
const pad = (page) => page.getByRole("button", {name: /^Pad A01 — assigned — Key /});
const readMeter = (page) => page.evaluate(() => window.lmdjWebRuntimeHost.outputMeter());
const physical = (page, name) => page.getByTestId("physical-controls").getByRole("button", {name});

async function retainJson(name, value) {
  // The line reporter retains no success trace. Persist the actual evidence
  // even when the entire journey passes; a body-only attachment is ephemeral.
  const path = test.info().outputPath(`${name}.json`);
  await writeFile(path, JSON.stringify(value, null, 2));
  await test.info().attach(name, {contentType: "application/json", path});
}

test.afterEach(async ({page}, info) => {
  if (info.status === info.expectedStatus || page.isClosed()) return;
  try {
    const observation = await page.evaluate(() => {
      const host = window.lmdjWebRuntimeHost;
      const proof = window.__outputMeterProof;
      return {diagnostics: host?.session?.diagnostics(), meter: host?.outputMeter?.(),
        contextState: proof?.context?.state, ownerMessages: proof?.ownerMessages,
        errorEvents: proof?.errorEvents, latestMeter: proof?.meters?.at(-1),
        renderedMeter: proof?.lastRenderedMeter, voiceEvents: proof?.voiceEvents,
        hitStartOrdinal: proof?.hitStartOrdinal, hitMinimumSequence: proof?.hitMinimumSequence,
        firstSignal: proof?.firstSignal};
    });
    await info.attach("meter-runtime-failure-observation", {contentType: "application/json",
      body: Buffer.from(JSON.stringify(observation))});
  } catch (error) {
    await info.attach("meter-runtime-observation-unavailable", {contentType: "text/plain", body: Buffer.from(String(error))});
  }
});

async function installAudioObserver(page) {
  await page.addInitScript(({mutateGraph}) => {
    const proof = window.__outputMeterProof = {meters: [], batches: [], stopped: [], clicks: [], errors: 0};
    const bounded = (values, value) => { values.push(value); if (values.length > 256) values.shift(); };
    const NativeContext = window.AudioContext;
    window.AudioContext = class extends NativeContext {
      constructor(...args) {
        super(...args);
        const addModule = this.audioWorklet.addModule.bind(this.audioWorklet);
        this.audioWorklet.addModule = (...args) => {
          (proof.moduleUrls ??= []).push(String(args[0]));
          return addModule(...args);
        };
      }
      createGain() {
        const gain = super.createGain();
        if (proof.context === undefined) {
          proof.context = this;
          proof.monitor = gain;
          proof.analyser = super.createAnalyser();
          proof.analyser.fftSize = 2048;
          // Passive measurement branch; the original destination edge and
          // original monitor node are never replaced or rewired.
          gain.connect(proof.analyser);
        }
        return gain;
      }
    };
    const NativeNode = window.AudioWorkletNode;
    window.AudioWorkletNode = class extends NativeNode {
      constructor(context, name, options) {
        super(context, name, options);
        if (mutateGraph) {
          // Negative control only: rebuild the REAL graph as
          // Native product → monitor → tap → destination. PCM, meter packets,
          // processor and getter are untouched; zero ENC4 must expose the error.
          const connect = this.connect.bind(this);
          this.connect = (...args) => {
            if (name === "lmdj-perform-master-tap" && args[0] === proof.monitor) {
              proof.monitor.disconnect(context.destination);
              proof.monitor.connect(this);
              (proof.graphMutations ??= []).push("tap-after-monitor");
              return connect(context.destination, ...args.slice(1));
            }
            if (name !== "lmdj-perform-master-tap" && args[0] === proof.tap) {
              (proof.graphMutations ??= []).push("product-before-monitor");
              return connect(proof.monitor, ...args.slice(1));
            }
            return connect(...args);
          };
        }
        if (name !== "lmdj-perform-master-tap") return;
        proof.tap = this;
        const postMessage = this.port.postMessage.bind(this.port);
        this.port.postMessage = (...args) => {
          if (args[0]?.type === "meter-owner") (proof.ownerMessages ??= []).push({...args[0]});
          return postMessage(...args);
        };
        const observeProcessorFailure = event => {
          (proof.errorEvents ??= []).push({type: event.type, trusted: event.isTrusted});
          proof.errors += 1;
        };
        this.addEventListener("processorerror", observeProcessorFailure);
        this.addEventListener("error", observeProcessorFailure);
        this.port.addEventListener("message", ({data}) => {
          if (data?.type === "meter") bounded(proof.meters, {...data});
          if (data?.type === "proof-fault-installed") proof.faultInstalled = (proof.faultInstalled ?? 0) + 1;
          if (data?.type === "proof-fault-armed") proof.faultArmed = (proof.faultArmed ?? 0) + 1;
          if (data?.type === "proof-render-threw") proof.renderThrows = (proof.renderThrows ?? 0) + 1;
          if (data?.type === "stopped") bounded(proof.stopped, {...data});
          if (data?.type !== "batch") return;
          let left = 0, right = 0;
          for (const sample of data.channels[0]) left = Math.max(left, Math.abs(sample));
          for (const sample of data.channels[1]) right = Math.max(right, Math.abs(sample));
          bounded(proof.batches, {generation: data.generation, sequence: data.sequence,
            frames: data.channels[0].length, left, right});
        });
      }
    };
    window.addEventListener("lmdj:metronome-click", ({detail}) => bounded(proof.clicks, {...detail}));
    proof.postMonitorPeak = () => {
      const pcm = new Float32Array(proof.analyser.fftSize);
      proof.analyser.getFloatTimeDomainData(pcm);
      let peak = 0;
      for (const value of pcm) peak = Math.max(peak, Math.abs(value));
      return peak;
    };
  }, {mutateGraph: process.env.LMDJ_METER_GRAPH_MUTATION_PROOF === "1"});
}

async function importWitnessProject(page) {
  await openProjectPageAfterBoot(page);
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await wakeAudioWithPad(page);
  await page.evaluate(() => {
    const proof = window.__outputMeterProof;
    proof.voiceEvents = [];
    proof.voiceOrdinal = 0;
    proof.hitStartOrdinal = 0;
    // Observe native publication only. This creates no command, transport
    // replacement or assumption that a private caller sees a substituted send.
    window.lmdjWebRuntimeHost.transport.subscribe((notification) => {
      if (notification.event !== "runtime.voice_state") return;
      for (const event of notification.payload.events) proof.voiceEvents.push({
        ...event, observedOrdinal: ++proof.voiceOrdinal,
        observedContextFrame: Math.ceil(proof.context.currentTime * proof.context.sampleRate),
      });
      if (proof.voiceEvents.length > 256) proof.voiceEvents.splice(0, proof.voiceEvents.length - 256);
    });
  });
}

async function silence(page) {
  await expect.poll(async () => {
    const meter = await readMeter(page);
    return meter.state === "available" && meter.leftPeak === 0 && meter.rightPeak === 0;
  }, {timeout: AUDIO_TRANSITION_TIMEOUT_MS, intervals: [20]}).toBe(true);
  if (await page.getByRole("group", {name: "Stereo output level"}).count()) await renderedMeter(page, "zero");
}

async function renderedMeter(page, expected = "signal") {
  // Packet/display agreement alone could share a wrong logarithm or source
  // assumption. The dry journey below also asserts independent literal PCM
  // and literal -5.1/-17.1 dBFS; owning unit controls cover20log/hold separately.
  await expect.poll(() => page.evaluate(expected => {
    const proof = window.__outputMeterProof;
    const root = document.querySelector('[aria-label="Stereo output level"]');
    if (root === null) { proof.lastRenderedMeter = {missing: true}; return false; }
    const rails = [...root.querySelectorAll('[role="meter"]')];
    const text = root.querySelector("output")?.textContent;
    const value = window.lmdjWebRuntimeHost.outputMeter();
    const packet = proof.meters.findLast(packet => packet.owner === root.dataset.owner &&
      packet.windowEndFrame === root.dataset.windowEndFrame);
    proof.lastRenderedMeter = {attributes: {...root.dataset}, text, packet, value,
      rails: rails.map(rail => ({...rail.dataset}))};
    if (expected === "unavailable") return root.dataset.state === "unavailable" &&
      text === "UNAVAILABLE" && rails.length === 0 && root.dataset.owner === undefined &&
      root.querySelector(".perform-output-meter-hold") === null;
    if (root.dataset.state !== "available" || rails.length !== 2 || packet === undefined ||
        value.state !== "available" || value.owner !== packet.owner) return false;
    const peaks = [packet.leftPeak, packet.rightPeak];
    const display = peak => {
      if (peak === 0) return "−∞";
      const rounded = Math.round(Math.min(0, Math.max(-60, 20 * Math.log10(peak))) * 10) / 10;
      return rounded < 0 ? `−${Math.abs(rounded).toFixed(1)}` : "0.0";
    };
    return peaks.every((peak, i) => Number(rails[i].dataset.peak) === peak) &&
      text === `L ${display(peaks[0])}  R ${display(peaks[1])} dBFS` &&
      (expected === "zero" ? peaks.every(peak => peak === 0) : peaks[0] > 0.01 && peaks[1] > 0.002);
  }, expected), {timeout: AUDIO_TRANSITION_TIMEOUT_MS, intervals: [20]}).toBe(true);
}

async function observeRenderedHold(page) {
  await page.evaluate(() => {
    const proof = window.__outputMeterProof;
    const root = document.querySelector('[aria-label="Stereo output level"]');
    proof.uiHold = [];
    const observe = () => {
      const rails = [...root.querySelectorAll('[role="meter"]')];
      if (rails.length !== 2) return;
      proof.uiHold.push({owner: root.dataset.owner, windowEndFrame: root.dataset.windowEndFrame,
        contextFrame: Math.round(proof.context.currentTime * proof.context.sampleRate),
        rate: proof.context.sampleRate, channels: rails.map(rail => ({peak: Number(rail.dataset.peak),
          held: Number(rail.dataset.heldPeak), frame: Number(rail.dataset.heldPeakFrame)}))});
      if (proof.uiHold.length > 256) proof.uiHold.shift();
    };
    proof.uiHoldObserver = new MutationObserver(observe);
    proof.uiHoldObserver.observe(root, {attributes: true, childList: true, subtree: true, characterData: true});
    observe();
  });
}

async function assertRenderedHoldAndExpiry(page) {
  await expect.poll(() => page.evaluate(() => {
    const proof = window.__outputMeterProof;
    const held = proof.uiHold.find(value => value.channels.every(channel => channel.peak === 0 &&
      channel.held > 0 && value.contextFrame - channel.frame >= 0 &&
      value.contextFrame - channel.frame < value.rate));
    if (held === undefined) return false;
    const expired = proof.uiHold.find(value => value.owner === held.owner &&
      value.channels.every((channel, i) => channel.peak === 0 && channel.held === 0 &&
        value.contextFrame - held.channels[i].frame >= value.rate));
    if (expired === undefined) return false;
    proof.renderedHoldProof = {held, expired};
    return true;
  }), {timeout: AUDIO_TRANSITION_TIMEOUT_MS, intervals: [20]}).toBe(true);
  await retainJson("real-rendered-one-second-hold",
    await page.evaluate(() => window.__outputMeterProof.renderedHoldProof));
}

async function meterLayout(page) {
  const measurements = [];
  for (const viewport of [{width: 1440, height: 900}, {width: 1280, height: 720},
    {width: 1024, height: 768}, {width: 820, height: 1180}, {width: 768, height: 1024},
    {width: 390, height: 844}]) {
    await page.setViewportSize(viewport);
    await page.waitForFunction(({width, height}) => window.innerWidth === width && window.innerHeight === height, viewport);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
    const geometry = await page.evaluate(() => {
      const root = document.querySelector('[aria-label="Stereo output level"]');
      const overview = root.closest('[data-testid="overview-display"]');
      const box = element => {
        const b = element.getBoundingClientRect(); return {x: b.x, y: b.y, width: b.width, height: b.height};
      };
      const overlaps = (a, b) => Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x) > 0.5 &&
        Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y) > 0.5;
      const meter = box(root), outer = box(overview), label = box(root.querySelector("output"));
      const launch = box(overview.querySelector('.perform-overview-launch'));
      const facts = box(overview.querySelector('.perform-overview-facts'));
      const conflicts = [...overview.querySelectorAll('.perform-overview-columns dt,.perform-overview-columns dd,' +
        '.perform-overview-launch,.perform-overview-facts,.perform-overview-progress,.encoder-readbacks')]
        .filter(element => overlaps(meter, box(element))).map(element => ({name: element.textContent, box: box(element)}));
      return {meter, outer, label, conflicts, footersOverlap: overlaps(launch, facts),
        scroll: root.scrollWidth, width: root.clientWidth,
        readoutScroll: root.querySelector("output").scrollWidth, readoutWidth: root.querySelector("output").clientWidth,
        height: getComputedStyle(root).height,
        railHeights: [...root.querySelectorAll('.perform-output-meter-rail')].map(rail => getComputedStyle(rail).height),
        interactive: root.querySelectorAll('button,input,select,[tabindex]').length};
    });
    measurements.push({viewport, ...geometry});
    expect(geometry.conflicts, JSON.stringify({viewport, geometry})).toEqual([]);
    expect(geometry.footersOverlap).toBe(false);
    expect(geometry.scroll).toBeLessThanOrEqual(geometry.width);
    expect(geometry.readoutScroll).toBeLessThanOrEqual(geometry.readoutWidth);
    expect(geometry.meter.x).toBeGreaterThanOrEqual(geometry.outer.x - 0.5);
    expect(geometry.meter.y).toBeGreaterThanOrEqual(geometry.outer.y - 0.5);
    expect(geometry.meter.x + geometry.meter.width).toBeLessThanOrEqual(geometry.outer.x + geometry.outer.width + 0.5);
    expect(geometry.meter.y + geometry.meter.height).toBeLessThanOrEqual(geometry.outer.y + geometry.outer.height + 0.5);
    expect(geometry.height).toBe("12px"); expect(geometry.railHeights).toEqual(["3px", "3px"]);
    expect(geometry.interactive).toBe(0);
    await page.getByTestId("overview-display").screenshot({path: test.info().outputPath(`meter-${viewport.width}x${viewport.height}.png`)});
  }
  await retainJson("meter-layout", measurements);
  await page.setViewportSize({width: 1440, height: 900});
  await page.waitForFunction(() => innerWidth === 1440 && innerHeight === 900);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
}

async function installUnequalStereo(page) {
  await physical(page, "Bank A").click();
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  // Core renders a mono voice per Pad then applies its equal-power Pan.
  // Two actual mono Pads give independent channels; a stereo file in one
  // centred Pad would produce the same downmix on L/R and prove no separation.
  for (const [slot, address, amplitude, panValue] of [[0, "A01", 16384, -100], [1, "A02", 4096, 100]]) {
    await page.getByRole("button", {name: new RegExp(`^Pad ${address} — assigned — Key `)})
      .evaluate(element => element.click());
    await showSamplePage(page, "Pad");
    const wav = pcm16Wav({frames: 48_000, channels: 1});
    for (let frame = 0; frame < 48_000; frame += 1) {
      wav.writeInt16LE(Math.round(Math.sin(2 * Math.PI * 3_000 * frame / 48_000) * amplitude),
        44 + frame * 2);
    }
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", {name: "Replace Sample"}).click();
    await (await chooser).setFiles({name: `meter-${address}.wav`, mimeType: "audio/wav", buffer: wav});
    await page.getByRole("dialog", {name: `Replace Pad ${address}?`})
      .getByRole("button", {name: "Confirm replace"}).click();
    const source = page.getByRole("dialog", {name: `Pad ${address} Long Source`});
    await expect(source).toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
    await source.getByRole("button", {name: "Commit selection"}).click();
    await expect(source).toBeHidden({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
    const sample = await page.evaluate(slot => window.lmdjWebRuntimeHost.inspection.inspectSample(slot), slot);
    expect(sample.metadata.channels).toBe(1);
    expect(sample.metadata.sourceFrames).toBe(48000);
    await showSamplePage(page, "Playback");
    const pan = page.getByRole("slider", {name: `Pad ${address} Pan`});
    await pan.dispatchEvent("pointerdown", {pointerId: 81 + slot, isPrimary: true, button: 0});
    await pan.fill(String(panValue));
    await pan.dispatchEvent("pointerup", {pointerId: 81 + slot, isPrimary: true, button: 0});
    await expect.poll(() => page.evaluate(slot => window.lmdjWebRuntimeHost.inspection.inspectSample(slot)
      .then(sample => sample.playback.pan), slot), {timeout: PROJECT_TRANSITION_TIMEOUT_MS}).toBe(panValue);
    await expect(pan).toBeEnabled({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  }
  await openPerform(page);
}

async function nativeHit(page, assertion) {
  await pad(page).focus();
  const startFrame = await page.evaluate(() => {
    const proof = window.__outputMeterProof;
    proof.hitStartOrdinal = proof.voiceOrdinal;
    proof.hitMinimumSequence = [0, 1].map(slot => Math.max(0, ...proof.voiceEvents
      .filter(event => event.slot === slot).map(event => event.sequence)));
    return Math.ceil(proof.context.currentTime * proof.context.sampleRate);
  });
  const label = await page.getByRole("button", {name: /^Pad A02 — assigned — Key /}).getAttribute("aria-label");
  const secondKey = /Key ([A-Z0-9])$/.exec(label)?.[1].toLowerCase();
  expect(secondKey).toBeTruthy();
  await page.keyboard.down("Enter");
  try {
    await page.keyboard.down(secondKey);
    try { await assertion(startFrame); } finally { await page.keyboard.up(secondKey); }
  } finally { await page.keyboard.up("Enter"); }
}

async function signal(page, {afterFrame = 0} = {}) {
  let meter;
  // These are one-second one-shot voices. Poll within the 50ms meter window;
  // Playwright's default backoff reaches 1s and can skip the entire interval
  // where both asynchronous starts have a complete steady window.
  await expect.poll(async () => {
    const snapshot = await page.evaluate((minimumFrame) => {
      const meter = window.lmdjWebRuntimeHost.outputMeter();
      const proof = window.__outputMeterProof;
      // Both real native voices must start after this chord, with their
      // latest exact sequence/slot still started; old tails cannot witness FX.
      let admittedFrame = minimumFrame;
      const bothStarted = [0, 1].every(slot => {
        const started = proof.voiceEvents.findLast(event => event.slot === slot &&
          event.state === "started" && event.sequence > proof.hitMinimumSequence[slot] &&
          event.observedOrdinal > proof.hitStartOrdinal);
        const voice = started === undefined ? undefined : proof.voiceEvents.findLast(event =>
          event.slot === slot && event.sequence === started.sequence);
        if (started !== undefined) admittedFrame = Math.max(admittedFrame, started.observedContextFrame);
        return voice?.state === "started";
      });
      // Native chord onsets are asynchronous. Require a complete steady
      // window beyond both received start receipts, excluding unequal attack/
      // filter-onset transients. This is only a conservative witness bound;
      // it never changes producer freshness or claims a Native engine frame.
      const steadyFrame = admittedFrame + Math.ceil(proof.context.sampleRate / 20);
      proof.firstSignal ??= {meter, bothStarted, steadyFrame,
        voiceEvents: [...proof.voiceEvents], hitStartOrdinal: proof.hitStartOrdinal,
        hitMinimumSequence: [...proof.hitMinimumSequence]};
      return {meter, qualifies: bothStarted && meter.state === "available" &&
        Number(meter.windowStartFrame) >= steadyFrame && meter.leftPeak > 0.01 && meter.rightPeak > 0.002};
    }, afterFrame);
    if (snapshot.qualifies) meter = snapshot.meter;
    return snapshot.qualifies;
  }, {timeout: AUDIO_TRANSITION_TIMEOUT_MS, intervals: [20]}).toBe(true);
  expect(meter.leftPeak / meter.rightPeak).toBeCloseTo(4, 1);
  const delivered = await page.evaluate((windowEndFrame) => window.__outputMeterProof.meters
    .findLast((message) => message.windowEndFrame === windowEndFrame), meter.windowEndFrame);
  expect(delivered).toMatchObject({owner: meter.owner, leftPeak: meter.leftPeak,
    rightPeak: meter.rightPeak, leftPeakFrame: meter.leftPeakFrame,
    rightPeakFrame: meter.rightPeakFrame, sampleRate: meter.sampleRate});
  await renderedMeter(page);
  return meter;
}

async function monitorVolume(page, percent) {
  const encoder = physical(page, "Encoder 4 — Output Volume");
  await encoder.hover();
  await page.mouse.wheel(0, percent === 0 ? 8_000 : -8_000);
  await expect(page.locator('.encoder-readbacks [data-encoder="4"] dd')).toHaveText(`${percent}%`);
  await expect.poll(() => page.evaluate(() => window.__outputMeterProof.monitor.gain.value))
    .toBe(percent / 100);
}


test("real stereo meter excludes monitor and click, survives capture and requires a fresh running owner", async ({page}) => {
  test.setTimeout(300_000);
  await installAudioObserver(page);
  await page.goto("/index.html");
  await importWitnessProject(page);
  await openPerform(page);
  if (process.env.LMDJ_METER_GRAPH_MUTATION_PROOF === "1") {
    const rewired = await page.evaluate(() => window.__outputMeterProof.graphMutations);
    expect(rewired).toEqual(["tap-after-monitor", "product-before-monitor"]);
    await test.info().attach("actual-downstream-monitor-graph", {
      contentType: "application/json", body: Buffer.from(JSON.stringify({rewired})),
    });
  }
  await silence(page); // Positive inactive-capture render; unavailable is not zero.
  expect(await page.evaluate(() => window.__outputMeterProof.batches.length)).toBe(0);
  await installUnequalStereo(page);
  await observeRenderedHold(page);
  let baseline;
  await nativeHit(page, async () => {
    baseline = await signal(page);
    // Independent literal PCM oracle: positive int16 peaks /32767,
    // default keyboard velocity 100/127, hard-pan gain sqrt(2). At least
    // one 16-frame period fits the 2400-frame window; no run calibrates it.
    expect(baseline.leftPeak).toBeCloseTo(0.55679399, 4);
    expect(baseline.rightPeak).toBeCloseTo(0.13919850, 4);
    await expect(page.getByLabel("Stereo output readout")).toHaveText("L −5.1  R −17.1 dBFS");
    await page.getByTestId("overview-display").screenshot({path: test.info().outputPath("meter-real-stereo-signal.png")});
  });
  await silence(page);
  await assertRenderedHoldAndExpiry(page);
  await meterLayout(page);

  await page.getByRole("button", {name: "HOLD", exact: true}).click();
  await expect(page.getByRole("button", {name: "HOLD", exact: true})).toHaveAttribute("aria-pressed", "true");
  // Current independent Cutoff: 50px/detent × 10 positions/detent.
  // +2000px moves 1000→600, i.e. 1262Hz LP. The existing 3kHz witness,
  // native started receipt and fresh window keep the original >10% FX oracle.
  const filterEncoder = physical(page, "Encoder 1 — Cutoff");
  await filterEncoder.hover();
  await page.mouse.wheel(0, 2000);
  await expect(page.getByRole("slider", {name: "Filter", exact: true})).toHaveValue("600");
  await nativeHit(page, async (startFrame) => {
    const meter = await signal(page, {afterFrame: startFrame});
    expect(Math.abs(meter.leftPeak - baseline.leftPeak)).toBeGreaterThan(baseline.leftPeak * 0.1);
  });
  // Restore maximum cutoff using the opposite native detents. Current
  // independent LP remains engaged there; release its rotary owner on page
  // exit with HOLD off before requiring the dry absolute monitor oracle.
  await filterEncoder.hover();
  await page.mouse.wheel(0, -2000);
  await expect(page.getByRole("slider", {name: "Filter", exact: true})).toHaveValue("1000");
  await page.getByRole("button", {name: "HOLD", exact: true}).click();
  await expect(page.getByRole("button", {name: "HOLD", exact: true})).toHaveAttribute("aria-pressed", "false");
  // The button is optimistic. Wait for the real applied HOLD-off before page
  // exit can retire unsent local controls and release the rotary owner.
  await expect.poll(() => page.evaluate(async () => {
    const status = await window.lmdjWebRuntimeHost.session.queryPerformanceLiveStatus();
    return status.available && status.applied.hold === false &&
      status.appliedControlSequence === status.acceptedControlSequence;
  }), {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(true);
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"}))
    .toBeVisible({timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await openPerform(page);
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  await expect(page.getByRole("status", {name: "Filter status"})).toHaveText("OFF · core",
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await page.getByRole("button", {name: "FILTER", exact: true}).click();
  await silence(page);
  await monitorVolume(page, 0);
  await nativeHit(page, async () => {
    const meter = await signal(page);
    expect(meter.leftPeak).toBeCloseTo(0.55679399, 4);
    expect(meter.rightPeak).toBeCloseTo(0.13919850, 4);
    await expect.poll(() => page.evaluate(() => window.__outputMeterProof.postMonitorPeak()),
      {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(0);
  });
  await silence(page);

  await beginRecording(page);
  await expect.poll(() => page.evaluate(() => window.__outputMeterProof.batches.length),
    {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBeGreaterThan(0); // Actual capture applied, independent of meter.
  const before = await page.evaluate(() => window.__outputMeterProof.batches.at(-1).sequence);
  await nativeHit(page, async () => {
    const meter = await signal(page);
    await expect.poll(() => page.evaluate((sequence) => window.__outputMeterProof.batches
      .some((batch) => batch.sequence > sequence && batch.left > 0.01 && batch.right > 0.002), before),
    {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(true);
    const capture = await page.evaluate((sequence) => window.__outputMeterProof.batches
      .findLast((batch) => batch.sequence > sequence && batch.left > 0.01), before);
    expect(capture.left).toBeCloseTo(meter.leftPeak, 3);
    expect(capture.right).toBeCloseTo(meter.rightPeak, 3);
    expect(capture.left / capture.right).toBeCloseTo(4, 1);
  });
  await stopRecording(page);
  const final = await page.evaluate(() => ({stop: window.__outputMeterProof.stopped.at(-1),
    batch: window.__outputMeterProof.batches.at(-1)}));
  expect(final.stop.generation).toBe(final.batch.generation);
  expect(final.stop.finalSequence).toBe(final.batch.sequence);
  await silence(page);
  const endAtStop = (await readMeter(page)).windowEndFrame;
  await expect.poll(async () => {
    const meter = await readMeter(page);
    return meter.state === "available" && Number(meter.windowEndFrame) > Number(endAtStop);
  }, {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(true);

  await showPerformPage(page, "Takes");
  await page.getByRole("button", {name: "Discard Performance", exact: true}).click();
  await expect(page.getByRole("status", {name: "WAV recording status"}))
    .toContainText("temporary removed", {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  await monitorVolume(page, 100);
  await page.getByRole("button", {name: "Sequence", exact: true}).click();
  const previousPattern = await page.getByTestId("sequence-pattern").getAttribute("data-pattern-id");
  await createSequencePattern(page, 1);
  await expect(page.getByTestId("sequence-pattern")).not.toHaveAttribute("data-pattern-id", previousPattern,
    {timeout: PROJECT_TRANSITION_TIMEOUT_MS});
  const emptyId = await page.getByTestId("sequence-pattern").getAttribute("data-pattern-id");
  const emptyTruth = await page.evaluate(() => window.lmdjWebRuntimeHost.inspection.inspectProject());
  expect(emptyTruth.project.patterns[emptyId].events).toEqual([]);
  await showSequenceLayer(page, "SETUP");
  await silence(page);
  const clickStart = await page.evaluate(() => window.__outputMeterProof.clicks.length);
  await page.getByRole("button", {name: "Metronome", exact: true}).click();
  await expect(page.getByRole("button", {name: "Metronome", exact: true})).toHaveAttribute("aria-pressed", "true");
  await physical(page, /^Play\/Stop/).click();
  await expect(physical(page, /^Play\/Stop/)).toHaveAttribute("aria-label", "Play/Stop — Pattern is playing",
    {timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await expect.poll(() => page.evaluate(() => window.__outputMeterProof.clicks.length),
    {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBeGreaterThan(clickStart + 1);
  const aliasControl = process.env.LMDJ_METER_POLL_ALIAS_CONTROL === "1";
  const period = await page.evaluate(() => {
    const clicks = window.__outputMeterProof.clicks;
    return clicks.at(-1).contextTime - clicks.at(-2).contextTime;
  });
  if (aliasControl) {
    // Negative observation control only: sample the gap between real clicks
    // at an integer number of their periods, without changing the audio clock.
    const delay = await page.evaluate(period => {
      const proof = window.__outputMeterProof;
      let target = proof.clicks.at(-1).contextTime + period / 2;
      while (target <= proof.context.currentTime) target += period;
      return (target - proof.context.currentTime) * 1000;
    }, period);
    await page.waitForTimeout(delay);
  }
  try {
    await expect.poll(() => page.evaluate(start => {
      const proof = window.__outputMeterProof;
      const peak = proof.postMonitorPeak();
      const now = proof.context.currentTime;
      const click = proof.clicks.slice(start).findLast(click => click.contextTime <= now &&
        now - click.contextTime <= proof.analyser.fftSize / proof.context.sampleRate + 0.04);
      const observation = {now, peak, clickTime: click?.contextTime ?? null};
      (proof.clickObservations ??= []).push(observation);
      if (proof.clickObservations.length > 512) proof.clickObservations.shift();
      const meter = window.lmdjWebRuntimeHost.outputMeter();
      if (peak > 0.001 && click !== undefined && meter.state === "available") {
        proof.audibleClick = {start: Math.floor(click.contextTime * meter.sampleRate),
          end: Math.ceil((click.contextTime + 0.04) * meter.sampleRate), owner: meter.owner};
        return peak;
      }
      return 0;
    }, clickStart), {timeout: AUDIO_TRANSITION_TIMEOUT_MS,
      intervals: [aliasControl ? Math.round(period * 2000) : 20]}).toBeGreaterThan(0.001);
  } catch (error) {
    await test.info().attach("click-observation-clock", {contentType: "application/json",
      body: Buffer.from(JSON.stringify(await page.evaluate(start => {
        const proof = window.__outputMeterProof;
        return {clicks: proof.clicks.slice(start), observations: proof.clickObservations,
          rate: proof.context.sampleRate, monitorGain: proof.monitor.gain.value};
      }, clickStart)))});
    throw error;
  }
  // Cover the entire actual 40ms click, not a zero sample just before it.
  const audibleClick = await page.evaluate(() => window.__outputMeterProof.audibleClick);
  await expect.poll(() => page.evaluate(click => {
    const windows = window.__outputMeterProof.meters.filter(window => window.owner === click.owner &&
      Number(window.windowStartFrame) < click.end && Number(window.windowEndFrame) > click.start);
    return windows.length > 0 && Number(windows[0].windowStartFrame) <= click.start &&
      Number(windows.at(-1).windowEndFrame) >= click.end && windows.every((window, i) =>
        window.leftPeak === 0 && window.rightPeak === 0 &&
        (i === 0 || window.windowStartFrame === windows[i - 1].windowEndFrame));
  }, audibleClick), {timeout: AUDIO_TRANSITION_TIMEOUT_MS, intervals: [20]}).toBe(true);
  await retainJson("click-measurement-window-proof", await page.evaluate(start => {
      const proof = window.__outputMeterProof;
      return {click: proof.audibleClick, clicks: proof.clicks.slice(start),
        observations: proof.clickObservations, rate: proof.context.sampleRate,
        windows: proof.meters.filter(window => window.owner === proof.audibleClick.owner &&
          Number(window.windowStartFrame) < proof.audibleClick.end &&
          Number(window.windowEndFrame) > proof.audibleClick.start)};
    }, clickStart));
  await silence(page); // Real click output is nonzero while tap samples are zero.
  await physical(page, /^Play\/Stop/).click();
  // creator-phase is the Host audio lifecycle and stays running. The
  // transport projection and its physical lamp are the actual Stop far side.
  await expect(page.getByRole("status").filter({has: page.getByTestId("creator-phase"), hasText: "stopped"}))
    .toBeVisible({timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  await expect(physical(page, /^Play\/Stop/)).toHaveAttribute("aria-label", "Play/Stop");
  await page.getByRole("button", {name: "Metronome", exact: true}).click();
  await expect(page.getByRole("button", {name: "Metronome", exact: true})).toHaveAttribute("aria-pressed", "false");

  const oldOwner = (await readMeter(page)).owner;
  await clickCreatorSystemAction(page, "Suspend audio");
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  expect(await readMeter(page)).toEqual({state: "unavailable", reason: "not-running"});
  await physical(page, "Perform").click();
  await renderedMeter(page, "unavailable");
  await wakeAudioWithPad(page, {padAddress: "A01"});
  await silence(page);
  expect((await readMeter(page)).owner).not.toBe(oldOwner);
  const resumedOwner = (await readMeter(page)).owner;
  // Revoke on a REAL browser suspension, then end that controlled browser
  // interruption by resuming the same context. Explicit Web Audio suspend
  // stays parked until resume; Native cleanup/Stop ACKs must remain genuine.
  const revocations = await page.evaluate(() => window.__outputMeterProof.ownerMessages
    .filter(message => message.owner === null).length);
  await page.evaluate(() => window.__outputMeterProof.context.suspend());
  await expect.poll(() => page.evaluate(() => window.__outputMeterProof.ownerMessages
    .filter(message => message.owner === null).length),
  {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBeGreaterThan(revocations);
  expect((await readMeter(page)).state).toBe("unavailable");
  await renderedMeter(page, "unavailable");
  await page.evaluate(() => window.__outputMeterProof.context.resume());
  await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {timeout: AUDIO_TRANSITION_TIMEOUT_MS});
  expect((await readMeter(page)).state).toBe("unavailable");
  await wakeAudioWithPad(page, {padAddress: "A01"});
  await silence(page);
  expect((await readMeter(page)).owner).not.toBe(resumedOwner);
  // Thousands of synchronous getter calls stay outside the ordinary command
  // queue. The real transport method forwards identical arguments/results;
  // exceptions and rejected promises are not swallowed or remapped.
  const sends = await page.evaluate(() => {
    const host = window.lmdjWebRuntimeHost;
    const original = host.transport;
    let calls = 0;
    host.transport = new Proxy(original, {get(target, key) {
      if (key === "send") return (...args) => { calls += 1; return target.send(...args); };
      const member = Reflect.get(target, key, target);
      return typeof member === "function" ? member.bind(target) : member;
    }});
    try { for (let i = 0; i < 1_000; i += 1) host.outputMeter(); return calls; }
    finally { host.transport = original; }
  });
  expect(sends).toBe(0);
});

function sha256(bytes) { return createHash("sha256").update(bytes).digest("hex"); }
function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.keys(value).sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
function replaceOnce(source, before, after) {
  if (source.split(before).length !== 2) throw new Error(`Fault candidate binding is not unique: ${before}`);
  return source.replace(before, after);
}

function readOfflineWorker(bytes) {
  const prefix = Buffer.from("globalThis.LMDJ_CREATOR_OFFLINE_GRAPH=", "utf8");
  if (!bytes.subarray(0, prefix.length).equals(prefix)) throw new Error("offline Worker header is missing");
  const end = bytes.indexOf(Buffer.from(";\n"), prefix.length);
  if (end < 0) throw new Error("offline Worker header boundary is missing");
  const serialized = bytes.subarray(prefix.length, end).toString("utf8");
  const graph = JSON.parse(serialized);
  expect(Object.keys(graph)).toEqual(["assets", "host_version", "product_build"]);
  expect(canonicalJson(graph)).toBe(serialized);
  return {graph, source: bytes.subarray(end + 2)};
}

async function faultCandidate(request) {
  const upstream = process.env.LMDJ_CREATOR_WEB_BASE_URL;
  if (!upstream) throw new Error("LMDJ_CREATOR_WEB_BASE_URL is required");
  const responseHeaders = new Map();
  const get = async (asset) => {
    const response = await request.get(new URL(asset, upstream).href);
    expect(response.ok(), asset).toBe(true);
    const headers = {...response.headers()};
    for (const key of ["connection", "content-encoding", "content-length", "transfer-encoding"])
      delete headers[key];
    responseHeaders.set(asset, headers);
    return response.body();
  };
  const originalManifestBytes = await get("/host-manifest.json");
  const manifest = JSON.parse(originalManifestBytes.toString("utf8"));
  const entryFor = (role) => {
    const entries = manifest.assets.filter((entry) => entry.role === role);
    expect(entries, role).toHaveLength(1);
    return entries[0];
  };
  const tap = entryFor("perform_master_tap_worklet");
  const main = entryFor("host_main");
  const worker = entryFor("offline_worker");
  const assets = new Map(await Promise.all(manifest.assets.map(async (entry) => {
    const bytes = await get(`/${entry.path}`);
    expect(sha256(bytes), entry.path).toBe(entry.sha256);
    expect(bytes.byteLength, entry.path).toBe(entry.bytes);
    return [entry.path, bytes];
  })));
  const originalWorker = readOfflineWorker(assets.get(worker.path));
  expect(originalWorker.graph).toEqual({assets: manifest.assets.filter((entry) => entry.role !== worker.role),
    host_version: manifest.host_version, product_build: manifest.product_build});
  expect(JSON.stringify(originalWorker.graph.assets)).toBe(JSON.stringify(manifest.assets
    .filter((entry) => entry.role !== worker.role)));
  // Fault is isolated to a derived candidate. Wrap registration of the actual
  // processor; a private proof command only arms a throw in a real render.
  const tapSource = assets.get(tap.path).toString("utf8");
  const faultTap = Buffer.from(`{
    const registerProcessor = (name, Processor) => globalThis.registerProcessor(name, class extends Processor {
      constructor(...args) { super(...args); this.proofFault = false;
        this.port.postMessage({type: "proof-fault-installed"});
        const original = this.port.onmessage;
        this.port.onmessage = (event) => {
          if (event.data?.type === "proof-render-fault" && Object.keys(event.data).length === 1) {
            this.proofFault = true; this.port.postMessage({type: "proof-fault-armed"});
          } else original(event);
        };
      }
      process(...args) { if (this.proofFault) {
        this.port.postMessage({type: "proof-render-threw"});
        throw new Error("meter proof actual render fault");
      } return super.process(...args); }
    });
    ${tapSource}
  }`, "utf8");
  const newTap = {...tap, path: `assets/perform-master-tap.${sha256(faultTap)}.js`,
    sha256: sha256(faultTap), bytes: faultTap.byteLength};
  const mainBytes = Buffer.from(replaceOnce(assets.get(main.path).toString("utf8"),
    `/${tap.path}`, `/${newTap.path}`), "utf8");
  const newMain = {...main, path: `assets/main.${sha256(mainBytes)}.js`,
    sha256: sha256(mainBytes), bytes: mainBytes.byteLength};
  const nonWorkerAssets = manifest.assets.filter((entry) => entry.role !== worker.role)
    .map((entry) => entry.role === tap.role ? newTap : entry.role === main.role ? newMain : entry);
  // Match package.py's canonical header exactly, excluding the Worker itself
  // from its resource graph so its own content hash cannot become circular.
  const workerBytes = Buffer.concat([Buffer.from(`globalThis.LMDJ_CREATOR_OFFLINE_GRAPH=${canonicalJson({
    assets: nonWorkerAssets, host_version: manifest.host_version, product_build: manifest.product_build,
  })};\n`, "utf8"), originalWorker.source]);
  const newWorker = {...worker, path: `assets/offline-worker.${sha256(workerBytes)}.js`,
    sha256: sha256(workerBytes), bytes: workerBytes.byteLength};
  const candidate = {...manifest, assets: manifest.assets.map((entry) =>
    entry.role === tap.role ? newTap : entry.role === main.role ? newMain : entry.role === worker.role ? newWorker : entry)};
  const manifestBytes = Buffer.from(canonicalJson(candidate), "utf8");
  const decodedCandidate = JSON.parse(manifestBytes.toString("utf8"));
  const rebuiltWorker = readOfflineWorker(workerBytes);
  expect(rebuiltWorker.source.equals(originalWorker.source)).toBe(true);
  expect(rebuiltWorker.graph.host_version).toBe(decodedCandidate.host_version);
  expect(rebuiltWorker.graph.product_build).toBe(decodedCandidate.product_build);
  // Independently check the exact comparison used by the real install path;
  // verify_distribution alone does not inspect this embedded resource graph.
  expect(JSON.stringify(rebuiltWorker.graph.assets)).toBe(JSON.stringify(decodedCandidate.assets
    .filter((entry) => entry.role !== worker.role)));
  let index = (await get("/index.html")).toString("utf8");
  const digest = /(<meta name="lmdj-host-manifest-sha256" content=")[0-9a-f]{64}("\s*\/?>)/;
  if ((index.match(new RegExp(digest.source, "g")) ?? []).length !== 1) throw new Error("manifest meta is not unique");
  index = index.replace(digest, `$1${sha256(manifestBytes)}$2`);
  index = replaceOnce(index, `./${main.path}`, `./${newMain.path}`);
  assets.delete(tap.path); assets.delete(main.path); assets.delete(worker.path);
  assets.set(newTap.path, faultTap); assets.set(newMain.path, mainBytes); assets.set(newWorker.path, workerBytes);
  assets.set("host-manifest.json", manifestBytes); assets.set("index.html", Buffer.from(index));
  responseHeaders.set(`/${newTap.path}`, responseHeaders.get(`/${tap.path}`));
  responseHeaders.set(`/${newMain.path}`, responseHeaders.get(`/${main.path}`));
  responseHeaders.set(`/${newWorker.path}`, responseHeaders.get(`/${worker.path}`));
  expect(responseHeaders.get(`/${newWorker.path}`)["service-worker-allowed"]).toBe("/");
  expect([...assets.keys()].sort()).toEqual(["host-manifest.json", "index.html",
    ...candidate.assets.map((entry) => entry.path)].sort());
  const verifiedAssets = candidate.assets.map((entry) => {
    const bytes = assets.get(entry.path);
    const actualSha256 = sha256(bytes);
    expect(actualSha256, entry.path).toBe(entry.sha256);
    expect(bytes.byteLength, entry.path).toBe(entry.bytes);
    return {...entry, actualSha256, actualBytes: bytes.byteLength};
  });
  const directory = await mkdtemp(join(tmpdir(), "lmdj-meter-fault-"));
  let server;
  try {
    for (const [asset, bytes] of assets) {
      const destination = join(directory, asset);
      await mkdir(dirname(destination), {recursive: true});
      await writeFile(destination, bytes);
    }
    const verify = spawn("python3", ["-c", "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from package import verify_distribution; verify_distribution(Path(sys.argv[2]), Path(sys.argv[3]))",
      join(repoRoot, "apps/creator-web/tools"), directory, repoRoot], {stdio: ["ignore", "pipe", "pipe"]});
    let output = "";
    verify.stdout.on("data", (bytes) => { output += bytes; });
    verify.stderr.on("data", (bytes) => { output += bytes; });
    await new Promise((done, reject) => {
      verify.once("error", reject);
      verify.once("close", (code) => code === 0 ? done() : reject(new Error(`fault distribution verification failed: ${output}`)));
    });
    await test.info().attach("meter-fault-candidate-graph", {contentType: "application/json",
      body: Buffer.from(canonicalJson({parentManifestSha256: sha256(originalManifestBytes),
        manifestSha256: sha256(manifestBytes), indexSha256: sha256(assets.get("index.html")),
        workerSourceSha256: sha256(originalWorker.source), workerGraph: rebuiltWorker.graph,
        assets: verifiedAssets, inventory: [...assets.keys()].sort(), verification: output}), "utf8")});
    for (const entry of [newTap, newMain, newWorker]) await test.info().attach(`meter-fault-${entry.role}`,
      {body: assets.get(entry.path), contentType: "text/javascript"});
    await test.info().attach("meter-fault-manifest", {body: manifestBytes, contentType: "application/json"});
    await test.info().attach("meter-fault-index", {body: assets.get("index.html"), contentType: "text/html"});
    server = createServer((request_, response) => {
      const asset = new URL(request_.url, "http://127.0.0.1").pathname.slice(1) || "index.html";
      const bytes = assets.get(asset);
      if (!bytes) { response.writeHead(404); response.end(); return; }
      // Preserve the formal server's CSP/isolation/content-type/cache headers.
      // Only changed payload lengths differ on the independently bound origin.
      response.writeHead(200, {...responseHeaders.get(`/${asset}`), "content-length": bytes.byteLength});
      response.end(request_.method === "HEAD" ? undefined : bytes);
    });
    await new Promise((done, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", done); });
    return {origin: `http://127.0.0.1:${server.address().port}`, candidate, manifest,
      close: async () => {
        await new Promise((done) => { server.close(done); server.closeAllConnections(); });
        await rm(directory, {recursive: true, force: true});
      }};
  } catch (error) {
    server?.closeAllConnections(); server?.close();
    await rm(directory, {recursive: true, force: true});
    throw error;
  }
}

test("actual render processorerror keeps monitor audio but never restores the old meter", async ({page}) => {
  test.setTimeout(240_000);
  const fault = await faultCandidate(page.request);
  try {
    const originalWasm = fault.manifest.assets.find(({role}) => role === "runtime_wasm");
    expect(fault.candidate.assets.find(({role}) => role === "runtime_wasm")).toEqual(originalWasm);
    await installAudioObserver(page);
    await page.goto(`${fault.origin}/index.html`);
    await expect.poll(() => page.evaluate(() => window.__LMDJ_OFFLINE_SHELL__),
      {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe("ready");
    await importWitnessProject(page);
    await installUnequalStereo(page);
    await nativeHit(page, async () => { await signal(page); });
    await silence(page);
    const before = await readMeter(page);
    expect(before.state).toBe("available");
    await page.evaluate(() => window.__outputMeterProof.tap.port.postMessage({type: "proof-render-fault"}));
    await expect.poll(() => page.evaluate(() => window.__outputMeterProof.faultArmed ?? 0),
      {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(1);
    await expect.poll(() => page.evaluate(() => window.__outputMeterProof.renderThrows ?? 0),
      {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(1);
    await expect.poll(() => page.evaluate(() => window.__outputMeterProof.errors),
      {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBe(1);
    const nativeErrors = await page.evaluate(() => window.__outputMeterProof.errorEvents);
    expect(nativeErrors).toHaveLength(1);
    expect(nativeErrors[0].trusted).toBe(true);
    expect(["error", "processorerror"]).toContain(nativeErrors[0].type);
    expect(await readMeter(page)).toEqual({state: "unavailable", reason: "processor-failed"});
    await renderedMeter(page, "unavailable");
    let fallbackPeak;
    await nativeHit(page, async () => {
      await expect.poll(async () => {
        fallbackPeak = await page.evaluate(() => window.__outputMeterProof.postMonitorPeak());
        return fallbackPeak;
      },
        {timeout: AUDIO_TRANSITION_TIMEOUT_MS}).toBeGreaterThan(0.01);
      expect(await readMeter(page)).toEqual({state: "unavailable", reason: "processor-failed"});
      await renderedMeter(page, "unavailable");
    });
    expect(await page.evaluate(() => window.__outputMeterProof.context.state)).toBe("running");
    expect(await readMeter(page)).toEqual({state: "unavailable", reason: "processor-failed"});
    await retainJson("native-fault-meter-ui", {nativeErrors, fallbackPeak,
      contextState: await page.evaluate(() => window.__outputMeterProof.context.state),
      meter: await readMeter(page), rendered: await page.evaluate(() => window.__outputMeterProof.lastRenderedMeter)});
  } catch (error) {
    const observation = await page.evaluate(() => {
      const proof = window.__outputMeterProof;
      return {moduleUrls: proof.moduleUrls, installed: proof.faultInstalled ?? 0,
        armed: proof.faultArmed ?? 0, throws: proof.renderThrows ?? 0, errors: proof.errors,
        errorEvents: proof.errorEvents,
        contextState: proof.context?.state, meter: window.lmdjWebRuntimeHost.outputMeter(),
        latestMeter: proof.meters.at(-1)};
    });
    await test.info().attach("fault-render-observation", {
      contentType: "application/json", body: Buffer.from(JSON.stringify(observation)),
    });
    throw error;
  } finally { await fault.close(); }
});
