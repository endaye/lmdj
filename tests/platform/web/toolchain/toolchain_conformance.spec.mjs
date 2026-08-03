import { expect, test } from "@playwright/test";


const CAPABILITY_ORDER = Object.freeze([
  "secureContext",
  "crossOriginIsolated",
  "sharedArrayBuffer",
  "webAssembly",
  "audioWorklet",
  "opfs",
  "opfsSyncAccessHandle",
  "opfsWritableReplace",
]);
const REQUIRED_LINKER_FLAGS = Object.freeze([
  "-pthread",
  "-sWASMFS",
  "-sAUDIO_WORKLET",
  "-sWASM_WORKERS",
  "-sPROXY_TO_PTHREAD",
  "-sINITIAL_MEMORY=536870912",
  "-sALLOW_MEMORY_GROWTH=0",
  "-sASYNCIFY=1",
  "-sASYNCIFY_IMPORTS=['lmdj_opfs_acquire_writer','lmdj_opfs_replace_complete','lmdj_opfs_list_names']",
]);
const FAULT_POINTS = Object.freeze([
  "before_write",
  "during_write",
  "before_close",
  "after_close",
  "before_cleanup",
]);


async function inspectCapabilities(page) {
  return page.evaluate(async (capabilityOrder) => {
    const workerSource = `
      self.onmessage = async () => {
        const result = {
          opfs: false,
          opfsSyncAccessHandle: false,
          opfsWritableReplace: false,
        };
        try {
          result.opfs = typeof navigator.storage?.getDirectory === "function";
          if (result.opfs) {
            const root = await navigator.storage.getDirectory();
            const file = await root.getFileHandle(".lmdj-capability-probe", {create: true});
            result.opfsSyncAccessHandle = typeof file.createSyncAccessHandle === "function";
            result.opfsWritableReplace = typeof file.createWritable === "function";
            await root.removeEntry(".lmdj-capability-probe");
          }
        } catch (error) {
          result.error = String(error);
        }
        self.postMessage(result);
      };
    `;
    const url = URL.createObjectURL(new Blob([workerSource], {type: "text/javascript"}));
    const storage = await new Promise((resolve) => {
      const worker = new Worker(url);
      const timeout = setTimeout(() => {
        worker.terminate();
        resolve({error: "storage capability worker timed out"});
      }, 5_000);
      worker.onmessage = (event) => {
        clearTimeout(timeout);
        worker.terminate();
        resolve(event.data);
      };
      worker.onerror = (event) => {
        clearTimeout(timeout);
        worker.terminate();
        resolve({error: event.message || "storage capability worker failed"});
      };
      worker.postMessage(null);
    });
    URL.revokeObjectURL(url);

    const capabilities = {
      secureContext: window.isSecureContext === true,
      crossOriginIsolated: window.crossOriginIsolated === true,
      sharedArrayBuffer: typeof SharedArrayBuffer === "function",
      webAssembly: typeof WebAssembly === "object",
      audioWorklet:
        typeof AudioContext === "function" &&
        typeof AudioWorkletNode === "function",
      opfs: storage.opfs === true,
      opfsSyncAccessHandle: storage.opfsSyncAccessHandle === true,
      opfsWritableReplace: storage.opfsWritableReplace === true,
    };
    const missing = capabilityOrder.filter((name) => capabilities[name] !== true);
    if (missing.length > 0) {
      return {
        status: "unsupported",
        error: {code: "UNSUPPORTED_WEB_RUNTIME", missing},
        capabilities,
      };
    }
    return {status: "supported", missing: [], capabilities};
  }, CAPABILITY_ORDER);
}


async function loadIdentity(page) {
  return page.evaluate(async () => {
    const response = await fetch("/toolchain-identity.json", {cache: "no-store"});
    if (!response.ok) throw new Error(`identity fetch failed: ${response.status}`);
    return response.json();
  });
}


async function waitForProbe(page, predicate, timeout = 120_000) {
  await page.waitForFunction(
    predicate,
    undefined,
    {timeout},
  );
  return page.evaluate(() => window.lmdjToolchainProbe.snapshot());
}


