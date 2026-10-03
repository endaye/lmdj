import {expect, test} from "@playwright/test";
import {openProjectPageAfterBoot} from "./fixtures/creator_boot.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
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
});
