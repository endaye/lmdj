import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";
import {SystemSurface, ProviderSettings} from "../src/components/system_surface";
import {CandidateSurface} from "../src/components/candidate_surface";
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
  expect(screen.queryByText("local · slice")).toBeNull();
});
test("Provider refresh failure refuses permission mutation and stays local to System", async () => {
  const configure = vi.fn();const list = vi.fn().mockResolvedValueOnce({providers:[],granted_permissions:["analysis"]}).mockRejectedValue(new Error("offline"));
  render(<ProviderSettings session={{listProviders:list,configureProviderPermissions:configure} as unknown as CreatorCandidateRuntimeSession} />);
  await userEvent.click(await screen.findByRole("button", {name:"Revoke analysis"}));
  await screen.findByRole("alert");expect(configure).not.toHaveBeenCalled();
});

function retainedPermissionSurfaces(initial: string[], delayFirstWrite = false, delayInspection = false) {
  const projectId = "11111111-1111-4111-8111-111111111111";
  let grants = [...initial];
  let release!: () => void;
  const firstWrite = new Promise<void>(resolve => {release = resolve;});
  let releaseInspection!: () => void;
  const inspection = new Promise<void>(resolve => {releaseInspection = resolve;});
  let tail = Promise.resolve();
  let writes = 0;
  const configure = vi.fn((permissions: readonly string[]) => {
    const first = ++writes === 1;
    // The real Host processes control requests in order. Hold the first
    // response so a second settings gesture can read before that write.
    const pending = tail.then(async () => {
      if (first && delayFirstWrite) await firstWrite;
      grants = [...permissions];
      return {granted_permissions: [...grants]};
    });
    tail = pending.then(() => undefined, () => undefined);
    return pending;
  });
  const session = {
    inspectProject: async () => {
      if (delayInspection) await inspection;
      return {project_revision: 3, project: {
        project_id: projectId, revision: 3, assets: {}, patterns: {}, banks: [],
      }};
    },
    listProviders: async () => ({providers: [], granted_permissions: [...grants]}),
    configureProviderPermissions: configure,
  } as unknown as CreatorCandidateRuntimeSession;
  render(<>
    <CandidateSurface session={session} projectId={projectId} projectRevision={3}
      onRefreshProject={async () => {}} />
    <ProviderSettings session={session} />
  </>);
  return {configure, release, releaseInspection, permissions: () => [...grants]};
}

test("a System revoke preserves the Slice grant whose Host write is still in flight", async () => {
  const state = retainedPermissionSurfaces(["other.permission"], true);
  const grant = await screen.findByRole("button", {name: "Grant analysis permission"});
  await waitFor(() => expect(grant.hasAttribute("disabled")).toBe(false));
  fireEvent.click(grant);
  await waitFor(() => expect(state.configure).toHaveBeenCalledTimes(1));
  fireEvent.click(await screen.findByRole("button", {name: "Revoke other.permission"}));
  await act(async () => {await Promise.resolve(); await Promise.resolve();});
  await act(async () => {state.release();});
  await waitFor(() => expect(state.permissions()).toEqual(["sample.slice.execute"]));
});

test("System revoke updates the retained Slice so the same permission can be granted again", async () => {
  const state = retainedPermissionSurfaces(["sample.slice.execute"]);
  await screen.findByRole("button", {name: "Analysis permission granted"});
  fireEvent.click(await screen.findByRole("button", {name: "Revoke sample.slice.execute"}));
  await waitFor(() => expect(state.permissions()).toEqual([]));
  const grant = await screen.findByRole("button", {name: "Grant analysis permission"});
  expect(grant.hasAttribute("disabled")).toBe(false);
  fireEvent.click(grant);
  await waitFor(() => expect(state.permissions()).toEqual(["sample.slice.execute"]));
});

test("late Slice initialization cannot overwrite the completed System permission update", async () => {
  const state = retainedPermissionSurfaces(["sample.slice.execute"], false, true);
  fireEvent.click(await screen.findByRole("button", {name: "Revoke sample.slice.execute"}));
  await waitFor(() => expect(state.permissions()).toEqual([]));
  await act(async () => {state.releaseInspection();});
  expect(screen.getByRole("button", {name: "Grant analysis permission"}).hasAttribute("disabled")).toBe(false);
});

test("a refused permission read releases the session queue for the next explicit revoke", async () => {
  const listing = {providers: [], granted_permissions: ["analysis"]};
  const list = vi.fn().mockResolvedValueOnce(listing).mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(listing);
  const configure = vi.fn(async (permissions: readonly string[]) => ({granted_permissions: permissions}));
  render(<ProviderSettings session={{listProviders: list, configureProviderPermissions: configure} as unknown as CreatorCandidateRuntimeSession} />);
  fireEvent.click(await screen.findByRole("button", {name: "Revoke analysis"}));
  await screen.findByRole("alert");
  expect(configure).not.toHaveBeenCalled();
  const revoke = screen.getByRole("button", {name: "Revoke analysis"});
  await waitFor(() => expect(revoke.hasAttribute("disabled")).toBe(false));
  fireEvent.click(revoke);
  await waitFor(() => expect(configure).toHaveBeenCalledExactlyOnceWith([]));
  await waitFor(() => expect(screen.queryByRole("button", {name: "Revoke analysis"})).toBeNull());
});