function assertIdentity(identity) {
  expect(identity.emsdk_tag).toBe("6.0.5");
  expect(identity.emsdk_revision).toBe(
    "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190",
  );
  expect(identity.emscripten_releases_revision).toBe(
    "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
  );
  expect(identity.initial_memory).toBe(536_870_912);
  expect(identity.allow_memory_growth).toBe(false);
  expect(identity.node).toBe("22");
  expect(identity.playwright).toBe("1.62.1");
  expect(identity.linker_flags).toEqual(REQUIRED_LINKER_FLAGS);
  expect(identity.emcc_version).toContain("6.0.5");
}


function assertDirectOpfs(snapshot, expectedPhase) {
  expect(snapshot.wasmfs).toBe(1);
  expect(snapshot.lease.ok).toBe(true);
  expect(snapshot.lease.code).toBe("PROJECT_BUSY");
  expect(snapshot.lease.contentionError).toBe("NoModificationAllowedError");
  expect(snapshot.lease.reacquired).toBe(true);
  expect(snapshot.lease.stableIdentity).toBe(true);
  expect(snapshot.lease.leaseKey).toMatch(/^[0-9a-f]{64}$/);
  expect(snapshot.iteration).toEqual({
    ok: true,
    collected: expect.arrayContaining(["z", "ä", "a", "é", "😀"]),
    sorted: ["a", "z", "ä", "é", "😀"],
    ordering: "unsigned-utf8",
  });
  expect(snapshot.replacement.ok).toBe(true);
  expect(snapshot.replacement.phase).toBe(expectedPhase);
  expect(snapshot.replacement.faultPoints).toEqual(FAULT_POINTS);
  expect(snapshot.replacement.successfulClose).toBe("new");
}


test("audio mismatches use one latched unsupported-runtime path", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium");
  await page.goto("/probe.html");
  await expect(page.locator("#activate")).toBeEnabled({timeout: 60_000});

  const classifications = await page.evaluate(() => {
    const probe = window.lmdjToolchainProbe;
    const sampleRate = probe.classifyAudioRuntime({
      sampleRate: 44_100,
      observedFrames: 128,
      quantumMismatch: false,
    });
    probe.observeQuantumForTest(127);
    const firstMismatch = probe.snapshot().audio;
    probe.observeQuantumForTest(128);
    const afterMatchingQuantum = probe.snapshot().audio;
    return {sampleRate, firstMismatch, afterMatchingQuantum};
  });

  expect(classifications.sampleRate).toEqual({
    status: "unsupported",
    error: {
      code: "UNSUPPORTED_WEB_RUNTIME",
      expected_sample_rate: 48_000,
      observed_sample_rate: 44_100,
    },
  });
  expect(classifications.firstMismatch.quantumMismatch).toBe(true);
  expect(classifications.firstMismatch.observedFrames).toBe(127);
  expect(classifications.firstMismatch.runtime).toEqual({
    status: "unsupported",
    error: {
      code: "UNSUPPORTED_WEB_RUNTIME",
      expected_render_quantum_frames: 128,
      observed_render_quantum_frames: 127,
    },
  });
  expect(classifications.afterMatchingQuantum.quantumMismatch).toBe(true);
  expect(classifications.afterMatchingQuantum.observedFrames).toBe(127);
  expect(classifications.afterMatchingQuantum.runtime).toEqual(
    classifications.firstMismatch.runtime,
  );
});


