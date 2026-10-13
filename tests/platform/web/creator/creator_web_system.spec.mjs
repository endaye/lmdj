import {expect, test} from "@playwright/test";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
async function projectTruth(page) {
  const result = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version: 1, request_id: crypto.randomUUID(), operation: "project.inspect", payload: {},
  }));
  expect(result.ok).toBe(true);
  return result.result;
}
async function transport(page) {
  const response = await page.evaluate(() => window.lmdjWebRuntimeHost.transport.send({
    protocol_version:1,request_id:crypto.randomUUID(),operation:"pattern.transport.inspect",
    payload:{session_id:window.__systemTransportSession},
  }));
  expect(response.ok).toBe(true);return response.result;
}
test("System restores creative focus while real Pattern playback continues", async ({page,browserName}) => {
  test.skip(browserName !== "chromium");test.setTimeout(180_000);
  expect(bundle).toBeTruthy();
  await page.addInitScript(() => {
    let exposed;
    Object.defineProperty(window,"lmdjWebRuntimeHost",{configurable:true,get:()=>exposed,set(host){
      const original=host.transport;
      host.transport=new Proxy({}, {get(_target,key){
        if(key!=="send") return Reflect.get(original,key);
        return (...args)=>{
          if(args[0]?.operation==="pattern.transport.request") window.__systemTransportSession=args[0].payload.session_id;
          return original.send(...args);
        };
      }});exposed=host;
    }});
  });
  await page.goto("/index.html");await openProjectPageAfterBoot(page);
  const chooser = page.waitForEvent("filechooser");await page.getByRole("button", {name:"Import .lmdj"}).click();
  await (await chooser).setFiles(bundle);await expect(page.getByRole("heading", {name:"Project 00000000"})).toBeVisible({timeout:120_000});
  await wakeAudioWithPad(page);await page.getByRole("button", {name:"Sequence",exact:true}).click();
  await page.getByTestId("physical-controls").getByRole("button", {name:/^Play\/Stop/}).click();
  await expect.poll(() => page.evaluate(() => window.__systemTransportSession)).toMatch(/^[0-9a-f-]{36}$/);
  await expect.poll(async () => (await transport(page)).playing).toBe(true);
  const before = await transport(page);expect(before.transport_epoch).toBeGreaterThan(0);const entry = page.getByRole("button", {name:"System",exact:true});
  await expect(page.getByRole("button", {name:"Enable MIDI"})).toHaveCount(0);
  await entry.click();await expect(page.getByRole("heading", {name:"System",exact:true})).toBeFocused();
  await expect(page.getByRole("button", {name:"Enable MIDI"})).toBeVisible();
  await expect(page.getByRole("region", {name:"Sequence editor"})).toHaveCount(0);
  expect(await transport(page)).toMatchObject({engaged:true,playing:true,transport_epoch:before.transport_epoch});
  await expect(page.getByTestId("physical-controls").getByRole("button", {name:"Sequence",exact:true})).toHaveAttribute("aria-current","page");
  await page.getByRole("button", {name:"Back to music",exact:true}).click();await expect(entry).toBeFocused();
  await expect(page.getByRole("region", {name:"Sequence editor"})).toBeVisible();
  expect(await transport(page)).toMatchObject({engaged:true,playing:true,transport_epoch:before.transport_epoch});
  await page.getByRole("button", {name:"SETUP",exact:true}).click();
  const refresh = page.getByRole("button", {name:"Refresh playback",exact:true});
  await expect(refresh).toHaveCount(0);
  await page.getByText("Playback details", {exact:true}).click();
  await expect(refresh).toBeVisible();
  await refresh.click();
  expect(await transport(page)).toMatchObject({engaged:true,playing:true,transport_epoch:before.transport_epoch});
});

for (const viewport of [{width: 1440, height: 900}, {width: 1024, height: 768}, {width: 768, height: 1024}]) {
  test(`System source and disclosures remain reachable at ${viewport.width}×${viewport.height}`, async ({page, browserName}, testInfo) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(180_000);
    expect(bundle).toBeTruthy();
    await page.setViewportSize(viewport);
    await page.goto("/index.html");
    await openProjectPageAfterBoot(page);
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", {name: "Import .lmdj", exact: true}).click();
    await (await chooser).setFiles(bundle);
    await expect(page.getByRole("heading", {name: "Project 00000000"})).toBeVisible({timeout: 120_000});
    const before = await projectTruth(page);
    const entry = page.getByRole("button", {name: "System", exact: true});
    await entry.click();
    const system = page.getByRole("region", {name: "System", exact: true});
    await expect(system.getByRole("heading", {name: "System", exact: true})).toBeFocused();
    await expect(system.getByLabel("System audio status")).toHaveText(/inactive|running|suspended/);
    const source = system.getByRole("group", {name: "Pad recording source"});
    await source.getByRole("button", {name: "Internal playback", exact: true}).click();
    await expect(source.getByRole("button", {name: "Internal playback", exact: true})).toHaveAttribute("aria-pressed", "true");
    await expect(source.getByRole("button", {name: "Microphone", exact: true})).toHaveAttribute("aria-pressed", "false");
    expect(await page.evaluate(() => localStorage.getItem("lmdj.creator.pad-capture-source.v1"))).toBe("master");
    expect(await projectTruth(page)).toEqual(before);
    const details = system.locator(".creator-details");
    await details.locator("summary").click();
    await expect(details).toHaveAttribute("open", "");
    await expect(details.getByTestId("midi-state")).toBeVisible();
    await details.locator("summary").click();
    await system.getByRole("button", {name: "Export report", exact: true}).scrollIntoViewIfNeeded();
    await expect(system.getByRole("button", {name: "Export report", exact: true})).toBeEnabled();
    await system.locator(".system-providers > summary").click();
    await expect(system.getByRole("region", {name: "Provider management"})).toBeVisible();
    await system.locator(".system-providers > summary").click();
    await system.locator(".diagnostics-log > summary").click();
    await expect(system.getByRole("region", {name: "Developer diagnostics"})).toBeVisible();
    await system.locator(".diagnostics-log > summary").click();
    expect(await system.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    await details.locator("summary").click();
    await system.getByRole("button", {name: "Back to music", exact: true}).click();
    await expect(entry).toBeFocused();
    await expect(system).toBeHidden();
    await entry.click();
    await expect(details).toHaveAttribute("open", "");
    await details.locator("summary").click();
    await system.getByRole("heading", {name: "System", exact: true}).scrollIntoViewIfNeeded();
    await page.screenshot({path: testInfo.outputPath("system.png")});
    expect(await projectTruth(page)).toEqual(before);
    await page.reload();
    await waitForProjectReopen(page, "00000000");
    await entry.click();
    await expect(source.getByRole("button", {name: "Internal playback", exact: true})).toHaveAttribute("aria-pressed", "true");
    expect(await projectTruth(page)).toEqual(before);
  });
}
