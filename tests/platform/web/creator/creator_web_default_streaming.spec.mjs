import {readFile, writeFile} from "node:fs/promises";
import {createServer} from "node:http";
import {resolve} from "node:path";
import {expect, test} from "@playwright/test";
import worker from "../../../../tools/asset-server/worker.mjs";
import {waitForBootProject} from "./fixtures/creator_boot.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
const root = resolve(import.meta.dirname, "../../../../products/lmdj/assets/default-kit");
const upstreamFile = process.env.LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE;

async function projectIdentity(page) {
  const response = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version: 1, request_id: crypto.randomUUID(), operation: "project.inspect", payload: {},
  }));
  expect(response, JSON.stringify(response)).toHaveProperty("ok", true);
  expect(response.result.project.project_id).toMatch(/^[0-9a-f]{8}-[0-9a-f-]{27}$/);
  return response.result.project.project_id;
}

test("default Bank A plays a verified first slot while the next object waits, and never seeds manual Projects", async ({page, browserName}) => {
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
    await page.addInitScript(() => {
      window.__seedResponses = [];
      let exposed;
      Object.defineProperty(window, "lmdjWebRuntimeHost", {configurable:true,
        get: () => exposed, set(host) {
          const transport = host.transport;
          host.transport = new Proxy({}, {get(_target,key) {
            if (key !== "send") return Reflect.get(transport,key);
            return async (...args) => {
              const result = await transport.send(...args);
              if (args[0]?.operation.startsWith("soundset.")) window.__seedResponses.push({operation:args[0].operation,result});
              return result;
            };
          }});exposed=host;
        },
      });
    });
    await page.goto("/index.html");
    await waitForBootProject(page);
    try {await expect(page.getByRole("button", {name:/^Pad A1 — assigned/})).toBeEnabled({timeout:60_000});}
    catch (error) {throw new Error(`${error.message}\nFacade responses: ${JSON.stringify(await page.evaluate(() => window.__seedResponses))}`);}
    await expect.poll(() => blocked).toBe(true);
    await expect(page.getByRole("button", {name:/^Pad A2 — loading/})).toBeDisabled();
    await wakeAudioWithPad(page, {padAddress:"A1"});
    expect(blocked).toBe(true);
    expect(blobs).toHaveLength(2);
    release();
    await expect(page.getByRole("button", {name:/^Pad A16 — assigned/})).toBeEnabled({timeout:120_000});
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
    await expect(page.getByRole("button", {name:/^Pad A1 — empty/})).toBeVisible();
    const manualId = await projectIdentity(page);
    expect(manualId).not.toBe(ownedId);
    expect(JSON.parse(await page.evaluate(() => localStorage.getItem("lmdj.creator.default-seed.v1"))).projectId).toBe(ownedId);
    expect(blobs).toHaveLength(16);
    // The native identity, rather than a volatile legacy cache, owns the
    // remembered Project. Reload the manual Project and assert its far side.
    await page.reload();
    await waitForBootProject(page);
    expect(await projectIdentity(page)).toBe(manualId);
    await expect(page.getByRole("button", {name:/^Pad A1 — empty/})).toBeVisible();
    expect(blobs).toHaveLength(16);
  } finally {
    release(); await writeFile(upstreamFile, "");
    await new Promise(yes => {server.close(yes);server.closeAllConnections();});
  }
});