test("exact shared-memory Web toolchain topology is conformant", async ({page}, testInfo) => {
  test.setTimeout(180_000);
  await page.goto("/preflight.html");
  const identity = await loadIdentity(page);
  assertIdentity(identity);

  const preflight = await inspectCapabilities(page);
  if (preflight.status === "unsupported") {
    expect(testInfo.project.name).toBe("webkit");
    expect(preflight.error.code).toBe("UNSUPPORTED_WEB_RUNTIME");
    expect(preflight.error.missing.length).toBeGreaterThan(0);
    expect(preflight.error.missing).toEqual(
      CAPABILITY_ORDER.filter((name) => preflight.capabilities[name] !== true),
    );
    testInfo.annotations.push({
      type: "platform-limitation",
      description: preflight.error.missing.join(","),
    });
    console.log(`WebKit capability limitation: ${JSON.stringify(preflight)}`);
    return;
  }
  expect(preflight).toEqual({
    status: "supported",
    missing: [],
    capabilities: Object.fromEntries(CAPABILITY_ORDER.map((name) => [name, true])),
  });
  console.log(`${testInfo.project.name} mandatory capabilities: PASS`);

  await page.goto("/probe.html");
  await expect(page.locator("#activate")).toBeEnabled({timeout: 60_000});
  await page.locator("#activate").click();
  const rendering = await waitForProbe(
    page,
    () => {
      const probe = window.lmdjToolchainProbe;
      if (!probe) return false;
      const state = probe.snapshot();
      return (
        state.audio.runtime.status !== "pending" &&
        state.replacement?.phase === "prepared"
      );
    },
  );
  expect(rendering.audio.runtime).toEqual({status: "supported"});
  const renderingTime = rendering.audio.contextTime;

  const first = await waitForProbe(
    page,
    () => {
      const probe = window.lmdjToolchainProbe;
      if (!probe) return false;
      const state = probe.snapshot();
      return state.control.done !== 0 && state.control.probes === 1000;
    },
  );
  expect(first.runtimeInitialized).toBe(true);
  expect(first.control.browserMainThread).toBe(0);
  expect(first.control.done).toBe(1);
  expect(first.control.probes).toBe(1000);
  expect(first.control.mainThreadProxyCount).toBe(1000);
  expect(first.audio.ready).toBe(1);
  expect(first.audio.state).toBe(1);
  expect(first.audio.observedFrames).toBe(128);
  expect(first.audio.configuredChannels).toBe(2);
  expect(first.audio.nodeChannels).toBe(2);
  expect(first.audio.numberOfOutputs).toBe(1);
  expect(first.audio.sharedMarker).toBe(1);
  expect(first.audio.quantumMismatch).toBe(false);
  expect(first.audio.runtime).toEqual({status: "supported"});
  expect(first.audio.outputPeak).toBeGreaterThan(0.99);
  expect(first.audio.contextTime).toBeGreaterThan(renderingTime + 0.05);
  assertDirectOpfs(first, "prepared");
  expect(first.lease.existingIdentity).toBe(false);
  const leaseKey = first.lease.leaseKey;

  await page.reload();
  await expect(page.locator("#activate")).toBeEnabled({timeout: 60_000});
  await page.locator("#activate").click();
  const recovered = await waitForProbe(
    page,
    () => {
      const probe = window.lmdjToolchainProbe;
      if (!probe) return false;
      const state = probe.snapshot();
      return (
        state.control.done !== 0 &&
        state.control.probes === 1000 &&
        state.replacement?.phase === "recovered"
      );
    },
  );
  expect(recovered.control.done).toBe(1);
  expect(recovered.control.mainThreadProxyCount).toBe(1000);
  expect(recovered.audio.observedFrames).toBe(128);
  expect(recovered.audio.configuredChannels).toBe(2);
  expect(recovered.audio.quantumMismatch).toBe(false);
  expect(recovered.audio.runtime).toEqual({status: "supported"});
  expect(recovered.audio.outputPeak).toBeGreaterThan(0.99);
  assertDirectOpfs(recovered, "recovered");
  expect(recovered.lease.existingIdentity).toBe(true);
  expect(recovered.lease.leaseKey).toBe(leaseKey);
  for (const point of FAULT_POINTS) {
    expect(["old", "new"]).toContain(recovered.replacement.recovered[point]);
    expect(recovered.replacement.recovered[point]).not.toBe("");
    expect(recovered.replacement.recovered[point]).not.toBe("n");
  }
  console.log(
    `${testInfo.project.name} restart recovery: ${JSON.stringify(recovered.replacement.recovered)}`,
  );
});
