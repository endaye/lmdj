import {webcrypto} from "node:crypto";
import {expect, test, vi} from "vitest";
import {registerOfflineShell} from "../src/runtime/offline_shell";

const crypto = webcrypto as unknown as Crypto;
async function fixture() {
  const hash = "a".repeat(64);
  const bytes = new TextEncoder().encode(JSON.stringify({host_id: "creator-web",
    assets: [{role: "offline_worker", path: `assets/offline-worker.${hash}.js`, sha256: hash}]}));
  const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map(value => value.toString(16).padStart(2, "0")).join("");
  const document = {baseURI: "https://creator.test/index.html",
    querySelector: () => ({getAttribute: () => digest})} as unknown as Document;
  const registration = {active: {scriptURL: `https://creator.test/assets/offline-worker.${hash}.js`},
    installing: null, waiting: null, addEventListener: vi.fn()};
  const register = vi.fn(async () => registration);
  const navigator = {serviceWorker: {register, ready: Promise.resolve(registration)}} as unknown as Navigator;
  return {document, navigator, register, bytes, registration};
}

test("registers only the manifest-bound same-origin worker without taking over active clients", async () => {
  const value = await fixture();
  const phases: string[] = [];
  const fetch = vi.fn(async (url: RequestInfo | URL) => String(url).endsWith("host-manifest.json")
    ? new Response(value.bytes) : new Response("unavailable", {status: 503}));
  await registerOfflineShell(value.document, value.navigator, crypto, fetch, phase => phases.push(phase));
  expect(value.register).toHaveBeenCalledExactlyOnceWith(value.registration.active.scriptURL,
    {scope: "https://creator.test/", type: "module", updateViaCache: "none"});
  expect(phases).toContain("ready");
  expect(phases).not.toContain("unavailable");
});

test("a changed manifest is refused before worker registration", async () => {
  const value = await fixture();
  const phases: string[] = [];
  await registerOfflineShell(value.document, value.navigator, crypto,
    async () => new Response("{}"), phase => phases.push(phase));
  expect(value.register).not.toHaveBeenCalled();
  expect(phases).toEqual(["preparing", "unavailable"]);
});

test("a failed network update probe retains the ready offline build", async () => {
  const value = await fixture();
  const phases: string[] = [];
  let calls = 0;
  await registerOfflineShell(value.document, value.navigator, crypto, async () => {
    if (calls++ === 0) return new Response(value.bytes);
    throw new TypeError("offline");
  }, phase => phases.push(phase));
  expect(value.register).toHaveBeenCalledTimes(1);
  expect(phases.at(-1)).toBe("ready");
});


test("a network replacement observes its own registration and reports waiting", async () => {
  const value=await fixture();const hash="b".repeat(64);
  const bytes=new TextEncoder().encode(JSON.stringify({host_id:"creator-web",assets:[{role:"offline_worker",path:`assets/offline-worker.${hash}.js`,sha256:hash}]}));
  const identity=[...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))].map(v=>v.toString(16).padStart(2,"0")).join("");
  const replacement={active:value.registration.active,waiting:{scriptURL:`https://creator.test/assets/offline-worker.${hash}.js`},installing:null,addEventListener:vi.fn()};
  value.register.mockResolvedValueOnce(value.registration).mockResolvedValueOnce(replacement as unknown as typeof value.registration);
  const phases:string[]=[];let manifests=0;
  await registerOfflineShell(value.document,value.navigator,crypto,async url=>String(url).endsWith("index.html")
    ?new Response(`<meta name="lmdj-host-manifest-sha256" content="${identity}">`)
    :new Response(manifests++===0?value.bytes:bytes),phase=>phases.push(phase));
  expect(value.register).toHaveBeenCalledTimes(2);
  expect(replacement.addEventListener).toHaveBeenCalledWith("updatefound",expect.any(Function));
  expect(phases.at(-1)).toBe("waiting");
});
