import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";
import {SystemSurface, ProviderSettings} from "../src/components/system_surface";
import type {CreatorCandidateRuntimeSession} from "../src/runtime/runtime_types";

test("System focuses its heading and offers an explicit return without changing creative mode", async () => {
  const back = vi.fn();render(<SystemSurface onBack={back}><p>Settings</p></SystemSurface>);
  expect(document.activeElement).toBe(screen.getByRole("heading", {name:"System"}));
  await userEvent.click(screen.getByRole("button", {name:"Back to music"}));expect(back).toHaveBeenCalledOnce();
});
test("Provider permission revocation refreshes and preserves other grants", async () => {
  const configure = vi.fn(async permissions => ({granted_permissions:permissions}));
  const list = vi.fn().mockResolvedValueOnce({providers:[{id:"local",capabilities:[{capability_id:"slice"}]}],granted_permissions:["analysis"]})
    .mockResolvedValue({providers:[],granted_permissions:["analysis","other"]});
  render(<ProviderSettings session={{listProviders:list,configureProviderPermissions:configure} as unknown as CreatorCandidateRuntimeSession} />);
  await userEvent.click(await screen.findByRole("button", {name:"Revoke analysis"}));
  await waitFor(() => expect(configure).toHaveBeenCalledExactlyOnceWith(["other"]));
  expect(await screen.findByRole("button", {name:"Revoke other"})).toBeTruthy();
});
test("Provider refresh failure refuses permission mutation and stays local to System", async () => {
  const configure = vi.fn();const list = vi.fn().mockResolvedValueOnce({providers:[],granted_permissions:["analysis"]}).mockRejectedValue(new Error("offline"));
  render(<ProviderSettings session={{listProviders:list,configureProviderPermissions:configure} as unknown as CreatorCandidateRuntimeSession} />);
  await userEvent.click(await screen.findByRole("button", {name:"Revoke analysis"}));
  await screen.findByRole("alert");expect(configure).not.toHaveBeenCalled();
});
