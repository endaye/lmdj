import type {CandidateProviderList, CreatorCandidateRuntimeSession} from "../runtime/runtime_types";

type Listener = (listing: CandidateProviderList) => void;
const sessions = new WeakMap<CreatorCandidateRuntimeSession, {
  tail: Promise<void>;
  listeners: Set<Listener>;
}>();

function settings(session: CreatorCandidateRuntimeSession) {
  let state = sessions.get(session);
  if (!state) {
    state = {tail: Promise.resolve(), listeners: new Set()};
    sessions.set(session, state);
  }
  return state;
}

export function subscribeProviderPermissions(session: CreatorCandidateRuntimeSession, listener: Listener) {
  const state = settings(session);
  state.listeners.add(listener);
  return () => {state.listeners.delete(listener);};
}

export function changeProviderPermission(session: CreatorCandidateRuntimeSession, permission: string, grant: boolean) {
  const state = settings(session);
  // Both Creator settings gestures share the complete read/change/write.
  // The Runtime configure command deliberately replaces its entire grant set.
  const pending = state.tail.then(async () => {
    const current = await session.listProviders();
    if (!Array.isArray(current.granted_permissions)) {
      throw new Error("Current permissions are unavailable; no permissions were changed.");
    }
    const permissions = grant
      ? [...new Set([...current.granted_permissions, permission])]
      : current.granted_permissions.filter(value => value !== permission);
    const result = await session.configureProviderPermissions(permissions);
    const listing = {...current, granted_permissions: result.granted_permissions};
    for (const listener of state.listeners) listener(listing);
    return listing;
  });
  // A refused action releases the Host queue without inventing a success.
  state.tail = pending.then(() => undefined, () => undefined);
  return pending;
}
