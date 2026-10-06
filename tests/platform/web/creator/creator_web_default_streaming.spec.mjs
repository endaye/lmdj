import {readFile, writeFile} from "node:fs/promises";
import {createServer} from "node:http";
import {resolve} from "node:path";
import {expect, test} from "@playwright/test";
import worker from "../../../../tools/asset-server/worker.mjs";
import {waitForBootProject} from "./fixtures/creator_boot.mjs";
const root = resolve(import.meta.dirname, "../../../../products/lmdj/assets/default-kit");
const upstreamFile = process.env.LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE;
// DOM trace snapshots also evaluate scripts. Preserve the cold document for
// this activation journey; retain action/network/source traces on failure.
test.use({hasTouch: true, trace: {mode: "retain-on-failure", snapshots: false}});

async function projectIdentity(page) {
  const response = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version: 1, request_id: crypto.randomUUID(), operation: "project.inspect", payload: {},
  }));
  expect(response, JSON.stringify(response)).toHaveProperty("ok", true);
  expect(response.result.project.project_id).toMatch(/^[0-9a-f]{8}-[0-9a-f-]{27}$/);
  return response.result.project.project_id;
}

test("default Bank A plays on the first native touch while the next object waits, and never seeds manual Projects", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  expect(upstreamFile).toBeTruthy();
  let release;
  const gate = new Promise(resolve => {release = resolve;});
  let blocked = false;
  const blobs = [];
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://kit.test");
      if (url.pathname.startsWith("/object/blob/")) {
        blobs.push(url.pathname);
        if (blobs.length === 2) {blocked = true; await gate;}
      }
      const result = await worker.fetch(new Request(url, {method: request.method}), {
        ASSETS: {fetch: async request => {
          try {return new Response(await readFile(resolve(root, "." + new URL(request.url).pathname)));}
          catch {return new Response("missing", {status:404});}
        }},
      });
      response.writeHead(result.status, Object.fromEntries(result.headers));
      response.end(Buffer.from(await result.arrayBuffer()));
    } catch {response.writeHead(502);response.end();}
  });
  await new Promise(yes => server.listen(0,"127.0.0.1",yes));
  try {
    await writeFile(upstreamFile, `http://127.0.0.1:${server.address().port}/`);
    const client = await page.context().newCDPSession(page);
    // Playwright's ordinary evaluate uses userGesture:true. Read this first
    // leg through CDP without granting the activation the test is proving.
    const read = async expression => {
      const result = await client.send("Runtime.evaluate", {expression, returnByValue: true, userGesture: false});
      expect(result.exceptionDetails).toBeUndefined();
      return result.result.value;
    };
    await page.addInitScript(() => {
      window.__seedResponses = [];
      window.__firstTouchProof = {pointers: [], contexts: [], resumes: [], responses: [], voices: []};
      for (const type of ["pointerdown", "pointerup"]) document.addEventListener(type, event => {
        window.__firstTouchProof.pointers.push({type, pointerType: event.pointerType,
          isPrimary: event.isPrimary, isTrusted: event.isTrusted});
      }, {capture: true});
      const resume = AudioContext.prototype.resume;
      AudioContext.prototype.resume = function (...args) {
        window.__firstTouchProof.resumes.push({...window.__firstTouchProof.pointers.at(-1),
          hasBeenActive: navigator.userActivation.hasBeenActive});
        return Reflect.apply(resume, this, args);
      };
      window.AudioContext = new Proxy(AudioContext, {construct(target, args, newTarget) {
        window.__firstTouchProof.contexts.push({...window.__firstTouchProof.pointers.at(-1),
          hasBeenActive: navigator.userActivation.hasBeenActive});
        return Reflect.construct(target, args, newTarget);
      }});
      let exposed;
      Object.defineProperty(window, "lmdjWebRuntimeHost", {configurable:true,
        get: () => exposed, set(host) {
          const transport = host.transport;
          transport.subscribe(message => {
            if (message.event === "runtime.voice_state") window.__firstTouchProof.voices.push(...message.payload.events);
          });
          host.transport = new Proxy({}, {get(_target,key) {
            if (key !== "send") return Reflect.get(transport,key);
            return async (...args) => {
              const result = await transport.send(...args);
              if (args[0]?.operation.startsWith("soundset.")) window.__seedResponses.push({operation:args[0].operation,result});
              if (args[0]?.operation === "trigger" && args[0]?.payload?.velocity > 0) window.__firstTouchProof.responses.push(result);
              return result;
            };
          }});exposed=host;
        },
      });
    });
    await page.goto("/index.html");
    await expect.poll(() => read(`document.querySelector('[data-testid="creator-phase"]')?.textContent`), {timeout: 60_000}).toBe("ready");
    const firstPadExpression = `[...document.querySelectorAll('.pad-grid button')].find(button => /^Pad A01 — assigned/.test(button.getAttribute('aria-label')))`;
    try {await expect.poll(() => read(`(${firstPadExpression})?.disabled`), {timeout:60_000}).toBe(false);}
    catch (error) {throw new Error(`${error.message}\nFacade responses: ${JSON.stringify(await read("window.__seedResponses"))}`);}
    await expect.poll(() => blocked).toBe(true);
    expect(await read(`[...document.querySelectorAll('.pad-grid button')].find(button => /^Pad A02 — loading/.test(button.getAttribute('aria-label')))?.disabled`)).toBe(true);
    expect(await read("navigator.userActivation.hasBeenActive")).toBe(false);
    expect(await read(`document.querySelector('[data-testid="audio-state"]')?.textContent`)).toBe("Audio inactive");
    const box = await read(`(() => {const button = ${firstPadExpression}; button.scrollIntoView(); return button.getBoundingClientRect().toJSON();})()`);
    expect(box).not.toBeNull();
    await client.send("Input.dispatchTouchEvent", {type: "touchStart",
      touchPoints: [{x: box.x + box.width / 2, y: box.y + box.height / 2, id: 1}]});
    const pressed = await read("window.__firstTouchProof");
    expect(pressed.pointers).toEqual([{type: "pointerdown", pointerType: "touch", isPrimary: true, isTrusted: true}]);
    expect(pressed.contexts).toEqual([]);
    expect(pressed.resumes).toEqual([]);
    expect(pressed.responses).toEqual([]);
    await client.send("Input.dispatchTouchEvent", {type: "touchEnd", touchPoints: []});
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {timeout: 30_000});
    await expect.poll(() => page.evaluate(() => window.__firstTouchProof.responses.length), {timeout: 30_000}).toBe(1);
    const played = await page.evaluate(() => window.__firstTouchProof.responses[0]);
    expect(played, JSON.stringify(played)).toHaveProperty("ok", true);
    expect(played.result.sequence).toBeGreaterThan(0);
    await expect.poll(() => page.evaluate(sequence => window.__firstTouchProof.voices
      .some(event => event.sequence === sequence && event.state === "started"), played.result.sequence), {timeout: 30_000}).toBe(true);
    const resumed = await page.evaluate(() => window.__firstTouchProof.resumes);
    expect(await page.evaluate(() => window.__firstTouchProof.contexts)).toEqual([
      {type: "pointerup", pointerType: "touch", isPrimary: true, isTrusted: true, hasBeenActive: true},
    ]);
    expect(resumed.length).toBeGreaterThan(0);
    for (const call of resumed) expect(call).toMatchObject({type: "pointerup", pointerType: "touch", isTrusted: true, hasBeenActive: true});
    const stopped = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
      protocol_version: 1, request_id: crypto.randomUUID(), operation: "sample.stop", payload: {},
    }));
    expect(stopped, JSON.stringify(stopped)).toHaveProperty("ok", true);
    await client.detach();
    expect(blocked).toBe(true);
    expect(blobs).toHaveLength(2);
    release();
    try {
      await expect(page.getByRole("button", {name:/^Pad A16 — assigned/})).toBeEnabled({timeout:120_000});
    } catch (error) {
      const observed = await page.evaluate(() => ({
        phase: document.querySelector('[data-testid="creator-phase"]')?.textContent,
        audio: document.querySelector('[data-testid="audio-state"]')?.textContent,
        pads: [...document.querySelectorAll('.pad-grid button')].map(button => ({
          label: button.getAttribute("aria-label"), disabled: button.disabled,
        })),
        responses: window.__seedResponses,
      }));
      throw new Error(`${error.message}\nProgressive completion evidence: ${JSON.stringify(observed)}`);
    }
    expect(new Set(blobs).size).toBe(16);
    const ownedId = await projectIdentity(page);
    await page.reload();
    await waitForBootProject(page);
    await expect(page.getByRole("button", {name:/^Pad A16 — assigned/})).toBeEnabled({timeout:60_000});
    expect(await projectIdentity(page)).toBe(ownedId);
    expect(blobs).toHaveLength(16);
    await page.getByRole("button", {name:"Project",exact:true}).click();
    await page.getByRole("button", {name:"New Project",exact:true}).click();
    await waitForBootProject(page);
    await expect(page.getByRole("button", {name:/^Pad A01 — empty/})).toBeVisible();
    const manualId = await projectIdentity(page);
    expect(manualId).not.toBe(ownedId);
    expect(JSON.parse(await page.evaluate(() => localStorage.getItem("lmdj.creator.default-seed.v1"))).projectId).toBe(ownedId);
    expect(blobs).toHaveLength(16);
    // The native identity, rather than a volatile legacy cache, owns the
    // remembered Project. Reload the manual Project and assert its far side.
    await page.reload();
    await waitForBootProject(page);
    expect(await projectIdentity(page)).toBe(manualId);
    await expect(page.getByRole("button", {name:/^Pad A01 — empty/})).toBeVisible();
    expect(blobs).toHaveLength(16);
  } finally {
    release(); await writeFile(upstreamFile, "");
    await new Promise(yes => {server.close(yes);server.closeAllConnections();});
  }
});
